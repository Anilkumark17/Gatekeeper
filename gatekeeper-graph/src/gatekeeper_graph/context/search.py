"""BM25 search over symbol nodes. Missing summaries or literals only lower the score."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from gatekeeper_graph.models import Graph, NodeKind, parse_node_id

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "to",
        "and",
        "or",
        "for",
        "in",
        "on",
        "is",
        "it",
        "at",
        "by",
        "with",
        "from",
        "as",
        "this",
        "that",
        "be",
        "are",
        "was",
        "were",
    }
)
_PART = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
_FIELDS = ("name", "literal", "summary", "path")
_WEIGHTS = {"name": 3.0, "literal": 2.0, "summary": 1.0, "path": 0.5}
_K1 = 1.2
_B = 0.75
_SYMBOL_KINDS = frozenset(NodeKind) - {NodeKind.FILE, NodeKind.EXTERNAL, NodeKind.MODULE}


class Hit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    score: float
    matched: dict[str, list[str]]


class SearchIndex:
    def __init__(
        self,
        documents: list[dict[str, object]],
        *,
        summaries: bool,
        literals: bool,
    ) -> None:
        self.summaries = summaries
        self.literals = literals
        self._docs: list[tuple[str, dict[str, list[str]]]] = []
        for item in documents:
            node_id = item.get("id")
            if not isinstance(node_id, str):
                continue
            fields = {name: _strings(item.get(name, [])) for name in _FIELDS}
            self._docs.append((node_id, fields))
        self._docs.sort(key=lambda item: item[0])
        self._avg = self._average_lengths()
        self._df = self._document_frequencies()

    @classmethod
    def build(cls, graph: Graph) -> SearchIndex:
        documents: list[dict[str, object]] = []
        summaries = False
        literals = False
        for node in graph.nodes.values():
            if node.kind not in _SYMBOL_KINDS:
                continue
            name = parse_node_id(node.id)[2] or ""
            literal_tokens: list[str] = []
            for literal in node.literals:
                literal_tokens.extend(tokenize(literal))
            summary_tokens = tokenize(node.summary or "")
            if node.summary:
                summaries = True
            if node.literals:
                literals = True
            documents.append(
                {
                    "id": node.id,
                    "name": tokenize(name),
                    "literal": literal_tokens,
                    "summary": summary_tokens,
                    "path": tokenize(node.file or ""),
                }
            )
        logger.info(
            "search fields summaries=%s literals=%s documents=%s",
            summaries,
            literals,
            len(documents),
        )
        return cls(documents, summaries=summaries, literals=literals)

    def search(self, query_terms: str, k: int = 25) -> list[Hit]:
        terms = tokenize(query_terms)
        if not terms or not self._docs:
            return []
        hits: list[Hit] = []
        total = len(self._docs)
        for node_id, fields in self._docs:
            score = 0.0
            matched: dict[str, list[str]] = {}
            for field in _FIELDS:
                tokens = fields[field]
                if not tokens:
                    continue
                counts = Counter(tokens)
                length = len(tokens)
                average = self._avg[field] or 1.0
                field_hits: list[str] = []
                for term in terms:
                    tf = counts.get(term, 0)
                    if tf == 0:
                        continue
                    df = self._df[field].get(term, 0)
                    idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
                    denom = tf + _K1 * (1 - _B + _B * length / average)
                    score += _WEIGHTS[field] * idf * (tf * (_K1 + 1)) / denom
                    field_hits.append(term)
                if field_hits:
                    matched[field] = field_hits
            if score > 0:
                hits.append(Hit(node_id=node_id, score=score, matched=matched))
        hits.sort(key=lambda hit: (-hit.score, hit.node_id))
        return hits[:k]

    def _average_lengths(self) -> dict[str, float]:
        averages: dict[str, float] = {}
        count = len(self._docs) or 1
        for field in _FIELDS:
            averages[field] = sum(len(fields[field]) for _node, fields in self._docs) / count
        return averages

    def _document_frequencies(self) -> dict[str, Counter[str]]:
        frequencies: dict[str, Counter[str]] = {field: Counter() for field in _FIELDS}
        for _node, fields in self._docs:
            for field in _FIELDS:
                for term in set(fields[field]):
                    frequencies[field][term] += 1
        return frequencies


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def tokenize(text: str) -> list[str]:
    """Lowercase, split camel and snake boundaries, drop stopwords, light stem."""
    tokens: list[str] = []
    for part in _PART.findall(text):
        token = _stem(part.lower())
        if len(token) >= 2 and token not in _STOPWORDS:
            tokens.append(token)
    return tokens


def load_or_build(graph: Graph, graph_path: Path, *, write: bool) -> SearchIndex:
    """Load search_index.json when its fingerprint matches. Otherwise build in memory."""
    fingerprint = _fingerprint(graph)
    path = graph_path.with_name("search_index.json")
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            logger.info("search index rebuild reason=%s path=%s", exc, path)
        else:
            if isinstance(payload, dict) and payload.get("fingerprint") == fingerprint:
                documents = payload.get("documents", [])
                if isinstance(documents, list):
                    logger.info(
                        "search index loaded path=%s summaries=%s literals=%s",
                        path,
                        payload.get("summaries"),
                        payload.get("literals"),
                    )
                    return SearchIndex(
                        documents,
                        summaries=bool(payload.get("summaries")),
                        literals=bool(payload.get("literals")),
                    )
            logger.info("search index rebuild reason=fingerprint path=%s", path)
    index = SearchIndex.build(graph)
    if write:
        _write(path, fingerprint, index)
    return index


def _stem(token: str) -> str:
    for suffix in ("ing", "ed"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    if token.endswith(("ches", "shes", "ses", "xes", "zes")) and len(token) - 2 >= 3:
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) - 1 >= 3:
        return token[:-1]
    return token


def _fingerprint(graph: Graph) -> str:
    lines = [
        f"{node.id}\t{node.hash or ''}\t{node.summary_hash or ''}"
        for node in graph.nodes.values()
        if node.kind in _SYMBOL_KINDS
    ]
    digest = hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()
    return digest


def _write(path: Path, fingerprint: str, index: SearchIndex) -> None:
    documents = []
    for node_id, fields in index._docs:
        documents.append({"id": node_id, **fields})
    payload = {
        "fingerprint": fingerprint,
        "summaries": index.summaries,
        "literals": index.literals,
        "documents": documents,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info("search index wrote path=%s documents=%s", path, len(documents))

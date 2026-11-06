"""Fill symbol summaries through the shared LLM client."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gatekeeper_graph.llm import LLMClient, make_client
from gatekeeper_graph.llm.errors import LLMOutputInvalid, LLMUnavailable
from gatekeeper_graph.models import Graph, Node, NodeKind
from gatekeeper_graph.search import build_search_index

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Summarize the source in one or two sentences. "
    "The id is the correct graph key. Do not question the id or the filename. "
    "Do not invent behavior that is not in the source."
)


class NodeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)


@dataclass(frozen=True)
class SummaryStats:
    reused: int
    written: int
    skipped: int


def make_summarizer_client() -> LLMClient:
    """Return the configured client for summary text."""
    return make_client()


def apply_summaries(
    graph: Graph,
    root: Path,
    client: LLMClient | None,
    previous: Graph | None,
) -> SummaryStats:
    """Copy unchanged summaries and ask the client for the rest."""
    prior_nodes = previous.nodes if previous is not None else {}
    reused = 0
    written = 0
    skipped = 0
    ordered = [
        *[node for node in graph.nodes.values() if _is_symbol(node)],
        *[node for node in graph.nodes.values() if node.kind is NodeKind.FILE and node.hash],
        *[node for node in graph.nodes.values() if node.kind is NodeKind.MODULE and node.hash],
    ]
    for node in ordered:
        prior = prior_nodes.get(node.id)
        if prior is not None and prior.hash == node.hash and prior.summary:
            node.summary = prior.summary
            node.summary_hash = prior.summary_hash or _summary_hash(prior.summary)
            node.stale = False
            reused += 1
            continue
        try:
            text = _request_summary(client, node, root, graph)
        except (LLMUnavailable, LLMOutputInvalid):
            logger.info("summary skipped node=%s", node.id)
            if prior is not None and prior.summary:
                node.summary = prior.summary
                node.summary_hash = prior.summary_hash or _summary_hash(prior.summary)
            node.stale = True
            skipped += 1
            continue
        node.summary = text
        node.summary_hash = _summary_hash(text)
        node.stale = False
        written += 1
    graph.search = build_search_index(graph)
    return SummaryStats(reused=reused, written=written, skipped=skipped)


def _is_symbol(node: Node) -> bool:
    structural = {NodeKind.FILE, NodeKind.MODULE, NodeKind.EXTERNAL}
    return node.kind not in structural and node.hash is not None


def _request_summary(client: LLMClient | None, node: Node, root: Path, graph: Graph) -> str:
    if client is None:
        raise LLMUnavailable("summary client unavailable")
    parsed, _stats = client.generate_structured(
        _SYSTEM,
        _user_prompt(node, root, graph),
        NodeSummary,
    )
    return parsed.summary.strip()


def _user_prompt(node: Node, root: Path, graph: Graph) -> str:
    params = ", ".join(node.signature.params)
    return (
        f"id={node.id}\nkind={node.kind.value}\nparams={params}\n\n"
        f"{_child_summaries(graph, node)}\n\n"
        f"{_source(root, node)}"
    )


def _child_summaries(graph: Graph, node: Node) -> str:
    if node.kind is NodeKind.FILE:
        lines = [
            f"{child.id}: {child.summary}"
            for child in graph.nodes.values()
            if child.file == node.id and child.summary and _is_symbol(child)
        ]
        return "\n".join(sorted(lines))
    if node.kind is NodeKind.MODULE and node.file is not None:
        file_node = graph.nodes.get(node.file)
        if file_node is not None and file_node.summary:
            return f"{file_node.id}: {file_node.summary}"
    return ""


def _source(root: Path, node: Node) -> str:
    if node.file is None:
        return ""
    path = root / node.file
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.info("summary source unreadable node=%s", node.id)
        return ""
    if node.range is None:
        return "\n".join(lines)
    return "\n".join(lines[node.range.start - 1 : node.range.end])


def _summary_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

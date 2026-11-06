"""Inverted index over names, paths, tokens, literals, and summaries."""

from __future__ import annotations

import re
from collections import defaultdict

from gatekeeper_graph.models import MODULE_PREFIX, SYMBOL_SEP, Graph, Node

_WORD = re.compile(r"[A-Za-z0-9_./-]+")


def build_search_index(graph: Graph) -> dict[str, list[str]]:
    """Map each searchable term to the sorted node ids that contain it."""
    index: dict[str, set[str]] = defaultdict(set)
    for node in graph.nodes.values():
        for term in _terms(node):
            index[term].add(node.id)
    return {term: sorted(index[term]) for term in sorted(index)}


def search(graph: Graph, query: str) -> list[str]:
    """Return node ids whose indexed terms contain every word in query."""
    terms = _words(query)
    if not terms:
        return []
    index = graph.search or build_search_index(graph)
    found: set[str] | None = None
    for term in terms:
        matches = set(index.get(term, []))
        found = matches if found is None else found & matches
    return sorted(found or [])


def _terms(node: Node) -> set[str]:
    values = [node.id, node.file or "", node.summary or "", *node.tokens, *node.literals]
    if SYMBOL_SEP in node.id and not node.id.startswith(MODULE_PREFIX):
        values.append(node.id.split(SYMBOL_SEP, 1)[1])
    terms: set[str] = set()
    for value in values:
        terms.update(_words(value))
        for part in re.split(r"[/.:]", value):
            if len(part) >= 2:
                terms.add(part.lower())
    return terms


def _words(value: str) -> list[str]:
    return [word.lower() for word in _WORD.findall(value) if len(word) >= 2]

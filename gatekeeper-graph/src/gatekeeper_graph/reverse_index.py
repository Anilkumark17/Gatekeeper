"""Reverse edges from a dependency to the nodes that use it."""

from __future__ import annotations

from collections import defaultdict

from gatekeeper_graph.models import Edge, EdgeType, Graph

DEPENDENCY_TYPES = frozenset(
    {
        EdgeType.IMPORTS,
        EdgeType.RENDERS,
        EdgeType.CALLS,
        EdgeType.USES_HOOK,
        EdgeType.READS_CONTEXT,
        EdgeType.PROVIDES_CONTEXT,
        EdgeType.PASSES_PROP,
        EdgeType.REFERENCES,
        EdgeType.FLOWS_INTO,
    }
)


def compute_reverse(edges: list[Edge]) -> dict[str, list[str]]:
    """Map each target to the sorted unique sources that depend on it."""
    reverse: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.type in DEPENDENCY_TYPES:
            reverse[edge.target].add(edge.source)
        elif edge.type is EdgeType.TESTED_BY:
            reverse[edge.source].add(edge.target)
    return {key: sorted(reverse[key]) for key in sorted(reverse)}


def dependents(graph: Graph, node_id: str, *, transitive: bool = False) -> list[str]:
    """Return nodes that depend on node_id. Transitive search is cycle-safe."""
    direct = list(graph.reverse.get(node_id, []))
    if not transitive:
        return direct
    seen = {node_id}
    ordered: list[str] = []
    stack = list(direct)
    while stack:
        current = stack.pop(0)
        if current in seen:
            continue
        seen.add(current)
        ordered.append(current)
        stack.extend(graph.reverse.get(current, []))
    return sorted(ordered)

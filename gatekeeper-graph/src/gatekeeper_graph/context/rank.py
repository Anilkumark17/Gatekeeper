"""Score reached nodes. Equal scores break toward the smaller node id."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

import networkx as nx

from gatekeeper_graph.context.expand import Expansion, Reach
from gatekeeper_graph.context.graph_index import GraphIndex
from gatekeeper_graph.context.intent import Intent, ProblemType
from gatekeeper_graph.context.select import Anchor
from gatekeeper_graph.context.shortlist import Candidate
from gatekeeper_graph.models import EdgeType, NodeKind

Role = Literal["symptom", "anchor", "upstream", "downstream", "test", "file"]

_EDGE_WEIGHT = {
    EdgeType.CALLS.value: 1.0,
    EdgeType.FLOWS_INTO.value: 1.0,
    EdgeType.REFERENCES.value: 0.9,
    EdgeType.RENDERS.value: 0.9,
    EdgeType.USES_HOOK.value: 0.8,
    EdgeType.READS_CONTEXT.value: 0.8,
    EdgeType.PROVIDES_CONTEXT.value: 0.7,
    EdgeType.PASSES_PROP.value: 0.7,
    EdgeType.IMPORTS.value: 0.4,
    EdgeType.TESTED_BY.value: 0.3,
    EdgeType.CONTAINS.value: 0.2,
}
_WALK = (
    EdgeType.CALLS,
    EdgeType.REFERENCES,
    EdgeType.FLOWS_INTO,
    EdgeType.RENDERS,
    EdgeType.USES_HOOK,
    EdgeType.READS_CONTEXT,
    EdgeType.PROVIDES_CONTEXT,
    EdgeType.PASSES_PROP,
)


@dataclass(frozen=True)
class RankWeights:
    relevance: float = 0.35
    proximity: float = 0.25
    edge: float = 0.15
    shared_ancestor: float = 0.15
    changed: float = 0.07
    untested: float = 0.03


@dataclass(frozen=True)
class RankedPath:
    start: str
    end: str
    node_ids: tuple[str, ...]
    edge_types: tuple[str, ...]


@dataclass(frozen=True)
class RankedNode:
    node_id: str
    score: float
    role: Role
    hops: int
    paths: tuple[RankedPath, ...]


def rank(
    intent: Intent,
    anchors: list[Anchor],
    shortlist: list[Candidate],
    expansion: Expansion,
    index: GraphIndex,
    changed: set[str],
    weights: RankWeights | None = None,
) -> list[RankedNode]:
    """Score every expanded node and return them highest score first."""
    used = weights or RankWeights()
    by_short = {item.node_id: item for item in shortlist}
    anchor_ids = [item.node_id for item in anchors]
    closures = (
        {anchor: _upstream(index, anchor) for anchor in anchor_ids}
        if intent.problem_type is ProblemType.BUG
        else {}
    )
    graph = _path_graph(index, intent.problem_type)
    origins = _origins(intent, anchors, by_short, expansion)
    ranked: list[RankedNode] = []
    for node_id, reach in expansion.nodes.items():
        role = _role(node_id, intent, anchor_ids, by_short, reach, index)
        if node_id in anchor_ids:
            relevance = 1.0
        elif node_id in by_short:
            relevance = by_short[node_id].score
        else:
            relevance = 0.0
        proximity = 1 / (1 + reach.hops)
        edge = _EDGE_WEIGHT.get(reach.via_edge_type or "", 0.0)
        shared = _shared(node_id, closures) if closures else 0.0
        changed_bit = 1.0 if node_id in changed else 0.0
        untested = 1.0 if _untested(index, node_id) else 0.0
        score = (
            used.relevance * relevance
            + used.proximity * proximity
            + used.edge * edge
            + used.shared_ancestor * shared
            + used.changed * changed_bit
            + used.untested * untested
        )
        paths = _paths(intent.problem_type, role, origins, node_id, graph)
        ranked.append(
            RankedNode(node_id=node_id, score=score, role=role, hops=reach.hops, paths=paths)
        )
    ranked.sort(key=lambda item: (-item.score, item.node_id))
    return ranked


def shared_ancestor_fraction(node_id: str, anchor_ids: list[str], index: GraphIndex) -> float:
    """Fraction of anchors that reach node_id through outgoing dependency edges."""
    if not anchor_ids:
        return 0.0
    hits = sum(1 for anchor in anchor_ids if node_id in _upstream(index, anchor))
    return hits / len(anchor_ids)


def _shared(node_id: str, closures: dict[str, set[str]]) -> float:
    if not closures:
        return 0.0
    hits = sum(1 for nodes in closures.values() if node_id in nodes)
    return hits / len(closures)


def _upstream(index: GraphIndex, anchor: str) -> set[str]:
    present = {edge.type for edge in index.graph.edges}
    types = [kind for kind in _WALK if kind in present]
    seen: set[str] = set()
    stack = [anchor]
    while stack:
        current = stack.pop()
        for _edge, nxt in index.dependencies(current, types):
            if nxt in seen:
                continue
            seen.add(nxt)
            stack.append(nxt)
    return seen


def _role(
    node_id: str,
    intent: Intent,
    anchor_ids: list[str],
    shortlist: dict[str, Candidate],
    reach: Reach,
    index: GraphIndex,
) -> Role:
    node = index.get(node_id)
    if reach.direction == "test" or (node is not None and node.kind is NodeKind.TEST):
        return "test"
    if reach.direction == "file" or (node is not None and node.kind is NodeKind.FILE):
        return "file"
    candidate = shortlist.get(node_id)
    pinned_symptom = candidate is not None and candidate.pinned and bool(
        candidate.sources & {"frame", "quoted", "observed"}
    )
    if pinned_symptom or (intent.problem_type is ProblemType.BUG and node_id in anchor_ids):
        return "symptom"
    if node_id in anchor_ids:
        return "anchor"
    if reach.direction == "downstream":
        return "downstream"
    return "upstream"


def _untested(index: GraphIndex, node_id: str) -> bool:
    return not index.outgoing(node_id, [EdgeType.TESTED_BY]) and not index.incoming(
        node_id, [EdgeType.TESTED_BY]
    )


def _origins(
    intent: Intent,
    anchors: list[Anchor],
    shortlist: dict[str, Candidate],
    expansion: Expansion,
) -> list[str]:
    if intent.problem_type is ProblemType.IMPACT:
        return sorted(item.node_id for item in anchors)
    found = set()
    for item in anchors:
        if item.node_id in expansion.nodes:
            found.add(item.node_id)
    for node_id, candidate in shortlist.items():
        if candidate.pinned and candidate.sources & {"frame", "quoted", "observed"}:
            found.add(node_id)
    return sorted(found)


def _path_graph(index: GraphIndex, problem: ProblemType) -> nx.DiGraph:
    graph: nx.DiGraph = nx.DiGraph()
    reverse = problem is ProblemType.IMPACT
    present = {edge.type for edge in index.graph.edges}
    for edge in index.graph.edges:
        if edge.type not in _WALK or edge.type not in present:
            continue
        if reverse:
            graph.add_edge(edge.target, edge.source, kind=edge.type.value)
        else:
            graph.add_edge(edge.source, edge.target, kind=edge.type.value)
    return graph


def _paths(
    problem: ProblemType,
    role: Role,
    origins: list[str],
    node_id: str,
    graph: nx.DiGraph,
) -> tuple[RankedPath, ...]:
    if problem is ProblemType.BUG and role != "upstream":
        return ()
    if problem is ProblemType.IMPACT and role != "downstream":
        return ()
    if problem not in {ProblemType.BUG, ProblemType.IMPACT}:
        return ()
    found: list[RankedPath] = []
    for origin in origins:
        if origin == node_id or origin not in graph or node_id not in graph:
            continue
        if not nx.has_path(graph, origin, node_id):
            continue
        nodes = tuple(str(item) for item in nx.shortest_path(graph, origin, node_id))
        kinds: list[str] = []
        for left, right in pairwise(nodes):
            kinds.append(str(graph.edges[left, right].get("kind", "")))
        found.append(
            RankedPath(start=origin, end=node_id, node_ids=nodes, edge_types=tuple(kinds))
        )
        if len(found) == 3:
            break
    return tuple(found)

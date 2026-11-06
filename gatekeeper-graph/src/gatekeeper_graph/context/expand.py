"""Walk dependency edges out from the anchors. Cycles stop. The walk caps at 120 nodes."""

from __future__ import annotations

from collections import deque
from typing import Literal

from pydantic import BaseModel, ConfigDict

from gatekeeper_graph.context.graph_index import GraphIndex
from gatekeeper_graph.context.intent import Confidence, ProblemType
from gatekeeper_graph.models import EdgeType, NodeKind

Direction = Literal["self", "upstream", "downstream", "file", "test"]

_DEPENDENCY = (
    EdgeType.CALLS,
    EdgeType.REFERENCES,
    EdgeType.FLOWS_INTO,
    EdgeType.RENDERS,
    EdgeType.USES_HOOK,
    EdgeType.READS_CONTEXT,
    EdgeType.PROVIDES_CONTEXT,
    EdgeType.PASSES_PROP,
)
_CAP = 120


class Gap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    detail: str


class Reach(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hops: int
    direction: Direction
    via_edge_type: str | None
    parent: str | None


class Expansion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: dict[str, Reach]


def expand(
    problem: ProblemType,
    confidence: Confidence,
    anchors: list[str],
    index: GraphIndex,
) -> tuple[Expansion, list[Gap]]:
    """Follow the policy for this problem type. Missing edge types become gaps, not errors."""
    present = {edge.type for edge in index.graph.edges}
    gaps: list[Gap] = []
    if EdgeType.REFERENCES not in present:
        gaps.append(Gap(kind="missing_references", detail="missing references edges"))
    if EdgeType.FLOWS_INTO not in present:
        gaps.append(Gap(kind="missing_flows_into", detail="missing flows_into edges"))
    usable = [kind for kind in _DEPENDENCY if kind in present]
    depth_up, depth_down = _depths(problem, confidence)
    reach: dict[str, Reach] = {}
    for anchor in anchors:
        if anchor in index.graph.nodes and anchor not in reach:
            reach[anchor] = Reach(hops=0, direction="self", via_edge_type=None, parent=None)
    _walk(reach, anchors, index, usable, depth_up, "upstream")
    _walk(reach, anchors, index, usable, depth_down, "downstream")
    _files_and_tests(reach, index)
    ordered = sorted(reach, key=lambda node_id: (reach[node_id].hops, node_id))
    if len(ordered) > _CAP:
        reach = {node_id: reach[node_id] for node_id in ordered[:_CAP]}
    return Expansion(nodes=reach), gaps


def _depths(problem: ProblemType, confidence: Confidence) -> tuple[int, int]:
    extra = 1 if confidence is Confidence.LOW else 0
    if problem is ProblemType.BUG:
        return 3 + extra, 1
    if problem is ProblemType.IMPACT or problem is ProblemType.CHANGE:
        return 1, 3 + extra
    if problem is ProblemType.EXPLAIN:
        return 1, 1
    return 2 + extra, 2 + extra


def _walk(
    reach: dict[str, Reach],
    anchors: list[str],
    index: GraphIndex,
    types: list[EdgeType],
    depth: int,
    direction: Literal["upstream", "downstream"],
) -> None:
    if depth <= 0:
        return
    queue: deque[tuple[str, int]] = deque((anchor, 0) for anchor in anchors if anchor in reach)
    seen = set(anchors)
    while queue:
        current, hops = queue.popleft()
        if hops >= depth:
            continue
        if direction == "upstream":
            edges = index.outgoing(current, types)
        else:
            edges = index.incoming(current, types)
        for edge in edges:
            nxt = edge.target if direction == "upstream" else edge.source
            if nxt in seen or nxt in reach:
                continue
            seen.add(nxt)
            reach[nxt] = Reach(
                hops=hops + 1,
                direction=direction,
                via_edge_type=edge.type.value,
                parent=current,
            )
            queue.append((nxt, hops + 1))


def _files_and_tests(reach: dict[str, Reach], index: GraphIndex) -> None:
    for node_id in list(reach):
        node = index.get(node_id)
        file_kinds = {NodeKind.FILE, NodeKind.MODULE, NodeKind.EXTERNAL}
        if node is not None and node.kind not in file_kinds:
            file_id = node.file
            if file_id and file_id not in reach:
                reach[file_id] = Reach(
                    hops=reach[node_id].hops,
                    direction="file",
                    via_edge_type=EdgeType.CONTAINS.value,
                    parent=node_id,
                )
        for edge in index.outgoing(node_id, [EdgeType.TESTED_BY]):
            if edge.target not in reach:
                reach[edge.target] = Reach(
                    hops=reach[node_id].hops + 1,
                    direction="test",
                    via_edge_type=edge.type.value,
                    parent=node_id,
                )
    file_ids = [
        node_id
        for node_id, item in reach.items()
        if item.direction == "file" or _is_file(index, node_id)
    ]
    for file_id in file_ids:
        for edge in index.outgoing(file_id, [EdgeType.IMPORTS]):
            if edge.target not in reach:
                reach[edge.target] = Reach(
                    hops=1,
                    direction="file",
                    via_edge_type=edge.type.value,
                    parent=file_id,
                )


def _is_file(index: GraphIndex, node_id: str) -> bool:
    node = index.get(node_id)
    return node is not None and node.kind is NodeKind.FILE

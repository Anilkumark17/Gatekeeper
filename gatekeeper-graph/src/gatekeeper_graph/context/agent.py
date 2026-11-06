"""Build a context pack. This module does not diagnose or edit code."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from gatekeeper_graph.context.analyse import analyse
from gatekeeper_graph.context.budget import apply_budget, estimate_tokens
from gatekeeper_graph.context.expand import Gap, expand
from gatekeeper_graph.context.graph_index import GraphIndex
from gatekeeper_graph.context.pack import (
    AnalysisInfo,
    ChangeNote,
    ContextPack,
    PackBudget,
    PackEdge,
    PackNode,
    PackPath,
    PackTests,
)
from gatekeeper_graph.context.rank import RankedNode, rank
from gatekeeper_graph.context.search import load_or_build
from gatekeeper_graph.context.select import select
from gatekeeper_graph.context.shortlist import build_shortlist
from gatekeeper_graph.llm.base import LLMClient
from gatekeeper_graph.models import EdgeType, Graph, NodeKind
from gatekeeper_graph.store import load_graph

logger = logging.getLogger(__name__)

_SYMBOL_KINDS = frozenset(NodeKind) - {NodeKind.FILE, NodeKind.EXTERNAL, NodeKind.MODULE}


def build_context(
    question: str,
    graph_path: Path,
    repo_root: Path,
    client: LLMClient,
    active_file: str | None = None,
    budget: int = 3000,
    *,
    write_index: bool = False,
) -> ContextPack:
    """Analyse the question, then fetch and trim the graph context."""
    timings: dict[str, float] = {}
    started = time.perf_counter()
    graph = load_graph(graph_path)
    index = GraphIndex(graph)
    timings["index"] = _ms(started)

    started = time.perf_counter()
    analysed = analyse(question, graph, client, active_file)
    timings["analyse"] = _ms(started)

    started = time.perf_counter()
    search = load_or_build(graph, graph_path, write=write_index)
    timings["search"] = _ms(started)

    started = time.perf_counter()
    shortlist = build_shortlist(analysed.intent, index, search)
    timings["shortlist"] = _ms(started)

    started = time.perf_counter()
    selection = select(analysed.intent, shortlist, index, client, analysed.route)
    timings["select"] = _ms(started)

    started = time.perf_counter()
    expansion, gaps = expand(
        analysed.intent.problem_type,
        analysed.intent.confidence,
        [item.node_id for item in selection.anchors],
        index,
    )
    timings["expand"] = _ms(started)

    change_ids, change_gaps = _change_ids(graph_path)
    gaps.extend(change_gaps)
    gaps.extend(_capability_gaps(graph))
    if analysed.fallback_reason:
        gaps.append(Gap(kind="qwen_fallback", detail=analysed.fallback_reason))
    if selection.fallback_reason:
        gaps.append(Gap(kind="qwen_fallback", detail=selection.fallback_reason))

    started = time.perf_counter()
    ranked = rank(analysed.intent, list(selection.anchors), shortlist, expansion, index, change_ids)
    timings["rank"] = _ms(started)

    ranked_ids = [item.node_id for item in ranked]
    ranges = _ranges(index, ranked_ids)
    required = {item.node_id for item in selection.anchors}
    required.update(item.node_id for item in ranked if item.role == "symptom")
    overhead = estimate_tokens(analysed.intent.model_dump_json()) + 200
    started = time.perf_counter()
    kept, dropped, used = apply_budget(
        ranked,
        repo_root,
        ranges,
        limit=budget,
        overhead=overhead,
        required=required,
    )
    timings["budget"] = _ms(started)
    if dropped:
        gaps.append(Gap(kind="budget_drop", detail=f"dropped: budget count={len(dropped)}"))

    kept_ids = {item.node_id for item in kept}
    snippets = {item.node_id: item.snippet for item in kept}
    nodes: list[PackNode] = []
    for item in ranked:
        if item.node_id not in kept_ids:
            continue
        node = index.get(item.node_id)
        if node is None:
            continue
        span = (node.range.start, node.range.end) if node.range is not None else None
        params = ", ".join(node.signature.params)
        nodes.append(
            PackNode(
                id=node.id,
                kind=node.kind.value,
                file=node.file,
                range=span,
                signature=f"({params})",
                summary=node.summary,
                literals=node.literals,
                role=item.role,
                score=item.score,
                hops=item.hops,
                snippet=snippets.get(node.id),
            )
        )
    edges = _edges(index, kept_ids)
    paths = _paths(ranked, kept_ids)
    notes = _change_notes(graph_path, kept_ids)
    tests, test_gaps = _tests(graph_path, index, kept_ids)
    gaps.extend(test_gaps)
    gaps.extend(_unresolved(index, kept_ids))
    trace = _trace([item.node_id for item in shortlist], selection, expansion, dropped)
    logger.info(
        "context nodes=%s gaps=%s budget_used=%s budget_limit=%s",
        len(nodes),
        len(gaps),
        used,
        budget,
    )
    return ContextPack(
        question=question,
        intent=analysed.intent,
        analysis=AnalysisInfo(
            route=analysed.route,
            fallback_reason=analysed.fallback_reason or selection.fallback_reason,
            stats=selection.stats or analysed.stats,
        ),
        nodes=tuple(nodes),
        edges=tuple(edges),
        paths=tuple(paths),
        changes=tuple(notes),
        tests=tests,
        gaps=tuple(sorted(gaps, key=lambda gap: (gap.kind, gap.detail))),
        trace={key: tuple(trace[key]) for key in sorted(trace)},
        budget=PackBudget(limit=budget, used=used),
        timings_ms=timings,
    )


def _ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _ranges(index: GraphIndex, node_ids: list[str]) -> dict[str, tuple[str, int, int]]:
    found: dict[str, tuple[str, int, int]] = {}
    for node_id in node_ids:
        node = index.get(node_id)
        if node is None or node.file is None or node.range is None:
            continue
        found[node_id] = (node.file, node.range.start, node.range.end)
    return found


def _edges(index: GraphIndex, node_ids: set[str]) -> list[PackEdge]:
    edges: list[PackEdge] = []
    for edge in index.graph.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            continue
        if edge.type is EdgeType.UNRESOLVED:
            continue
        edges.append(
            PackEdge(
                source=edge.source,
                target=edge.target,
                type=edge.type.value,
                file=edge.evidence.file,
                line=edge.evidence.line,
            )
        )
    edges.sort(key=lambda edge: (edge.source, edge.type, edge.target, edge.file, edge.line))
    return edges


def _paths(ranked: list[RankedNode], node_ids: set[str]) -> list[PackPath]:
    paths: list[PackPath] = []
    seen: set[tuple[str, ...]] = set()
    for item in ranked:
        if item.node_id not in node_ids:
            continue
        for path in item.paths:
            if any(node_id not in node_ids for node_id in path.node_ids):
                continue
            if path.node_ids in seen:
                continue
            seen.add(path.node_ids)
            paths.append(
                PackPath(
                    source=path.start,
                    target=path.end,
                    node_ids=path.node_ids,
                    edge_types=path.edge_types,
                )
            )
    paths.sort(key=lambda path: (path.source, path.target, path.node_ids))
    return paths


def _trace(
    shortlist: list[str],
    selection: object,
    expansion: object,
    dropped: list[str],
) -> dict[str, list[str]]:
    from gatekeeper_graph.context.expand import Expansion
    from gatekeeper_graph.context.select import Selection

    trace: dict[str, list[str]] = {}
    for node_id in shortlist:
        trace.setdefault(node_id, []).append("shortlist")
    if isinstance(selection, Selection):
        for anchor in selection.anchors:
            trace.setdefault(anchor.node_id, []).append("selected")
    if isinstance(expansion, Expansion):
        for node_id in expansion.nodes:
            trace.setdefault(node_id, []).append("expanded")
    for node_id in dropped:
        trace.setdefault(node_id, []).append("dropped: budget")
    return trace


def _capability_gaps(graph: Graph) -> list[Gap]:
    symbols = [node for node in graph.nodes.values() if node.kind in _SYMBOL_KINDS]
    gaps: list[Gap] = []
    if symbols and all(node.summary is None for node in symbols):
        gaps.append(Gap(kind="missing_summaries", detail="symbol nodes have no summaries"))
    if symbols and all(not node.literals for node in symbols):
        gaps.append(Gap(kind="missing_literals", detail="symbol nodes have no literals"))
    return gaps


def _change_ids(graph_path: Path) -> tuple[set[str], list[Gap]]:
    path = graph_path.with_name("changes.jsonl")
    if not path.is_file():
        return set(), [Gap(kind="no_changes_file", detail="changes.jsonl is absent")]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return set(), [Gap(kind="no_changes_file", detail=f"changes.jsonl unreadable: {exc}")]
    found: set[str] = set()
    for line in lines:
        node_id = _change_id(line)
        if node_id:
            found.add(node_id)
    return found, []


def _change_notes(graph_path: Path, node_ids: set[str]) -> list[ChangeNote]:
    path = graph_path.with_name("changes.jsonl")
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    notes: list[ChangeNote] = []
    for line in lines:
        node_id = _change_id(line)
        if node_id in node_ids:
            notes.append(ChangeNote(id=node_id, text=line))
    notes.sort(key=lambda note: note.id)
    return notes


def _change_id(line: str) -> str:
    if not line.strip():
        return ""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        raw = payload.get("id", payload.get("node_id", ""))
        return raw if isinstance(raw, str) else ""
    return ""


def _tests(graph_path: Path, index: GraphIndex, node_ids: set[str]) -> tuple[PackTests, list[Gap]]:
    path = graph_path.with_name("tests.json")
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return _tested_by(index, node_ids), [
                Gap(kind="no_tests_file", detail=f"tests.json unreadable: {exc}")
            ]
        mapped: dict[str, tuple[str, ...]] = {}
        failing: list[str] = []
        if isinstance(payload, dict):
            raw_map = payload.get("mapped", {})
            if isinstance(raw_map, dict):
                for key, value in raw_map.items():
                    if isinstance(key, str) and key in node_ids and isinstance(value, list):
                        mapped[key] = tuple(str(item) for item in value)
            raw_failing = payload.get("failing", [])
            if isinstance(raw_failing, list):
                failing = [str(item) for item in raw_failing]
        return PackTests(mapped=mapped, failing=tuple(failing)), []
    return _tested_by(index, node_ids), [Gap(kind="no_tests_file", detail="tests.json is absent")]


def _tested_by(index: GraphIndex, node_ids: set[str]) -> PackTests:
    mapped: dict[str, list[str]] = {}
    for edge in index.graph.edges:
        if edge.type is not EdgeType.TESTED_BY:
            continue
        symbol, test = _test_ends(index, edge.source, edge.target)
        if symbol in node_ids:
            mapped.setdefault(symbol, []).append(test)
    frozen = {key: tuple(sorted(set(mapped[key]))) for key in sorted(mapped)}
    return PackTests(mapped=frozen, failing=())


def _test_ends(index: GraphIndex, source: str, target: str) -> tuple[str, str]:
    source_node = index.get(source)
    target_node = index.get(target)
    if target_node is not None and target_node.kind is NodeKind.TEST:
        return source, target
    if source_node is not None and source_node.kind is NodeKind.TEST:
        return target, source
    return source, target


def _unresolved(index: GraphIndex, node_ids: set[str]) -> list[Gap]:
    gaps: list[Gap] = []
    for edge in index.graph.edges:
        if edge.type is not EdgeType.UNRESOLVED:
            continue
        if edge.source not in node_ids and edge.target not in node_ids:
            continue
        gaps.append(Gap(kind="unresolved_edge", detail=f"{edge.source} {edge.raw or ''}"))
    return gaps


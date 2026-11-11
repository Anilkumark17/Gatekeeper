"""Compare two graphs and report the symbols that changed."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from gatekeeper_graph.models import Graph, Node, NodeKind, parse_node_id

_STRUCTURAL = frozenset({NodeKind.FILE, NodeKind.MODULE})


class GraphDiff(BaseModel):
    """Sorted, deterministic difference between an older graph and a newer one."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    renamed: tuple[tuple[str, str], ...] = ()
    signature_changed: tuple[str, ...] = ()
    edges_added: tuple[tuple[str, str, str], ...] = ()
    edges_removed: tuple[tuple[str, str, str], ...] = ()
    seeds: tuple[str, ...] = ()


def diff_graphs(g0: Graph, g1: Graph) -> GraphDiff:
    """Return what changed from g0 to g1. Line moves with the same hash are not changes."""
    only_g1 = set(g1.nodes) - set(g0.nodes)
    only_g0 = set(g0.nodes) - set(g1.nodes)
    modified = tuple(
        node_id
        for node_id in sorted(set(g0.nodes) & set(g1.nodes))
        if g0.nodes[node_id].kind not in _STRUCTURAL
        and g1.nodes[node_id].kind not in _STRUCTURAL
        and g0.nodes[node_id].hash != g1.nodes[node_id].hash
    )
    renamed = _renames(g0, g1, only_g0, only_g1)
    renamed_old = {old for old, _new in renamed}
    renamed_new = {new for _old, new in renamed}
    added = tuple(sorted(only_g1 - renamed_new))
    removed = tuple(sorted(only_g0 - renamed_old))
    signature_changed = tuple(
        node_id
        for node_id in modified
        if g0.nodes[node_id].signature != g1.nodes[node_id].signature
    )
    edges_before = _edge_ids(g0)
    edges_after = _edge_ids(g1)
    seeds = tuple(sorted(set(added) | set(modified) | renamed_new | set(removed)))
    return GraphDiff(
        added=added,
        removed=removed,
        modified=modified,
        renamed=renamed,
        signature_changed=signature_changed,
        edges_added=tuple(sorted(edges_after - edges_before)),
        edges_removed=tuple(sorted(edges_before - edges_after)),
        seeds=seeds,
    )


def _renames(
    g0: Graph,
    g1: Graph,
    removed: set[str],
    added: set[str],
) -> tuple[tuple[str, str], ...]:
    by_file: dict[str, tuple[list[str], list[str]]] = {}
    for node_id in removed:
        node = g0.nodes[node_id]
        if not _is_symbol(node):
            continue
        by_file.setdefault(node.file or "", ([], []))[0].append(node_id)
    for node_id in added:
        node = g1.nodes[node_id]
        if not _is_symbol(node):
            continue
        by_file.setdefault(node.file or "", ([], []))[1].append(node_id)
    pairs: list[tuple[str, str]] = []
    for _file, (old_ids, new_ids) in sorted(by_file.items()):
        pairs.extend(_pair_file(g0, g1, old_ids, new_ids))
    pairs.sort()
    return tuple(pairs)


def _pair_file(
    g0: Graph,
    g1: Graph,
    old_ids: list[str],
    new_ids: list[str],
) -> list[tuple[str, str]]:
    remaining_old = set(old_ids)
    remaining_new = set(new_ids)
    paired = _unique_pairs(
        remaining_old,
        remaining_new,
        lambda old, new: _same_hash(g0.nodes[old], g1.nodes[new]),
    )
    remaining_old -= {old for old, _new in paired}
    remaining_new -= {new for _old, new in paired}
    paired.extend(
        _unique_pairs(
            remaining_old,
            remaining_new,
            lambda old, new: _same_shape(g0.nodes[old], g1.nodes[new]),
        )
    )
    return paired


def _unique_pairs(
    old_ids: set[str],
    new_ids: set[str],
    matches: Callable[[str, str], bool],
) -> list[tuple[str, str]]:
    found: dict[str, list[str]] = {}
    for old in sorted(old_ids):
        hits = [new for new in sorted(new_ids) if matches(old, new)]
        if hits:
            found[old] = hits
    chosen_by: dict[str, list[str]] = {}
    for old, hits in found.items():
        for new in hits:
            chosen_by.setdefault(new, []).append(old)
    pairs: list[tuple[str, str]] = []
    for old, hits in found.items():
        if len(hits) == 1 and len(chosen_by[hits[0]]) == 1:
            pairs.append((old, hits[0]))
    return pairs


def _same_hash(old: Node, new: Node) -> bool:
    return old.hash is not None and old.hash == new.hash


def _same_shape(old: Node, new: Node) -> bool:
    if old.kind != new.kind or old.signature != new.signature or old.literals != new.literals:
        return False
    old_name = parse_node_id(old.id)[2] or ""
    new_name = parse_node_id(new.id)[2] or ""
    return set(old.tokens) - {old_name} == set(new.tokens) - {new_name}


def _is_symbol(node: Node) -> bool:
    return node.kind not in {NodeKind.FILE, NodeKind.MODULE, NodeKind.EXTERNAL}


def _edge_ids(graph: Graph) -> set[tuple[str, str, str]]:
    return {(edge.source, edge.target, edge.type.value) for edge in graph.edges}

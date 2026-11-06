"""Command line entry for building and showing a graph."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

from gatekeeper_graph.builder import build_graph
from gatekeeper_graph.models import Edge, EdgeType
from gatekeeper_graph.reverse_index import dependents
from gatekeeper_graph.store import load_graph, save_graph
from gatekeeper_graph.watcher import watch


def main(argv: list[str] | None = None) -> int:
    """Run the gatekeeper command. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="gatekeeper")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="build a graph for a repository")
    build.add_argument("root", type=Path)
    build.add_argument("--out", type=Path)

    watch_command = commands.add_parser("watch", help="rebuild the graph when files change")
    watch_command.add_argument("root", type=Path)
    watch_command.add_argument("--out", type=Path)

    show = commands.add_parser("show", help="print a saved graph")
    show.add_argument("graph", type=Path)
    show.add_argument("--kind")
    show.add_argument("--node")

    args = parser.parse_args(argv)
    if args.command == "build":
        return _build(args.root, args.out)
    if args.command == "watch":
        return _watch(args.root, args.out)
    return _show(args.graph, args.kind, args.node)


def _output_path(root: Path, out: Path | None) -> tuple[Path, Path] | int:
    source = root.resolve()
    if not source.is_dir():
        print(f"root is not a directory path={source}", file=sys.stderr)
        return 2
    destination = (out or Path("out") / f"{source.name}.graph.json").resolve()
    if source == destination or source in destination.parents:
        print(f"refusing to write inside the scanned repo out={destination}", file=sys.stderr)
        return 2
    return source, destination


def _build(root: Path, out: Path | None) -> int:
    prepared = _output_path(root, out)
    if isinstance(prepared, int):
        return prepared
    source, destination = prepared
    result = build_graph(source)
    save_graph(result.graph, destination)
    stats = result.stats
    print(
        f"files={stats.files_parsed} skipped={stats.files_skipped} "
        f"nodes={stats.nodes} edges={stats.edges}"
    )
    print(f"wrote path={destination}")
    _print_edges(result.graph.edges)
    return 0


def _watch(root: Path, out: Path | None) -> int:
    prepared = _output_path(root, out)
    if isinstance(prepared, int):
        return prepared
    source, destination = prepared
    _write_update(source, destination)
    print(f"watching root={source}")
    watch(source, lambda: _write_update(source, destination))
    return 0


def _write_update(source: Path, destination: Path) -> None:
    result = build_graph(source)
    save_graph(result.graph, destination)
    stats = result.stats
    print(
        f"files={stats.files_parsed} skipped={stats.files_skipped} "
        f"nodes={stats.nodes} edges={stats.edges} wrote path={destination}"
    )


def _show(path: Path, kind: str | None, node_id: str | None) -> int:
    graph = load_graph(path)
    if node_id is not None:
        node = graph.nodes.get(node_id)
        if node is None:
            print(f"node is missing id={node_id}", file=sys.stderr)
            return 2
        print(f"id={node.id} kind={node.kind.value} file={node.file}")
        if node.range is not None:
            print(f"range={node.range.start}-{node.range.end}")
        print("outgoing")
        _print_edges(edge for edge in graph.edges if edge.source == node_id)
        print("incoming")
        _print_edges(edge for edge in graph.edges if edge.target == node_id)
        print("dependents")
        for item in dependents(graph, node_id):
            print(item)
        return 0
    counts: dict[str, int] = {}
    for node in graph.nodes.values():
        if kind is not None and node.kind.value != kind:
            continue
        counts[node.kind.value] = counts.get(node.kind.value, 0) + 1
        if node.range is None:
            print(f"{node.kind.value} {node.id}")
        else:
            print(f"{node.kind.value} {node.id} {node.range.start}-{node.range.end}")
    print("counts " + " ".join(f"{name}={count}" for name, count in sorted(counts.items())))
    return 0


def _print_edges(edges: Iterable[Edge]) -> None:
    for edge in edges:
        suffix = f" raw={edge.raw}" if edge.type is EdgeType.UNRESOLVED else ""
        line = (
            f"{edge.type.value} {edge.source} -> {edge.target} "
            f"@{edge.evidence.file}:{edge.evidence.line}{suffix}"
        )
        print(line)

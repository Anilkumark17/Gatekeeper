"""Command line entry for building and showing a graph."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from gatekeeper_graph.builder import build_graph
from gatekeeper_graph.llm import LLMClient, load_config, make_client
from gatekeeper_graph.llm.errors import LLMOutputInvalid, LLMUnavailable
from gatekeeper_graph.models import Edge, EdgeType, Graph
from gatekeeper_graph.reverse_index import dependents
from gatekeeper_graph.store import load_graph, save_graph
from gatekeeper_graph.summarizer import apply_summaries
from gatekeeper_graph.watcher import watch

logger = logging.getLogger(__name__)


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

    commands.add_parser("llm-check", help="check the configured model and print call stats")

    show = commands.add_parser("show", help="print a saved graph")
    show.add_argument("graph", type=Path)
    show.add_argument("--kind")
    show.add_argument("--node")

    args = parser.parse_args(argv)
    if args.command == "build":
        return _build(args.root, args.out)
    if args.command == "watch":
        return _watch(args.root, args.out)
    if args.command == "llm-check":
        return _llm_check()
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
    counts = apply_summaries(result.graph, source, _summary_client(), _previous_graph(destination))
    save_graph(result.graph, destination)
    stats = result.stats
    print(
        f"files={stats.files_parsed} skipped={stats.files_skipped} "
        f"nodes={stats.nodes} edges={stats.edges} "
        f"summaries_reused={counts.reused} summaries_written={counts.written} "
        f"summaries_skipped={counts.skipped} wrote path={destination}"
    )


def _previous_graph(path: Path) -> Graph | None:
    if not path.is_file():
        return None
    try:
        return load_graph(path)
    except (OSError, ValidationError, ValueError):
        logger.warning("previous graph unreadable path=%s", path)
        return None


def _summary_client() -> LLMClient | None:
    try:
        return make_client()
    except (LLMUnavailable, ImportError, ValidationError) as exc:
        logger.warning("summary client unavailable reason=%s", exc)
        return None


class _OkCheck(BaseModel):
    ok: bool


def _llm_check() -> int:
    config = load_config()
    print(f"provider={config.provider} model={config.model}")
    client = make_client(config)
    if not client.is_available():
        print(f"llm unavailable provider={config.provider} model={config.model}", file=sys.stderr)
        return 2
    try:
        _value, stats = client.generate_structured(
            "Reply with one JSON object.",
            "Set ok to true.",
            _OkCheck,
        )
    except LLMUnavailable as exc:
        print(f"llm unavailable reason={exc}", file=sys.stderr)
        return 2
    except LLMOutputInvalid as exc:
        print(f"llm output invalid raw={exc.raw}", file=sys.stderr)
        return 3
    print(
        f"backend={stats.backend} model={stats.model} prompt_tokens={stats.prompt_tokens} "
        f"output_tokens={stats.output_tokens} total_ms={stats.total_ms} "
        f"load_ms={stats.load_ms} retries={stats.retries}"
    )
    return 0


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

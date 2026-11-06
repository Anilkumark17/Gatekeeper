"""Discover source files and build a graph for one repository."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from gatekeeper_graph.extractor import FileExtraction, extract_file
from gatekeeper_graph.ignore import DEFAULT_IGNORED_DIRS, is_ignored
from gatekeeper_graph.models import Graph
from gatekeeper_graph.parser.core import parse_file
from gatekeeper_graph.parser.languages import language_for_path
from gatekeeper_graph.resolver import resolve_all
from gatekeeper_graph.reverse_index import compute_reverse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuildStats:
    files_found: int
    files_parsed: int
    files_skipped: int
    nodes: int
    edges: int
    dropped_calls: int
    nodes_by_kind: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildResult:
    graph: Graph
    stats: BuildStats
    extractions: dict[str, FileExtraction]


def discover_files(root: Path) -> list[Path]:
    """Return supported source files under root, skipping ignored directories."""
    found: list[Path] = []
    root_resolved = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in DEFAULT_IGNORED_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            relative = path.resolve().relative_to(root_resolved).as_posix()
            if is_ignored(relative) or language_for_path(relative) is None:
                continue
            found.append(path)
    found.sort(key=lambda path: path.resolve().relative_to(root_resolved).as_posix())
    return found


def build_graph(root: Path) -> BuildResult:
    """Parse, extract, and resolve every discovered file under root."""
    paths = discover_files(root)
    extractions: dict[str, FileExtraction] = {}
    skipped = 0
    for path in paths:
        parsed = parse_file(path, root)
        if parsed is None:
            skipped += 1
            continue
        extractions[parsed.path] = extract_file(parsed)
    edges, externals, dropped = resolve_all(extractions, root)
    nodes = [node for extraction in extractions.values() for node in extraction.nodes]
    nodes.extend(externals)
    contains = [edge for extraction in extractions.values() for edge in extraction.contains]
    combined = sorted([*contains, *edges], key=lambda edge: edge.key())
    graph = Graph(
        root=root.resolve().as_posix(),
        nodes={node.id: node for node in sorted(nodes, key=lambda node: node.id)},
        edges=combined,
        reverse=compute_reverse(combined),
    )
    counts: dict[str, int] = {}
    for node in graph.nodes.values():
        counts[node.kind.value] = counts.get(node.kind.value, 0) + 1
    stats = BuildStats(
        files_found=len(paths),
        files_parsed=len(extractions),
        files_skipped=skipped,
        nodes=len(graph.nodes),
        edges=len(graph.edges),
        dropped_calls=dropped,
        nodes_by_kind=counts,
    )
    logger.info(
        "built root=%s files=%s nodes=%s edges=%s",
        root,
        stats.files_parsed,
        stats.nodes,
        stats.edges,
    )
    return BuildResult(graph=graph, stats=stats, extractions=extractions)

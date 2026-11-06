"""Link per-file extractions into graph edges."""

from __future__ import annotations

import logging
import posixpath
from pathlib import Path

from gatekeeper_graph.extractor.types import FileExtraction, ImportKind, ImportRef
from gatekeeper_graph.models import (
    Edge,
    EdgeType,
    Evidence,
    NodeKind,
    make_external_id,
    make_symbol_id,
)
from gatekeeper_graph.models import Node as GraphNode
from gatekeeper_graph.resolver.config import ResolverConfig, load_config

logger = logging.getLogger(__name__)

_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")


def resolve_all(
    extractions: dict[str, FileExtraction],
    root: Path,
) -> tuple[list[Edge], list[GraphNode], int]:
    """Return resolved edges, external nodes, and the number of dropped calls."""
    config = load_config(root)
    files = frozenset(extractions)
    tables = _export_tables(extractions, files, config)
    edges: list[Edge] = []
    externals: dict[str, GraphNode] = {}
    dropped = 0
    for extraction in extractions.values():
        bindings = _bindings(extraction, tables, files, config)
        for ref in extraction.imports:
            _import_edge(extraction.path, ref, files, config, edges, externals)
        for export in extraction.exports:
            if export.from_specifier is None:
                continue
            _link(
                extraction.path,
                export.from_specifier,
                export.line,
                files,
                config,
                edges,
                externals,
            )
        for call in extraction.calls:
            target = _call_target(call.callee, bindings)
            if target is None:
                dropped += 1
                continue
            if target.startswith("external:"):
                externals.setdefault(target, GraphNode(id=target, kind=NodeKind.EXTERNAL))
            edges.append(
                Edge(
                    source=call.owner,
                    target=target,
                    type=EdgeType.CALLS,
                    evidence=Evidence(file=extraction.path, line=call.line),
                )
            )
    logger.info(
        "resolved files=%s edges=%s dropped_calls=%s",
        len(extractions),
        len(edges),
        dropped,
    )
    return _dedupe(edges), list(externals.values()), dropped


def resolve_specifier(
    from_file: str,
    specifier: str,
    files: frozenset[str],
    config: ResolverConfig,
) -> str | None:
    """Resolve a specifier to a file id or an external id."""
    if specifier.startswith("."):
        joined = posixpath.normpath(posixpath.join(posixpath.dirname(from_file), specifier))
        if joined == ".." or joined.startswith("../"):
            return None
        return _existing(joined, files)
    for pattern, replacements in config.paths.items():
        mapped = _apply_pattern(pattern, replacements[0] if replacements else None, specifier)
        if mapped is None:
            continue
        if config.base_url:
            mapped = posixpath.normpath(posixpath.join(config.base_url, mapped))
        return _existing(mapped, files)
    if specifier.startswith(".") or specifier.startswith("/"):
        return None
    return make_external_id(_package_name(specifier))


def _existing(candidate: str, files: frozenset[str]) -> str | None:
    ordered: list[str] = []
    for option in (
        candidate,
        *[f"{candidate}{extension}" for extension in _EXTENSIONS],
        *[f"{candidate}/index{extension}" for extension in ("", *_EXTENSIONS)],
    ):
        normalized = option[2:] if option.startswith("./") else option
        if normalized not in ordered:
            ordered.append(normalized)
    for option in ordered:
        if option in files:
            return option
    return None


def _apply_pattern(pattern: str, replacement: str | None, specifier: str) -> str | None:
    if replacement is None:
        return None
    if pattern.endswith("/*") and replacement.endswith("/*"):
        prefix = pattern[:-1]
        if specifier.startswith(prefix):
            return replacement[:-1] + specifier[len(prefix) :]
        return None
    if pattern == specifier:
        return replacement
    return None


def _package_name(specifier: str) -> str:
    if specifier.startswith("@"):
        scope, _, rest = specifier.partition("/")
        name, _, _subpath = rest.partition("/")
        return f"{scope}/{name}" if name else scope
    return specifier.split("/", 1)[0]


def _export_tables(
    extractions: dict[str, FileExtraction],
    files: frozenset[str],
    config: ResolverConfig,
) -> dict[str, dict[str, str]]:
    tables: dict[str, dict[str, str]] = {}

    def lookup(file_id: str, name: str, seen: set[tuple[str, str]]) -> str | None:
        if (file_id, name) in seen or file_id not in extractions:
            return None
        seen.add((file_id, name))
        for ref in extractions[file_id].exports:
            if ref.is_star or ref.exported != name:
                continue
            if ref.from_specifier is None:
                return make_symbol_id(file_id, ref.local or name)
            target = resolve_specifier(file_id, ref.from_specifier, files, config)
            if target is None or target.startswith("external:"):
                logger.warning(
                    "reexport unresolved file=%s name=%s specifier=%s",
                    file_id,
                    name,
                    ref.from_specifier,
                )
                return None
            return lookup(target, ref.local or name, seen)
        return None

    for file_id in extractions:
        mapping: dict[str, str] = {}
        for ref in extractions[file_id].exports:
            if ref.is_star:
                continue
            found = lookup(file_id, ref.exported, set())
            if found is not None:
                mapping[ref.exported] = found
        tables[file_id] = mapping
    return tables


def _bindings(
    extraction: FileExtraction,
    tables: dict[str, dict[str, str]],
    files: frozenset[str],
    config: ResolverConfig,
) -> dict[str, str]:
    bound = {
        node.id.split("#", 1)[1]: node.id
        for node in extraction.nodes
        if node.kind not in {NodeKind.FILE, NodeKind.EXTERNAL} and "#" in node.id
    }
    for ref in extraction.imports:
        if ref.kind is ImportKind.DYNAMIC:
            continue
        target = resolve_specifier(extraction.path, ref.specifier, files, config)
        for imported in ref.names:
            if target is None:
                continue
            if target.startswith("external:"):
                bound[imported.local] = target
                continue
            symbol = tables.get(target, {}).get(imported.imported)
            if symbol is not None:
                bound[imported.local] = symbol
    return bound


def _import_edge(
    path: str,
    ref: ImportRef,
    files: frozenset[str],
    config: ResolverConfig,
    edges: list[Edge],
    externals: dict[str, GraphNode],
) -> None:
    if ref.kind is ImportKind.DYNAMIC:
        edges.append(
            Edge(
                source=ref.owner,
                target=f"unresolved:{ref.specifier}",
                type=EdgeType.UNRESOLVED,
                evidence=Evidence(file=path, line=ref.line),
                raw=f"import({ref.specifier})",
            )
        )
        return
    _link(path, ref.specifier, ref.line, files, config, edges, externals)


def _link(
    path: str,
    specifier: str,
    line: int,
    files: frozenset[str],
    config: ResolverConfig,
    edges: list[Edge],
    externals: dict[str, GraphNode],
) -> None:
    target = resolve_specifier(path, specifier, files, config)
    if target is None:
        edges.append(
            Edge(
                source=path,
                target=f"unresolved:{specifier}",
                type=EdgeType.UNRESOLVED,
                evidence=Evidence(file=path, line=line),
                raw=specifier,
            )
        )
        return
    if target.startswith("external:"):
        externals.setdefault(target, GraphNode(id=target, kind=NodeKind.EXTERNAL))
    edges.append(
        Edge(
            source=path,
            target=target,
            type=EdgeType.IMPORTS,
            evidence=Evidence(file=path, line=line),
        )
    )


def _call_target(callee: str, bindings: dict[str, str]) -> str | None:
    head = callee.split(".", 1)[0]
    return bindings.get(head)


def _dedupe(edges: list[Edge]) -> list[Edge]:
    unique: dict[tuple[str, str, EdgeType, str, int], Edge] = {}
    for edge in edges:
        unique.setdefault(edge.key(), edge)
    return sorted(unique.values(), key=lambda edge: edge.key())

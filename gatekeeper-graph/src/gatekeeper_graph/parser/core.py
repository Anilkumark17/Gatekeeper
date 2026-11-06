"""Parse source bytes and files into tree-sitter trees."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from tree_sitter import Node, Parser, Tree

from gatekeeper_graph.parser.languages import LanguageId, get_language, language_for_path

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 1_000_000
_MAX_LINE_BYTES = 5000


@dataclass(frozen=True)
class ParsedFile:
    path: str
    language: LanguageId
    source: bytes
    tree: Tree

    @property
    def root(self) -> Node:
        return self.tree.root_node


@cache
def get_parser(lang: LanguageId) -> Parser:
    """Return the cached parser for lang."""
    return Parser(get_language(lang))


def parse_source(
    source: bytes,
    path: str,
    language: LanguageId | None = None,
) -> ParsedFile | None:
    """Parse source as path. None when the extension is unsupported."""
    chosen = language if language is not None else language_for_path(path)
    if chosen is None:
        return None
    tree = get_parser(chosen).parse(source)
    return ParsedFile(path=path, language=chosen, source=source, tree=tree)


def parse_file(abs_path: Path, root: Path) -> ParsedFile | None:
    """Read and parse abs_path relative to root. Never raises for bad input."""
    try:
        relative = abs_path.resolve().relative_to(root.resolve())
    except ValueError:
        logger.info("parse skipped path=%s reason=outside_root", abs_path)
        return None
    rel = relative.as_posix()
    if language_for_path(rel) is None:
        return None
    try:
        raw = abs_path.read_bytes()
    except OSError as exc:
        logger.info("parse skipped path=%s reason=unreadable error=%s", rel, exc)
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    if len(raw) > MAX_FILE_BYTES:
        logger.info("parse skipped path=%s reason=too_large size=%s", rel, len(raw))
        return None
    if any(len(line) > _MAX_LINE_BYTES for line in raw.splitlines()):
        logger.info("parse skipped path=%s reason=minified", rel)
        return None
    return parse_source(raw, rel)

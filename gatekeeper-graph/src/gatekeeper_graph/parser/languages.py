"""Tree-sitter language registry."""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import StrEnum
from functools import cache

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language

logger = logging.getLogger(__name__)

_JAVASCRIPT_SUFFIXES = frozenset({".js", ".jsx", ".mjs", ".cjs"})
_TYPESCRIPT_SUFFIXES = frozenset({".ts", ".mts", ".cts"})


class LanguageId(StrEnum):
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    TSX = "tsx"


_LOADERS: dict[LanguageId, Callable[[], object]] = {
    LanguageId.JAVASCRIPT: tree_sitter_javascript.language,
    LanguageId.TYPESCRIPT: tree_sitter_typescript.language_typescript,
    LanguageId.TSX: tree_sitter_typescript.language_tsx,
}


def language_for_path(path: str) -> LanguageId | None:
    """Return the grammar for a repo-relative path, or None if unsupported."""
    normalized = path.replace("\\", "/").lower()
    if normalized.endswith(".d.ts"):
        return None
    name = normalized.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    if dot <= 0:
        return None
    suffix = name[dot:]
    if suffix in _JAVASCRIPT_SUFFIXES:
        return LanguageId.JAVASCRIPT
    if suffix in _TYPESCRIPT_SUFFIXES:
        return LanguageId.TYPESCRIPT
    if suffix == ".tsx":
        return LanguageId.TSX
    return None


@cache
def get_language(lang: LanguageId) -> Language:
    """Return the tree-sitter language for lang. The same object is reused."""
    try:
        load = _LOADERS[lang]
    except KeyError as exc:
        raise ValueError(f"unknown language={lang}") from exc
    loaded = Language(load())
    logger.info("language loaded id=%s", lang.value)
    return loaded

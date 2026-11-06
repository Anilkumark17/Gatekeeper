"""Directory names skipped while discovering and watching a repository."""

from __future__ import annotations

DEFAULT_IGNORED_DIRS = frozenset(
    {"node_modules", "dist", "build", ".git", "coverage", ".next", ".turbo", "out"}
)


def is_ignored(rel_posix: str) -> bool:
    """True when any path segment is an ignored directory name."""
    return any(part in DEFAULT_IGNORED_DIRS for part in rel_posix.split("/"))

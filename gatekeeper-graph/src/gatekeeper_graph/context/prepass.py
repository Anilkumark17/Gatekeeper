"""Deterministic extraction of quotes, paths, frames, and error types."""

from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from gatekeeper_graph.context.intent import StackFrame

_EXTENSIONS = ("js", "jsx", "ts", "tsx", "mjs", "cjs")
_EXT = "|".join(_EXTENSIONS)
_FILE_RE = re.compile(
    rf"(?<![\w@])(?P<path>(?:[A-Za-z]:[\\/])?(?:\.[\\/])?(?:[\w.-]+[\\/])*[\w.-]+\.(?:{_EXT}))(?![\w-])"
)
_FRAME_RE = re.compile(
    rf"\bat\s+(?:(?P<name>[A-Za-z_$][\w$]*)\s+\()?"
    rf"(?P<path>(?:[A-Za-z]:[\\/])?(?:\.[\\/])?(?:[\w.-]+[\\/])*[\w.-]+\.(?:{_EXT}))"
    rf":(?P<line>\d+):(?P<col>\d+)\)?"
)
_ERROR_RE = re.compile(r"\b[A-Z][A-Za-z]*Error\b")


class PrePass(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    quoted: tuple[str, ...] = ()
    backticks: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    frames: tuple[StackFrame, ...] = ()
    error_types: tuple[str, ...] = ()


def prepass(question: str, repo_files: frozenset[str] | None = None) -> PrePass:
    """Pull quoted text, code names, files, frames, and error types from a question."""
    quoted, backticks = _quotes(question)
    raw_files = (_resolve(match.group("path"), repo_files) for match in _FILE_RE.finditer(question))
    files = _unique(raw_files)
    frames: list[StackFrame] = []
    seen_frames: set[tuple[str, int, str]] = set()
    for match in _FRAME_RE.finditer(question):
        resolved = _resolve(match.group("path"), repo_files)
        if resolved is None:
            continue
        name = match.group("name") or ""
        line = int(match.group("line"))
        if line < 1:
            continue
        key = (resolved, line, name)
        if key in seen_frames:
            continue
        seen_frames.add(key)
        frames.append(StackFrame(name=name, file=resolved, line=line))
    frames.sort(key=lambda frame: (frame.file, frame.line, frame.name))
    errors = tuple(sorted(set(_ERROR_RE.findall(question))))
    return PrePass(
        quoted=quoted,
        backticks=backticks,
        files=tuple(sorted(files)),
        frames=tuple(frames),
        error_types=errors,
    )


def _quotes(question: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    quoted: list[str] = []
    backticks: list[str] = []
    index = 0
    while index < len(question):
        char = question[index]
        if char == "`":
            end = question.find("`", index + 1)
            if end < 0:
                break
            backticks.append(question[index + 1 : end])
            index = end + 1
            continue
        if char in {'"', "'"}:
            end = question.find(char, index + 1)
            if end < 0:
                index += 1
                continue
            text = question[index + 1 : end]
            if len(text) >= 2:
                quoted.append(text)
            index = end + 1
            continue
        index += 1
    return tuple(quoted), tuple(backticks)


def _resolve(raw: str, repo_files: frozenset[str] | None) -> str | None:
    text = raw.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if len(text) >= 2 and text[1] == ":":
        text = text[2:].lstrip("/")
    text = text.lstrip("/")
    if repo_files is None:
        return text or None
    if text in repo_files:
        return text
    suffix = sorted(item for item in repo_files if text.endswith("/" + item))
    if len(suffix) == 1:
        return suffix[0]
    partial = sorted(item for item in repo_files if item.endswith("/" + text))
    if len(partial) == 1:
        return partial[0]
    return None


def _unique(items: Iterable[str | None]) -> list[str]:
    found: list[str] = []
    for item in items:
        if item is not None and item not in found:
            found.append(item)
    return found

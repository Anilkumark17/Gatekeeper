"""Token budget. Anchors and symptoms keep their snippets."""

from __future__ import annotations

import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from gatekeeper_graph.context.rank import RankedNode


class Snippet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: int
    end: int
    text: str


class BudgetItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    snippet: Snippet | None


def estimate_tokens(text: str) -> int:
    """Rough token count used for the pack budget."""
    if not text:
        return 0
    return math.ceil(len(text) / 4)


def source_snippet(repo: Path, file: str, start: int, end: int) -> Snippet | None:
    """Read the node's lines. Longer than 40 lines keeps the first 30 and the last 10."""
    path = repo / Path(file)
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    if not lines or start < 1:
        return None
    stop = min(end, len(lines))
    begin = min(start, stop)
    selected = lines[begin - 1 : stop]
    if len(selected) > 40:
        omitted = len(selected) - 40
        marker = f"… {omitted} lines omitted …"
        selected = [*selected[:30], marker, *selected[-10:]]
    return Snippet(start=begin, end=stop, text="\n".join(selected))


def apply_budget(
    ranked: list[RankedNode],
    repo: Path,
    ranges: dict[str, tuple[str, int, int]],
    *,
    limit: int,
    overhead: int,
    required: set[str],
) -> tuple[list[BudgetItem], list[str], int]:
    """Fill in rank order. Required nodes always stay. Others drop when the budget is spent."""
    used = min(overhead, limit) if overhead > 0 else 0
    if overhead > limit:
        used = overhead
    kept: list[BudgetItem] = []
    dropped: list[str] = []
    for item in ranked:
        span = ranges.get(item.node_id)
        snippet = source_snippet(repo, span[0], span[1], span[2]) if span is not None else None
        meta = f"{item.node_id} {item.role} {item.score:.4f}"
        meta_cost = estimate_tokens(meta)
        snippet_cost = estimate_tokens(snippet.text) if snippet is not None else 0
        must = item.node_id in required or item.role in {"anchor", "symptom"}
        if must:
            kept.append(BudgetItem(node_id=item.node_id, snippet=snippet))
            used += meta_cost + snippet_cost
            continue
        if used + meta_cost + snippet_cost <= limit:
            kept.append(BudgetItem(node_id=item.node_id, snippet=snippet))
            used += meta_cost + snippet_cost
            continue
        if used + meta_cost <= limit:
            kept.append(BudgetItem(node_id=item.node_id, snippet=None))
            used += meta_cost
            continue
        dropped.append(item.node_id)
    return kept, dropped, used

"""Atomic graph.json reads and writes."""

from __future__ import annotations

import os
import time
from pathlib import Path

from gatekeeper_graph.models import Graph, graph_from_json, graph_to_json


def save_graph(graph: Graph, path: Path) -> None:
    """Write graph.json by replacing a complete temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(graph_to_json(graph))
        handle.flush()
        os.fsync(handle.fileno())
    for attempt in range(5):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05)


def load_graph(path: Path) -> Graph:
    """Load a graph. A missing file raises FileNotFoundError naming the path."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"graph file is missing path={path}") from exc
    return graph_from_json(text)

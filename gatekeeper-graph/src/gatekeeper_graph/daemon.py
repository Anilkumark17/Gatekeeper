"""One process that keeps a graph live and answers questions from it."""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from gatekeeper_graph.builder import build_graph
from gatekeeper_graph.context.agent import build_context
from gatekeeper_graph.context.pack import render_markdown
from gatekeeper_graph.llm.base import LLMClient
from gatekeeper_graph.llm.errors import LLMUnavailable
from gatekeeper_graph.llm.stats import CallStats
from gatekeeper_graph.models import Graph
from gatekeeper_graph.store import load_graph, save_graph
from gatekeeper_graph.summarizer import apply_summaries
from gatekeeper_graph.watcher import WatchSession

logger = logging.getLogger(__name__)


class _Down:
    """Stand-in client used when no model is configured."""

    def generate_structured[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
    ) -> tuple[T, CallStats]:
        raise LLMUnavailable("llm client unavailable")

    def generate_text(self, system: str, user: str) -> tuple[str, CallStats]:
        raise LLMUnavailable("llm client unavailable")

    def is_available(self) -> bool:
        return False


class Daemon:
    """Index a repository, watch it, and answer questions against the graph."""

    def __init__(
        self,
        source: Path,
        destination: Path,
        client: LLMClient | None,
        *,
        as_json: bool = False,
        budget: int = 3000,
    ) -> None:
        self.source = source
        self.destination = destination
        self.client = client
        self.as_json = as_json
        self.budget = budget
        self._lock = threading.Lock()

    def rebuild(self) -> None:
        """Rebuild the graph and fill summaries. Waits if a question is in progress."""
        with self._lock:
            write_update(self.source, self.destination, self.client)

    def answer(self, question: str) -> None:
        """Print a context pack for one question. Waits if a rebuild is in progress."""
        client = self.client if self.client is not None else _Down()
        with self._lock:
            pack = build_context(
                question,
                self.destination,
                self.source,
                client,
                budget=self.budget,
            )
        if self.as_json:
            print(pack.model_dump_json(indent=2, by_alias=True))
        else:
            print(render_markdown(pack))

    def run(self, questions: Iterable[str], *, watch_files: bool = True) -> int:
        """Index once, watch for edits, then answer each question. `quit` stops the loop."""
        self.rebuild()
        print(f"watching root={self.source}")
        session = WatchSession(self.source, self.rebuild) if watch_files else None
        if session is not None:
            session.start()
        try:
            for raw in questions:
                question = raw.strip()
                if not question:
                    continue
                if question == "quit":
                    break
                try:
                    self.answer(question)
                except (OSError, ValidationError, ValueError) as exc:
                    print(str(exc), file=sys.stderr)
        except KeyboardInterrupt:
            return 0
        finally:
            if session is not None:
                session.stop()
        return 0


def write_update(source: Path, destination: Path, client: LLMClient | None) -> None:
    """Build the graph, apply summaries, and replace the graph file."""
    result = build_graph(source)
    counts = apply_summaries(result.graph, source, client, _previous_graph(destination))
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

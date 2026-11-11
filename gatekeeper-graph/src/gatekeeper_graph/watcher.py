"""Rebuild a graph from operating-system file events."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from gatekeeper_graph.ignore import is_ignored

logger = logging.getLogger(__name__)

RELEVANT_EVENTS = frozenset({"created", "modified", "deleted", "moved"})
DEBOUNCE_SECONDS = 0.3


class PrintHandler(FileSystemEventHandler):
    def on_any_event(self, event: FileSystemEvent) -> None:
        logger.info(
            "event type=%s is_dir=%s src=%s dest=%s",
            event.event_type,
            event.is_directory,
            event.src_path,
            event.dest_path,
        )


class RebuildHandler(FileSystemEventHandler):
    """Call back once after a burst of relevant filesystem events."""

    def __init__(
        self,
        root: Path,
        on_change: Callable[[], None],
        delay: float = DEBOUNCE_SECONDS,
    ) -> None:
        self._root = root.resolve()
        self._on_change = on_change
        self._delay = delay
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.event_type not in RELEVANT_EVENTS:
            return
        if not self._relevant(event.src_path) and not self._relevant(event.dest_path):
            return
        self.schedule()

    def schedule(self) -> None:
        """Restart the debounce timer."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            timer = threading.Timer(self._delay, self._fire)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def close(self) -> None:
        """Cancel a pending rebuild."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _fire(self) -> None:
        try:
            self._on_change()
        except Exception:
            logger.exception("rebuild failed")

    def _relevant(self, raw: bytes | str) -> bool:
        text = os.fsdecode(raw) if isinstance(raw, bytes) else raw
        if not text:
            return False
        try:
            relative = Path(text).resolve().relative_to(self._root).as_posix()
        except ValueError:
            return False
        return not is_ignored(relative)


class WatchSession:
    """A started or startable watch on one repository root."""

    def __init__(self, root: Path, on_change: Callable[[], None] | None = None) -> None:
        self._root = root
        self._rebuild: RebuildHandler | None
        handler: FileSystemEventHandler
        if on_change is None:
            self._rebuild = None
            handler = PrintHandler()
        else:
            self._rebuild = RebuildHandler(root, on_change)
            handler = self._rebuild
        self._observer = Observer()
        self._observer.schedule(handler, str(root), recursive=True)
        self._started = False

    def start(self) -> None:
        """Start the operating-system watch."""
        self._observer.start()
        self._started = True
        logger.info("watching root=%s", self._root)

    def stop(self) -> None:
        """Stop the watch and cancel a pending rebuild."""
        if self._started:
            self._observer.stop()
        if self._rebuild is not None:
            self._rebuild.close()
        if self._started:
            self._observer.join()
            self._started = False


def watch(root: Path, on_change: Callable[[], None] | None = None) -> None:
    """Watch root until Ctrl+C. Pass on_change to rebuild instead of printing events."""
    session = WatchSession(root, on_change)
    session.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        session.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    watch(Path(sys.argv[1]).resolve())

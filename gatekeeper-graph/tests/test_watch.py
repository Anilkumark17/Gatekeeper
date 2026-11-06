import time
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileDeletedEvent, FileModifiedEvent, FileMovedEvent

from gatekeeper_graph.cli import main
from gatekeeper_graph.watcher import RebuildHandler

FIXTURE = Path(__file__).parent / "fixtures" / "sample_subset"
DELAY = 0.05


def _handler(root: Path, calls: list[int]) -> RebuildHandler:
    return RebuildHandler(root, lambda: calls.append(1), delay=DELAY)


def _wait() -> None:
    time.sleep(DELAY + 0.15)


def test_two_modified_events_schedule_one_rebuild(tmp_path: Path) -> None:
    calls: list[int] = []
    handler = _handler(tmp_path, calls)
    source = str(tmp_path / "src" / "main.js")
    try:
        handler.on_any_event(FileModifiedEvent(source))
        handler.on_any_event(FileModifiedEvent(source))
        _wait()
        assert calls == [1]
    finally:
        handler.close()


def test_moved_event_uses_both_paths(tmp_path: Path) -> None:
    calls: list[int] = []
    handler = _handler(tmp_path, calls)
    event = FileMovedEvent(
        str(tmp_path / "node_modules" / "old.js"),
        str(tmp_path / "src" / "new.js"),
    )
    try:
        handler.on_any_event(event)
        _wait()
        assert calls == [1]
    finally:
        handler.close()


def test_deleted_and_created_schedule_one_rebuild(tmp_path: Path) -> None:
    calls: list[int] = []
    handler = _handler(tmp_path, calls)
    try:
        handler.on_any_event(FileDeletedEvent(str(tmp_path / "src" / "old.js")))
        handler.on_any_event(FileCreatedEvent(str(tmp_path / "src" / "new.js")))
        _wait()
        assert calls == [1]
    finally:
        handler.close()


def test_ignored_directory_does_not_schedule_a_rebuild(tmp_path: Path) -> None:
    calls: list[int] = []
    handler = _handler(tmp_path, calls)
    try:
        handler.on_any_event(FileModifiedEvent(str(tmp_path / "node_modules" / "pkg" / "index.js")))
        _wait()
        assert calls == []
    finally:
        handler.close()


def test_source_file_event_ignores_is_directory_flag(tmp_path: Path) -> None:
    calls: list[int] = []
    handler = _handler(tmp_path, calls)
    event = FileModifiedEvent(str(tmp_path / "src" / "main.js"))
    assert event.is_directory is False
    try:
        handler.on_any_event(event)
        _wait()
        assert calls == [1]
    finally:
        handler.close()


def test_watch_refuses_to_write_inside_the_root() -> None:
    assert main(["watch", str(FIXTURE), "--out", str(FIXTURE / "inside.graph.json")]) == 2

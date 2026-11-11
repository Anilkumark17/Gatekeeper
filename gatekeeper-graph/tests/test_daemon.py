import shutil
from pathlib import Path

import pytest

from gatekeeper_graph.cli import main
from gatekeeper_graph.daemon import Daemon
from gatekeeper_graph.llm.fake import FakeClient

SHOP = Path(__file__).parent / "fixtures" / "shop"
_QUESTION = "explain `checkout`"
_CHECKOUT = "src/main.js#checkout"


def _daemon(tmp_path: Path) -> tuple[Daemon, Path]:
    source = tmp_path / "shop"
    shutil.copytree(SHOP, source)
    destination = tmp_path / "out" / "shop.graph.json"
    return Daemon(source, destination, FakeClient([])), source


def test_question_uses_the_graph_outside_the_repo(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    daemon, source = _daemon(tmp_path)
    daemon.rebuild()
    assert daemon.destination.is_file()
    assert not daemon.destination.resolve().is_relative_to(source)
    daemon.answer(_QUESTION)
    assert _CHECKOUT in capsys.readouterr().out
    daemon.rebuild()
    daemon.answer(_QUESTION)
    assert _CHECKOUT in capsys.readouterr().out


def test_quit_stops_before_later_questions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    daemon, _source = _daemon(tmp_path)
    assert daemon.run(["", "quit", _QUESTION], watch_files=False) == 0
    assert _CHECKOUT not in capsys.readouterr().out


def test_daemon_refuses_to_write_inside_the_root() -> None:
    assert main(["daemon", str(SHOP), "--out", str(SHOP / "inside.graph.json")]) == 2

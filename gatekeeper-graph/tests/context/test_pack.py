import json
import shutil
from pathlib import Path

import pytest
from pydantic import BaseModel

from gatekeeper_graph.cli import main
from gatekeeper_graph.context.agent import build_context
from gatekeeper_graph.context.handoff import clear_handlers, register_handler, send_to_diagnosis
from gatekeeper_graph.context.pack import ContextPack, render_markdown
from gatekeeper_graph.llm.stats import CallStats
from tests.context.conftest import GOLDEN, SHOP, groq_configured


class _Scripted:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate_structured[T: BaseModel](
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, CallStats]:
        self.calls.append((system, user))
        if schema.__name__ == "LlmIntentOut":
            payload: dict[str, object] = {
                "problem_type": "bug",
                "observed": "wrong case",
                "expected": None,
                "key_phrases": ["receipt", "letter case"],
                "confidence": "medium",
            }
        else:
            picks = [{"n": number, "reason": "likely involved"} for number in range(1, 9)]
            payload = {"picks": picks}
        return schema.model_validate(payload), _stats()

    def generate_text(self, system: str, user: str) -> tuple[str, CallStats]:
        self.calls.append((system, user))
        return "{}", _stats()

    def is_available(self) -> bool:
        return True


def _stats() -> CallStats:
    return CallStats(
        backend="fake",
        model="fake",
        prompt_tokens=None,
        output_tokens=None,
        total_ms=1.0,
        load_ms=None,
        retries=0,
    )


def test_pack_schema_matches_contract() -> None:
    path = Path("docs/contracts/context.v1.schema.json")
    assert json.loads(path.read_text(encoding="utf-8")) == ContextPack.model_json_schema()


def test_pack_renders_and_cli_prints_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    graph = tmp_path / "shop.graph.json"
    shutil.copyfile(GOLDEN, graph)
    pack = build_context("explain `titleCase`", graph, SHOP, _Scripted())
    text = render_markdown(pack)
    assert "titleCase" in text or "src/utils/string.js#titleCase" in text
    assert "Gaps" in text
    clear_handlers()
    code = main(["context", str(graph), "explain `checkout`", "--root", str(SHOP), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "gatekeeper.context.v1"
    assert any(node["id"] == "src/main.js#checkout" for node in payload["nodes"])


def test_analyse_cli_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyse", str(GOLDEN), "explain `checkout`", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "gatekeeper.analyse.v1"
    assert payload["ok"] is True
    assert payload["route"] == "rules"
    assert "fallback_reason" in payload


def test_handoff_default_and_registered_handler(tmp_path: Path) -> None:
    graph = tmp_path / "shop.graph.json"
    shutil.copyfile(GOLDEN, graph)
    clear_handlers()
    pack = build_context("explain `titleCase`", graph, SHOP, _Scripted())
    seen: list[ContextPack] = []
    register_handler(seen.append)
    send_to_diagnosis(pack, graph)
    assert seen == [pack]
    clear_handlers()
    destination = send_to_diagnosis(pack, graph)
    assert destination.is_file()
    assert json.loads(destination.read_text(encoding="utf-8"))["schema"] == "gatekeeper.context.v1"


@pytest.mark.ollama
def test_groq_receipt_intent() -> None:
    if not groq_configured():
        pytest.skip("Groq is not configured")
    from gatekeeper_graph.context.analyse import analyse
    from gatekeeper_graph.llm import make_client
    from gatekeeper_graph.store import load_graph

    question = "the receipt shows customer names in wrong case"
    result = analyse(question, load_graph(GOLDEN), make_client())
    assert result.intent.problem_type.value == "bug"
    assert any("receipt" in phrase for phrase in result.intent.key_phrases)
    report_path = Path("docs/verification/intent_eval.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(result.intent.model_dump_json(indent=2) + "\n", encoding="utf-8")

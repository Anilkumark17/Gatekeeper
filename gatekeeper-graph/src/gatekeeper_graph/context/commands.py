"""CLI commands for the context agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel, ValidationError

from gatekeeper_graph.context.agent import build_context
from gatekeeper_graph.context.eval_context import evaluate_context
from gatekeeper_graph.context.eval_intent import evaluate_intents, load_labelled
from gatekeeper_graph.context.handoff import send_to_diagnosis
from gatekeeper_graph.context.pack import render_markdown
from gatekeeper_graph.llm.base import LLMClient
from gatekeeper_graph.llm.errors import LLMUnavailable
from gatekeeper_graph.llm.factory import make_client
from gatekeeper_graph.llm.stats import CallStats
from gatekeeper_graph.store import load_graph

_ANALYSE_SCHEMA = "gatekeeper.analyse.v1"


class _Unavailable:
    def generate_structured[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
    ) -> tuple[T, CallStats]:
        raise LLMUnavailable("llm client unavailable")

    def generate_text(self, system: str, user: str) -> tuple[str, CallStats]:
        raise LLMUnavailable("llm client unavailable")

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def is_available(self) -> bool:
        return False


def add_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    analyse = commands.add_parser("analyse", help="classify a question against a graph")
    analyse.add_argument("graph", type=Path)
    analyse.add_argument("question")
    analyse.add_argument("--file", dest="active_file")
    analyse.add_argument("--json", action="store_true")

    intent = commands.add_parser("eval-intent", help="score intent labels")
    intent.add_argument("graph", type=Path)
    intent.add_argument("--set", dest="labelled", type=Path)
    intent.add_argument("--json", action="store_true")

    context = commands.add_parser("context", help="build a context pack for a question")
    context.add_argument("graph", type=Path)
    context.add_argument("question")
    context.add_argument("--root", type=Path, required=True)
    context.add_argument("--file", dest="active_file")
    context.add_argument("--budget", type=int, default=3000)
    context.add_argument("--json", action="store_true")
    context.add_argument("--md", action="store_true")
    context.add_argument("--out", type=Path)
    context.add_argument("--write-index", action="store_true")

    evaluate = commands.add_parser("eval-context", help="score planted context scenarios")
    evaluate.add_argument("fixture", type=Path)
    evaluate.add_argument("--json", action="store_true")


def dispatch(argv: argparse.Namespace) -> int | None:
    if argv.command == "analyse":
        return analyse_command(argv.graph, argv.question, argv.active_file, argv.json)
    if argv.command == "eval-intent":
        return eval_intent_command(argv.graph, argv.labelled, argv.json)
    if argv.command == "context":
        return context_command(argv)
    if argv.command == "eval-context":
        return eval_context_command(argv.fixture, argv.json)
    return None


def analyse_command(graph_path: Path, question: str, active_file: str | None, as_json: bool) -> int:
    from gatekeeper_graph.context.analyse import analyse

    try:
        graph = load_graph(graph_path)
        result = analyse(question, graph, _client(), active_file)
    except (OSError, ValidationError, ValueError) as exc:
        return _fail(str(exc), as_json)
    payload = {
        "schema": _ANALYSE_SCHEMA,
        "ok": True,
        "route": result.route,
        "fallback_reason": result.fallback_reason,
        "stats": None if result.stats is None else result.stats.model_dump(mode="json"),
        "intent": result.intent.model_dump(mode="json"),
    }
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        intent = result.intent
        print(
            f"route={result.route} type={intent.problem_type.value} "
            f"confidence={intent.confidence.value} fallback={result.fallback_reason}"
        )
        print("phrases: " + ", ".join(intent.key_phrases))
    return 0


def context_command(argv: argparse.Namespace) -> int:
    try:
        pack = build_context(
            argv.question,
            argv.graph,
            argv.root,
            _client(),
            argv.active_file,
            argv.budget,
            write_index=argv.write_index,
        )
    except (OSError, ValidationError, ValueError) as exc:
        return _fail(str(exc), argv.json)
    text = pack.model_dump_json(indent=2, by_alias=True)
    if argv.out is not None:
        argv.out.parent.mkdir(parents=True, exist_ok=True)
        argv.out.write_text(text + "\n", encoding="utf-8")
    send_to_diagnosis(pack, argv.graph)
    if argv.json:
        print(text)
    else:
        print(render_markdown(pack))
    return 0


def eval_intent_command(graph_path: Path, labelled: Path | None, as_json: bool) -> int:
    path = labelled or Path("tests/context/labelled_prompts.json")
    try:
        report = evaluate_intents(load_labelled(path), load_graph(graph_path), _client())
    except (OSError, ValidationError, ValueError) as exc:
        return _fail(str(exc), as_json)
    if as_json:
        print(report.model_dump_json(indent=2))
    else:
        print(report.render())
    return 0


def eval_context_command(fixture: Path, as_json: bool) -> int:
    work = fixture.parent / ".eval-context"
    try:
        report = evaluate_context(fixture, _client(), work)
    except (OSError, ValidationError, ValueError) as exc:
        return _fail(str(exc), as_json)
    destination = Path("docs/verification/context_eval.md")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report.render(), encoding="utf-8")
    if as_json:
        print(report.model_dump_json(indent=2))
    else:
        print(report.render())
    return 0


def _client() -> LLMClient:
    try:
        return make_client()
    except (LLMUnavailable, ImportError, ValidationError) as exc:
        print(f"llm client unavailable reason={exc}", file=sys.stderr)
        return _Unavailable()


def _fail(message: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": message}))
    else:
        print(message, file=sys.stderr)
    return 2

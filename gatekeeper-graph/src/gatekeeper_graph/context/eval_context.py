"""Planted-bug recall for the context pack. Mutations stay in a temporary copy."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from gatekeeper_graph.builder import build_graph
from gatekeeper_graph.context.agent import build_context
from gatekeeper_graph.context.pack import ContextPack
from gatekeeper_graph.llm.base import LLMClient
from gatekeeper_graph.store import save_graph


class ScenarioScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    recall: bool
    detail: str
    pack_nodes: int
    tokens: int
    qwen_calls: int
    latency_ms: float


class ContextEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenarios: tuple[ScenarioScore, ...]

    def render(self) -> str:
        lines = ["# Context evaluation", ""]
        for item in self.scenarios:
            lines.append(
                f"- {item.name} recall={item.recall} nodes={item.pack_nodes} "
                f"tokens={item.tokens} qwen_calls={item.qwen_calls} "
                f"ms={item.latency_ms:.1f} {item.detail}"
            )
        lines.append("")
        return "\n".join(lines)


def evaluate_context(fixture: Path, client: LLMClient, work: Path) -> ContextEvalReport:
    """Copy the fixture, plant each bug, and check the pack."""
    scores = [
        _run(work, fixture, client, "wrong-case", _break_title_case, _expect_title_case),
        _run(work, fixture, client, "total-too-high", _break_discount, _expect_discount),
        _run(work, fixture, client, "discount-too-small", _shrink_rate, _expect_rate),
        _run(work, fixture, client, "line-for-throws", _throw_line_for, _expect_line_for),
    ]
    return ContextEvalReport(scenarios=tuple(scores))


def _run(
    work: Path,
    fixture: Path,
    client: LLMClient,
    name: str,
    plant: Callable[[Path], str],
    expect: Callable[[ContextPack], tuple[bool, str]],
) -> ScenarioScore:
    root = work / name
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(fixture, root)
    question = plant(root)
    graph_path = work / f"{name}.graph.json"
    save_graph(build_graph(root).graph, graph_path)
    before = _calls(client)
    started = time.perf_counter()
    pack = build_context(question, graph_path, root, client)
    recall, detail = expect(pack)
    return ScenarioScore(
        name=name,
        recall=bool(recall),
        detail=str(detail),
        pack_nodes=len(pack.nodes),
        tokens=pack.budget.used,
        qwen_calls=_calls(client) - before,
        latency_ms=(time.perf_counter() - started) * 1000,
    )


def _break_title_case(root: Path) -> str:
    path = root / "src" / "utils" / "string.js"
    text = path.read_text(encoding="utf-8").replace("toUpperCase()", "toLowerCase()")
    path.write_text(text, encoding="utf-8")
    return "customer names show in wrong case on the receipt"


def _break_discount(root: Path) -> str:
    path = root / "src" / "math.js"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "return amount - amount * rate;",
            "return amount + amount * rate;",
        ),
        encoding="utf-8",
    )
    return "checkout total is too high"


def _shrink_rate(root: Path) -> str:
    path = root / "src" / "constants.js"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "export const DISCOUNT_RATE = 0.1;",
            "export const DISCOUNT_RATE = 0.01;",
        ),
        encoding="utf-8",
    )
    return "discount looks too small"


def _throw_line_for(root: Path) -> str:
    path = root / "src" / "receipt.js"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "export function lineFor(item) {",
            "export function lineFor(item) {\n"
            '  if (!item.name) { throw new TypeError("missing name"); }',
        ),
        encoding="utf-8",
    )
    rows = path.read_text(encoding="utf-8").splitlines()
    line = next(i for i, row in enumerate(rows, start=1) if "function lineFor" in row)
    return f"TypeError: missing name\nat lineFor (src/receipt.js:{line}:3)"


def _expect_title_case(pack: ContextPack) -> tuple[bool, str]:
    roles = {node.id: node.role for node in pack.nodes}
    role = roles.get("src/utils/string.js#titleCase")
    return role in {"upstream", "anchor", "symptom"}, f"titleCase={role}"


def _expect_discount(pack: ContextPack) -> tuple[bool, str]:
    present = "src/math.js#applyDiscount" in {node.id for node in pack.nodes}
    return present, "applyDiscount" if present else "applyDiscount missing"


def _expect_rate(pack: ContextPack) -> tuple[bool, str]:
    present = "src/constants.js#DISCOUNT_RATE" in {node.id for node in pack.nodes}
    gap = any("references" in gap.detail for gap in pack.gaps)
    if present:
        return True, "DISCOUNT_RATE in pack"
    if gap:
        return True, "missing references edges"
    return False, "DISCOUNT_RATE missing and references edges exist"


def _expect_line_for(pack: ContextPack) -> tuple[bool, str]:
    roles = {node.id: node.role for node in pack.nodes}
    line_role = roles.get("src/receipt.js#lineFor")
    title_role = roles.get("src/utils/string.js#titleCase")
    ok = line_role == "symptom" and title_role == "upstream"
    return ok, f"lineFor={line_role} titleCase={title_role}"


def _calls(client: LLMClient) -> int:
    calls = getattr(client, "calls", None)
    return len(calls) if isinstance(calls, list) else 0

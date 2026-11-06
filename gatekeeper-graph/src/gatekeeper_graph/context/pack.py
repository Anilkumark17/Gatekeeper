"""Context pack contract gatekeeper.context.v1."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from gatekeeper_graph.context.budget import Snippet
from gatekeeper_graph.context.expand import Gap
from gatekeeper_graph.context.intent import Intent
from gatekeeper_graph.llm.stats import CallStats


class PackNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: str
    file: str | None
    range: tuple[int, int] | None
    signature: str
    summary: str | None
    literals: tuple[str, ...]
    role: str
    score: float
    hops: int
    snippet: Snippet | None


class PackEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    source: str = Field(validation_alias=AliasChoices("source", "from"), serialization_alias="from")
    target: str = Field(validation_alias=AliasChoices("target", "to"), serialization_alias="to")
    type: str
    file: str
    line: int


class PackPath(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    source: str = Field(validation_alias=AliasChoices("source", "from"), serialization_alias="from")
    target: str = Field(validation_alias=AliasChoices("target", "to"), serialization_alias="to")
    node_ids: tuple[str, ...]
    edge_types: tuple[str, ...]


class ChangeNote(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    text: str


class PackTests(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mapped: dict[str, tuple[str, ...]]
    failing: tuple[str, ...]


class PackBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int
    used: int


class AnalysisInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route: Literal["llm", "rules"]
    fallback_reason: str | None
    stats: CallStats | None


class ContextPack(BaseModel):
    """What the diagnosis agent receives. The context agent does not diagnose."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_name: Literal["gatekeeper.context.v1"] = Field(
        default="gatekeeper.context.v1",
        alias="schema",
    )
    question: str
    intent: Intent
    analysis: AnalysisInfo
    nodes: tuple[PackNode, ...]
    edges: tuple[PackEdge, ...]
    paths: tuple[PackPath, ...]
    changes: tuple[ChangeNote, ...]
    tests: PackTests
    gaps: tuple[Gap, ...]
    trace: dict[str, tuple[str, ...]]
    budget: PackBudget
    timings_ms: dict[str, float]


def render_markdown(pack: ContextPack) -> str:
    """Render a pack as intent, ranked nodes, paths, snippets, and gaps."""
    lines = [
        "# Context",
        "",
        pack.question,
        "",
        "## Intent",
        "",
        (
            f"{pack.intent.problem_type.value} confidence={pack.intent.confidence.value} "
            f"route={pack.analysis.route}"
        ),
        f"phrases: {', '.join(pack.intent.key_phrases) if pack.intent.key_phrases else 'none'}",
    ]
    if pack.analysis.fallback_reason:
        lines.append(f"fallback: {pack.analysis.fallback_reason}")
    lines.extend(["", "## Nodes", ""])
    for node in pack.nodes:
        span = f"{node.file}:{node.range[0]}" if node.file and node.range else node.file or node.id
        lines.append(f"- {node.id} role={node.role} score={node.score:.3f} {span}")
    lines.extend(["", "## Paths", ""])
    if pack.paths:
        for path in pack.paths:
            arrow = " -> ".join(path.node_ids)
            lines.append(f"- {arrow}")
    else:
        lines.append("- none")
    lines.extend(["", "## Snippets", ""])
    for node in pack.nodes:
        if node.snippet is None:
            continue
        lines.append(f"### {node.id}")
        lines.append(f"```{node.file}:{node.snippet.start}-{node.snippet.end}")
        lines.append(node.snippet.text)
        lines.append("```")
        lines.append("")
    lines.extend(["## Gaps", ""])
    if pack.gaps:
        for gap in pack.gaps:
            lines.append(f"- {gap.kind}: {gap.detail}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)

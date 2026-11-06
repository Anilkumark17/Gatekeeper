import json
from pathlib import Path

from gatekeeper_graph.builder import build_graph
from gatekeeper_graph.llm import FakeClient
from gatekeeper_graph.models import EdgeType, NodeKind
from gatekeeper_graph.search import search
from gatekeeper_graph.summarizer import apply_summaries

FIXTURE = Path(__file__).parent / "fixtures" / "sample_subset"


def test_schema_v2_records_modules_args_references_and_flows() -> None:
    graph = build_graph(FIXTURE).graph
    module = graph.nodes["module:src/math.js"]
    assert graph.version == 2
    assert module.kind is NodeKind.MODULE
    assert module.file == "src/math.js"
    assert "add" in module.tokens
    call = next(
        edge
        for edge in graph.edges
        if edge.type is EdgeType.CALLS
        and edge.target == "src/math.js#applyTax"
        and edge.evidence.line == 8
    )
    assert call.args == ("subtotal", "TAX_RATE")
    assert any(
        edge.type is EdgeType.REFERENCES
        and edge.source == "src/main.js#checkout"
        and edge.target == "src/constants.js#TAX_RATE"
        for edge in graph.edges
    )
    assert any(
        edge.type is EdgeType.FLOWS_INTO
        and edge.source == "src/constants.js#TAX_RATE"
        and edge.target == "src/math.js#applyTax"
        for edge in graph.edges
    )
    assert "src/utils/string.js#titleCase" in search(graph, "titleCase")
    assert "module:src/math.js" in search(graph, "math")


def test_file_summary_is_built_from_symbol_summaries(tmp_path: Path) -> None:
    source = tmp_path / "src" / "math.js"
    source.parent.mkdir(parents=True)
    source.write_text("export function add(a, b) {\n  return a + b;\n}\n", encoding="utf-8")
    graph = build_graph(tmp_path).graph
    texts = ("Adds two numbers.", "Math helpers.", "Math module.")
    client = FakeClient([json.dumps({"summary": text}) for text in texts])
    stats = apply_summaries(graph, tmp_path, client, None)
    assert stats.written == 3
    assert graph.nodes["src/math.js#add"].summary == "Adds two numbers."
    assert "Adds two numbers." in client.calls[1][1]
    assert graph.nodes["src/math.js"].summary == "Math helpers."
    assert "Math helpers." in client.calls[2][1]
    assert graph.nodes["module:src/math.js"].summary == "Math module."
    assert "math" in graph.search

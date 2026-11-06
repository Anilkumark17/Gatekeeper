from pathlib import Path

from gatekeeper_graph.builder import build_graph
from gatekeeper_graph.cli import main
from gatekeeper_graph.models import EdgeType

FIXTURE = Path(__file__).parent / "fixtures" / "sample_subset"


def test_sample_subset_links_checkout_calls() -> None:
    result = build_graph(FIXTURE)
    edges = {
        (edge.type, edge.source, edge.target, edge.evidence.line) for edge in result.graph.edges
    }
    assert (EdgeType.CALLS, "src/main.js#checkout", "src/math.js#add", 7) in edges
    assert (EdgeType.CALLS, "src/main.js#checkout", "src/math.js#applyTax", 8) in edges
    assert (EdgeType.CALLS, "src/main.js#checkout", "src/format.js#formatMoney", 9) in edges
    assert (EdgeType.CALLS, "src/main.js#checkout", "src/utils/string.js#titleCase", 9) in edges
    assert (EdgeType.IMPORTS, "src/main.js", "src/utils/index.js", 4) in edges
    assert (EdgeType.IMPORTS, "src/utils/index.js", "src/utils/string.js", 1) in edges
    assert any(
        edge.type is EdgeType.UNRESOLVED
        and edge.source == "src/main.js#loadExtra"
        and edge.raw == "import(./math.js)"
        and edge.evidence.line == 12
        for edge in result.graph.edges
    )
    assert "src/main.js#checkout" in result.graph.reverse["src/utils/string.js#titleCase"]


def test_cli_build_writes_outside_the_fixture(tmp_path: Path) -> None:
    destination = tmp_path / "sample_subset.graph.json"
    assert main(["build", str(FIXTURE), "--out", str(destination)]) == 0
    assert destination.is_file()
    assert main(["build", str(FIXTURE), "--out", str(FIXTURE / "inside.graph.json")]) == 2

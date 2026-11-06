import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
CITATION = re.compile(r"`([^`\s]+\.(?:js|jsx|json)):(\d+)`")


@pytest.mark.parametrize(
    ("inventory_name", "root_name"),
    [
        ("sample_inventory.md", "sample_subset"),
        ("react_mini_inventory.md", "react_mini"),
    ],
)
def test_inventory_citations_resolve(inventory_name: str, root_name: str) -> None:
    text = (FIXTURES / inventory_name).read_text(encoding="utf-8")
    root = FIXTURES / root_name
    citations = CITATION.findall(text)
    assert citations
    for relative, line_text in citations:
        path = root / relative
        assert path.is_file(), relative
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        line = int(line_text)
        assert 1 <= line <= line_count, f"{relative}:{line} length={line_count}"

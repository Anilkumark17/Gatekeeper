import shutil
from collections.abc import Callable
from pathlib import Path

from gatekeeper_graph.builder import build_graph
from gatekeeper_graph.graph_diff import GraphDiff, diff_graphs
from gatekeeper_graph.models import Graph

SHOP = Path(__file__).parent / "fixtures" / "shop"
TITLE = "src/utils/string.js#titleCase"
DISCOUNT = "src/math.js#applyDiscount"


def _graphs(tmp_path: Path, edit: Callable[[Path], None] | None) -> tuple[Graph, Graph]:
    source = tmp_path / "shop"
    shutil.copytree(SHOP, source)
    before = build_graph(source).graph
    if edit is not None:
        edit(source)
    return before, build_graph(source).graph


def _replace(root: Path, relative: str, old: str, new: str) -> None:
    path = root / relative
    path.write_text(path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")


def _assert_empty(diff: GraphDiff) -> None:
    assert diff.added == ()
    assert diff.removed == ()
    assert diff.modified == ()
    assert diff.renamed == ()
    assert diff.signature_changed == ()
    assert diff.edges_added == ()
    assert diff.edges_removed == ()
    assert diff.seeds == ()


def test_body_change_marks_only_that_symbol(tmp_path: Path) -> None:
    before, after = _graphs(
        tmp_path,
        lambda root: _replace(root, "src/utils/string.js", "toUpperCase", "toLowerCase"),
    )
    diff = diff_graphs(before, after)
    assert diff.modified == (TITLE,)
    assert diff.signature_changed == ()


def test_line_shift_is_empty(tmp_path: Path) -> None:
    def edit(root: Path) -> None:
        path = root / "src/utils/string.js"
        path.write_text("\n" + path.read_text(encoding="utf-8"), encoding="utf-8")

    before, after = _graphs(tmp_path, edit)
    _assert_empty(diff_graphs(before, after))


def test_rename_is_not_added_or_removed(tmp_path: Path) -> None:
    before, after = _graphs(
        tmp_path,
        lambda root: _replace(
            root,
            "src/utils/string.js",
            "function titleCase",
            "function toTitle",
        ),
    )
    diff = diff_graphs(before, after)
    pair = (TITLE, "src/utils/string.js#toTitle")
    assert pair in diff.renamed
    assert TITLE not in diff.added
    assert TITLE not in diff.removed
    assert pair[1] not in diff.added
    assert pair[1] not in diff.removed


def test_signature_change_is_recorded(tmp_path: Path) -> None:
    before, after = _graphs(
        tmp_path,
        lambda root: _replace(
            root,
            "src/math.js",
            "function applyDiscount(amount, rate)",
            "function applyDiscount(amount, rate, extra)",
        ),
    )
    diff = diff_graphs(before, after)
    assert DISCOUNT in diff.signature_changed
    assert DISCOUNT in diff.modified


def test_deleted_function_removes_its_edges(tmp_path: Path) -> None:
    before, after = _graphs(
        tmp_path,
        lambda root: _replace(
            root,
            "src/utils/string.js",
            "export function titleCase(value) {\n"
            "  return value.replace(/\\b\\w/g, (char) => char.toUpperCase());\n"
            "}\n",
            "",
        ),
    )
    diff = diff_graphs(before, after)
    touched = {
        (edge.source, edge.target, edge.type.value)
        for edge in before.edges
        if edge.source == TITLE or edge.target == TITLE
    }
    assert TITLE in diff.removed
    assert touched <= set(diff.edges_removed)


def test_unchanged_graphs_are_empty(tmp_path: Path) -> None:
    before, after = _graphs(tmp_path, None)
    _assert_empty(diff_graphs(before, after))

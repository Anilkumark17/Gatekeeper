import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from gatekeeper_graph.context.budget import apply_budget, source_snippet
from gatekeeper_graph.context.expand import expand
from gatekeeper_graph.context.graph_index import GraphIndex
from gatekeeper_graph.context.intent import Confidence, Intent, ProblemType, StackFrame
from gatekeeper_graph.context.rank import rank, shared_ancestor_fraction
from gatekeeper_graph.context.search import SearchIndex
from gatekeeper_graph.context.select import select
from gatekeeper_graph.context.shortlist import Candidate, build_shortlist
from gatekeeper_graph.llm import FakeClient
from gatekeeper_graph.llm.errors import LLMUnavailable
from gatekeeper_graph.llm.stats import CallStats
from gatekeeper_graph.models import Edge, EdgeType, Evidence, Graph, LineRange, Node, NodeKind
from gatekeeper_graph.store import load_graph
from tests.context.conftest import GOLDEN, SHOP

_TITLE = "src/utils/string.js#titleCase"
_LINE = "src/receipt.js#lineFor"
_LINES = "src/receipt.js#receiptLines"
_HEADER = "src/summary.js#header"
_CHECKOUT = "src/main.js#checkout"


def _intent(**overrides: object) -> Intent:
    payload: dict[str, object] = {
        "question": "receipt names wrong case",
        "problem_type": ProblemType.BUG,
        "confidence": Confidence.LOW,
        "source": "rules",
        "key_phrases": ("receipt", "names", "wrong", "case"),
    }
    payload.update(overrides)
    return Intent.model_validate(payload)


def test_node_at_and_title_case_callers() -> None:
    index = GraphIndex.from_file(GOLDEN)
    node = index.node_at("src/receipt.js", 4)
    assert node is not None
    assert node.id == _LINE
    callers = sorted(edge.source for edge in index.incoming(_TITLE, [EdgeType.CALLS]))
    assert callers == [_CHECKOUT, _LINE, _HEADER]
    assert _TITLE in index.find("title case")


def test_search_queries() -> None:
    index = SearchIndex.build(load_graph(GOLDEN))
    letter = [hit.node_id for hit in index.search("letter case", k=3)]
    receipt = [hit.node_id for hit in index.search("receipt line", k=3)]
    discount = {hit.node_id for hit in index.search("discount")}
    assert _TITLE in letter
    assert _LINE in receipt
    assert _LINES in receipt
    assert "src/math.js#applyDiscount" in discount
    assert "src/constants.js#DISCOUNT_RATE" in discount
    assert index.search("") == []
    assert index.search("a the") == []


def test_shortlist_pins_and_vague_bug() -> None:
    graph = load_graph(GOLDEN)
    index = GraphIndex(graph)
    search = SearchIndex.build(graph)
    framed = _intent(
        frames=(StackFrame(name="lineFor", file="src/receipt.js", line=4),),
        files=("src/receipt.js",),
    )
    frame_list = build_shortlist(framed, index, search)
    pinned = next(item for item in frame_list if item.node_id == _LINE)
    assert pinned.pinned
    assert "frame" in pinned.sources
    named = _intent(backtick_names=("titleCase",), key_phrases=())
    name_list = build_shortlist(named, index, search)
    title = next(item for item in name_list if item.node_id == _TITLE)
    assert title.pinned
    assert "backtick" in title.sources
    vague = {item.node_id for item in build_shortlist(_intent(), index, search)}
    assert {_LINE, _LINES, _TITLE} <= vague


def test_selection_drops_out_of_range_and_keeps_pins() -> None:
    graph = load_graph(GOLDEN)
    index = GraphIndex(graph)
    search = SearchIndex.build(graph)
    intent = _intent(backtick_names=("titleCase",), confidence=Confidence.LOW, source="llm")
    candidates = build_shortlist(intent, index, search)
    raw = json.dumps({"picks": [{"n": 1, "reason": "first"}, {"n": 99, "reason": "nope"}]})
    client = FakeClient([raw])
    chosen = select(intent, candidates, index, client, "llm")
    ids = [item.node_id for item in chosen.anchors]
    assert _TITLE in ids
    assert chosen.fallback_reason is None
    known = {candidate.node_id for candidate in candidates}
    assert all(item.node_id in known for item in chosen.anchors)


def test_selection_skips_rules_and_falls_back() -> None:
    graph = load_graph(GOLDEN)
    index = GraphIndex(graph)
    named = _intent(backtick_names=("titleCase",))
    candidates = build_shortlist(named, index, SearchIndex.build(graph))
    explicit = _intent(backtick_names=("titleCase",), confidence=Confidence.HIGH, source="rules")
    skipped = select(explicit, candidates, index, FakeClient([]), "rules")
    assert skipped.stats is None
    assert skipped.anchors
    vague = _intent(source="llm", confidence=Confidence.MEDIUM, key_phrases=())
    long_list = [
        Candidate(
            node_id=f"src/wide.js#f{i}",
            score=1.0 - i / 10,
            sources=frozenset({"phrase"}),
            pinned=False,
        )
        for i in range(8)
    ]
    down = FakeClient([LLMUnavailable("down")])
    failed = select(vague, long_list, index, down, "llm")
    assert failed.fallback_reason is not None
    assert all(item.via in {"pinned", "score"} for item in failed.anchors)


def test_expansion_policies_and_cap() -> None:
    index = GraphIndex(load_graph(GOLDEN))
    bug, _gaps = expand(ProblemType.BUG, Confidence.HIGH, [_LINE], index)
    assert bug.nodes[_TITLE].direction == "upstream"
    impact, _gaps = expand(ProblemType.IMPACT, Confidence.HIGH, [_TITLE], index)
    assert {_LINE, _HEADER, _CHECKOUT} <= set(impact.nodes)
    explain, _gaps = expand(ProblemType.EXPLAIN, Confidence.HIGH, [_TITLE], index)
    assert _LINE in explain.nodes
    assert _LINES not in explain.nodes
    wide = GraphIndex(_wide_graph(150))
    capped, _gaps = expand(ProblemType.BUG, Confidence.HIGH, ["src/wide.js#f000"], wide)
    assert len(capped.nodes) == 120


def test_rank_prefers_title_case_and_shared_ancestors() -> None:
    graph = load_graph(GOLDEN)
    index = GraphIndex(graph)
    intent = _intent()
    search = SearchIndex.build(graph)
    shortlist = build_shortlist(intent, index, search)
    anchors = [
        item
        for item in select(intent, shortlist, index, FakeClient([]), "rules").anchors
    ]
    anchor_ids = [item.node_id for item in anchors]
    expansion, _gaps = expand(intent.problem_type, intent.confidence, anchor_ids, index)
    ranked = rank(intent, anchors, shortlist, expansion, index, set())
    scores = {item.node_id: item.score for item in ranked}
    assert scores[_TITLE] > scores["src/math.js"]
    fraction = shared_ancestor_fraction(_TITLE, [_LINE, _HEADER], index)
    assert fraction == 1
    assert shared_ancestor_fraction("src/math.js#multiply", [_LINE, _HEADER], index) == 0
    tied = sorted(ranked, key=lambda item: (-item.score, item.node_id))
    assert [item.node_id for item in tied] == [item.node_id for item in ranked]


def test_budget_keeps_anchors_and_truncates(tmp_path: Path) -> None:
    graph = load_graph(GOLDEN)
    index = GraphIndex(graph)
    intent = _intent(frames=(StackFrame(name="lineFor", file="src/receipt.js", line=4),))
    shortlist = build_shortlist(intent, index, SearchIndex.build(graph))
    chosen = select(intent, shortlist, index, FakeClient([]), "rules")
    anchor_ids = [item.node_id for item in chosen.anchors]
    expansion, _gaps = expand(intent.problem_type, Confidence.HIGH, anchor_ids, index)
    ranked = rank(intent, list(chosen.anchors), shortlist, expansion, index, set())
    ranges = {
        node_id: (node.file, node.range.start, node.range.end)
        for node_id, node in graph.nodes.items()
        if node.file is not None and node.range is not None
    }
    required = {item.node_id for item in chosen.anchors}
    kept, dropped, _used = apply_budget(
        ranked, SHOP, ranges, limit=80, overhead=0, required=required
    )
    kept_ids = {item.node_id for item in kept}
    assert required <= kept_ids
    assert not (set(dropped) & kept_ids)
    snippet = source_snippet(SHOP, "src/receipt.js", 3, 5)
    assert snippet is not None
    source = (SHOP / "src/receipt.js").read_text(encoding="utf-8").splitlines()
    assert snippet.text == "\n".join(source[2:5])
    body = "\n".join(f"line {index}" for index in range(1, 51))
    (tmp_path / "long.js").write_text(body, encoding="utf-8")
    truncated = source_snippet(tmp_path, "long.js", 1, 50)
    assert truncated is not None
    assert "… 10 lines omitted …" in truncated.text


def test_select_prompt_uses_only_supplied_numbers() -> None:
    class Recording(FakeClient):
        def generate_structured[T: BaseModel](
            self,
            system: str,
            user: str,
            schema: type[T],
        ) -> tuple[T, CallStats]:
            return super().generate_structured(system, user, schema)

    graph = load_graph(GOLDEN)
    intent = _intent(source="llm", confidence=Confidence.MEDIUM, key_phrases=("receipt", "case"))
    candidates = build_shortlist(intent, GraphIndex(graph), SearchIndex.build(graph))
    if len(candidates) <= 5:
        pytest.skip("shortlist is already small")
    client = FakeClient([json.dumps({"picks": [{"n": 1, "reason": "closest"}]})])
    select(intent, candidates, GraphIndex(graph), client, "llm")
    assert "1." in client.calls[0][1]


def _wide_graph(count: int) -> Graph:
    nodes = {
        "src/wide.js": Node(id="src/wide.js", kind=NodeKind.FILE, file="src/wide.js", hash="h"),
    }
    edges: list[Edge] = []
    for index in range(count + 1):
        node_id = f"src/wide.js#f{index:03d}"
        nodes[node_id] = Node(
            id=node_id,
            kind=NodeKind.FUNCTION,
            file="src/wide.js",
            range=LineRange(start=index + 1, end=index + 1),
            hash=f"h{index}",
        )
        if index:
            edges.append(
                Edge(
                    source="src/wide.js#f000",
                    target=node_id,
                    type=EdgeType.CALLS,
                    evidence=Evidence(file="src/wide.js", line=1),
                )
            )
    return Graph(root="<fixture>", nodes=nodes, edges=edges)

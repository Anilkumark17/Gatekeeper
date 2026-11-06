import os
from pathlib import Path

from gatekeeper_graph.builder import build_graph
from gatekeeper_graph.models import graph_to_json
from gatekeeper_graph.search import build_search_index
from gatekeeper_graph.store import load_graph, save_graph

SHOP = Path(__file__).parent / "fixtures" / "shop"
GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "shop.graph.json"


def test_shop_golden_root_is_normalized() -> None:
    built = build_graph(SHOP).graph
    built.root = "<fixture>"
    built.search = build_search_index(built)
    if os.environ.get("GATEKEEPER_UPDATE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        save_graph(built, GOLDEN)
    saved = load_graph(GOLDEN)
    assert saved.root == "<fixture>"
    assert graph_to_json(saved) == graph_to_json(built)

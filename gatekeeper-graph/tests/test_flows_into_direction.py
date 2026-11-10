"""flows_into points value -> consumer. Dependency walks must treat it as consumer -> value."""

from pathlib import Path

import pytest

from gatekeeper_graph.builder import build_graph
from gatekeeper_graph.context.expand import expand
from gatekeeper_graph.context.graph_index import GraphIndex
from gatekeeper_graph.context.intent import Confidence, ProblemType
from gatekeeper_graph.reverse_index import dependents

SHOP = Path(__file__).parent / "fixtures" / "shop"
RATE = "src/constants.js#DISCOUNT_RATE"
APPLY = "src/math.js#applyDiscount"
CHECKOUT = "src/main.js#checkout"


@pytest.fixture(scope="module")
def index() -> GraphIndex:
    return GraphIndex(build_graph(SHOP).graph)


def test_constant_is_not_a_dependent_of_its_consumer(index: GraphIndex) -> None:
    assert RATE not in dependents(index.graph, APPLY)
    assert RATE not in index.dependents(APPLY)


def test_consumer_is_a_dependent_of_the_constant(index: GraphIndex) -> None:
    assert APPLY in dependents(index.graph, RATE)
    assert APPLY in index.dependents(RATE)
    assert CHECKOUT in index.dependents(RATE)


def test_bug_expansion_reaches_constant_upstream_of_consumer(index: GraphIndex) -> None:
    expansion, _gaps = expand(ProblemType.BUG, Confidence.HIGH, [APPLY], index)
    reach = expansion.nodes[RATE]
    assert reach.direction == "upstream"
    assert reach.hops == 1
    assert reach.via_edge_type == "flows_into"

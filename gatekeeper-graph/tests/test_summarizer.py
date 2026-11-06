import hashlib
import json
from pathlib import Path

from gatekeeper_graph.llm import FakeClient
from gatekeeper_graph.llm.errors import LLMUnavailable
from gatekeeper_graph.models import Graph, LineRange, Node, NodeKind
from gatekeeper_graph.summarizer import apply_summaries


def _symbol(content_hash: str, summary: str | None = None, summary_hash: str | None = None) -> Node:
    return Node(
        id="src/math.js#add",
        kind=NodeKind.FUNCTION,
        file="src/math.js",
        range=LineRange(start=1, end=2),
        hash=content_hash,
        summary=summary,
        summary_hash=summary_hash,
    )


def _graph(root: Path, content_hash: str, summary: str | None = None) -> Graph:
    summary_hash = hashlib.sha256(summary.encode("utf-8")).hexdigest() if summary else None
    file_node = Node(id="src/math.js", kind=NodeKind.FILE, file="src/math.js")
    return Graph(
        root=root.as_posix(),
        nodes={
            "src/math.js": file_node,
            "src/math.js#add": _symbol(content_hash, summary, summary_hash),
        },
    )


def _source(root: Path) -> None:
    path = root / "src" / "math.js"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("export function add(a, b) {\n  return a + b;\n}\n", encoding="utf-8")


def _summary(text: str) -> str:
    return json.dumps({"summary": text})


def test_queued_summary_is_stored(tmp_path: Path) -> None:
    _source(tmp_path)
    graph = _graph(tmp_path, "hash-1")
    client = FakeClient([_summary("Adds two numbers.")])
    stats = apply_summaries(graph, tmp_path, client, None)
    node = graph.nodes["src/math.js#add"]
    assert stats.written == 1
    assert node.summary == "Adds two numbers."
    assert node.summary_hash == hashlib.sha256(b"Adds two numbers.").hexdigest()
    assert node.stale is False
    assert graph.nodes["src/math.js"].summary is None
    assert "src/math.js#add" in client.calls[0][1]


def test_unchanged_hash_does_not_call_the_client(tmp_path: Path) -> None:
    _source(tmp_path)
    previous = _graph(tmp_path, "hash-1", "Adds two numbers.")
    graph = _graph(tmp_path, "hash-1")
    client = FakeClient([])
    stats = apply_summaries(graph, tmp_path, client, previous)
    assert stats.reused == 1
    assert stats.written == 0
    assert client.calls == []
    assert graph.nodes["src/math.js#add"].summary == "Adds two numbers."
    assert graph.nodes["src/math.js#add"].stale is False


def test_changed_hash_requests_a_new_summary(tmp_path: Path) -> None:
    _source(tmp_path)
    previous = _graph(tmp_path, "hash-1", "Adds two numbers.")
    graph = _graph(tmp_path, "hash-2")
    client = FakeClient([_summary("Adds two numbers and returns the total.")])
    stats = apply_summaries(graph, tmp_path, client, previous)
    assert stats.written == 1
    assert len(client.calls) == 1
    assert graph.nodes["src/math.js#add"].summary == "Adds two numbers and returns the total."


def test_unavailable_client_keeps_the_previous_summary(tmp_path: Path) -> None:
    _source(tmp_path)
    previous = _graph(tmp_path, "hash-1", "Adds two numbers.")
    graph = _graph(tmp_path, "hash-2")
    client = FakeClient([LLMUnavailable("down")])
    stats = apply_summaries(graph, tmp_path, client, previous)
    node = graph.nodes["src/math.js#add"]
    assert stats.skipped == 1
    assert node.summary == "Adds two numbers."
    assert node.stale is True
    assert "src/math.js#add" in graph.nodes
    assert "src/math.js" in graph.nodes

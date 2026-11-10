"""In-memory lookups over one graph."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from gatekeeper_graph.models import Edge, EdgeType, Graph, Node, NodeKind, parse_node_id
from gatekeeper_graph.reverse_index import DEPENDENCY_TYPES, dependency_ends
from gatekeeper_graph.store import load_graph

_SYMBOL_KINDS = frozenset(NodeKind) - {NodeKind.FILE, NodeKind.EXTERNAL, NodeKind.MODULE}


def _edge_order(edge: Edge) -> tuple[str, str, int]:
    return (edge.target, edge.type.value, edge.evidence.line)
_NAME_PART = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


class GraphIndex:
    """Precomputed node, edge, name, and line lookups."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self._by_file: dict[str, list[str]] = defaultdict(list)
        self._by_kind: dict[NodeKind, list[str]] = defaultdict(list)
        self._out: dict[str, list[Edge]] = defaultdict(list)
        self._in: dict[str, list[Edge]] = defaultdict(list)
        self._exact: dict[str, list[str]] = defaultdict(list)
        self._lower: dict[str, list[str]] = defaultdict(list)
        self._tokens: dict[str, tuple[str, ...]] = {}
        for node_id, node in graph.nodes.items():
            self._by_kind[node.kind].append(node_id)
            if node.file is not None:
                self._by_file[node.file].append(node_id)
            if node.kind not in _SYMBOL_KINDS:
                continue
            _category, _path, name = parse_node_id(node_id)
            if name is None:
                continue
            self._exact[name].append(node_id)
            self._lower[name.lower()].append(node_id)
            self._tokens[node_id] = tuple(part.lower() for part in _NAME_PART.findall(name))
        for values in self._by_file.values():
            values.sort()
        for values in self._by_kind.values():
            values.sort()
        for values in self._exact.values():
            values.sort()
        for values in self._lower.values():
            values.sort()

        for edge in graph.edges:
            self._out[edge.source].append(edge)
            self._in[edge.target].append(edge)
        for edges in self._out.values():
            edges.sort(key=_edge_order)
        for edges in self._in.values():
            edges.sort(key=_edge_order)

    @classmethod
    def from_file(cls, path: Path) -> GraphIndex:
        return cls(load_graph(path))

    def get(self, node_id: str) -> Node | None:
        return self.graph.nodes.get(node_id)

    def in_file(self, file: str) -> list[Node]:
        return [self.graph.nodes[node_id] for node_id in self._by_file.get(file, [])]

    def symbols_in_file(self, file: str) -> list[Node]:
        return [node for node in self.in_file(file) if node.kind in _SYMBOL_KINDS]

    def find(self, name: str) -> list[str]:
        """Exact, then case-insensitive, then word, then substring. Symbols only."""
        query = name.strip()
        if not query:
            return []
        found: list[str] = []
        seen: set[str] = set()

        def add(ids: Iterable[str]) -> None:
            for node_id in ids:
                if node_id not in seen:
                    seen.add(node_id)
                    found.append(node_id)

        add(self._exact.get(query, []))
        add(self._lower.get(query.lower(), []))
        query_tokens = [part.lower() for part in _NAME_PART.findall(query)]
        if query_tokens:
            word_hits = [
                node_id
                for node_id, tokens in self._tokens.items()
                if all(token in tokens for token in query_tokens)
            ]
            add(sorted(word_hits))
        compact = re.sub(r"[^a-z0-9]", "", query.lower())
        if compact:
            substr = []
            for node_id in self._tokens:
                bare = parse_node_id(node_id)[2] or ""
                if compact in re.sub(r"[^a-z0-9]", "", bare.lower()):
                    substr.append(node_id)
            add(sorted(substr))
        return found

    def exact(self, name: str) -> list[str]:
        return list(self._exact.get(name, [])) or list(self._lower.get(name.lower(), []))

    def outgoing(self, node_id: str, types: Iterable[EdgeType]) -> list[Edge]:
        allowed = set(types)
        return [edge for edge in self._out.get(node_id, []) if edge.type in allowed]

    def incoming(self, node_id: str, types: Iterable[EdgeType]) -> list[Edge]:
        allowed = set(types)
        return [edge for edge in self._in.get(node_id, []) if edge.type in allowed]

    def dependencies(self, node_id: str, types: Iterable[EdgeType]) -> list[tuple[Edge, str]]:
        """Nodes this node depends on, as (edge, neighbour). Direction-safe for flows_into."""
        allowed = set(types)
        edges = [*self._out.get(node_id, []), *self._in.get(node_id, [])]
        found: list[tuple[Edge, str]] = []
        for edge in edges:
            if edge.type not in allowed:
                continue
            dependent, dependency = dependency_ends(edge)
            if dependent == node_id and dependency != node_id:
                found.append((edge, dependency))
        found.sort(key=lambda item: (item[1], *_edge_order(item[0])))
        return found

    def users(self, node_id: str, types: Iterable[EdgeType]) -> list[tuple[Edge, str]]:
        """Nodes that depend on this node, as (edge, neighbour). Direction-safe for flows_into."""
        allowed = set(types)
        edges = [*self._out.get(node_id, []), *self._in.get(node_id, [])]
        found: list[tuple[Edge, str]] = []
        for edge in edges:
            if edge.type not in allowed:
                continue
            dependent, dependency = dependency_ends(edge)
            if dependency == node_id and dependent != node_id:
                found.append((edge, dependent))
        found.sort(key=lambda item: (item[1], *_edge_order(item[0])))
        return found

    def dependents(self, node_id: str, transitive: bool = False) -> list[str]:
        direct = sorted({user for _edge, user in self.users(node_id, DEPENDENCY_TYPES)})
        if not transitive:
            return direct
        seen = {node_id}
        ordered: list[str] = []
        stack = list(direct)
        while stack:
            current = stack.pop(0)
            if current in seen:
                continue
            seen.add(current)
            ordered.append(current)
            stack.extend(self.dependents(current, transitive=False))
        return sorted(ordered)

    def node_at(self, file: str, line: int) -> Node | None:
        """Innermost symbol whose range contains the line, or the file node."""
        containing: list[tuple[int, int, str, Node]] = []
        for node in self.symbols_in_file(file):
            span = node.range
            if span is not None and span.start <= line <= span.end:
                containing.append((span.end - span.start, span.start, node.id, node))
        if containing:
            containing.sort()
            return containing[0][3]
        return self.get(file)

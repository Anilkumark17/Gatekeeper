"""Generic tree-sitter node helpers. Line numbers are 1-based."""

from __future__ import annotations

from collections.abc import Iterator

from tree_sitter import Node


def line_of(node: Node) -> int:
    return node.start_point[0] + 1


def end_line_of(node: Node) -> int:
    return node.end_point[0] + 1


def text_of(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def walk(node: Node) -> Iterator[Node]:
    """Pre-order walk using a cursor so deep trees do not recurse."""
    cursor = node.walk()
    if cursor.node is None:
        return
    while True:
        current = cursor.node
        if current is not None:
            yield current
        if cursor.goto_first_child():
            continue
        while True:
            if cursor.node == node:
                return
            if cursor.goto_next_sibling():
                break
            if not cursor.goto_parent():
                return


def find_all(node: Node, *types: str) -> list[Node]:
    wanted = set(types)
    return [item for item in walk(node) if item.type in wanted]


def field_text(node: Node, field: str, source: bytes) -> str | None:
    child = node.child_by_field_name(field)
    if child is None:
        return None
    return text_of(child, source)

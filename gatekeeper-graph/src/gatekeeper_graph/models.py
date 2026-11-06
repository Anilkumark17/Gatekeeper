"""Graph contract shared by the extractor, resolver, builder, and store."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal, Self

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

SYMBOL_SEP = "#"
EXTERNAL_PREFIX = "external:"
GRAPH_SCHEMA_VERSION = 1

NodeCategory = Literal["file", "symbol", "external"]


class NodeKind(StrEnum):
    FILE = "file"
    COMPONENT = "component"
    HOOK = "hook"
    FUNCTION = "function"
    TYPE = "type"
    CONSTANT = "constant"
    ROUTE = "route"
    TEST = "test"
    EXTERNAL = "external"


class EdgeType(StrEnum):
    IMPORTS = "imports"
    RENDERS = "renders"
    CALLS = "calls"
    USES_HOOK = "uses_hook"
    PASSES_PROP = "passes_prop"
    READS_CONTEXT = "reads_context"
    PROVIDES_CONTEXT = "provides_context"
    TESTED_BY = "tested_by"
    CONTAINS = "contains"
    UNRESOLVED = "unresolved"


_SYMBOL_KINDS = frozenset(NodeKind) - {NodeKind.FILE, NodeKind.EXTERNAL}


def make_file_id(path: str) -> str:
    """Return a stable repo-relative POSIX file id."""
    if not path or path.strip() != path:
        raise ValueError(f"file id must be non-empty path={path!r}")
    if "\\" in path or path.startswith("/") or ":" in path:
        raise ValueError(f"file id must be relative POSIX path={path!r}")
    if any(part == ".." for part in path.split("/")):
        raise ValueError(f"file id must not contain '..' path={path!r}")
    return path


def make_symbol_id(path: str, name: str) -> str:
    """Return ``path#name`` for a symbol declared in path."""
    file_id = make_file_id(path)
    if not name or any(char in name for char in ("#", "/", " ", "\t")):
        raise ValueError(f"symbol name is invalid name={name!r}")
    return f"{file_id}{SYMBOL_SEP}{name}"


def make_external_id(package: str) -> str:
    """Return ``external:package``. Scoped package names are allowed."""
    if not package or any(char.isspace() for char in package):
        raise ValueError(f"package name is invalid package={package!r}")
    if package.startswith("@"):
        scope, separator, name = package.partition("/")
        if separator != "/" or not scope[1:] or not name or "/" in name:
            raise ValueError(f"package name is invalid package={package!r}")
    elif "/" in package:
        raise ValueError(f"package name is invalid package={package!r}")
    return f"{EXTERNAL_PREFIX}{package}"


def parse_node_id(node_id: str) -> tuple[NodeCategory, str, str | None]:
    """Split a node id into file, symbol, or external parts."""
    if node_id.startswith(EXTERNAL_PREFIX):
        package = node_id[len(EXTERNAL_PREFIX) :]
        if not package:
            raise ValueError(f"external id is missing a package node_id={node_id!r}")
        return ("external", package, None)
    if SYMBOL_SEP in node_id:
        path, name = node_id.split(SYMBOL_SEP, 1)
        if not name:
            raise ValueError(f"symbol id is missing a name node_id={node_id!r}")
        return ("symbol", make_file_id(path), name)
    return ("file", make_file_id(node_id), None)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str
    line: int = Field(ge=1)

    @field_validator("file")
    @classmethod
    def _file_id(cls, value: str) -> str:
        return make_file_id(value)


class LineRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: int = Field(ge=1)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def _order(self) -> Self:
        if self.start > self.end:
            raise ValueError(f"range start={self.start} is after end={self.end}")
        return self


class Signature(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    props: tuple[str, ...] = ()
    params: tuple[str, ...] = ()
    returns: str | None = None


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: NodeKind
    file: str | None = None
    range: LineRange | None = None
    hash: str | None = None
    signature: Signature = Field(default_factory=Signature)
    summary: str | None = None
    summary_hash: str | None = None
    stale: bool = True

    @model_validator(mode="after")
    def _shape(self) -> Self:
        category, path, name = parse_node_id(self.id)
        if self.summary_hash is not None and self.summary is None:
            raise ValueError(f"summary_hash requires summary id={self.id}")
        if self.kind is NodeKind.FILE:
            if category != "file" or self.file != self.id:
                raise ValueError(f"file node file must equal id id={self.id}")
            return self
        if self.kind is NodeKind.EXTERNAL:
            if category != "external" or self.file is not None or self.range is not None:
                raise ValueError(f"external node must not carry file data id={self.id}")
            if self.hash is not None:
                raise ValueError(f"external node must not carry a hash id={self.id}")
            return self
        if self.kind not in _SYMBOL_KINDS or category != "symbol" or name is None:
            raise ValueError(f"symbol node id is invalid id={self.id} kind={self.kind}")
        if self.file != path or self.range is None or self.hash is None:
            raise ValueError(f"symbol node requires file, range, and hash id={self.id}")
        return self


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    source: str = Field(validation_alias=AliasChoices("source", "from"), serialization_alias="from")
    target: str = Field(validation_alias=AliasChoices("target", "to"), serialization_alias="to")
    type: EdgeType
    evidence: Evidence
    props: tuple[str, ...] = ()
    raw: str | None = None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.type is EdgeType.UNRESOLVED and not self.raw:
            raise ValueError("unresolved edge requires raw")
        if self.type is not EdgeType.UNRESOLVED and self.raw is not None:
            raise ValueError("raw is only allowed on unresolved edges")
        if self.type is EdgeType.PASSES_PROP and not self.props:
            raise ValueError("passes_prop edge requires props")
        if self.type is not EdgeType.PASSES_PROP and self.props:
            raise ValueError("props are only allowed on passes_prop edges")
        if self.source == self.target and self.type is not EdgeType.CALLS:
            raise ValueError(f"edge source equals target type={self.type}")
        return self

    def key(self) -> tuple[str, str, EdgeType, str, int]:
        return (self.source, self.target, self.type, self.evidence.file, self.evidence.line)


class Graph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = GRAPH_SCHEMA_VERSION
    root: str
    nodes: dict[str, Node] = Field(default_factory=dict)
    edges: list[Edge] = Field(default_factory=list)
    reverse: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.version != GRAPH_SCHEMA_VERSION:
            raise ValueError(
                f"graph version={self.version} does not match schema={GRAPH_SCHEMA_VERSION}"
            )
        for key, node in self.nodes.items():
            if key != node.id:
                raise ValueError(f"node key={key} does not equal id={node.id}")
        seen: set[tuple[str, str, EdgeType, str, int]] = set()
        for edge in self.edges:
            if edge.source not in self.nodes:
                raise ValueError(f"edge source is missing source={edge.source}")
            if edge.type is not EdgeType.UNRESOLVED and edge.target not in self.nodes:
                raise ValueError(f"edge target is missing target={edge.target}")
            identity = edge.key()
            if identity in seen:
                raise ValueError(f"duplicate edge key={identity}")
            seen.add(identity)
        return self


def graph_to_json(graph: Graph) -> str:
    """Serialize a graph with stable key order and alias names."""
    payload = graph.model_dump(mode="json", by_alias=True)
    payload["nodes"] = {key: payload["nodes"][key] for key in sorted(payload["nodes"])}
    payload["edges"] = sorted(
        payload["edges"],
        key=lambda item: (
            item["from"],
            item["type"],
            item["to"],
            item["evidence"]["file"],
            item["evidence"]["line"],
        ),
    )
    payload["reverse"] = {key: payload["reverse"][key] for key in sorted(payload["reverse"])}
    return json.dumps(payload, indent=2) + "\n"


def graph_from_json(text: str) -> Graph:
    """Load a graph produced by graph_to_json."""
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError("graph json must be an object")
    return Graph.model_validate(loaded)

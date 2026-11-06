"""Facts knowable from a single parsed file."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from gatekeeper_graph.models import Edge, Node


class ImportKind(StrEnum):
    NAMED = "named"
    DEFAULT = "default"
    NAMESPACE = "namespace"
    SIDE_EFFECT = "side_effect"
    DYNAMIC = "dynamic"


class ImportedName(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    imported: str
    local: str


class ImportRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    specifier: str
    kind: ImportKind
    names: tuple[ImportedName, ...] = ()
    line: int = Field(ge=1)
    owner: str
    lazy: bool = False


class ExportRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exported: str
    local: str | None
    line: int = Field(ge=1)
    from_specifier: str | None = None
    is_star: bool = False


class CallRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: str
    callee: str
    line: int = Field(ge=1)


class FileExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    nodes: tuple[Node, ...]
    contains: tuple[Edge, ...]
    imports: tuple[ImportRef, ...]
    exports: tuple[ExportRef, ...]
    calls: tuple[CallRef, ...]

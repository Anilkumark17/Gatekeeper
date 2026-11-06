"""Structured reading of a user question. No graph access."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gatekeeper_graph.models import make_file_id


class ProblemType(StrEnum):
    BUG = "bug"
    IMPACT = "impact"
    CHANGE = "change"
    EXPLAIN = "explain"
    UNKNOWN = "unknown"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StackFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    file: str
    line: int = Field(ge=1)

    @field_validator("file")
    @classmethod
    def _relative(cls, value: str) -> str:
        return make_file_id(value)


class Intent(BaseModel):
    """What the context agent believes the question is asking for."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str
    problem_type: ProblemType
    observed: str | None = None
    expected: str | None = None
    key_phrases: tuple[str, ...] = ()
    quoted_text: tuple[str, ...] = ()
    backtick_names: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    frames: tuple[StackFrame, ...] = ()
    confidence: Confidence
    source: Literal["llm", "rules"]

    @field_validator("key_phrases")
    @classmethod
    def _phrases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned: list[str] = []
        for item in value:
            phrase = " ".join(item.strip().lower().split())
            if not phrase:
                raise ValueError("key phrase is empty")
            if len(phrase.split(" ")) > 4:
                raise ValueError(f"key phrase is too long phrase={phrase}")
            if phrase not in cleaned:
                cleaned.append(phrase)
        if len(cleaned) > 6:
            raise ValueError("key phrases exceed 6")
        return tuple(cleaned)

    @field_validator("files")
    @classmethod
    def _files(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({make_file_id(item) for item in value}))

    @field_validator("frames")
    @classmethod
    def _frames(cls, value: tuple[StackFrame, ...]) -> tuple[StackFrame, ...]:
        unique = {(frame.file, frame.line, frame.name): frame for frame in value}
        return tuple(unique[key] for key in sorted(unique))

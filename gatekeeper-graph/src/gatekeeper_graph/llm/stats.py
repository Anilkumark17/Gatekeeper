"""Timing and token counts for one model call."""

from pydantic import BaseModel, ConfigDict


class CallStats(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: str
    model: str
    prompt_tokens: int | None
    output_tokens: int | None
    total_ms: float
    load_ms: float | None
    retries: int

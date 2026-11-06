"""Ollama HTTP client. No other module posts to /api/generate."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from gatekeeper_graph.llm.config import LLMConfig
from gatekeeper_graph.llm.errors import LLMOutputInvalid, LLMUnavailable
from gatekeeper_graph.llm.stats import CallStats

logger = logging.getLogger(__name__)

_REMINDER = "\n\nThe previous reply was invalid. Reply with JSON matching the schema only."


class OllamaHttpClient:
    def __init__(
        self,
        config: LLMConfig,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    def generate_structured[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
    ) -> tuple[T, CallStats]:
        reminder = ""
        last_raw = ""
        for attempt in range(self._config.retries + 1):
            try:
                payload = self._post(self._body(system, user + reminder, schema))
            except (httpx.HTTPError, TimeoutError, OSError) as exc:
                if attempt >= self._config.retries:
                    raise LLMUnavailable(f"ollama unreachable model={self._config.model}") from exc
                logger.info("llm retry backend=ollama_http attempt=%s", attempt + 1)
                continue
            raw = payload.get("response", "")
            text = raw if isinstance(raw, str) else str(raw)
            try:
                parsed = schema.model_validate_json(text)
            except ValidationError:
                last_raw = text
                reminder = _REMINDER
                logger.info("llm retry backend=ollama_http attempt=%s", attempt + 1)
                continue
            return parsed, _stats(self._config, payload, attempt)
        raise LLMOutputInvalid(last_raw)

    def generate_text(self, system: str, user: str) -> tuple[str, CallStats]:
        for attempt in range(self._config.retries + 1):
            try:
                payload = self._post(self._body(system, user, None))
            except (httpx.HTTPError, TimeoutError, OSError) as exc:
                if attempt >= self._config.retries:
                    raise LLMUnavailable(f"ollama unreachable model={self._config.model}") from exc
                logger.info("llm retry backend=ollama_http attempt=%s", attempt + 1)
                continue
            raw = payload.get("response", "")
            text = raw if isinstance(raw, str) else str(raw)
            return text, _stats(self._config, payload, attempt)
        raise LLMUnavailable(f"ollama unreachable model={self._config.model}")

    def is_available(self) -> bool:
        return ollama_model_available(
            self._config.base_url,
            self._config.model,
            self._config.timeout_s,
            self._transport,
        )

    def _body(self, system: str, user: str, schema: type[BaseModel] | None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._config.model,
            "prompt": f"{system}\n\n---\n\n{user}",
            "stream": False,
            "keep_alive": self._config.keep_alive,
            "options": {
                "temperature": self._config.temperature,
                "num_ctx": self._config.num_ctx,
                "num_predict": self._config.num_predict,
            },
        }
        if schema is not None:
            body["format"] = schema.model_json_schema()
        return body

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(
            base_url=self._config.base_url.rstrip("/"),
            timeout=self._config.timeout_s,
            transport=self._transport,
        ) as client:
            response = client.post("/api/generate", json=body)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("ollama response was not an object")
        return payload


def ollama_model_available(
    base_url: str,
    model: str,
    timeout_s: float,
    transport: httpx.BaseTransport | None = None,
) -> bool:
    """True only when GET /api/tags lists this model name."""
    try:
        with httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_s,
            transport=transport,
        ) as client:
            response = client.get("/api/tags")
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, TimeoutError, OSError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    names: set[str] = set()
    models = payload.get("models", [])
    if isinstance(models, list):
        for item in models:
            if not isinstance(item, dict):
                continue
            for key in ("name", "model"):
                value = item.get(key)
                if isinstance(value, str):
                    names.add(value)
    return model in names


def _stats(config: LLMConfig, payload: dict[str, Any], retries: int) -> CallStats:
    return CallStats(
        backend="ollama_http",
        model=config.model,
        prompt_tokens=_as_int(payload.get("prompt_eval_count")),
        output_tokens=_as_int(payload.get("eval_count")),
        total_ms=_ns_to_ms(payload.get("total_duration")) or 0.0,
        load_ms=_ns_to_ms(payload.get("load_duration")),
        retries=retries,
    )


def _ns_to_ms(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) / 1_000_000


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value

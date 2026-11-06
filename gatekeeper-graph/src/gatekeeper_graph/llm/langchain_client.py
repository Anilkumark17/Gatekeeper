"""LangChain backends. This module imports LangChain only when constructed."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from gatekeeper_graph.llm.config import LLMConfig
from gatekeeper_graph.llm.errors import LLMOutputInvalid, LLMUnavailable
from gatekeeper_graph.llm.ollama_http import ollama_model_available
from gatekeeper_graph.llm.stats import CallStats

logger = logging.getLogger(__name__)

_REMINDER = "\n\nThe previous reply was invalid. Reply with JSON matching the schema only."
_INSTALL = "langchain extra is not installed; install it with `uv sync --extra langchain`"
_CONNECTION_NAMES = frozenset(
    {
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
    }
)
_INVALID_NAMES = frozenset({"OutputParserException", "ValidationError", "BadRequestError"})


class LangChainClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        if config.provider == "langchain_groq" and not os.environ.get("GROQ_API_KEY"):
            raise LLMUnavailable("GROQ_API_KEY is missing")
        try:
            if config.provider == "langchain_ollama":
                from langchain_ollama import ChatOllama

                self._llm: Any = ChatOllama(
                    model=config.model,
                    base_url=config.base_url,
                    temperature=config.temperature,
                    num_ctx=config.num_ctx,
                    num_predict=config.num_predict,
                    keep_alive=config.keep_alive,
                )
            elif config.provider == "langchain_groq":
                from langchain_groq import ChatGroq

                self._llm = ChatGroq(model=config.model, temperature=config.temperature)
            else:
                raise LLMUnavailable(f"unsupported langchain provider={config.provider}")
        except ImportError as exc:
            raise ImportError(_INSTALL) from exc

    def generate_structured[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
    ) -> tuple[T, CallStats]:
        from langchain_core.messages import HumanMessage, SystemMessage

        reminder = ""
        last_raw = ""
        started = time.perf_counter()
        for attempt in range(self._config.retries + 1):
            messages = [
                SystemMessage(content=system),
                HumanMessage(content=user + reminder),
            ]
            try:
                structured = self._llm.with_structured_output(schema, method="json_schema")
                result = structured.invoke(messages)
            except Exception as exc:
                if _is_unavailable(exc):
                    if attempt >= self._config.retries:
                        raise LLMUnavailable(f"llm unreachable model={self._config.model}") from exc
                    _log_retry(self._config.provider, attempt)
                    continue
                if _is_invalid(exc):
                    last_raw = str(exc)
                    reminder = _REMINDER
                    _log_retry(self._config.provider, attempt)
                    continue
                raise
            parsed, raw_text, prompt_tokens, output_tokens = _interpret(result, schema)
            if parsed is not None:
                elapsed = (time.perf_counter() - started) * 1000
                return parsed, _call_stats(
                    self._config,
                    elapsed,
                    attempt,
                    prompt_tokens,
                    output_tokens,
                )
            last_raw = raw_text
            reminder = _REMINDER
            _log_retry(self._config.provider, attempt)
        raise LLMOutputInvalid(last_raw)

    def generate_text(self, system: str, user: str) -> tuple[str, CallStats]:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        started = time.perf_counter()
        for attempt in range(self._config.retries + 1):
            try:
                result = self._llm.invoke(messages)
            except Exception as exc:
                if _is_unavailable(exc) and attempt >= self._config.retries:
                    raise LLMUnavailable(f"llm unreachable model={self._config.model}") from exc
                if _is_unavailable(exc):
                    _log_retry(self._config.provider, attempt)
                    continue
                raise
            elapsed = (time.perf_counter() - started) * 1000
            prompt_tokens, output_tokens = _usage(result)
            return _content_text(getattr(result, "content", result)), _call_stats(
                self._config,
                elapsed,
                attempt,
                prompt_tokens,
                output_tokens,
            )
        raise LLMUnavailable(f"llm unreachable model={self._config.model}")

    def is_available(self) -> bool:
        if self._config.provider == "langchain_groq":
            return bool(os.environ.get("GROQ_API_KEY"))
        return ollama_model_available(
            self._config.base_url,
            self._config.model,
            self._config.timeout_s,
        )


def _interpret[T: BaseModel](
    result: object,
    schema: type[T],
) -> tuple[T | None, str, int | None, int | None]:
    if isinstance(result, schema):
        return result, "", None, None
    if isinstance(result, dict) and "parsed" in result:
        raw_message = result.get("raw")
        prompt_tokens, output_tokens = _usage(raw_message)
        parsed = result.get("parsed")
        if isinstance(parsed, schema):
            return parsed, "", prompt_tokens, output_tokens
        raw_text = _content_text(getattr(raw_message, "content", ""))
        return None, raw_text, prompt_tokens, output_tokens
    content = getattr(result, "content", None)
    prompt_tokens, output_tokens = _usage(result)
    if isinstance(content, str):
        try:
            return schema.model_validate_json(content), "", prompt_tokens, output_tokens
        except ValidationError:
            return None, content, prompt_tokens, output_tokens
    return None, _content_text(result), prompt_tokens, output_tokens


def _usage(message: object) -> tuple[int | None, int | None]:
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        return None, None
    prompt = usage.get("input_tokens", usage.get("prompt_tokens"))
    output = usage.get("output_tokens")
    return _as_int(prompt), _as_int(output)


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


def _call_stats(
    config: LLMConfig,
    total_ms: float,
    retries: int,
    prompt_tokens: int | None,
    output_tokens: int | None,
) -> CallStats:
    return CallStats(
        backend=config.provider,
        model=config.model,
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        total_ms=total_ms,
        load_ms=None,
        retries=retries,
    )


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _log_retry(provider: str, attempt: int) -> None:
    logger.info("llm retry backend=%s attempt=%s", provider, attempt + 1)


def _is_unavailable(exc: Exception) -> bool:
    if isinstance(exc, (httpx.HTTPError, TimeoutError, ConnectionError, OSError)):
        return True
    return type(exc).__name__ in _CONNECTION_NAMES


def _is_invalid(exc: Exception) -> bool:
    if isinstance(exc, ValidationError) or type(exc).__name__ in _INVALID_NAMES:
        return True
    return "json_validate_failed" in str(exc)

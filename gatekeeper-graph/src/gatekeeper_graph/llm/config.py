"""LLM settings from defaults, gatekeeper.toml, then the environment."""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

Provider = Literal["ollama_http", "langchain_ollama", "langchain_groq"]

_ENV_FIELDS = {
    "GATEKEEPER_LLM_PROVIDER": "provider",
    "GATEKEEPER_LLM_MODEL": "model",
    "GATEKEEPER_LLM_BASE_URL": "base_url",
}


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Provider = "ollama_http"
    model: str = "qwen2.5-coder:3b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.0
    num_ctx: int = 2048
    num_predict: int = 256
    keep_alive: str = "30m"
    timeout_s: float = 120
    retries: int = 1


def load_config() -> LLMConfig:
    """Defaults, then `[llm]` in `./gatekeeper.toml`, then env vars. Env wins."""
    data = LLMConfig().model_dump()
    path = Path("gatekeeper.toml")
    if path.is_file():
        with path.open("rb") as handle:
            parsed = tomllib.load(handle)
        section = parsed.get("llm", {})
        if isinstance(section, dict):
            data.update({key: value for key, value in section.items() if key in data})
    for env_name, field in _ENV_FIELDS.items():
        value = os.environ.get(env_name)
        if value:
            data[field] = value
    config = LLMConfig.model_validate(data)
    logger.info("llm config provider=%s model=%s", config.provider, config.model)
    return config

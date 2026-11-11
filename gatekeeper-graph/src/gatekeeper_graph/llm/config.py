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


def load_dotenv(path: Path | None = None) -> None:
    """Fill missing environment variables from `.env`. Existing variables stay."""
    for file in _dotenv_files(path):
        _load_dotenv_file(file)


def _dotenv_files(path: Path | None) -> list[Path]:
    if path is not None:
        return [path]
    files = [Path.cwd() / ".env"]
    project = _project_dotenv()
    if project is not None and project not in files:
        files.append(project)
    return files


def _project_dotenv() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            candidate = parent / ".env"
            return candidate if candidate.is_file() else None
    return None


def _load_dotenv_file(file: Path) -> None:
    if not file.is_file():
        return
    try:
        lines = file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        logger.info("dotenv skipped path=%s reason=%s", file, exc)
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    logger.info("dotenv loaded path=%s", file)


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

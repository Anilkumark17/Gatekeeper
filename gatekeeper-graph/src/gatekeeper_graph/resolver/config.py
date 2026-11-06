"""Load jsconfig or tsconfig path aliases."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class ResolverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str | None = None
    paths: dict[str, tuple[str, ...]] = {}


def load_config(root: Path) -> ResolverConfig:
    """Read jsconfig.json, otherwise tsconfig.json. Missing files use defaults."""
    for name in ("jsconfig.json", "tsconfig.json"):
        path = root / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(_strip_json_comments(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            logger.warning("config skipped path=%s reason=invalid error=%s", path, exc)
            return ResolverConfig()
        if not isinstance(payload, dict):
            logger.warning("config skipped path=%s reason=invalid", path)
            return ResolverConfig()
        options = payload.get("compilerOptions", {})
        if not isinstance(options, dict):
            return ResolverConfig()
        base_url = options.get("baseUrl")
        raw_paths = options.get("paths", {})
        paths: dict[str, tuple[str, ...]] = {}
        if isinstance(raw_paths, dict):
            for key, value in raw_paths.items():
                if isinstance(key, str) and isinstance(value, list):
                    paths[key] = tuple(item for item in value if isinstance(item, str))
        return ResolverConfig(base_url=base_url if isinstance(base_url, str) else None, paths=paths)
    return ResolverConfig()


def _strip_json_comments(text: str) -> str:
    """Remove // and /* */ comments and trailing commas from JSON-like config text."""
    output: list[str] = []
    index = 0
    in_string = False
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(char)
            if char == "\\" and nxt:
                output.append(nxt)
                index += 2
                continue
            if char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and nxt == "/":
            index = text.find("\n", index)
            if index < 0:
                break
            continue
        if char == "/" and nxt == "*":
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
            continue
        output.append(char)
        index += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(output))

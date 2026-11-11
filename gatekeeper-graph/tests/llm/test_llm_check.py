from pathlib import Path

import httpx
import pytest

from gatekeeper_graph.cli import main

_ENV = ("GATEKEEPER_LLM_PROVIDER", "GATEKEEPER_LLM_MODEL", "GATEKEEPER_LLM_BASE_URL")


@pytest.mark.ollama
def test_llm_check_against_local_qwen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GATEKEEPER_LLM_PROVIDER", "ollama_http")
    monkeypatch.setenv("GATEKEEPER_LLM_MODEL", "qwen2.5-coder:3b")
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=2)
        response.raise_for_status()
    except httpx.HTTPError:
        pytest.skip("ollama is down")
    payload = response.json()
    names = {
        item.get("name")
        for item in payload.get("models", [])
        if isinstance(item, dict)
    }
    if "qwen2.5-coder:3b" not in names:
        pytest.skip("qwen2.5-coder:3b is not loaded")
    assert main(["llm-check"]) == 0

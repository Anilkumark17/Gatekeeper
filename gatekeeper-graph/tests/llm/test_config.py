import logging
import os
from pathlib import Path

import pytest

from gatekeeper_graph.llm import LLMConfig, load_config
from gatekeeper_graph.llm.config import load_dotenv

_ENV = ("GATEKEEPER_LLM_PROVIDER", "GATEKEEPER_LLM_MODEL", "GATEKEEPER_LLM_BASE_URL")


@pytest.fixture
def clean_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.chdir(tmp_path)
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_dotenv_fills_missing_names_and_keeps_existing(
    clean_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_dir.joinpath(".env").write_text(
        "GATEKEEPER_LLM_PROVIDER=langchain_groq\n"
        "GATEKEEPER_LLM_MODEL=from-dotenv\n"
        "GROQ_API_KEY=dotenv-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GROQ_API_KEY", "already-set")
    load_dotenv()
    try:
        config = load_config()
        assert config.provider == "langchain_groq"
        assert config.model == "from-dotenv"
        assert os.environ["GROQ_API_KEY"] == "already-set"
    finally:
        os.environ.pop("GATEKEEPER_LLM_PROVIDER", None)
        os.environ.pop("GATEKEEPER_LLM_MODEL", None)


def test_cli_reads_dotenv_before_the_command(
    clean_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_dir.joinpath(".env").write_text(
        "GATEKEEPER_LLM_PROVIDER=langchain_groq\nGROQ_API_KEY=cli-secret\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from gatekeeper_graph.cli import main

    with pytest.raises(SystemExit):
        main([])
    try:
        assert os.environ["GATEKEEPER_LLM_PROVIDER"] == "langchain_groq"
        assert os.environ["GROQ_API_KEY"] == "cli-secret"
    finally:
        os.environ.pop("GATEKEEPER_LLM_PROVIDER", None)
        os.environ.pop("GATEKEEPER_LLM_MODEL", None)
        os.environ.pop("GROQ_API_KEY", None)


def test_dotenv_reads_a_later_file_without_overriding(
    clean_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = clean_dir / ".env"
    second = clean_dir / "project.env"
    first.write_text("GATEKEEPER_LLM_PROVIDER=langchain_groq\n", encoding="utf-8")
    second.write_text(
        "GATEKEEPER_LLM_PROVIDER=ollama_http\nGATEKEEPER_LLM_MODEL=from-project\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "gatekeeper_graph.llm.config._dotenv_files",
        lambda _path: [first, second],
    )
    load_dotenv()
    try:
        config = load_config()
        assert config.provider == "langchain_groq"
        assert config.model == "from-project"
    finally:
        os.environ.pop("GATEKEEPER_LLM_PROVIDER", None)
        os.environ.pop("GATEKEEPER_LLM_MODEL", None)


def test_defaults(clean_dir: Path) -> None:
    config = load_config()
    assert config.provider == "ollama_http"
    assert config.model == "qwen2.5-coder:3b"
    assert config.base_url == "http://localhost:11434"
    assert config.temperature == 0.0
    assert config.num_ctx == 2048
    assert config.num_predict == 256
    assert config.keep_alive == "30m"


def test_toml_overrides_defaults(clean_dir: Path) -> None:
    clean_dir.joinpath("gatekeeper.toml").write_text(
        '[llm]\nprovider = "langchain_ollama"\nmodel = "from-toml"\n',
        encoding="utf-8",
    )
    config = load_config()
    assert config == LLMConfig(provider="langchain_ollama", model="from-toml")


def test_env_overrides_toml(clean_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clean_dir.joinpath("gatekeeper.toml").write_text(
        '[llm]\nprovider = "langchain_ollama"\nmodel = "from-toml"\nbase_url = "http://toml"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("GATEKEEPER_LLM_MODEL", "from-env")
    monkeypatch.setenv("GATEKEEPER_LLM_BASE_URL", "http://env")
    config = load_config()
    assert config.provider == "langchain_ollama"
    assert config.model == "from-env"
    assert config.base_url == "http://env"


def test_groq_key_is_absent_from_repr_and_logs(
    clean_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "groq-test-secret-not-a-real-key"
    monkeypatch.setenv("GROQ_API_KEY", secret)
    monkeypatch.setenv("GATEKEEPER_LLM_PROVIDER", "langchain_groq")
    with caplog.at_level(logging.DEBUG, logger="gatekeeper_graph.llm.config"):
        config = load_config()
    assert "provider=langchain_groq" in caplog.text
    assert secret not in repr(config)
    assert secret not in config.model_dump_json()
    assert secret not in caplog.text

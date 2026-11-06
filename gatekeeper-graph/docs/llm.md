# LLM client

Summaries, and later the prompt analyser and diagnosis agent, call a model only through `LLMClient`. They use `make_client()` and do not open their own HTTP clients.

## Interface

`generate_structured(system, user, schema)` returns a pydantic model and `CallStats`. `generate_text(system, user)` returns plain text and `CallStats`. `is_available()` is true only when a call can be attempted.

`CallStats` records `backend`, `model`, `prompt_tokens`, `output_tokens`, `total_ms`, `load_ms`, and `retries`.

## Providers

| `provider` | Client | Notes |
| --- | --- | --- |
| `ollama_http` | `POST /api/generate` | Default. No extra install. |
| `langchain_ollama` | `ChatOllama` | `uv sync --extra langchain` |
| `langchain_groq` | `ChatGroq` | Same extra. Reads `GROQ_API_KEY` from the environment. |

The default model is the local Ollama tag `qwen2.5-coder:3b`. A current Groq Qwen id is `qwen/qwen3.8-27b`.

Importing `gatekeeper_graph.llm` does not import LangChain. Constructing a LangChain provider without the extra raises `ImportError` and names `uv sync --extra langchain`.

## Config precedence

1. Built-in defaults (`ollama_http`, `http://localhost:11434`, temperature `0.0`, `num_ctx` 2048, `num_predict` 256, `keep_alive` `30m`, timeout 120s, 1 retry).
2. `[llm]` in `gatekeeper.toml` in the current directory.
3. `GATEKEEPER_LLM_PROVIDER`, `GATEKEEPER_LLM_MODEL`, and `GATEKEEPER_LLM_BASE_URL`. These win.

`GROQ_API_KEY` is never a config field, never part of `repr(config)`, and never written to logs.

```toml
[llm]
provider = "langchain_groq"
model = "qwen/qwen3.8-27b"
```

```powershell
$env:GROQ_API_KEY = "<your key>"
uv run gatekeeper llm-check
```

`llm-check` prints the provider and model, checks `is_available()`, then warms up with a schema `{"ok": bool}`. Exit 0 on success, 2 when the model is unavailable, 3 when the reply does not match the schema.

## Summaries while watching

`gatekeeper watch` rebuilds the graph after a file event, then fills symbol summaries through `LLMClient`. A symbol whose content hash is unchanged keeps its summary. A changed symbol is sent to the configured model. If the model is unavailable, the previous summary stays and `stale` is true. `gatekeeper build` does not call the model.

```powershell
$env:GROQ_API_KEY = "<your key>"
$env:GATEKEEPER_LLM_PROVIDER = "langchain_groq"
$env:GATEKEEPER_LLM_MODEL = "qwen/qwen3.8-27b"
uv sync --extra langchain
uv run gatekeeper watch C:\Users\anilk\Desktop\coding\Visualize\sample-js --out C:\Users\anilk\Desktop\coding\Visualize\gatekeeper-data\sample-js.graph.json
```

## Errors

`LLMUnavailable`: the server cannot be reached, the call times out after retries, or `GROQ_API_KEY` is missing.

`LLMOutputInvalid`: structured output still fails schema validation after retries. The stored text is truncated to 300 characters.

Tests under `tests/llm/` use `httpx.MockTransport` and `FakeClient`. They do not need a running model. `tests/llm/test_llm_check.py` is marked `ollama` and skips when `http://localhost:11434` is down.

import os
from pathlib import Path

SHOP = Path(__file__).parents[1] / "fixtures" / "shop"
GOLDEN = Path(__file__).parents[1] / "fixtures" / "golden" / "shop.graph.json"


def groq_configured() -> bool:
    provider = os.environ.get("GATEKEEPER_LLM_PROVIDER")
    return provider == "langchain_groq" and bool(os.environ.get("GROQ_API_KEY"))

"""Failures shared by every LLM backend."""


class LLMUnavailable(Exception):
    """The model server cannot be reached, timed out, or has no API key."""


class LLMOutputInvalid(Exception):
    """The model reply still does not match the schema after retries."""

    def __init__(self, raw: str) -> None:
        self.raw = raw[:300]
        super().__init__(f"llm output invalid raw={self.raw}")

class LLMCallError(Exception):
    """Raised when an LLM provider call fails."""


class LLMTimeoutError(LLMCallError):
    """Raised when an LLM provider call times out."""

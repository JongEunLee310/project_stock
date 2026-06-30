class LLMCallError(Exception):
    """Raised when an LLM provider call fails."""


class LLMTimeoutError(LLMCallError):
    """Raised when an LLM provider call times out."""


class LLMRoutingError(LLMCallError):
    """Raised when an LLM task cannot be mapped to a provider."""

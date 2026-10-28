"""The one place a live Claude client is built, for the LLM negotiators and the front desk.

Both need the ``claude`` extra (``uv sync --extra claude``) and credentials. Tests never build
it: they inject a client, so nothing here runs in the test suite.

**Timeout and retries (proposed).** The SDK's defaults are a 10 minute timeout and 2 retries,
so one stuck call could hold a negotiation turn for half an hour. A move is one non-streaming
request with at most ``max_tokens`` 8000 (``data/llm_config.json``); that is well under
``REQUEST_TIMEOUT_S``. One retry covers a dropped connection or a brief 429 or 5xx. After that,
the caller treats the error as a failed call: the negotiator sends its rules-based move, and
the front desk asks for the text form.
"""
from __future__ import annotations

from typing import Any

__all__ = ["MAX_RETRIES", "REQUEST_TIMEOUT_S", "api_error_types", "default_client"]

REQUEST_TIMEOUT_S = 180.0
MAX_RETRIES = 1


def default_client(needed_by: str) -> Any:
    """``anthropic.Anthropic()`` with this module's timeout and retries."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on the optional extra
        raise RuntimeError(f"{needed_by} need the 'claude' extra: uv sync --extra claude") from exc
    return anthropic.Anthropic(timeout=REQUEST_TIMEOUT_S, max_retries=MAX_RETRIES)


def api_error_types() -> tuple[type[BaseException], ...]:
    """The SDK's API errors (``anthropic.APIError``: status errors such as ``RateLimitError``
    and 5xx, ``APIConnectionError`` and ``APITimeoutError``), or none without the SDK."""
    try:
        import anthropic
    except ImportError:
        return ()
    return (anthropic.APIError,)

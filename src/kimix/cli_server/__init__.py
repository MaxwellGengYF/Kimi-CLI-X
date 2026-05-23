"""Kimix CLI HTTP server client.

Provides sync and async HTTP clients for the Kimix opencode-style REST API,
using httpx for transport and orjson for JSON serialization.
"""

from kimix.cli_server.client import (
    KimixHttpClient,
    KimixAsyncClient,
    HealthResponse,
    SessionResponse,
    SessionStatusResponse,
    PromptInput,
    PromptPart,
    MessageResponse,
    MessagePart,
    SSEEvent,
    EventType,
    ParsedEvent,
    parse_event,
    check_health_sync,
    abort_session_sync,
)

__all__ = [
    "KimixHttpClient",
    "KimixAsyncClient",
    "HealthResponse",
    "SessionResponse",
    "SessionStatusResponse",
    "PromptInput",
    "PromptPart",
    "MessageResponse",
    "MessagePart",
    "SSEEvent",
    "EventType",
    "ParsedEvent",
    "parse_event",
    "check_health_sync",
    "abort_session_sync",
]

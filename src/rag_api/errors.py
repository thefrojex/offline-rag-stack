"""Upstream failure handling.

The LLM, embedding server and Qdrant are all network dependencies that can time out or
fail. Without this module those failures surface as an opaque 500. Here they become a
504 (timeout) or a 502 (anything else the upstream did wrong) with a JSON body that names
the component, and the streaming endpoint turns them into an SSE `error` event.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

import httpx
import openai
from fastapi import Request
from fastapi.responses import JSONResponse
from qdrant_client.http.exceptions import ApiException, ResponseHandlingException

logger = logging.getLogger(__name__)

Component = Literal["llm", "embeddings", "vector_store"]
Kind = Literal["timeout", "unavailable"]

_STATUS: dict[Kind, int] = {"timeout": 504, "unavailable": 502}
_TYPE: dict[Kind, str] = {"timeout": "upstream_timeout", "unavailable": "upstream_error"}
_SUMMARY: dict[Kind, str] = {
    "timeout": "did not respond in time",
    "unavailable": "request failed",
}


class UpstreamError(Exception):
    """A dependency timed out or failed. Carries enough to build an HTTP or SSE error."""

    def __init__(self, component: Component, kind: Kind, detail: str) -> None:
        super().__init__(f"{component} {_SUMMARY[kind]}: {detail}")
        self.component: Component = component
        self.kind: Kind = kind
        self.detail = detail

    @property
    def status_code(self) -> int:
        return _STATUS[self.kind]

    def payload(self) -> dict[str, str]:
        return {
            "type": _TYPE[self.kind],
            "component": self.component,
            "message": f"{self.component} {_SUMMARY[self.kind]}",
            "detail": self.detail,
        }


def classify(exc: BaseException) -> Kind | None:
    """Map a client exception to a failure kind, or None if it is not an upstream failure."""
    if isinstance(exc, openai.APITimeoutError | httpx.TimeoutException | TimeoutError):
        return "timeout"
    if isinstance(exc, ResponseHandlingException):
        return "timeout" if isinstance(exc.source, httpx.TimeoutException) else "unavailable"
    if isinstance(
        exc,
        openai.APIConnectionError
        | openai.APIStatusError
        | httpx.TransportError
        | ApiException
        | ConnectionError,
    ):
        return "unavailable"
    return None


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


@contextmanager
def upstream(component: Component) -> Iterator[None]:
    """Re-raise recognised client failures as UpstreamError; let everything else through."""
    try:
        yield
    except UpstreamError:
        raise
    except Exception as exc:
        kind = classify(exc)
        if kind is None:
            raise
        raise UpstreamError(component, kind, _describe(exc)) from exc


async def upstream_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, UpstreamError):
        raise exc
    logger.warning(
        "upstream failure",
        extra={"component": exc.component, "kind": exc.kind, "detail": exc.detail},
    )
    return JSONResponse({"error": exc.payload()}, status_code=exc.status_code)

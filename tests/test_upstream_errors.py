"""Upstream failures become 504/502 with a JSON body, or an SSE error event, never a bare 500."""

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import httpx2
import openai
import pytest
from fastapi.testclient import TestClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from rag_api.clients.qdrant_store import QdrantStore
from rag_api.errors import Kind, classify
from rag_api.main import create_app
from rag_api.settings import Settings
from tests.fakes import FakeChat, FakeEmbedder, FakeStore

_REQUEST = httpx2.Request("POST", "http://ollama:11434/v1/chat/completions")


def _timeout() -> Exception:
    return openai.APITimeoutError(request=_REQUEST)


def _refused() -> Exception:
    return openai.APIConnectionError(request=_REQUEST)


def _server_error() -> Exception:
    return openai.InternalServerError(
        "model runner crashed", response=httpx2.Response(500, request=_REQUEST), body=None
    )


def _qdrant_timeout() -> Exception:
    return ResponseHandlingException(httpx.ReadTimeout("qdrant too slow"))


def _qdrant_down() -> Exception:
    return ResponseHandlingException(httpx.ConnectError("connection refused"))


def _build(
    settings: Settings,
    *,
    embedder: FakeEmbedder | None = None,
    chat: FakeChat | None = None,
    store: FakeStore | None = None,
    raise_server_exceptions: bool = True,
) -> TestClient:
    app = create_app(
        settings,
        embedder=embedder or FakeEmbedder(),
        chat=chat or FakeChat(),
        store=store or FakeStore(),
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _seed(client: TestClient) -> None:
    response = client.post("/ingest", files=[("files", ("ops.md", b"Backups run nightly."))])
    assert response.status_code == 200


def _sse(raw: str) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    for block in raw.strip().split("\n\n"):
        name, data = block.splitlines()[:2]
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_timeout(), "timeout"),
        (TimeoutError(), "timeout"),
        (httpx.ReadTimeout("slow"), "timeout"),
        (_qdrant_timeout(), "timeout"),
        (_refused(), "unavailable"),
        (_server_error(), "unavailable"),
        (
            openai.NotFoundError(
                "model not found", response=httpx2.Response(404, request=_REQUEST), body=None
            ),
            "unavailable",
        ),
        (_qdrant_down(), "unavailable"),
        (UnexpectedResponse(503, "Service Unavailable", b"", httpx.Headers()), "unavailable"),
        (ConnectionRefusedError(), "unavailable"),
        (ValueError("a bug"), None),
        (KeyError("a bug"), None),
        (RuntimeError("a bug"), None),
    ],
)
def test_classify_maps_each_failure_kind(exc: Exception, expected: Kind | None) -> None:
    assert classify(exc) == expected


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    ("make_exc", "status", "error_type"),
    [(_timeout, 504, "upstream_timeout"), (_refused, 502, "upstream_error")],
)
def test_embedding_failure_on_query_is_a_json_error(
    settings: Settings,
    make_exc: Any,
    status: int,
    error_type: str,
    stream: bool,
) -> None:
    client = _build(settings, embedder=FakeEmbedder(fail_with=make_exc()))
    response = client.post("/query", json={"question": "When?", "stream": stream})
    assert response.status_code == status
    error = response.json()["error"]
    assert error["type"] == error_type
    assert error["component"] == "embeddings"
    assert error["message"]


@pytest.mark.parametrize(
    ("make_exc", "status", "error_type", "detail_has"),
    [
        (_timeout, 504, "upstream_timeout", "APITimeoutError"),
        (_server_error, 502, "upstream_error", "model runner crashed"),
    ],
)
def test_llm_failure_on_non_streaming_query_is_a_json_error(
    settings: Settings, make_exc: Any, status: int, error_type: str, detail_has: str
) -> None:
    client = _build(settings, chat=FakeChat(fail_with=make_exc()))
    _seed(client)
    response = client.post("/query", json={"question": "When?", "stream": False})
    assert response.status_code == status
    error = response.json()["error"]
    assert (error["type"], error["component"]) == (error_type, "llm")
    assert detail_has in error["detail"]


@pytest.mark.parametrize(
    ("make_exc", "status", "error_type"),
    [(_qdrant_timeout, 504, "upstream_timeout"), (_qdrant_down, 502, "upstream_error")],
)
def test_vector_store_failure_on_query_is_a_json_error(
    settings: Settings, make_exc: Any, status: int, error_type: str
) -> None:
    client = _build(settings, store=FakeStore(fail_with=make_exc()))
    response = client.post("/query", json={"question": "When?", "stream": False})
    assert response.status_code == status
    assert response.json()["error"]["type"] == error_type
    assert response.json()["error"]["component"] == "vector_store"


def test_streaming_llm_timeout_before_first_token_emits_an_error_event(
    settings: Settings,
) -> None:
    client = _build(settings, chat=FakeChat(fail_with=_timeout()))
    _seed(client)
    response = client.post("/query", json={"question": "When?"})
    assert response.status_code == 200
    events = _sse(response.text)
    assert [name for name, _ in events] == ["sources", "error"]
    error = events[1][1]
    assert (error["type"], error["component"]) == ("upstream_timeout", "llm")


def test_streaming_failure_mid_answer_keeps_tokens_then_errors_without_done(
    settings: Settings,
) -> None:
    chat = FakeChat("one two three four", fail_with=_refused(), fail_after_tokens=2)
    client = _build(settings, chat=chat)
    _seed(client)
    events = _sse(client.post("/query", json={"question": "When?"}).text)
    assert [name for name, _ in events] == ["sources", "token", "token", "error"]
    assert events[-1][1]["type"] == "upstream_error"
    assert "done" not in [name for name, _ in events]


def test_streaming_unclassified_failure_is_reported_as_internal_error(settings: Settings) -> None:
    client = _build(settings, chat=FakeChat(fail_with=ValueError("a bug")))
    _seed(client)
    events = _sse(client.post("/query", json={"question": "When?"}).text)
    assert [name for name, _ in events] == ["sources", "error"]
    assert events[1][1]["type"] == "internal_error"


@pytest.mark.parametrize(
    ("embedder_exc", "store_exc", "status", "component"),
    [
        (_timeout(), None, 504, "embeddings"),
        (None, _qdrant_down(), 502, "vector_store"),
    ],
)
def test_ingest_failures_are_json_errors(
    settings: Settings,
    embedder_exc: Exception | None,
    store_exc: Exception | None,
    status: int,
    component: str,
) -> None:
    client = _build(
        settings,
        embedder=FakeEmbedder(fail_with=embedder_exc),
        store=FakeStore(fail_with=store_exc),
    )
    response = client.post("/ingest", files=[("files", ("ops.md", b"Backups run nightly."))])
    assert response.status_code == status
    assert response.json()["error"]["component"] == component


def test_document_listing_and_deletion_report_store_outages(settings: Settings) -> None:
    client = _build(settings, store=FakeStore(fail_with=_qdrant_down()))
    listing = client.get("/documents")
    deletion = client.delete("/documents/ops.md")
    assert (listing.status_code, deletion.status_code) == (502, 502)
    assert listing.json()["error"]["component"] == "vector_store"


def test_missing_document_is_still_a_404_not_an_upstream_error(settings: Settings) -> None:
    assert _build(settings).delete("/documents/ghost.md").status_code == 404


def test_unclassified_errors_are_not_disguised_as_upstream_failures(settings: Settings) -> None:
    client = _build(
        settings,
        embedder=FakeEmbedder(fail_with=ValueError("a real bug")),
        raise_server_exceptions=False,
    )
    response = client.post("/query", json={"question": "When?", "stream": False})
    assert response.status_code == 500
    assert "upstream" not in response.text.lower()


def test_health_still_reports_failures_itself(settings: Settings) -> None:
    app = create_app(
        settings,
        embedder=FakeEmbedder(healthy=False),
        chat=FakeChat(),
        store=FakeStore(),
    )
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["embeddings"]["ok"] is False


class TestQdrantStoreOnAnEmptyServer:
    """A server with no collection yet means 'no documents', not an error."""

    @staticmethod
    def _store() -> QdrantStore:
        store = QdrantStore("http://qdrant:6333", "documents")
        client = AsyncMock()
        client.collection_exists.return_value = False
        store._client = client
        return store

    async def test_list_search_and_delete_return_empty(self) -> None:
        store = self._store()
        assert await store.list_documents() == []
        assert await store.search([0.1, 0.2], limit=3) == []
        assert await store.delete_document("ops.md") == 0

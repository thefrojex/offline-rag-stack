from typing import Any

from fastapi.testclient import TestClient

from rag_api.main import create_app
from rag_api.settings import Settings
from tests.fakes import FakeChat, FakeEmbedder, FakeStore


def test_livez_needs_no_backends(client: TestClient) -> None:
    assert client.get("/livez").json() == {"status": "alive"}


def test_health_ok_when_everything_is_up(client: TestClient) -> None:
    response = client.get("/health")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert all(body[name]["ok"] for name in ("llm", "embeddings", "qdrant"))


def _health_with(settings: Settings, **broken: bool) -> tuple[int, dict[str, Any]]:
    app = create_app(
        settings,
        embedder=FakeEmbedder(healthy=not broken.get("embeddings", False)),
        chat=FakeChat(healthy=not broken.get("llm", False)),
        store=FakeStore(healthy=not broken.get("qdrant", False)),
    )
    with TestClient(app) as test_client:
        response = test_client.get("/health")
    return response.status_code, response.json()


def test_health_names_the_component_that_is_down(settings: Settings) -> None:
    for component in ("llm", "embeddings", "qdrant"):
        status, body = _health_with(settings, **{component: True})
        assert status == 503
        assert body["status"] == "degraded"
        assert body[component]["ok"] is False
        others = {"llm", "embeddings", "qdrant"} - {component}
        assert all(body[name]["ok"] for name in others)

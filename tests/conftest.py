from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from rag_api.main import create_app
from rag_api.settings import Settings
from tests.fakes import FakeChat, FakeEmbedder, FakeStore


@pytest.fixture
def settings() -> Settings:
    return Settings(chunk_size=300, chunk_overlap=40, top_k=3, log_level="WARNING")


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def chat() -> FakeChat:
    return FakeChat()


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def client(
    settings: Settings, embedder: FakeEmbedder, chat: FakeChat, store: FakeStore
) -> Iterator[TestClient]:
    app = create_app(settings, embedder=embedder, chat=chat, store=store)
    with TestClient(app) as test_client:
        yield test_client

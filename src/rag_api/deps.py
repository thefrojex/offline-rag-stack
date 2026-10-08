from dataclasses import dataclass

from fastapi import Request

from rag_api.clients.protocols import ChatModel, Embedder, VectorStore
from rag_api.settings import Settings


@dataclass(frozen=True, slots=True)
class Deps:
    settings: Settings
    embedder: Embedder
    chat: ChatModel
    store: VectorStore


def get_deps(request: Request) -> Deps:
    deps: Deps = request.app.state.deps
    return deps

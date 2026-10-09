"""Wrappers that turn client failures into UpstreamError, whatever client is behind them.

They sit between the routes and the real (or, in tests, fake) clients, so the same
mapping applies to every implementation. `ping` is left alone: /health reports failures
itself.
"""

from collections.abc import AsyncIterator, Sequence

from rag_api.clients.protocols import ChatMessage, ChatModel, Embedder, StoredChunk, VectorStore
from rag_api.errors import upstream
from rag_api.schemas import DocumentInfo, Hit


class GuardedEmbedder:
    def __init__(self, inner: Embedder) -> None:
        self._inner = inner

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        with upstream("embeddings"):
            return await self._inner.embed(texts)

    async def ping(self) -> str:
        return await self._inner.ping()


class GuardedChat:
    def __init__(self, inner: ChatModel) -> None:
        self._inner = inner

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        with upstream("llm"):
            async for token in self._inner.stream(messages):
                yield token

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        with upstream("llm"):
            return await self._inner.complete(messages)

    async def ping(self) -> str:
        return await self._inner.ping()


class GuardedStore:
    def __init__(self, inner: VectorStore) -> None:
        self._inner = inner

    async def ensure_collection(self, dim: int) -> None:
        with upstream("vector_store"):
            await self._inner.ensure_collection(dim)

    async def replace_document(self, filename: str, chunks: Sequence[StoredChunk]) -> None:
        with upstream("vector_store"):
            await self._inner.replace_document(filename, chunks)

    async def delete_document(self, filename: str) -> int:
        with upstream("vector_store"):
            return await self._inner.delete_document(filename)

    async def search(self, vector: Sequence[float], limit: int) -> list[Hit]:
        with upstream("vector_store"):
            return await self._inner.search(vector, limit)

    async def list_documents(self) -> list[DocumentInfo]:
        with upstream("vector_store"):
            return await self._inner.list_documents()

    async def ping(self) -> str:
        return await self._inner.ping()

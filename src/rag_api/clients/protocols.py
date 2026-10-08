from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from rag_api.schemas import DocumentInfo, Hit


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class StoredChunk:
    filename: str
    chunk_index: int
    text: str
    vector: tuple[float, ...]


class Embedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def ping(self) -> str: ...


class ChatModel(Protocol):
    def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]: ...

    async def complete(self, messages: Sequence[ChatMessage]) -> str: ...

    async def ping(self) -> str: ...


class VectorStore(Protocol):
    async def ensure_collection(self, dim: int) -> None: ...

    async def replace_document(self, filename: str, chunks: Sequence[StoredChunk]) -> None: ...

    async def delete_document(self, filename: str) -> int: ...

    async def search(self, vector: Sequence[float], limit: int) -> list[Hit]: ...

    async def list_documents(self) -> list[DocumentInfo]: ...

    async def ping(self) -> str: ...

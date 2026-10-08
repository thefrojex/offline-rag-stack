"""In-memory stand-ins for the LLM, embedding and vector store clients."""

import hashlib
import math
import re
from collections.abc import AsyncIterator, Sequence

from rag_api.clients.protocols import ChatMessage, StoredChunk
from rag_api.schemas import DocumentInfo, Hit

DIM = 64
_TOKEN = re.compile(r"[a-z0-9]+")


def _bucket(token: str) -> int:
    return int(hashlib.sha256(token.encode()).hexdigest(), 16) % DIM


class FakeEmbedder:
    """Bag-of-words hashing embedder: texts sharing words get similar vectors."""

    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy
        self.calls: list[list[str]] = []

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * DIM
            for token in _TOKEN.findall(text.lower()):
                vector[_bucket(token)] += 1.0
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            vectors.append([v / norm for v in vector])
        return vectors

    async def ping(self) -> str:
        if not self.healthy:
            raise RuntimeError("embedding model not loaded")
        return "fake embedder"


class FakeChat:
    def __init__(
        self, reply: str = "The answer is stated in the context [1].", *, healthy: bool = True
    ) -> None:
        self.reply = reply
        self.healthy = healthy
        self.seen: list[list[ChatMessage]] = []

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.seen.append(list(messages))
        for word in self.reply.split(" "):
            yield word + " "

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        self.seen.append(list(messages))
        return self.reply

    async def ping(self) -> str:
        if not self.healthy:
            raise RuntimeError("llm unreachable")
        return "fake llm"


class FakeStore:
    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy
        self.rows: dict[str, list[StoredChunk]] = {}

    async def ensure_collection(self, dim: int) -> None:
        return None

    async def replace_document(self, filename: str, chunks: Sequence[StoredChunk]) -> None:
        self.rows[filename] = list(chunks)

    async def delete_document(self, filename: str) -> int:
        return len(self.rows.pop(filename, []))

    async def search(self, vector: Sequence[float], limit: int) -> list[Hit]:
        scored = [
            Hit(
                filename=c.filename,
                chunk_index=c.chunk_index,
                text=c.text,
                score=sum(a * b for a, b in zip(vector, c.vector, strict=True)),
            )
            for chunks in self.rows.values()
            for c in chunks
        ]
        return sorted(scored, key=lambda h: h.score, reverse=True)[:limit]

    async def list_documents(self) -> list[DocumentInfo]:
        return [DocumentInfo(filename=n, chunks=len(c)) for n, c in sorted(self.rows.items())]

    async def ping(self) -> str:
        if not self.healthy:
            raise RuntimeError("qdrant unreachable")
        return "fake store"

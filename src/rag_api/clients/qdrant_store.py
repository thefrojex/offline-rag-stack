import uuid
from collections import Counter
from collections.abc import Sequence

from qdrant_client import AsyncQdrantClient, models

from rag_api.clients.protocols import StoredChunk
from rag_api.schemas import DocumentInfo, Hit

_NAMESPACE = uuid.UUID("5c1f3a7e-8d0b-4a55-9e53-2f1d0c6a7b11")


def _point_id(filename: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{filename}:{chunk_index}"))


def _by_filename(filename: str) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key="filename", match=models.MatchValue(value=filename))]
    )


class QdrantStore:
    def __init__(self, url: str, collection: str) -> None:
        self._client = AsyncQdrantClient(url=url, check_compatibility=False)
        self._collection = collection

    async def ensure_collection(self, dim: int) -> None:
        if await self._client.collection_exists(self._collection):
            info = await self._client.get_collection(self._collection)
            vectors = info.config.params.vectors
            existing = vectors.size if isinstance(vectors, models.VectorParams) else None
            if existing != dim:
                raise RuntimeError(
                    f"collection {self._collection!r} has dim {existing}, embeddings are {dim}; "
                    "use a new collection or re-ingest"
                )
            return
        await self._client.create_collection(
            self._collection,
            vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )
        await self._client.create_payload_index(
            self._collection, "filename", models.PayloadSchemaType.KEYWORD
        )

    async def replace_document(self, filename: str, chunks: Sequence[StoredChunk]) -> None:
        await self.delete_document(filename)
        points = [
            models.PointStruct(
                id=_point_id(chunk.filename, chunk.chunk_index),
                vector=list(chunk.vector),
                payload={
                    "filename": chunk.filename,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                },
            )
            for chunk in chunks
        ]
        if points:
            await self._client.upsert(self._collection, points=points, wait=True)

    async def delete_document(self, filename: str) -> int:
        before = await self._count(filename)
        if before:
            await self._client.delete(
                self._collection,
                points_selector=models.FilterSelector(filter=_by_filename(filename)),
                wait=True,
            )
        return before

    async def _count(self, filename: str) -> int:
        result = await self._client.count(
            self._collection, count_filter=_by_filename(filename), exact=True
        )
        return result.count

    async def search(self, vector: Sequence[float], limit: int) -> list[Hit]:
        response = await self._client.query_points(
            self._collection, query=list(vector), limit=limit, with_payload=True
        )
        hits: list[Hit] = []
        for point in response.points:
            payload = point.payload or {}
            hits.append(
                Hit(
                    filename=str(payload.get("filename", "")),
                    chunk_index=int(payload.get("chunk_index", 0)),
                    text=str(payload.get("text", "")),
                    score=float(point.score),
                )
            )
        return hits

    async def list_documents(self) -> list[DocumentInfo]:
        counts: Counter[str] = Counter()
        offset: models.ExtendedPointId | None = None
        while True:
            points, offset = await self._client.scroll(
                self._collection,
                limit=256,
                offset=offset,
                with_payload=["filename"],
                with_vectors=False,
            )
            counts.update(str((p.payload or {}).get("filename", "")) for p in points)
            if offset is None:
                break
        return [DocumentInfo(filename=name, chunks=n) for name, n in sorted(counts.items())]

    async def ping(self) -> str:
        collections = await self._client.get_collections()
        names = [c.name for c in collections.collections]
        return f"reachable, collections: {names}"

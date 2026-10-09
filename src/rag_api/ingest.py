import logging
import time

from rag_api.chunking import chunk_text
from rag_api.clients.protocols import Embedder, StoredChunk, VectorStore
from rag_api.parsing import parse_document
from rag_api.schemas import IngestResult
from rag_api.settings import Settings

logger = logging.getLogger(__name__)


async def ingest_document(
    filename: str,
    data: bytes,
    *,
    settings: Settings,
    embedder: Embedder,
    store: VectorStore,
) -> IngestResult:
    """Parse, chunk, embed and upsert one file. Re-ingesting a filename replaces it."""
    started = time.perf_counter()
    text = parse_document(filename, data)
    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    vectors = await embedder.embed([settings.embed_document_prefix + c.text for c in chunks])
    if len(vectors) != len(chunks):
        raise RuntimeError(f"embedder returned {len(vectors)} vectors for {len(chunks)} chunks")
    await store.ensure_collection(len(vectors[0]) if vectors else settings.embed_dim)
    await store.replace_document(
        filename,
        [
            StoredChunk(filename, chunk.index, chunk.text, tuple(vector))
            for chunk, vector in zip(chunks, vectors, strict=True)
        ],
    )
    logger.info(
        "document ingested",
        extra={
            "document": filename,
            "chunks": len(chunks),
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return IngestResult(filename=filename, status="ingested", chunks=len(chunks))

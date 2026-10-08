from collections.abc import Sequence

from rag_api.clients.protocols import ChatMessage, Embedder, VectorStore
from rag_api.schemas import Hit, Source
from rag_api.settings import Settings

SYSTEM_PROMPT = (
    "You answer questions using only the numbered context passages provided. "
    "Cite the passages you used with their numbers in square brackets, like [1] or [2][3]. "
    "If the context does not contain the answer, reply exactly: "
    "I could not find that in the provided documents. "
    "Keep answers short and factual."
)


async def retrieve(
    question: str,
    *,
    settings: Settings,
    embedder: Embedder,
    store: VectorStore,
    top_k: int | None = None,
) -> list[Hit]:
    vectors = await embedder.embed([settings.embed_query_prefix + question])
    return await store.search(vectors[0], top_k or settings.top_k)


def to_sources(hits: Sequence[Hit]) -> tuple[Source, ...]:
    return tuple(
        Source(
            n=position,
            filename=hit.filename,
            chunk_index=hit.chunk_index,
            score=round(hit.score, 4),
            text=hit.text,
        )
        for position, hit in enumerate(hits, start=1)
    )


def build_messages(question: str, sources: Sequence[Source]) -> list[ChatMessage]:
    context = "\n\n".join(
        f"[{s.n}] ({s.filename}, chunk {s.chunk_index})\n{s.text}" for s in sources
    )
    user = f"Context:\n{context}\n\nQuestion: {question}"
    return [ChatMessage("system", SYSTEM_PROMPT), ChatMessage("user", user)]

import json
import logging
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from rag_api.deps import Deps, get_deps
from rag_api.retrieval import build_messages, retrieve, to_sources
from rag_api.schemas import QueryRequest, QueryResponse, Source

router = APIRouter()
logger = logging.getLogger(__name__)


def _event(name: str, payload: object) -> str:
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"


async def _stream_answer(
    deps: Deps, request: QueryRequest, sources: tuple[Source, ...]
) -> AsyncIterator[str]:
    started = time.perf_counter()
    yield _event("sources", [s.model_dump() for s in sources])
    first_token_ms: int | None = None
    try:
        async for token in deps.chat.stream(build_messages(request.question, sources)):
            if first_token_ms is None:
                first_token_ms = round((time.perf_counter() - started) * 1000)
            yield _event("token", token)
    except Exception as exc:
        logger.exception("generation failed")
        yield _event("error", f"{type(exc).__name__}: {exc}"[:300])
        return
    logger.info(
        "query answered",
        extra={
            "first_token_ms": first_token_ms,
            "total_ms": round((time.perf_counter() - started) * 1000),
            "sources": len(sources),
        },
    )
    yield _event("done", {"total_ms": round((time.perf_counter() - started) * 1000)})


@router.post("/query", response_model=None)
async def query(
    request: QueryRequest,
    deps: Deps = Depends(get_deps),  # noqa: B008
) -> StreamingResponse | QueryResponse:
    hits = await retrieve(
        request.question,
        settings=deps.settings,
        embedder=deps.embedder,
        store=deps.store,
        top_k=request.top_k,
    )
    sources = to_sources(hits)
    if request.stream:
        return StreamingResponse(
            _stream_answer(deps, request, sources),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    answer = await deps.chat.complete(build_messages(request.question, sources))
    return QueryResponse(answer=answer, sources=sources)

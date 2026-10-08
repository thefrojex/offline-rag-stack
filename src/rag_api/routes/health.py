import asyncio
import logging
from collections.abc import Awaitable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from rag_api import __version__
from rag_api.deps import Deps, get_deps
from rag_api.schemas import ComponentHealth, HealthResponse, InfoResponse

router = APIRouter()
logger = logging.getLogger(__name__)


async def _check(probe: Awaitable[str]) -> ComponentHealth:
    try:
        return ComponentHealth(ok=True, detail=await asyncio.wait_for(probe, timeout=15))
    except Exception as exc:
        return ComponentHealth(ok=False, detail=f"{type(exc).__name__}: {exc}"[:300])


@router.get("/livez")
async def livez() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health", response_model=HealthResponse)
async def health(deps: Deps = Depends(get_deps)) -> JSONResponse:  # noqa: B008
    llm, embeddings, qdrant = await asyncio.gather(
        _check(deps.chat.ping()), _check(deps.embedder.ping()), _check(deps.store.ping())
    )
    healthy = llm.ok and embeddings.ok and qdrant.ok
    body = HealthResponse(
        status="ok" if healthy else "degraded", llm=llm, embeddings=embeddings, qdrant=qdrant
    )
    return JSONResponse(body.model_dump(), status_code=200 if healthy else 503)


@router.get("/info", response_model=InfoResponse)
async def info(deps: Deps = Depends(get_deps)) -> InfoResponse:  # noqa: B008
    settings = deps.settings
    return InfoResponse(
        version=__version__,
        llm_model=settings.llm_model,
        embed_model=settings.embed_model,
        top_k=settings.top_k,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

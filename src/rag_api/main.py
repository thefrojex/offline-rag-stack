import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse

from rag_api import __version__
from rag_api.clients.guarded import GuardedChat, GuardedEmbedder, GuardedStore
from rag_api.clients.openai_compat import OpenAIChat, OpenAIEmbedder
from rag_api.clients.protocols import ChatModel, Embedder, VectorStore
from rag_api.clients.qdrant_store import QdrantStore
from rag_api.deps import Deps
from rag_api.errors import UpstreamError, upstream_error_handler
from rag_api.log import configure_logging
from rag_api.routes import documents, health, query
from rag_api.settings import Settings, get_settings

STATIC_DIR = Path(__file__).parent / "static"
logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    embedder: Embedder | None = None,
    chat: ChatModel | None = None,
    store: VectorStore | None = None,
) -> FastAPI:
    """Build the app. Any client can be injected, which is how tests avoid real models."""
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)
    deps = Deps(
        settings=resolved,
        embedder=GuardedEmbedder(embedder or OpenAIEmbedder(resolved)),
        chat=GuardedChat(chat or OpenAIChat(resolved)),
        store=GuardedStore(store or QdrantStore(resolved.qdrant_url, resolved.qdrant_collection)),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "starting",
            extra={
                "llm_base_url": resolved.llm_base_url,
                "llm_model": resolved.llm_model,
                "embed_base_url": resolved.embed_base_url,
                "embed_model": resolved.embed_model,
                "qdrant_url": resolved.qdrant_url,
            },
        )
        yield

    app = FastAPI(title="offline-rag-stack", version=__version__, lifespan=lifespan)
    app.state.deps = deps
    app.add_exception_handler(UpstreamError, upstream_error_handler)

    @app.middleware("http")
    async def access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        if request.url.path != "/livez":
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
        return response

    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(query.router)

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app

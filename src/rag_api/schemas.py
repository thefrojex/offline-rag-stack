from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Hit(Frozen):
    """One retrieved chunk."""

    filename: str
    chunk_index: int
    text: str
    score: float


class Source(Frozen):
    """A citation returned with an answer. `n` matches the [n] markers in the text."""

    n: int
    filename: str
    chunk_index: int
    score: float
    text: str


class QueryRequest(Frozen):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, gt=0, le=20)
    stream: bool = True


class QueryResponse(Frozen):
    answer: str
    sources: tuple[Source, ...]


class IngestResult(Frozen):
    filename: str
    status: Literal["ingested", "skipped"]
    chunks: int = 0
    reason: str | None = None


class IngestResponse(Frozen):
    results: tuple[IngestResult, ...]


class DocumentInfo(Frozen):
    filename: str
    chunks: int


class ComponentHealth(Frozen):
    ok: bool
    detail: str


class HealthResponse(Frozen):
    status: Literal["ok", "degraded"]
    llm: ComponentHealth
    embeddings: ComponentHealth
    qdrant: ComponentHealth


class InfoResponse(Frozen):
    version: str
    llm_model: str
    embed_model: str
    top_k: int
    chunk_size: int
    chunk_overlap: int

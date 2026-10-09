import logging
from pathlib import PurePath

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from rag_api.deps import Deps, get_deps
from rag_api.ingest import ingest_document
from rag_api.parsing import EmptyDocumentError, UnsupportedFormatError
from rag_api.schemas import DocumentInfo, IngestResponse, IngestResult

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/ingest", response_model=IngestResponse)
async def ingest(files: list[UploadFile], deps: Deps = Depends(get_deps)) -> IngestResponse:  # noqa: B008
    limit = deps.settings.max_upload_mb * 1024 * 1024
    results: list[IngestResult] = []
    for upload in files:
        filename = PurePath(upload.filename or "upload").name
        data = await upload.read(limit + 1)
        if len(data) > limit:
            results.append(
                IngestResult(
                    filename=filename,
                    status="skipped",
                    reason=f"larger than {deps.settings.max_upload_mb} MB",
                )
            )
            continue
        try:
            results.append(
                await ingest_document(
                    filename,
                    data,
                    settings=deps.settings,
                    embedder=deps.embedder,
                    store=deps.store,
                )
            )
        except (UnsupportedFormatError, EmptyDocumentError) as exc:
            results.append(IngestResult(filename=filename, status="skipped", reason=str(exc)))
    return IngestResponse(results=tuple(results))


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents(deps: Deps = Depends(get_deps)) -> list[DocumentInfo]:  # noqa: B008
    return await deps.store.list_documents()


@router.delete("/documents/{filename}")
async def delete_document(filename: str, deps: Deps = Depends(get_deps)) -> dict[str, int]:  # noqa: B008
    removed = await deps.store.delete_document(filename)
    if not removed:
        raise HTTPException(status_code=404, detail="document not found")
    return {"removed_chunks": removed}

import pytest

from rag_api.ingest import ingest_document
from rag_api.parsing import UnsupportedFormatError
from rag_api.settings import Settings
from tests.fakes import FakeEmbedder, FakeStore

TEXT = "\n\n".join(f"Paragraph {i} describes the {i}th procedure in detail. " * 4 for i in range(6))


async def test_ingest_embeds_and_stores_every_chunk(
    settings: Settings, embedder: FakeEmbedder, store: FakeStore
) -> None:
    result = await ingest_document(
        "runbook.md", TEXT.encode(), settings=settings, embedder=embedder, store=store
    )
    stored = store.rows["runbook.md"]
    assert result.status == "ingested"
    assert result.chunks == len(stored) > 1
    assert [c.chunk_index for c in stored] == list(range(len(stored)))
    assert all(len(c.vector) == len(stored[0].vector) for c in stored)


async def test_document_prefix_is_applied_to_embedded_text_only(
    settings: Settings, embedder: FakeEmbedder, store: FakeStore
) -> None:
    await ingest_document(
        "a.txt", b"Plain text.", settings=settings, embedder=embedder, store=store
    )
    assert embedder.calls[0] == [settings.embed_document_prefix + "Plain text."]
    assert store.rows["a.txt"][0].text == "Plain text."


async def test_reingesting_a_filename_replaces_old_chunks(
    settings: Settings, embedder: FakeEmbedder, store: FakeStore
) -> None:
    await ingest_document("a.txt", TEXT.encode(), settings=settings, embedder=embedder, store=store)
    await ingest_document(
        "a.txt", b"Only one line now.", settings=settings, embedder=embedder, store=store
    )
    assert [c.text for c in store.rows["a.txt"]] == ["Only one line now."]


async def test_unsupported_file_is_rejected_before_embedding(
    settings: Settings, embedder: FakeEmbedder, store: FakeStore
) -> None:
    with pytest.raises(UnsupportedFormatError):
        await ingest_document("a.exe", b"MZ", settings=settings, embedder=embedder, store=store)
    assert embedder.calls == []
    assert store.rows == {}

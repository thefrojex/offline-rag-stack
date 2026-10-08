from rag_api.ingest import ingest_document
from rag_api.retrieval import SYSTEM_PROMPT, build_messages, retrieve, to_sources
from rag_api.schemas import Hit
from rag_api.settings import Settings
from tests.fakes import FakeEmbedder, FakeStore


async def _load(settings: Settings, embedder: FakeEmbedder, store: FakeStore) -> None:
    docs = {
        "tides.md": "Harbor pilots board inbound vessels at the outer buoy during spring tides.",
        "payroll.md": "Payroll is processed on the last business day of each month by finance.",
        "fire.md": "The fire marshal inspects extinguisher pressure gauges every quarter.",
    }
    for name, body in docs.items():
        await ingest_document(
            name, body.encode(), settings=settings, embedder=embedder, store=store
        )


async def test_retrieve_ranks_the_relevant_document_first(
    settings: Settings, embedder: FakeEmbedder, store: FakeStore
) -> None:
    await _load(settings, embedder, store)
    hits = await retrieve(
        "when is payroll processed", settings=settings, embedder=embedder, store=store
    )
    assert hits[0].filename == "payroll.md"
    assert hits[0].score >= hits[-1].score


async def test_retrieve_honours_top_k(
    settings: Settings, embedder: FakeEmbedder, store: FakeStore
) -> None:
    await _load(settings, embedder, store)
    one = await retrieve("fire", settings=settings, embedder=embedder, store=store, top_k=1)
    default = await retrieve("fire", settings=settings, embedder=embedder, store=store)
    assert len(one) == 1
    assert len(default) == settings.top_k


async def test_query_text_gets_the_query_prefix(
    settings: Settings, embedder: FakeEmbedder, store: FakeStore
) -> None:
    await retrieve("anything", settings=settings, embedder=embedder, store=store)
    assert embedder.calls[-1] == [settings.embed_query_prefix + "anything"]


def test_sources_are_numbered_from_one() -> None:
    hits = [
        Hit(filename="a.md", chunk_index=3, text="alpha", score=0.912345),
        Hit(filename="b.md", chunk_index=0, text="beta", score=0.5),
    ]
    sources = to_sources(hits)
    assert [s.n for s in sources] == [1, 2]
    assert (sources[0].filename, sources[0].chunk_index, sources[0].score) == ("a.md", 3, 0.9123)


def test_prompt_contains_numbered_context_and_question() -> None:
    sources = to_sources([Hit(filename="a.md", chunk_index=2, text="alpha fact", score=0.9)])
    system, user = build_messages("What is alpha?", sources)
    assert system.role == "system"
    assert system.content == SYSTEM_PROMPT
    assert "[1] (a.md, chunk 2)\nalpha fact" in user.content
    assert user.content.endswith("Question: What is alpha?")

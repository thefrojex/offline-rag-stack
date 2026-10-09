import json

import pytest
from fastapi.testclient import TestClient

from rag_api.main import create_app
from rag_api.settings import Settings
from tests.fakes import FakeChat, FakeEmbedder, FakeStore


def _upload(client: TestClient, name: str, body: bytes) -> dict[str, object]:
    response = client.post("/ingest", files=[("files", (name, body, "text/plain"))])
    assert response.status_code == 200
    result: dict[str, object] = response.json()
    return result


def _events(raw: str) -> list[tuple[str, object]]:
    parsed: list[tuple[str, object]] = []
    for block in raw.strip().split("\n\n"):
        name = block.splitlines()[0].removeprefix("event: ")
        data = json.loads(block.splitlines()[1].removeprefix("data: "))
        parsed.append((name, data))
    return parsed


def test_ingest_reports_each_file(client: TestClient) -> None:
    response = client.post(
        "/ingest",
        files=[
            ("files", ("good.md", b"The vault code rotates every Monday.", "text/markdown")),
            ("files", ("bad.exe", b"MZ", "application/octet-stream")),
            ("files", ("empty.txt", b"   ", "text/plain")),
        ],
    )
    results = {r["filename"]: r for r in response.json()["results"]}
    assert results["good.md"]["status"] == "ingested"
    assert results["bad.exe"]["status"] == "skipped"
    assert "unsupported" in results["bad.exe"]["reason"]
    assert results["empty.txt"]["status"] == "skipped"


def test_ingest_strips_directories_from_filenames(client: TestClient, store: FakeStore) -> None:
    _upload(client, "../../etc/notes.txt", b"harmless text")
    assert list(store.rows) == ["notes.txt"]


def test_oversized_upload_is_skipped(client: TestClient, settings, store: FakeStore) -> None:  # type: ignore[no-untyped-def]
    from rag_api.main import create_app

    small = settings.model_copy(update={"max_upload_mb": 1})
    app = create_app(small, embedder=FakeEmbedder(), chat=FakeChat(), store=store)
    with TestClient(app) as tight:
        response = tight.post("/ingest", files=[("files", ("big.txt", b"a" * (1024 * 1024 + 1)))])
    assert response.json()["results"][0]["status"] == "skipped"
    assert store.rows == {}


def test_list_and_delete_documents(client: TestClient) -> None:
    _upload(client, "one.txt", b"first document text")
    assert client.get("/documents").json() == [{"filename": "one.txt", "chunks": 1}]
    assert client.delete("/documents/one.txt").json() == {"removed_chunks": 1}
    assert client.delete("/documents/one.txt").status_code == 404
    assert client.get("/documents").json() == []


def test_query_streams_sources_then_tokens_then_done(client: TestClient) -> None:
    _upload(client, "ops.md", b"Backups run nightly at two in the morning.")
    response = client.post("/query", json={"question": "When do backups run?"})
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    names = [name for name, _ in events]
    assert names[0] == "sources"
    assert names[-1] == "done"
    assert set(names[1:-1]) == {"token"}
    sources = events[0][1]
    assert isinstance(sources, list)
    assert sources[0]["filename"] == "ops.md"
    assert sources[0]["chunk_index"] == 0
    answer = "".join(str(data) for name, data in events if name == "token")
    assert answer.strip() == "The answer is stated in the context [1]."


def test_query_without_streaming_returns_json(client: TestClient) -> None:
    _upload(client, "ops.md", b"Backups run nightly at two in the morning.")
    body = client.post("/query", json={"question": "When?", "stream": False}).json()
    assert body["answer"] == "The answer is stated in the context [1]."
    assert body["sources"][0]["n"] == 1


def test_query_sends_retrieved_context_to_the_llm(client: TestClient, chat: FakeChat) -> None:
    _upload(client, "ops.md", b"Backups run nightly at two in the morning.")
    client.post("/query", json={"question": "When do backups run?", "stream": False})
    system, user = chat.seen[-1]
    assert system.role == "system"
    assert "Backups run nightly" in user.content
    assert "When do backups run?" in user.content


def test_query_validates_input(client: TestClient) -> None:
    assert client.post("/query", json={"question": ""}).status_code == 422
    assert client.post("/query", json={"question": "x", "top_k": 0}).status_code == 422


def test_stream_reports_llm_failure_as_an_error_event(client: TestClient, chat: FakeChat) -> None:
    async def broken(_messages):  # type: ignore[no-untyped-def]
        raise RuntimeError("model crashed")
        yield  # pragma: no cover

    chat.stream = broken  # type: ignore[method-assign]
    _upload(client, "ops.md", b"Some indexed text.")
    names = [n for n, _ in _events(client.post("/query", json={"question": "x"}).text)]
    assert names == ["sources", "error"]


def test_index_page_is_served(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "offline-rag-stack" in response.text


def test_info_level_logging_works_and_emits_json(
    capsys: pytest.CaptureFixture[str], settings: Settings
) -> None:
    verbose = settings.model_copy(update={"log_level": "INFO"})
    app = create_app(verbose, embedder=FakeEmbedder(), chat=FakeChat(), store=FakeStore())
    with TestClient(app) as client:
        client.post("/ingest", files=[("files", ("ops.md", b"Backups run nightly."))])
        client.post("/query", json={"question": "When?", "stream": False})
        client.post("/query", json={"question": "When?"})
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    messages = {r["msg"] for r in records}
    assert {"document ingested", "request", "query answered"} <= messages
    ingested = next(r for r in records if r["msg"] == "document ingested")
    assert ingested["document"] == "ops.md"
    assert ingested["chunks"] == 1

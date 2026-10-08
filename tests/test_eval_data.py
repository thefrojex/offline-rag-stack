import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = json.loads((ROOT / "eval" / "questions.json").read_text())


def test_there_are_ten_questions() -> None:
    assert len(QUESTIONS) == 10


def test_every_evidence_phrase_exists_in_its_document() -> None:
    for item in QUESTIONS:
        document = (ROOT / "eval" / "docs" / item["expected_file"]).read_text()
        assert item["evidence"].lower() in document.lower(), item["question"]


def test_every_answer_keyword_exists_in_its_document() -> None:
    for item in QUESTIONS:
        document = (ROOT / "eval" / "docs" / item["expected_file"]).read_text().lower()
        assert any(k.lower() in document for k in item["answer_keywords"]), item["question"]

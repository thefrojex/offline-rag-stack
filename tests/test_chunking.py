from itertools import pairwise

import pytest

from rag_api.chunking import chunk_text


def test_short_text_is_one_chunk() -> None:
    chunks = chunk_text("One short paragraph.", size=200, overlap=20)
    assert [c.text for c in chunks] == ["One short paragraph."]
    assert chunks[0].index == 0


def test_empty_and_blank_text_produce_no_chunks() -> None:
    assert chunk_text("", 200, 20) == ()
    assert chunk_text("  \n\n \t ", 200, 20) == ()


def test_chunks_respect_size_limit() -> None:
    text = " ".join(f"Sentence number {i} is here." for i in range(200))
    chunks = chunk_text(text, size=250, overlap=40)
    assert len(chunks) > 5
    assert all(len(c.text) <= 250 for c in chunks)


def test_paragraph_boundaries_are_preferred() -> None:
    first = "Alpha beta gamma. " * 8
    second = "Delta epsilon zeta. " * 8
    chunks = chunk_text(f"{first.strip()}\n\n{second.strip()}", size=170, overlap=0)
    assert len(chunks) == 2
    assert chunks[0].text.startswith("Alpha")
    assert chunks[1].text.startswith("Delta")


def test_chunks_start_on_sentence_boundaries() -> None:
    text = " ".join(f"Item {i} was recorded on the log." for i in range(60))
    for chunk in chunk_text(text, size=200, overlap=60):
        assert chunk.text.startswith("Item ")
        assert chunk.text.endswith(".")


def test_overlap_repeats_trailing_sentences() -> None:
    text = " ".join(f"Fact {i} holds." for i in range(40))
    chunks = chunk_text(text, size=120, overlap=40)
    for previous, current in pairwise(chunks):
        last_sentence = previous.text.split(". ")[-1]
        assert last_sentence.rstrip(".") in current.text


def test_zero_overlap_does_not_repeat_text() -> None:
    text = " ".join(f"Fact {i} holds." for i in range(40))
    chunks = chunk_text(text, size=120, overlap=0)
    assert " ".join(c.text for c in chunks) == text


def test_oversized_word_is_hard_split() -> None:
    chunks = chunk_text("x" * 1000, size=300, overlap=0)
    assert [len(c.text) for c in chunks] == [300, 300, 300, 100]


def test_indexes_are_sequential() -> None:
    chunks = chunk_text("Para one.\n\nPara two.\n\nPara three.", size=12, overlap=0)
    assert [c.index for c in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (100, 100), (100, -1)])
def test_invalid_parameters_raise(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("text", size, overlap)

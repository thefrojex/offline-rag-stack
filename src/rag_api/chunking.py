"""Boundary-aware chunking.

Text is split on paragraph breaks first, then sentences, then words, and the
pieces are packed into chunks of at most `size` characters. Consecutive chunks
share up to `overlap` characters of trailing context, taken on piece boundaries
so a chunk never starts mid-sentence unless a single sentence is longer than
`size`.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


@dataclass(frozen=True, slots=True)
class Chunk:
    index: int
    text: str


def _split_words(text: str, size: int) -> Iterator[str]:
    current = ""
    for word in text.split():
        while len(word) > size:
            if current:
                yield current
                current = ""
            yield word[:size]
            word = word[size:]
        candidate = f"{current} {word}".strip()
        if len(candidate) > size:
            yield current
            current = word
        else:
            current = candidate
    if current:
        yield current


def _pieces(text: str, size: int) -> Iterator[str]:
    for paragraph in _PARAGRAPH.split(text):
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue
        if len(paragraph) <= size:
            yield paragraph
            continue
        for sentence in _SENTENCE.split(paragraph):
            if len(sentence) <= size:
                yield sentence
            else:
                yield from _split_words(sentence, size)


def _tail(pieces: list[str], overlap: int) -> list[str]:
    kept: list[str] = []
    total = 0
    for piece in reversed(pieces):
        added = len(piece) + (1 if kept else 0)
        if total + added > overlap:
            break
        kept.insert(0, piece)
        total += added
    return kept


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> tuple[Chunk, ...]:
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be >= 0 and smaller than size")

    chunks: list[Chunk] = []
    window: list[str] = []
    length = 0
    for piece in _pieces(text, size):
        extra = len(piece) + (1 if window else 0)
        if window and length + extra > size:
            chunks.append(Chunk(index=len(chunks), text=" ".join(window)))
            window = _tail(window, overlap)
            length = len(" ".join(window))
            extra = len(piece) + (1 if window else 0)
            if length + extra > size:
                window, length = [], 0
                extra = len(piece)
        window.append(piece)
        length += extra
    if window:
        chunks.append(Chunk(index=len(chunks), text=" ".join(window)))
    return tuple(chunks)

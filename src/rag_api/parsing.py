import io
from pathlib import PurePath

from docx import Document
from pypdf import PdfReader

SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".txt", ".md"})


class UnsupportedFormatError(ValueError):
    """Raised for file types the ingest pipeline cannot read."""


class EmptyDocumentError(ValueError):
    """Raised when a file parses but contains no text."""


def _read_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    return "\n\n".join(paragraph.text for paragraph in document.paragraphs)


def parse_document(filename: str, data: bytes) -> str:
    suffix = PurePath(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedFormatError(f"unsupported file type: {suffix or 'none'}")
    if suffix == ".pdf":
        text = _read_pdf(data)
    elif suffix == ".docx":
        text = _read_docx(data)
    else:
        text = data.decode("utf-8", errors="replace")
    if not text.strip():
        raise EmptyDocumentError(f"no extractable text in {filename}")
    return text

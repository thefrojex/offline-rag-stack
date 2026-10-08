import io

import pytest
from docx import Document

from rag_api.parsing import EmptyDocumentError, UnsupportedFormatError, parse_document


def _docx_bytes(*paragraphs: str) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _pdf_bytes(text: str) -> bytes:
    """A minimal one-page PDF with `text` drawn in Helvetica."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


def test_reads_plain_text_and_markdown() -> None:
    assert parse_document("a.txt", b"hello world") == "hello world"
    assert parse_document("notes.MD", b"# Title\n\nbody") == "# Title\n\nbody"


def test_reads_docx_paragraphs() -> None:
    text = parse_document("a.docx", _docx_bytes("First paragraph.", "Second paragraph."))
    assert "First paragraph." in text
    assert "Second paragraph." in text


def test_reads_pdf_text() -> None:
    assert "Quarterly retention policy" in parse_document(
        "a.pdf", _pdf_bytes("Quarterly retention policy")
    )


def test_rejects_unsupported_extension() -> None:
    with pytest.raises(UnsupportedFormatError):
        parse_document("a.exe", b"MZ")


def test_rejects_empty_document() -> None:
    with pytest.raises(EmptyDocumentError):
        parse_document("a.txt", b"   \n  ")

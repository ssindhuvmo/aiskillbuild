"""Upload checks and text extraction (no LLM)."""
import pytest

from core.agents.resume_parser import extract
from tests.resume_files import RESUME_LINES, make_docx, make_pdf


def test_docx_paragraphs_and_tables():
    content = make_docx(["Jane Doe", "Skills: Python"], table=[["Acme", "Engineer"]])
    kind, text = extract.read("cv.docx", content)
    assert kind == "docx"
    assert "Skills: Python" in text and "Acme | Engineer" in text


def test_pdf_text():
    kind, text = extract.read("cv.PDF", make_pdf(RESUME_LINES))
    assert kind == "pdf"
    assert "Acme Payments" in text and "PostgreSQL" in text


def test_too_large_is_413():
    with pytest.raises(extract.InvalidFile) as e:
        extract.read("cv.pdf", b"%PDF-" + b"0" * extract.MAX_BYTES)
    assert e.value.status == 413


@pytest.mark.parametrize("name, content", [
    ("cv.exe", b"MZ\x90\x00"),
    ("cv.pdf", b"MZ\x90\x00"),  # renamed executable
    ("cv.docx", b"%PDF-1.4"),  # wrong magic for the extension
    ("cv.docx", b"PK\x03\x04not a zip"),
    ("cv.txt", b"just text"),
    ("cv", b"%PDF-1.4"),
])
def test_wrong_type_is_415(name, content):
    with pytest.raises(extract.InvalidFile) as e:
        extract.read(name, content)
    assert e.value.status == 415


def test_zip_without_word_document_is_415():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(extract.InvalidFile) as e:
        extract.read("cv.docx", buf.getvalue())
    assert e.value.status == 415


def test_pdf_without_text_is_422():
    with pytest.raises(extract.InvalidFile) as e:
        extract.read("scan.pdf", make_pdf([]))
    assert e.value.status == 422


def test_long_text_is_truncated():
    _, text = extract.read("cv.docx", make_docx(["x" * 1000] * 40))
    assert len(text) == extract.MAX_CHARS

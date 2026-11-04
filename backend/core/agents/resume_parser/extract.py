"""Checks an uploaded resume and extracts its text (pure: no DB, no LLM). The file is untrusted:
the type comes from its bytes, not from its name or the browser's content type."""
import io
import zipfile

MAX_BYTES = 5 * 1024 * 1024
MAX_CHARS = 30_000  # text the parser reads; longer resumes are truncated
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class InvalidFile(Exception):
    """The upload can't be used; `status` is the HTTP status to answer with."""

    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


def detect_type(filename: str, content: bytes) -> str:
    """"pdf" or "docx", checked by extension and by magic bytes."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf" and content.startswith(b"%PDF-"):
        return "pdf"
    if ext == "docx" and content.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                if "word/document.xml" in z.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
    raise InvalidFile(415, "Upload a PDF or DOCX file.")


def _pdf_text(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _docx_text(content: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(content))
    lines = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(lines)


def read(filename: str, content: bytes) -> tuple[str, str]:
    """Validate the upload and return (kind, text). Raises InvalidFile."""
    if len(content) > MAX_BYTES:
        raise InvalidFile(413, "The file is larger than 5 MB.")
    kind = detect_type(filename, content)
    try:
        text = _pdf_text(content) if kind == "pdf" else _docx_text(content)
    except Exception:  # a damaged file: the libraries raise many different errors
        raise InvalidFile(422, "We couldn't read this file. Try saving it again as PDF or DOCX, or skip this step.")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not text:
        raise InvalidFile(422, "We couldn't read text from this file (it may be a scanned image). Upload a DOCX or skip.")
    return kind, text[:MAX_CHARS]

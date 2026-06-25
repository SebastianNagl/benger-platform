"""Document text extraction for comfortable exam setup (issue #35).

Law students set up training cases from a Word file, a text-layer PDF, or
pasted text — one document per field (Angabe, Musterlösung, optional rubric /
Gliederung). This module turns an uploaded document into plain text/markdown
the student can review and edit in the editor.

Supported (communicated explicitly in the UI):
- ``.docx`` (Word) via python-mammoth → Markdown (fits the Milkdown editors).
- text-layer ``.pdf`` via pdfplumber.
- ``.txt`` / ``.md`` plain text.

Deliberately NOT supported (fails loud, no silent OCR): image-only / scanned
PDFs with no text layer. The caller maps :class:`UnsupportedDocumentError` to a
422 with a clear German message so the student knows to paste the text or
upload a searchable version instead.

Pure functions over bytes — no DB, no HTTP — so they unit-test against fixture
files directly.
"""

import io
import os

# Hard cap on the document size we will parse (defense-in-depth; the endpoint
# also enforces it before reading the whole body). Documents for a single exam
# field are small; 15 MB is generous.
MAX_EXTRACT_BYTES = 15 * 1024 * 1024

_DOCX_EXTS = {".docx"}
_PDF_EXTS = {".pdf"}
_TEXT_EXTS = {".txt", ".md", ".markdown", ".text"}


class UnsupportedDocumentError(Exception):
    """Raised when a document cannot be extracted losslessly.

    ``code`` is a machine-readable token the frontend maps to localized copy;
    ``message`` is a human-readable fallback.
    """

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _extract_docx(data: bytes) -> str:
    import mammoth

    result = mammoth.convert_to_markdown(io.BytesIO(data))
    return (result.value or "").strip()


def _extract_pdf(data: bytes) -> str:
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if txt:
                parts.append(txt)
    text = "\n\n".join(parts).strip()
    if not text:
        # No extractable text layer → almost certainly a scanned/image PDF.
        # Fail loud rather than silently returning an empty Angabe.
        raise UnsupportedDocumentError(
            code="pdf_no_text_layer",
            message=(
                "Dieses PDF enthält keine Textebene (vermutlich ein Scan). "
                "Bitte füge den Text direkt ein oder lade eine durchsuchbare "
                "PDF-Version hoch."
            ),
        )
    return text


def _extract_text(data: bytes) -> str:
    # utf-8 with a permissive fallback so an odd encoding doesn't hard-fail.
    try:
        return data.decode("utf-8").strip()
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace").strip()


def extract_text(filename: str, data: bytes) -> dict:
    """Extract plain text / Markdown from an uploaded document.

    Returns ``{"text": str, "source_format": "docx"|"pdf"|"text", "warnings":
    [..]}``. Raises :class:`UnsupportedDocumentError` for an unsupported type or
    a PDF with no text layer, and ``ValueError`` when the document exceeds
    :data:`MAX_EXTRACT_BYTES`.
    """
    if len(data) > MAX_EXTRACT_BYTES:
        raise ValueError(
            f"Document exceeds the {MAX_EXTRACT_BYTES // (1024 * 1024)} MB limit."
        )

    ext = os.path.splitext(filename or "")[1].lower()
    warnings: list[str] = []

    if ext in _DOCX_EXTS:
        text = _extract_docx(data)
        source_format = "docx"
    elif ext in _PDF_EXTS:
        text = _extract_pdf(data)
        source_format = "pdf"
    elif ext in _TEXT_EXTS:
        text = _extract_text(data)
        source_format = "text"
    else:
        raise UnsupportedDocumentError(
            code="unsupported_type",
            message=(
                "Nicht unterstütztes Dateiformat. Unterstützt werden Word "
                "(.docx), text-basierte PDFs und Textdateien (.txt, .md). "
                "Bild-PDFs (Scans) werden nicht unterstützt."
            ),
        )

    if not text:
        warnings.append("Das Dokument enthielt keinen extrahierbaren Text.")

    return {"text": text, "source_format": source_format, "warnings": warnings}

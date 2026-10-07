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
import re

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


# Word bookmarks (every table-of-contents target, cross references) come out of
# mammoth as empty HTML anchors; the TOC itself as links to those anchors.
# Neither means anything outside the Word file, and both end up verbatim in the
# Musterlösung the judge and the students read.
_EMPTY_ANCHOR_RE = re.compile(r"<a\s+(?:name|id)\s*=\s*(?:\"[^\"]*\"|'[^']*')\s*>\s*</a>", re.IGNORECASE)
# mammoth 1.13 escapes the target ("(\\#\\_Toc…)"), older versions do not.
_INTERNAL_LINK_RE = re.compile(r"\[((?:[^\[\]\\]|\\.)*)\]\(\\?#[^()\s]*\)")
# mammoth 1.13 also escapes external link targets ("(https://www\.x\-y\.de/)").
# Markdown renderers undo that, but the raw text reaches the judge verbatim, so
# drop the escapes; ``\(`` and ``\)`` stay so the target keeps balanced parens.
_LINK_TARGET_RE = re.compile(r"\]\(((?:[^()\s\\]|\\.)*)\)")
_TARGET_ESCAPE_RE = re.compile(r"\\([!-'*-/:-@\[\]^_`{|}~])")


# mammoth escapes every character Markdown could ever treat as syntax
# (\\ ` * _ { } [ ] ( ) # + - . !), wherever it stands. Most of those are
# plain prose in a legal text ("Abs. 1", "(1)", "§§ 433-435") and the escapes
# reach the judge and the graders verbatim ("Abs\\. 1", "\\(1\\)"). These
# can never start Markdown syntax in mid-line, so their escape is dropped;
# ``[ ] * _ `` and backslashes stay escaped. A backslash only escapes when an
# even number of backslashes precedes it (mammoth doubles literal ones).
_INERT_ESCAPE_RE = re.compile(r"(?<!\\)((?:\\\\)*)\\([(){}!])")
# ``-``, ``+`` and ``#`` start a list or heading only as a line's first
# character; ``.`` starts an ordered list only right after a leading number.
_LINE_ESCAPE_RE = re.compile(r"(?<!\\)((?:\\\\)*)\\([-+#.])")
_BLANK_PREFIX_RE = re.compile(r"^\s*$")
_NUMBER_PREFIX_RE = re.compile(r"^\s*\d+$")


def _unescape_line(line: str, at_line_start: bool = True) -> str:
    """Drop inert escapes from ``line``; ``at_line_start`` is False for a
    segment that continues a line (after a link), where nothing starts syntax."""

    def keep_at_start(m: re.Match) -> str:
        # The text before the escaping backslash decides.
        prefix = line[: m.start() + len(m.group(1))]
        starts_syntax = at_line_start and (
            _NUMBER_PREFIX_RE.match(prefix)
            if m.group(2) == "."
            else _BLANK_PREFIX_RE.match(prefix)
        )
        return m.group(0) if starts_syntax else m.group(1) + m.group(2)

    line = _INERT_ESCAPE_RE.sub(r"\1\2", line)
    return _LINE_ESCAPE_RE.sub(keep_at_start, line)


def _clean_docx_markdown(text: str) -> str:
    """Drop bookmark anchors and unwrap in-document links to their text.

    External links (``[text](https://…)``) stay, with backslash escapes
    removed from their target. TOC entries join heading and page number with
    tabs; those become single spaces. Escapes mammoth puts on ordinary
    punctuation are removed where they cannot start Markdown syntax.
    """
    text = _EMPTY_ANCHOR_RE.sub("", text)
    text = _INTERNAL_LINK_RE.sub(
        lambda m: re.sub(r"[ \t]*\t[ \t]*", " ", m.group(1)).strip(), text
    )
    text = _LINK_TARGET_RE.sub(
        lambda m: "](" + _TARGET_ESCAPE_RE.sub(r"\1", m.group(1)) + ")", text
    )
    return "\n".join(_unescape_prose(line) for line in text.split("\n"))


def _unescape_prose(line: str) -> str:
    """:func:`_unescape_line` outside link targets, which keep their escapes."""
    parts = []
    last = 0
    for m in _LINK_TARGET_RE.finditer(line):
        parts.append(_unescape_line(line[last : m.start()], at_line_start=last == 0))
        parts.append(m.group(0))
        last = m.end()
    parts.append(_unescape_line(line[last:], at_line_start=last == 0))
    return "".join(parts)


def _extract_docx(data: bytes) -> str:
    import mammoth

    result = mammoth.convert_to_markdown(io.BytesIO(data))
    return _clean_docx_markdown(result.value or "").strip()


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
                "Bitte den Text direkt einfügen oder eine durchsuchbare "
                "PDF-Version hochladen."
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

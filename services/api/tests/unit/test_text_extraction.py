"""Unit tests for document text extraction (issue #35).

Covers the dispatch + error logic of ``services.text_extraction``. The heavy
parsers (mammoth, pdfplumber) are stubbed where convenient — their own parsing
is their concern; what matters here is that we route by extension, fail loud on
an image-only PDF / unsupported type, and enforce the size cap.
"""

import sys
import types

import pytest

from services.text_extraction import (
    MAX_EXTRACT_BYTES,
    UnsupportedDocumentError,
    extract_text,
)
import services.text_extraction as te


def test_plain_text_extraction():
    out = extract_text("notes.txt", "Hallo Welt\nÄÖÜ".encode("utf-8"))
    assert out["source_format"] == "text"
    assert out["text"] == "Hallo Welt\nÄÖÜ"
    assert out["warnings"] == []


def test_markdown_extension_is_text():
    out = extract_text("rubrik.md", b"# Bewertung\n- Aufbau")
    assert out["source_format"] == "text"
    assert "Bewertung" in out["text"]


def test_latin1_fallback_does_not_crash():
    # 0xff is invalid utf-8; the permissive fallback must not raise.
    out = extract_text("odd.txt", b"caf\xe9")
    assert out["source_format"] == "text"


def test_unsupported_type_fails_loud():
    with pytest.raises(UnsupportedDocumentError) as exc:
        extract_text("scan.png", b"\x89PNG")
    assert exc.value.code == "unsupported_type"


def test_size_limit_enforced():
    big = b"x" * (MAX_EXTRACT_BYTES + 1)
    with pytest.raises(ValueError):
        extract_text("huge.txt", big)


def test_docx_routes_to_mammoth(monkeypatch):
    monkeypatch.setattr(te, "_extract_docx", lambda data: "Aus Word")
    out = extract_text("angabe.docx", b"PK\x03\x04 fake docx")
    assert out["source_format"] == "docx"
    assert out["text"] == "Aus Word"


def test_pdf_routes_to_pdfplumber(monkeypatch):
    monkeypatch.setattr(te, "_extract_pdf", lambda data: "Aus PDF")
    out = extract_text("fall.pdf", b"%PDF-1.4 fake")
    assert out["source_format"] == "pdf"
    assert out["text"] == "Aus PDF"


def _install_fake_pdfplumber(monkeypatch, page_texts):
    """Install a fake ``pdfplumber`` whose pages return the given texts."""

    class _Page:
        def __init__(self, t):
            self._t = t

        def extract_text(self):
            return self._t

    class _PDF:
        def __init__(self, pages):
            self.pages = pages

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake = types.ModuleType("pdfplumber")
    fake.open = lambda _bytesio: _PDF([_Page(t) for t in page_texts])
    monkeypatch.setitem(sys.modules, "pdfplumber", fake)


def test_pdf_with_text_layer(monkeypatch):
    _install_fake_pdfplumber(monkeypatch, ["Seite 1 Text", "Seite 2 Text"])
    out = extract_text("fall.pdf", b"%PDF-1.4")
    assert out["source_format"] == "pdf"
    assert "Seite 1 Text" in out["text"] and "Seite 2 Text" in out["text"]


def test_image_only_pdf_fails_loud(monkeypatch):
    # No page yields text -> scanned/image PDF -> must fail loud, not return "".
    _install_fake_pdfplumber(monkeypatch, ["", "   ", None])
    with pytest.raises(UnsupportedDocumentError) as exc:
        extract_text("scan.pdf", b"%PDF-1.4")
    assert exc.value.code == "pdf_no_text_layer"

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


# ---------------------------------------------------------------------------
# DOCX cleanup: bookmark anchors and table-of-contents links
# ---------------------------------------------------------------------------

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _docx_with_toc() -> bytes:
    """Minimal Word file: a TOC hyperlink to a bookmarked heading, the heading
    itself (bookmark start/end around it) and an external hyperlink."""
    import io
    import zipfile

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_W_NS}" xmlns:r="{_R_NS}"><w:body>'
        '<w:p><w:hyperlink w:anchor="_Toc179377816" w:history="1">'
        "<w:r><w:t>A.</w:t></w:r><w:r><w:tab/><w:t>Zulässigkeit</w:t></w:r>"
        "<w:r><w:tab/><w:t>3</w:t></w:r></w:hyperlink></w:p>"
        '<w:p><w:bookmarkStart w:id="0" w:name="_Toc179377816"/>'
        "<w:r><w:t>A. Zulässigkeit</w:t></w:r>"
        '<w:bookmarkEnd w:id="0"/></w:p>'
        "<w:p><w:r><w:t>Die Klage ist zulässig. Siehe </w:t></w:r>"
        '<w:hyperlink r:id="rId9"><w:r><w:t>Gesetz</w:t></w:r></w:hyperlink></w:p>'
        "<w:sectPr/></w:body></w:document>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_PKG_REL_NS}">'
        '<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        'Target="https://www.gesetze-bayern.de/" TargetMode="External"/>'
        "</Relationships>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_PKG_REL_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/_rels/document.xml.rels", rels)
    return buffer.getvalue()


def test_docx_drops_bookmark_anchors_and_unwraps_toc_links():
    pytest.importorskip("mammoth")
    out = extract_text("loesung.docx", _docx_with_toc())
    text = out["text"]
    assert out["source_format"] == "docx"
    assert "<a " not in text and "</a>" not in text
    assert "_Toc" not in text
    assert "](#" not in text
    # The TOC entry survives as plain text, tabs collapsed to spaces.
    assert "Zulässigkeit 3" in text
    assert "\t" not in text
    # The heading and body text stay; the external link is untouched.
    assert "Die Klage ist zulässig" in text
    assert "[Gesetz](https://www.gesetze-bayern.de/)" in text


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('<a id="_Toc179377815"></a>A\\. Zulässigkeit', "A\\. Zulässigkeit"),
        ("## <a id='_Ref1'></a>Titel", "## Titel"),
        ('<a name="bm"> </a>x', "x"),
        ("[A\\.\tZulässigkeit\t3](#_Toc179377816)", "A\\. Zulässigkeit 3"),
        ("[Siehe \\[1\\]](#_Ref2)", "Siehe \\[1\\]"),
        ("[extern](https://example.org/#frag)", "[extern](https://example.org/#frag)"),
        ('<a href="https://example.org">keep</a>', '<a href="https://example.org">keep</a>'),
        ('<a id="x">Text</a>', '<a id="x">Text</a>'),
    ],
)
def test_clean_docx_markdown_patterns(raw, expected):
    assert te._clean_docx_markdown(raw) == expected

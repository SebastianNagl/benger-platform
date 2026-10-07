"""``POST /api/files/extract-text``: document text for exam setup fields.

Drives the endpoint through the real app with the real parsers (mammoth,
pdfplumber) on small generated documents: each accepted format, the coded
refusals (scan without text layer, unsupported type, size), the mapping of
unexpected parser failures, and authentication.
"""

import io
import zipfile

import pytest

import routers.file_uploads as file_uploads
from services.text_extraction import MAX_EXTRACT_BYTES

URL = "/api/files/extract-text"

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _docx(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{_PKG_REL_NS}">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{_W_NS}"><w:body>'
            f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p><w:sectPr/></w:body></w:document>",
        )
    return buffer.getvalue()


def _pdf(text):
    """One-page PDF; without ``text`` it has no text layer, like a scan."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode() if text else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def _post(client, headers, name, data):
    return client.post(URL, headers=headers, files={"file": (name, data, "application/octet-stream")})


@pytest.mark.parametrize(
    "name,data,fmt,text",
    [
        ("angabe.txt", "A verkauft B ein Auto.".encode(), "text", "A verkauft B ein Auto."),
        ("loesung.md", b"# I. Zulaessigkeit", "text", "# I. Zulaessigkeit"),
        ("angabe.docx", _docx("Die Klage ist gem. § 253 ZPO zulässig."), "docx",
         "Die Klage ist gem. § 253 ZPO zulässig."),
        ("fall.pdf", _pdf("Der Anspruch besteht."), "pdf", "Der Anspruch besteht."),
    ],
    ids=["txt", "md", "docx", "pdf"],
)
def test_each_accepted_format_returns_its_text(client, auth_headers, name, data, fmt, text):
    resp = _post(client, auth_headers["annotator"], name, data)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_format"] == fmt
    assert body["text"] == text
    assert body["warnings"] == []


def test_a_scan_without_text_layer_is_refused_with_a_code(client, auth_headers):
    resp = _post(client, auth_headers["annotator"], "scan.pdf", _pdf(None))
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "pdf_no_text_layer"
    assert "keine Textebene" in detail["message"]


def test_an_unsupported_type_is_refused_with_a_code(client, auth_headers):
    resp = _post(client, auth_headers["annotator"], "foto.png", b"\x89PNG\r\n")
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "unsupported_type"


def test_an_oversized_document_is_refused(client, auth_headers):
    resp = _post(client, auth_headers["annotator"], "gross.txt", b"a" * (MAX_EXTRACT_BYTES + 1))
    assert resp.status_code == 413
    assert "MB limit" in resp.json()["detail"]


def test_a_size_error_from_the_parser_is_a_413(client, auth_headers, monkeypatch):
    def too_big(_name, _data):
        raise ValueError("Document exceeds the 15 MB limit.")

    monkeypatch.setattr(file_uploads, "extract_text", too_big)
    resp = _post(client, auth_headers["annotator"], "a.txt", b"x")
    assert resp.status_code == 413
    assert resp.json()["detail"] == "Document exceeds the 15 MB limit."


def test_an_unexpected_parser_failure_is_a_coded_422(client, auth_headers, monkeypatch):
    def broken(_name, _data):
        raise RuntimeError("corrupt archive")

    monkeypatch.setattr(file_uploads, "extract_text", broken)
    resp = _post(client, auth_headers["annotator"], "kaputt.docx", b"PK\x03\x04")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "extraction_failed"
    # Neutral wording: the endpoint serves both editions.
    assert detail["message"] == "Der Text konnte nicht extrahiert werden. Bitte den Text direkt einfügen."


def test_a_broken_word_file_is_reported_not_crashed(client, auth_headers):
    resp = _post(client, auth_headers["annotator"], "kaputt.docx", b"PK\x03\x04 not really a zip")
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "extraction_failed"


def test_a_file_without_name_is_refused(client, auth_headers):
    # Over HTTP an empty filename is not an upload at all: FastAPI's request
    # validation refuses it before the handler runs.
    resp = client.post(
        URL,
        headers=auth_headers["annotator"],
        files={"file": ("", b"Text", "text/plain")},
    )
    assert resp.status_code == 422


def test_the_handler_itself_refuses_a_nameless_upload():
    from fastapi import HTTPException, UploadFile

    upload = UploadFile(file=io.BytesIO(b"Text"), filename="")
    with pytest.raises(HTTPException) as exc:
        file_uploads.extract_document_text(file=upload, current_user=object())
    assert exc.value.status_code == 400


def test_anonymous_callers_are_refused(client):
    resp = client.post(URL, files={"file": ("a.txt", b"Text", "text/plain")})
    assert resp.status_code == 401

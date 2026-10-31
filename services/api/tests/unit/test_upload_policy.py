"""Upload/download policy for client-driven object storage (audit S1).

The bucket is public at storage.<domain>, same-site with the app, so a stored
HTML/SVG object opened through a presigned link would run script there. These
tests pin the allowlist, magic-byte checks, prefix and size clamps, the
download expiry clamp and the Content-Disposition logic, plus the shared
ObjectStorageService defaults that back them up for every other caller.
"""

from unittest.mock import MagicMock

import pytest

from storage.upload_policy import (
    DEFAULT_MAX_UPLOAD_BYTES,
    UploadPolicyError,
    clamp_download_expiry,
    clamp_max_size,
    content_disposition_for,
    is_scriptable_content_type,
    resolve_client_content_type,
    resolve_client_prefix,
    safe_response_content_type,
    verify_magic_bytes,
)

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.mark.unit
class TestContentTypes:
    @pytest.mark.parametrize(
        "declared,filename,expected",
        [
            ("image/png", "a.png", "image/png"),
            ("IMAGE/JPG", "a.jpg", "image/jpeg"),
            ("text/plain; charset=utf-8", "a.txt", "text/plain"),
            (DOCX, "a.docx", DOCX),
            ("application/x-zip-compressed", "a.zip", "application/zip"),
            (None, "deck.apkg", "application/zip"),
            ("application/octet-stream", "notes.md", "text/markdown"),
            ("", "data.csv", "text/csv"),
            ("application/json", "x.json", "application/json"),
            ("application/pdf", "x.pdf", "application/pdf"),
        ],
    )
    def test_allowed(self, declared, filename, expected):
        assert resolve_client_content_type(declared, filename) == expected

    @pytest.mark.parametrize(
        "declared,filename",
        [
            ("text/html", "x.html"),
            ("text/html", "x.png"),  # no extension fallback for a named bad type
            ("image/svg+xml", "x.svg"),
            ("application/xml", "x.xml"),
            ("text/xml", "x.txt"),
            ("application/xhtml+xml", "x.xhtml"),
            ("text/javascript", "x.js"),
            ("application/javascript", "x.js"),
            ("application/octet-stream", "x.html"),
            (None, "x.svg"),
            (None, "x.exe"),
            ("application/x-msdownload", "x.exe"),
        ],
    )
    def test_refused_with_415(self, declared, filename):
        with pytest.raises(UploadPolicyError) as exc:
            resolve_client_content_type(declared, filename)
        assert exc.value.status_code == 415

    def test_docx_is_not_flagged_as_xml(self):
        assert is_scriptable_content_type(DOCX) is False
        assert is_scriptable_content_type("image/svg+xml") is True
        assert is_scriptable_content_type("text/html; charset=utf-8") is True

    def test_safe_response_type(self):
        assert safe_response_content_type("image/png") == "image/png"
        assert safe_response_content_type("text/html") == "application/octet-stream"
        assert safe_response_content_type(None) == "application/octet-stream"


@pytest.mark.unit
class TestMagicBytes:
    @pytest.mark.parametrize(
        "ctype,data",
        [
            ("image/png", b"\x89PNG\r\n\x1a\n...."),
            ("image/jpeg", b"\xff\xd8\xff\xe0...."),
            ("image/gif", b"GIF89a...."),
            ("image/webp", b"RIFF\x00\x00\x00\x00WEBPVP8 "),
            ("application/pdf", b"%PDF-1.7\n"),
            ("application/zip", b"PK\x03\x04...."),
            (DOCX, b"PK\x03\x04...."),
            ("text/plain", b"<html>anything goes for text types</html>"),
        ],
    )
    def test_matching_signature_passes(self, ctype, data):
        verify_magic_bytes(ctype, data)

    @pytest.mark.parametrize(
        "ctype",
        ["image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf", DOCX],
    )
    def test_html_disguised_as_binary_is_refused(self, ctype):
        with pytest.raises(UploadPolicyError) as exc:
            verify_magic_bytes(ctype, b"<html><script>alert(1)</script></html>")
        assert exc.value.status_code == 415


@pytest.mark.unit
class TestPrefixAndSize:
    @pytest.mark.parametrize("prefix", ["uploads", "temp"])
    def test_client_prefixes(self, prefix):
        assert resolve_client_prefix(prefix)[0] == prefix

    def test_default_prefix_is_uploads(self):
        assert resolve_client_prefix(None)[0] == "uploads"

    @pytest.mark.parametrize(
        "prefix", ["static", "exports", "imports", "submissions", "backups", "misc", "../x"]
    )
    def test_server_prefixes_refused(self, prefix):
        with pytest.raises(UploadPolicyError) as exc:
            resolve_client_prefix(prefix)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize(
        "requested,expected",
        [(None, 100), (0, 100), (-5, 100), (10, 10), (10_000, 100)],
    )
    def test_max_size_clamped(self, requested, expected):
        assert clamp_max_size(requested, 100) == expected


@pytest.mark.unit
class TestDownloadUrlPolicy:
    @pytest.mark.parametrize(
        "requested,expected",
        [(None, 3600), (0, 60), (1, 60), (600, 600), (3600, 3600), (86400, 3600)],
    )
    def test_expiry_clamped(self, requested, expected):
        assert clamp_download_expiry(requested) == expected

    @pytest.mark.parametrize(
        "ctype", ["text/plain", "application/json", DOCX, "application/zip", "text/csv"]
    )
    def test_attachment_for_non_inline_types(self, ctype):
        header = content_disposition_for("f.bin", ctype, allow_inline=True)
        assert header.startswith("attachment;")

    @pytest.mark.parametrize(
        "ctype", ["image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"]
    )
    def test_inline_only_when_allowed_for_safe_types(self, ctype):
        assert content_disposition_for("f", ctype, allow_inline=True).startswith("inline;")
        assert content_disposition_for("f", ctype).startswith("attachment;")

    def test_filename_cannot_break_the_header(self):
        header = content_disposition_for('evil"; filename="x.html\r\nX: y', "text/plain")
        ascii_part = header.split("; filename*=")[0]
        assert ascii_part.count('"') == 2
        assert "\r" not in header and "\n" not in header
        assert "filename*=UTF-8''" in header

    def test_unicode_filename_keeps_utf8_original(self):
        header = content_disposition_for("Lösung.pdf", "application/pdf")
        assert header == (
            "attachment; filename=\"L_sung.pdf\"; filename*=UTF-8''L%C3%B6sung.pdf"
        )


def _s3_service():
    """An ObjectStorageService on a mocked S3 client, without boto3 init."""
    from storage.object_storage import ObjectStorageService

    service = ObjectStorageService.__new__(ObjectStorageService)
    service.storage_backend = "s3"
    service.bucket_name = "b"
    service.cdn_enabled = False
    service.s3_client = MagicMock()
    service.public_s3_client = service.s3_client
    service.PREFIXES = {"uploads": "uploads/{year}/{month}/{day}"}
    service.EXPIRATION_TIMES = {"upload": 3600, "download": 86400, "public": 604800}
    return service


@pytest.mark.unit
class TestObjectStorageDefaults:
    def test_presigned_post_always_has_a_size_condition(self):
        service = _s3_service()
        service.s3_client.generate_presigned_post.return_value = {"url": "u", "fields": {}}
        for max_size in (None, 0):
            service.get_upload_url("a.txt", max_size=max_size)
            conditions = service.s3_client.generate_presigned_post.call_args.kwargs[
                "Conditions"
            ]
            assert ["content-length-range", 0, DEFAULT_MAX_UPLOAD_BYTES] in conditions

    def test_presigned_post_refuses_scriptable_type(self):
        service = _s3_service()
        with pytest.raises(UploadPolicyError):
            service.get_upload_url("a.html", content_type="text/html")
        with pytest.raises(UploadPolicyError):
            service.get_upload_url("a.svg")  # guessed image/svg+xml
        service.s3_client.generate_presigned_post.assert_not_called()

    def test_upload_file_never_stores_html(self):
        service = _s3_service()
        service.s3_client.generate_presigned_url.return_value = "https://signed"
        result = service.upload_file(b"<html>", "x.html", content_type="text/html")
        assert result["content_type"] == "application/octet-stream"
        put = service.s3_client.put_object.call_args.kwargs
        assert put["ContentType"] == "application/octet-stream"

    def test_download_defaults_to_attachment(self):
        service = _s3_service()
        service.s3_client.generate_presigned_url.return_value = "https://signed"
        service.get_download_url("uploads/x.txt")
        params = service.s3_client.generate_presigned_url.call_args.kwargs["Params"]
        assert params["ResponseContentDisposition"] == "attachment"

    def test_download_never_echoes_scriptable_type(self):
        service = _s3_service()
        service.s3_client.generate_presigned_url.return_value = "https://signed"
        service.get_download_url(
            "uploads/x", response_content_type="image/svg+xml",
            response_content_disposition="inline",
        )
        params = service.s3_client.generate_presigned_url.call_args.kwargs["Params"]
        assert params["ResponseContentType"] == "application/octet-stream"
        assert params["ResponseContentDisposition"] == "inline"

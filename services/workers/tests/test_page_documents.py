"""shared.page_documents: magic-byte sniffing, PDF page classification,
page subsets and photo normalisation for handwriting OCR (CORE 2.48)."""

import io

import pytest
from PIL import Image

from page_documents import (
    PageDocumentError,
    classify_pdf_pages,
    normalize_photo,
    pdf_page_count,
    pdf_subset,
    sniff_page_format,
)


def _text_pdf(lines: list[str]) -> bytes:
    """Minimal one-page PDF with a real Helvetica text layer."""
    stream = "BT /F1 12 Tf 50 750 Td 14 TL " + " ".join(
        f"({line}) Tj T*" for line in lines
    ) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def _scan_pdf(pages: int = 1) -> bytes:
    """Image-only PDF, like a scanner produces."""
    imgs = [Image.new("RGB", (600, 850), (255, 255, 255)) for _ in range(pages)]
    buf = io.BytesIO()
    imgs[0].save(buf, format="PDF", save_all=True, append_images=imgs[1:])
    return buf.getvalue()


def _merge(*pdfs: bytes) -> bytes:
    import pypdfium2 as pdfium

    out = pdfium.PdfDocument.new()
    for data in pdfs:
        src = pdfium.PdfDocument(data)
        out.import_pages(src)
    buf = io.BytesIO()
    out.save(buf)
    return buf.getvalue()


def _jpeg(size=(4000, 3000), exif_orientation=None) -> bytes:
    img = Image.new("RGB", size, (200, 200, 200))
    buf = io.BytesIO()
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


TYPED = [
    "Gutachten zur Frage, ob A gegen B einen Anspruch hat.",
    "Ein Anspruch koennte sich aus 433 II BGB ergeben.",
]


class TestSniff:
    def test_known_formats(self):
        png = io.BytesIO()
        Image.new("RGB", (2, 2)).save(png, format="PNG")
        assert sniff_page_format(_text_pdf(TYPED)) == "pdf"
        assert sniff_page_format(_jpeg((10, 10))) == "jpeg"
        assert sniff_page_format(png.getvalue()) == "png"
        assert sniff_page_format(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 20) == "heic"
        assert sniff_page_format(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"

    def test_unknown(self):
        assert sniff_page_format(b"PK\x03\x04docx") is None
        assert sniff_page_format(b"just text") is None


class TestClassifyPdfPages:
    def test_typed_page_keeps_its_text(self):
        (page,) = classify_pdf_pages(_text_pdf(TYPED))
        assert page.is_scan is False
        assert "Gutachten" in page.text

    def test_scanned_page_needs_ocr(self):
        (page,) = classify_pdf_pages(_scan_pdf())
        assert page.is_scan is True

    def test_mixed_pdf_keeps_page_order(self):
        mixed = _merge(_text_pdf(TYPED), _scan_pdf(2))
        pages = classify_pdf_pages(mixed)
        assert [p.is_scan for p in pages] == [False, True, True]
        assert [p.index for p in pages] == [0, 1, 2]

    def test_broken_pdf_raises_coded_error(self):
        with pytest.raises(PageDocumentError) as exc:
            classify_pdf_pages(b"%PDF-1.4 garbage")
        assert exc.value.code == "pdf_unreadable"


class TestPdfSubset:
    def test_subset_keeps_only_requested_pages(self):
        mixed = _merge(_text_pdf(TYPED), _scan_pdf(2))
        sub = pdf_subset(mixed, [1, 2])
        assert pdf_page_count(sub) == 2
        assert all(p.is_scan for p in classify_pdf_pages(sub))

    def test_empty_selection_is_refused(self):
        with pytest.raises(PageDocumentError):
            pdf_subset(_scan_pdf(), [])


class TestNormalizePhoto:
    def test_downsizes_to_max_side_as_jpeg(self):
        out = normalize_photo(_jpeg((4000, 3000)))
        with Image.open(io.BytesIO(out)) as img:
            assert img.format == "JPEG"
            assert max(img.size) == 2000

    def test_applies_exif_rotation(self):
        # Orientation 6 = rotate 90° clockwise to display: landscape becomes portrait.
        out = normalize_photo(_jpeg((400, 300), exif_orientation=6))
        with Image.open(io.BytesIO(out)) as img:
            assert img.size == (300, 400)

    def test_converts_rgba_png(self):
        buf = io.BytesIO()
        Image.new("RGBA", (50, 40), (0, 0, 0, 0)).save(buf, format="PNG")
        out = normalize_photo(buf.getvalue())
        assert sniff_page_format(out) == "jpeg"

    def test_heic_decodes(self):
        pillow_heif = pytest.importorskip("pillow_heif")
        pillow_heif.register_heif_opener()
        buf = io.BytesIO()
        Image.new("RGB", (64, 48), (10, 20, 30)).save(buf, format="HEIF")
        out = normalize_photo(buf.getvalue())
        assert sniff_page_format(out) == "jpeg"

    def test_rejects_non_images(self):
        with pytest.raises(PageDocumentError) as exc:
            normalize_photo(b"%PDF-1.4")
        assert exc.value.code == "unsupported_format"
        with pytest.raises(PageDocumentError) as exc:
            normalize_photo(b"\xff\xd8\xff broken jpeg")
        assert exc.value.code == "image_unreadable"

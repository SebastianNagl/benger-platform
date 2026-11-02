"""Page-level helpers for uploaded solution documents (handwriting OCR).

Generic data handling over uploaded bytes, used by the extended OCR worker:

- :func:`sniff_page_format` recognises PDFs and photos by their magic bytes.
- :func:`classify_pdf_pages` splits a PDF into pages that carry a real text
  layer (typed pages, read as text) and pages that are scans (handwriting,
  sent to a vision model). A page counts as a scan when an image covers most
  of it, even if it also has a text layer: scanner apps put their own OCR
  layer over handwriting, and that layer is mostly garbage.
- :func:`pdf_subset` cuts the scanned pages out into a smaller PDF.
- :func:`normalize_photo` decodes JPEG/PNG/WebP/HEIC, applies the EXIF
  rotation and downsizes to a size vision models read well, as JPEG.

Pure functions over bytes, no DB or network, so they unit-test directly.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import List, Optional, Sequence

# A page with at least this many characters of text and no page-sized image
# is a typed page.
TEXT_LAYER_MIN_CHARS = 40
# An image covering at least this share of the page area makes it a scan.
SCAN_IMAGE_MIN_AREA = 0.5
# Long side of a normalised photo, in pixels. Large enough for handwriting,
# small enough that one page stays a few hundred KB and ~1.5k image tokens.
PHOTO_MAX_SIDE = 2000
PHOTO_JPEG_QUALITY = 85


class PageDocumentError(ValueError):
    """The bytes are not a readable page document. ``code`` is machine-readable."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def sniff_page_format(data: bytes) -> Optional[str]:
    """Return ``pdf``, ``jpeg``, ``png``, ``webp``, ``heic`` or None."""
    head = data[:32]
    if b"%PDF" in data[:1024]:
        return "pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] == b"ftyp" and head[8:12] in (
        b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"
    ):
        return "heic"
    return None


@dataclass(frozen=True)
class PdfPage:
    index: int
    text: str
    is_scan: bool


def classify_pdf_pages(data: bytes) -> List[PdfPage]:
    """Read every page's text layer and decide whether it needs OCR."""
    import pdfplumber

    pages: List[PdfPage] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for i, page in enumerate(pdf.pages):
                text = (page.extract_text() or "").strip()
                page_area = float(page.width * page.height) or 1.0
                largest = 0.0
                for img in page.images or []:
                    w = abs(float(img.get("x1", 0)) - float(img.get("x0", 0)))
                    h = abs(float(img.get("bottom", 0)) - float(img.get("top", 0)))
                    largest = max(largest, (w * h) / page_area)
                is_scan = largest >= SCAN_IMAGE_MIN_AREA or len(text) < TEXT_LAYER_MIN_CHARS
                pages.append(PdfPage(index=i, text=text, is_scan=is_scan))
    except PageDocumentError:
        raise
    except Exception as exc:  # pdfminer raises a zoo of types on broken files
        raise PageDocumentError("pdf_unreadable", str(exc)) from exc
    if not pages:
        raise PageDocumentError("pdf_empty")
    return pages


def pdf_page_count(data: bytes) -> int:
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(data)
    except Exception as exc:
        raise PageDocumentError("pdf_unreadable", str(exc)) from exc
    try:
        return len(doc)
    finally:
        doc.close()


def pdf_subset(data: bytes, indices: Sequence[int]) -> bytes:
    """A new PDF holding only ``indices`` (0-based) of ``data``, in that order."""
    import pypdfium2 as pdfium

    if not indices:
        raise PageDocumentError("pdf_empty")
    src = pdfium.PdfDocument(data)
    out = pdfium.PdfDocument.new()
    try:
        out.import_pages(src, list(indices))
        buf = io.BytesIO()
        out.save(buf)
        return buf.getvalue()
    finally:
        out.close()
        src.close()


def normalize_photo(data: bytes, max_side: int = PHOTO_MAX_SIDE) -> bytes:
    """Decode a photo (incl. HEIC), apply EXIF rotation, downsize, return JPEG."""
    from PIL import Image, ImageOps

    fmt = sniff_page_format(data)
    if fmt not in {"jpeg", "png", "webp", "heic"}:
        raise PageDocumentError("unsupported_format")
    if fmt == "heic":
        try:
            from pillow_heif import register_heif_opener
        except ImportError as exc:  # pragma: no cover - image dependency missing
            raise PageDocumentError("heic_unsupported", str(exc)) from exc
        register_heif_opener()
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=PHOTO_JPEG_QUALITY, optimize=True)
            return buf.getvalue()
    except PageDocumentError:
        raise
    except Exception as exc:
        raise PageDocumentError("image_unreadable", str(exc)) from exc

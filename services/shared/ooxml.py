"""Small helpers for reading Office Open XML files (XLSX, DOCX) safely.

OOXML files are zip archives of XML parts. Both the spreadsheet reader
(``table_grid``) and the grading sheet importer's Word reader
(``services/rubric_import``) read them with the stdlib only (``zipfile`` and
``xml.etree``), so the size guard and the namespace-agnostic element helpers
live here once.
"""

from __future__ import annotations

import zipfile
import zlib
import xml.etree.ElementTree as ET
from typing import Iterable, Optional

#: Cap on the UNCOMPRESSED size of a single zip member. A small upload can
#: declare a multi-gigabyte part ("zip bomb") and exhaust the process's memory
#: inside ``ZipFile.read``; :func:`read_member` refuses oversized entries
#: before decompressing. 32 MB is far above any real sheet or document (a
#: hand-made 100-row worksheet part is about 28 KB).
MAX_MEMBER_BYTES = 32 * 1024 * 1024


class MemberTooLarge(Exception):
    """A zip member is larger than :data:`MAX_MEMBER_BYTES`."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"zip member {name!r} exceeds {MAX_MEMBER_BYTES} bytes")


def read_member(zf: zipfile.ZipFile, name: str) -> bytes:
    """``zf.read(name)`` with a declared-size guard.

    ``ZipInfo.file_size`` is the size recorded in the archive; a bomb has to
    declare its payload there, so refusing before the read keeps the
    decompression bounded. A lying header still cannot get past the cap
    because ``read`` is given ``MAX_MEMBER_BYTES + 1`` bytes at most.

    Raises ``KeyError`` for a missing member, :class:`MemberTooLarge`, and
    ``zipfile.BadZipFile`` for a member whose compressed data is damaged.
    """
    info = zf.getinfo(name)
    if info.file_size > MAX_MEMBER_BYTES:
        raise MemberTooLarge(name)
    try:
        with zf.open(name) as handle:
            data = handle.read(MAX_MEMBER_BYTES + 1)
    except (zlib.error, EOFError) as exc:
        raise zipfile.BadZipFile(f"zip member {name!r} is damaged: {exc}") from exc
    if len(data) > MAX_MEMBER_BYTES:
        raise MemberTooLarge(name)
    return data


def local(tag: str) -> str:
    """An element or attribute name without its ``{namespace}``."""
    return tag.rsplit("}", 1)[-1]


def children(el: ET.Element, name: str) -> Iterable[ET.Element]:
    """The direct children of ``el`` with local name ``name``."""
    for child in el:
        if local(child.tag) == name:
            yield child


def first(el: Optional[ET.Element], name: str) -> Optional[ET.Element]:
    """The first direct child of ``el`` with local name ``name``, or None."""
    if el is None:
        return None
    for child in el:
        if local(child.tag) == name:
            return child
    return None


def attr(el: Optional[ET.Element], name: str) -> Optional[str]:
    """The value of the attribute with local name ``name``, or None."""
    if el is None:
        return None
    for key, value in el.attrib.items():
        if local(key) == name:
            return value
    return None

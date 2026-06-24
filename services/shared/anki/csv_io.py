"""
CSV / TSV round-trip for :class:`AnkiCard`.

Uses only the stdlib :mod:`csv` module, which handles quoting/escaping of fields
that contain the delimiter, quotes, or newlines. The on-disk shape is three
columns — ``front``, ``back``, ``tags`` — where ``tags`` is the Anki-style
space-joined tag string.
"""

from __future__ import annotations

import csv
import io

from .ir import AnkiCard

__all__ = ["cards_to_csv", "cards_to_tsv", "csv_to_cards", "tsv_to_cards"]

_HEADER = ["front", "back", "tags"]


def cards_to_csv(cards: list[AnkiCard], delimiter: str = ",") -> str:
    """Serialize cards to a CSV string with a header row.

    Tags are joined with a single space (Anki convention). ``deck_name`` is not
    emitted — CSV/TSV is a flat single-deck format.
    """
    buf = io.StringIO()
    # lineterminator is fixed so output is deterministic across platforms.
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    writer.writerow(_HEADER)
    for card in cards:
        writer.writerow([card.front, card.back, " ".join(card.tags)])
    return buf.getvalue()


def cards_to_tsv(cards: list[AnkiCard]) -> str:
    """TSV variant of :func:`cards_to_csv` (tab-delimited)."""
    return cards_to_csv(cards, delimiter="\t")


def _looks_like_header(row: list[str]) -> bool:
    """Heuristic: does this first row look like our ``front,back[,tags]`` header?

    We only treat a row as a header when its first two cells are exactly the
    literal column names (case-insensitive). Real card data starting with the
    word "front" in a different case is vanishingly unlikely to also have "back"
    as its second cell, so this is safe in practice.
    """
    if len(row) < 2:
        return False
    return row[0].strip().lower() == "front" and row[1].strip().lower() == "back"


def _parse_tags(raw: str) -> list[str]:
    """Split a tag string on whitespace, dropping empties."""
    return raw.split()


def csv_to_cards(text: str, delimiter: str = ",") -> list[AnkiCard]:
    """Parse a CSV/TSV string back into cards.

    Tolerances:
    - With or without a header row (sniffed via :func:`_looks_like_header`).
    - 2-column ``front,back`` or 3-column ``front,back,tags`` rows.
    - Fully blank rows are skipped.

    Round-trips losslessly for ``front`` / ``back`` / ``tags``.
    """
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)

    cards: list[AnkiCard] = []
    for index, row in enumerate(rows):
        # csv yields [] for truly empty lines; also treat all-empty cells as blank.
        if not row or all(cell == "" for cell in row):
            continue
        if index == 0 and _looks_like_header(row):
            continue

        front = row[0]
        back = row[1] if len(row) > 1 else ""
        tags = _parse_tags(row[2]) if len(row) > 2 else []
        cards.append(AnkiCard(front=front, back=back, tags=tags))

    return cards


def tsv_to_cards(text: str) -> list[AnkiCard]:
    """TSV variant of :func:`csv_to_cards` (tab-delimited)."""
    return csv_to_cards(text, delimiter="\t")

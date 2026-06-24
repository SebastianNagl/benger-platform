"""
Anki import/export intermediate representation (IR) for BenGER (issue #35).

A self-contained, stdlib-plus-``zstandard`` package that converts Anki content
to and from a neutral card IR. It knows nothing about DB models, projects, or
tasks — downstream code maps decks onto projects and cards onto tasks.

Lives under ``services/shared`` so both the api and the workers (which mount
``/shared`` on ``sys.path``) can import the same code.

Public API:
    - :class:`AnkiCard`, :class:`AnkiDeck` — the IR dataclasses.
    - :class:`AnkiImportError` — fail-loud exception with a user-facing message.
    - :func:`cards_to_csv`, :func:`csv_to_cards` — CSV/TSV round-trip.
    - :func:`apkg_to_deck`, :func:`deck_to_apkg` — .apkg import/export.
"""

from .apkg_io import apkg_to_deck, deck_to_apkg
from .csv_io import cards_to_csv, cards_to_tsv, csv_to_cards, tsv_to_cards
from .ir import AnkiCard, AnkiDeck, AnkiImportError

__all__ = [
    "AnkiCard",
    "AnkiDeck",
    "AnkiImportError",
    "cards_to_csv",
    "cards_to_tsv",
    "csv_to_cards",
    "tsv_to_cards",
    "apkg_to_deck",
    "deck_to_apkg",
]

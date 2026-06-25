"""
Unit tests for the Anki import/export IR package (``services/shared/anki``).

All fixtures are generated in-code — no network, no external fixture files.
Covers:
    - CSV/TSV round-trip (headers, no-header, 2-col, tags, HTML, unicode).
    - .apkg legacy import (collection.anki21).
    - .anki21b (zstd-compressed) import.
    - protobuf-only fail-loud path.
    - full .apkg export -> import round-trip.

These rely on ``services/shared`` being on ``sys.path`` (the api test suite adds
it), so ``from anki import ...`` resolves to ``services/shared/anki``.
"""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import zipfile

import pytest
import zstandard

from anki import (
    AnkiCard,
    AnkiDeck,
    AnkiImportError,
    apkg_to_deck,
    cards_to_csv,
    cards_to_tsv,
    csv_to_cards,
    deck_to_apkg,
    tsv_to_cards,
)

_FIELD_SEP = "\x1f"


# ---------------------------------------------------------------------------
# CSV / TSV round-trip
# ---------------------------------------------------------------------------


def _sample_cards() -> list[AnkiCard]:
    """A mix of cases: tags, empty tags, HTML with commas/quotes/newlines, unicode."""
    return [
        AnkiCard(front="Was ist § 242 BGB?", back="Treu und Glauben", tags=["bgb", "at"]),
        AnkiCard(front="No tags here", back="plain back", tags=[]),
        AnkiCard(
            front='HTML <b>fett</b>, mit "Anführung", und Komma',
            back="Zeile 1\nZeile 2",
            tags=["html"],
        ),
        AnkiCard(front="Ärger, Öl, Übung, ß", back="Größe & Maß", tags=["umlaut", "ß-tag"]),
    ]


@pytest.mark.parametrize(
    "to_fn,from_fn",
    [
        (cards_to_csv, csv_to_cards),
        (cards_to_tsv, tsv_to_cards),
    ],
)
def test_csv_tsv_round_trip(to_fn, from_fn):
    """cards -> text -> cards is lossless for front/back/tags in both delimiters."""
    cards = _sample_cards()
    text = to_fn(cards)
    restored = from_fn(text)

    assert len(restored) == len(cards)
    for original, got in zip(cards, restored):
        assert got.front == original.front
        assert got.back == original.back
        assert got.tags == original.tags


def test_csv_has_header_row():
    text = cards_to_csv([AnkiCard(front="a", back="b", tags=["t"])])
    first_line = text.splitlines()[0]
    assert first_line == "front,back,tags"


def test_csv_to_cards_without_header():
    """Headerless data is parsed (no row is silently swallowed as a header)."""
    text = "frage1,antwort1,tag1\nfrage2,antwort2,tag2 tag3\n"
    cards = csv_to_cards(text)
    assert len(cards) == 2
    assert cards[0] == AnkiCard(front="frage1", back="antwort1", tags=["tag1"])
    assert cards[1].tags == ["tag2", "tag3"]


def test_csv_to_cards_two_column_rows():
    """2-column front,back rows yield empty tag lists."""
    text = "front,back\nQ1,A1\nQ2,A2\n"
    cards = csv_to_cards(text)
    assert len(cards) == 2
    assert all(card.tags == [] for card in cards)
    assert cards[0].front == "Q1"


def test_csv_to_cards_skips_blank_rows():
    text = "front,back,tags\nQ1,A1,t1\n\n\nQ2,A2,t2\n"
    cards = csv_to_cards(text)
    assert len(cards) == 2
    assert cards[1].front == "Q2"


def test_csv_quoting_preserves_special_chars():
    """The csv module's quoting must survive commas, quotes, and newlines."""
    card = AnkiCard(
        front='a, b "c"\nd', back="back, with, commas", tags=["x"]
    )
    text = cards_to_csv([card])
    restored = csv_to_cards(text)
    assert restored == [card]


def test_tsv_uses_tabs():
    text = cards_to_tsv([AnkiCard(front="a", back="b", tags=["t"])])
    assert "\t" in text.splitlines()[1]


# ---------------------------------------------------------------------------
# Fixture builders for .apkg import tests
# ---------------------------------------------------------------------------


def _build_anki_sqlite(notes: list[tuple[str, str, str]], deck_name: str) -> bytes:
    """Build minimal-but-real Anki SQLite bytes with the columns the reader queries.

    ``notes`` is a list of ``(front, back, tags)`` where ``tags`` is the raw
    space-separated tag string. We populate ``notes(id, flds, tags)``,
    ``cards(nid, did)``, and ``col(decks)`` — exactly what ``apkg_to_deck`` reads.
    """
    deck_id = 1500000000000
    with tempfile.NamedTemporaryFile(suffix=".anki21", delete=False) as tmp:
        path = tmp.name

    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE col (id integer primary key, decks text not null);
            CREATE TABLE notes (
                id integer primary key, flds text not null, tags text not null
            );
            CREATE TABLE cards (
                id integer primary key, nid integer not null, did integer not null
            );
            """
        )
        decks_json = json.dumps(
            {
                "1": {"id": 1, "name": "Default"},
                str(deck_id): {"id": deck_id, "name": deck_name},
            }
        )
        conn.execute("INSERT INTO col (id, decks) VALUES (1, ?)", (decks_json,))
        for index, (front, back, tags) in enumerate(notes):
            note_id = 9000 + index
            flds = front + _FIELD_SEP + back
            stored_tags = f" {tags} " if tags else ""
            conn.execute(
                "INSERT INTO notes (id, flds, tags) VALUES (?, ?, ?)",
                (note_id, flds, stored_tags),
            )
            conn.execute(
                "INSERT INTO cards (id, nid, did) VALUES (?, ?, ?)",
                (note_id + 100000, note_id, deck_id),
            )
        conn.commit()
    finally:
        conn.close()

    with open(path, "rb") as fh:
        data = fh.read()
    import os

    os.unlink(path)
    return data


def _zip_apkg(member_name: str, collection_bytes: bytes) -> bytes:
    """Wrap collection bytes + an empty media map into an .apkg ZIP blob."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member_name, collection_bytes)
        zf.writestr("media", "{}")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# .apkg import
# ---------------------------------------------------------------------------


def test_apkg_legacy_import():
    """A legacy collection.anki21 imports notes -> cards with tags and deck name."""
    notes = [
        ("Frage A", "Antwort A", "tag1 tag2"),
        ("Frage B", "Antwort B", ""),
        ("Ärger?", "Größe ß", "umlaut"),
    ]
    sqlite_bytes = _build_anki_sqlite(notes, deck_name="Jura Deck")
    apkg = _zip_apkg("collection.anki21", sqlite_bytes)

    deck = apkg_to_deck(apkg)

    assert deck.name == "Jura Deck"
    assert len(deck.cards) == 3
    assert deck.cards[0].front == "Frage A"
    assert deck.cards[0].back == "Antwort A"
    assert deck.cards[0].tags == ["tag1", "tag2"]
    assert deck.cards[0].deck_name == "Jura Deck"
    assert deck.cards[1].tags == []
    assert deck.cards[2].front == "Ärger?"
    assert deck.cards[2].back == "Größe ß"


def test_apkg_anki21b_zstd_import():
    """A .anki21b (zstd-compressed) collection imports identically to legacy."""
    notes = [("Z-Frage", "Z-Antwort", "ztag")]
    sqlite_bytes = _build_anki_sqlite(notes, deck_name="Compressed Deck")
    compressed = zstandard.ZstdCompressor().compress(sqlite_bytes)
    apkg = _zip_apkg("collection.anki21b", compressed)

    deck = apkg_to_deck(apkg)

    assert len(deck.cards) == 1
    assert deck.cards[0].front == "Z-Frage"
    assert deck.cards[0].back == "Z-Antwort"
    assert deck.cards[0].tags == ["ztag"]
    assert deck.name == "Compressed Deck"


def test_apkg_prefers_newest_collection_name():
    """When multiple collections coexist, the newest (.anki21b) wins."""
    legacy = _build_anki_sqlite([("Old", "Old", "")], deck_name="Old Deck")
    new = _build_anki_sqlite([("New", "New", "")], deck_name="New Deck")
    compressed_new = zstandard.ZstdCompressor().compress(new)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("collection.anki2", legacy)
        zf.writestr("collection.anki21b", compressed_new)
        zf.writestr("media", "{}")

    deck = apkg_to_deck(buf.getvalue())
    assert deck.cards[0].front == "New"
    assert deck.name == "New Deck"


def test_apkg_protobuf_only_fails_loud():
    """A collection that is not SQLite (modern protobuf form) raises AnkiImportError."""
    apkg = _zip_apkg("collection.anki21b", b"this-is-not-sqlite-or-zstd-data" * 4)

    with pytest.raises(AnkiImportError) as exc_info:
        apkg_to_deck(apkg)

    message = str(exc_info.value)
    assert "nicht unterstütztes Anki-Format" in message
    assert "ältere" in message


def test_apkg_sqlite_without_notes_table_fails_loud():
    """SQLite-valid bytes lacking a notes table also fail loud (not silent drop)."""
    with tempfile.NamedTemporaryFile(suffix=".anki21", delete=False) as tmp:
        path = tmp.name
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE unrelated (id integer primary key)")
    conn.commit()
    conn.close()
    with open(path, "rb") as fh:
        sqlite_bytes = fh.read()
    import os

    os.unlink(path)

    apkg = _zip_apkg("collection.anki21", sqlite_bytes)
    with pytest.raises(AnkiImportError):
        apkg_to_deck(apkg)


def test_apkg_missing_collection_fails_loud():
    """A ZIP with no collection member raises a clear error."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("media", "{}")
    with pytest.raises(AnkiImportError):
        apkg_to_deck(buf.getvalue())


def test_apkg_non_zip_fails_loud():
    """Random bytes that are not a ZIP raise a clear error."""
    with pytest.raises(AnkiImportError):
        apkg_to_deck(b"definitely not a zip archive")


# ---------------------------------------------------------------------------
# Full export -> import round-trip (highest risk)
# ---------------------------------------------------------------------------


def test_apkg_export_import_round_trip():
    """deck_to_apkg -> apkg_to_deck preserves front/back/tags across many cards."""
    deck = AnkiDeck(
        name="Examen Deck",
        cards=[
            AnkiCard(front="Frage 1", back="Antwort 1", tags=["zivilrecht", "examen"]),
            AnkiCard(front="Frage 2 ohne Tags", back="Antwort 2", tags=[]),
            AnkiCard(
                front='HTML <b>fett</b> & "Zitat", Komma',
                back="Mehrzeilig\nZeile 2",
                tags=["html"],
            ),
            AnkiCard(front="Ärger Öl Übung ß", back="Größe & Maß €", tags=["umlaut"]),
        ],
    )

    apkg_bytes = deck_to_apkg(deck)
    assert isinstance(apkg_bytes, bytes)

    # The blob really is a ZIP with the expected members.
    with zipfile.ZipFile(io.BytesIO(apkg_bytes)) as zf:
        names = set(zf.namelist())
        assert "collection.anki21" in names
        assert "media" in names
        assert zf.read("media") == b"{}"

    restored = apkg_to_deck(apkg_bytes)

    assert restored.name == "Examen Deck"
    assert len(restored.cards) == len(deck.cards)
    for original, got in zip(deck.cards, restored.cards):
        assert got.front == original.front
        assert got.back == original.back
        assert got.tags == original.tags


def test_apkg_export_determinism():
    """Exporting the same deck twice yields byte-identical collections."""
    deck = AnkiDeck(
        name="Stable",
        cards=[AnkiCard(front="a", back="b", tags=["t"])],
    )
    first = deck_to_apkg(deck)
    second = deck_to_apkg(deck)

    # Compare the collection member (ZIP wrapper metadata like timestamps can
    # vary; the SQLite content must not).
    def collection(blob: bytes) -> bytes:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            return zf.read("collection.anki21")

    assert collection(first) == collection(second)


def test_apkg_export_empty_deck():
    """An empty deck exports and re-imports to zero cards, name preserved."""
    deck = AnkiDeck(name="Leeres Deck", cards=[])
    restored = apkg_to_deck(deck_to_apkg(deck))
    assert restored.cards == []
    assert restored.name == "Leeres Deck"

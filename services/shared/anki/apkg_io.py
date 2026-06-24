"""
.apkg (Anki package) import and export.

An ``.apkg`` file is a ZIP archive containing an SQLite collection plus a media
mapping. Three collection encodings exist in the wild:

- ``collection.anki2``    — legacy SQLite (oldest).
- ``collection.anki21``   — SQLite, schema v11 (newer legacy; what we emit).
- ``collection.anki21b``  — zstandard-compressed SQLite, or, in the very newest
                            exports, a protobuf-only blob that is *not* SQLite.

Import reads the first usable collection (preferring the newest name) and turns
its ``notes`` rows into :class:`AnkiCard` entries. If the located collection is
not a readable SQLite database with a ``notes`` table (the protobuf-only case),
we fail loud with a German, user-facing :class:`AnkiImportError` rather than
silently dropping cards.

Export writes a *legacy* ``collection.anki21`` only — we never attempt to emit
the compressed/protobuf forms. The output round-trips back through
:func:`apkg_to_deck`.

Only stdlib (:mod:`zipfile`, :mod:`sqlite3`, :mod:`tempfile`, :mod:`json`,
:mod:`hashlib`) plus :mod:`zstandard` is used.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import tempfile
import zipfile

import zstandard

from .ir import AnkiCard, AnkiDeck, AnkiImportError

__all__ = ["apkg_to_deck", "deck_to_apkg"]

# Anki joins note fields with this control char (Unit Separator, 0x1f).
_FIELD_SEP = "\x1f"

# Preference order: newest name first.
_COLLECTION_NAMES = ("collection.anki21b", "collection.anki21", "collection.anki2")

_DEFAULT_DECK_NAME = "Imported Deck"

# German, user-facing message for the protobuf-only / unreadable case.
_PROTOBUF_MESSAGE = (
    "Diese .apkg-Datei verwendet ein neueres, nicht unterstütztes Anki-Format. "
    "Bitte exportiere aus Anki mit aktivierter Option 'Unterstütze ältere "
    "Anki-Versionen' und lade die Datei erneut hoch."
)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def _zstd_decompress(blob: bytes) -> bytes:
    """Decompress a zstandard blob, handling frames without a content size.

    ``decompress()`` requires the frame to declare its uncompressed size. Anki's
    ``.anki21b`` frames sometimes omit it, in which case we fall back to a
    streaming reader that does not need the size up front.
    """
    dctx = zstandard.ZstdDecompressor()
    try:
        return dctx.decompress(blob)
    except zstandard.ZstdError:
        with dctx.stream_reader(io.BytesIO(blob)) as reader:
            return reader.read()


def _read_collection_bytes(data: bytes) -> bytes:
    """Locate the collection member inside the apkg ZIP and return SQLite bytes.

    Decompresses ``.anki21b`` members. Raises :class:`AnkiImportError` when no
    collection member is present at all.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AnkiImportError(
            "Die hochgeladene Datei ist kein gültiges .apkg-Archiv (ZIP)."
        ) from exc

    with zf:
        names = set(zf.namelist())
        for name in _COLLECTION_NAMES:
            if name not in names:
                continue
            raw = zf.read(name)
            if name.endswith("b"):  # collection.anki21b → zstd-compressed
                try:
                    return _zstd_decompress(raw)
                except zstandard.ZstdError:
                    # Not zstd at all (e.g. raw protobuf mislabeled). Hand the
                    # raw bytes downstream; the SQLite-validity check fails loud.
                    return raw
            return raw

    raise AnkiImportError(
        "Im .apkg-Archiv wurde keine Anki-Sammlung (collection.anki2/anki21/"
        "anki21b) gefunden."
    )


def _is_sqlite(blob: bytes) -> bool:
    """Cheap pre-check: SQLite files begin with this 16-byte magic header."""
    return blob[:16] == b"SQLite format 3\x00"


def _load_deck_names(cur: sqlite3.Cursor) -> dict[int, str]:
    """Build a ``did -> deck name`` map from the ``col.decks`` JSON, if present.

    Returns an empty dict when the collection has no usable ``decks`` JSON; the
    caller then falls back to a single default deck name.
    """
    try:
        cur.execute("SELECT decks FROM col LIMIT 1")
        row = cur.fetchone()
    except sqlite3.Error:
        return {}
    if not row or not row[0]:
        return {}
    try:
        decks = json.loads(row[0])
    except (ValueError, TypeError):
        return {}

    mapping: dict[int, str] = {}
    # decks JSON is keyed by stringified deck id; each value has a "name".
    for key, value in (decks or {}).items():
        try:
            did = int(key)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and value.get("name"):
            mapping[did] = str(value["name"])
    return mapping


def _card_deck_map(cur: sqlite3.Cursor) -> dict[int, int]:
    """Map ``note id -> deck id`` via the ``cards`` table, best-effort.

    A note can have multiple cards; we take the first deck we see for each note.
    Returns an empty dict when the ``cards`` table is unavailable.
    """
    try:
        cur.execute("SELECT nid, did FROM cards")
    except sqlite3.Error:
        return {}
    note_to_deck: dict[int, int] = {}
    for nid, did in cur.fetchall():
        if nid not in note_to_deck:
            note_to_deck[nid] = did
    return note_to_deck


def _deck_name_from_col(cur: sqlite3.Cursor) -> str | None:
    """Best-effort single deck name: the first non-"Default" deck in ``col``."""
    deck_names = _load_deck_names(cur)
    for name in deck_names.values():
        if name and name != "Default":
            return name
    return None


def apkg_to_deck(data: bytes) -> AnkiDeck:
    """Import an ``.apkg`` byte blob into an :class:`AnkiDeck`.

    Accepts raw bytes so it works directly off an object-storage download.

    Raises :class:`AnkiImportError` when the archive contains no collection, or
    when the collection is not a readable SQLite database with a ``notes`` table
    (the modern protobuf-only export form).
    """
    collection_bytes = _read_collection_bytes(data)

    # Fail loud before touching sqlite if the magic header is wrong — this is the
    # protobuf-only case the message is written for.
    if not _is_sqlite(collection_bytes):
        raise AnkiImportError(_PROTOBUF_MESSAGE)

    # sqlite3 needs a filesystem path; write to a temp file and open read-only.
    tmp = tempfile.NamedTemporaryFile(suffix=".anki", delete=False)
    try:
        tmp.write(collection_bytes)
        tmp.flush()
        tmp.close()

        try:
            conn = sqlite3.connect(f"file:{tmp.name}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise AnkiImportError(_PROTOBUF_MESSAGE) from exc

        try:
            cur = conn.cursor()

            # Confirm a real notes table exists — guards the protobuf case where
            # the bytes happen to look SQLite-ish but lack the Anki schema.
            try:
                cur.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='notes'"
                )
                if cur.fetchone() is None:
                    raise AnkiImportError(_PROTOBUF_MESSAGE)
            except sqlite3.DatabaseError as exc:
                raise AnkiImportError(_PROTOBUF_MESSAGE) from exc

            deck_names = _load_deck_names(cur)
            note_to_deck = _card_deck_map(cur) if deck_names else {}
            fallback_deck = _deck_name_from_col(cur) or _DEFAULT_DECK_NAME

            try:
                cur.execute("SELECT id, flds, tags FROM notes")
                note_rows = cur.fetchall()
            except sqlite3.Error as exc:
                raise AnkiImportError(_PROTOBUF_MESSAGE) from exc

            cards: list[AnkiCard] = []
            for note_id, flds, tags in note_rows:
                fields = (flds or "").split(_FIELD_SEP)
                front = fields[0] if len(fields) > 0 else ""
                back = fields[1] if len(fields) > 1 else ""
                tag_list = (tags or "").split()

                deck_name = fallback_deck
                did = note_to_deck.get(note_id)
                if did is not None and did in deck_names:
                    deck_name = deck_names[did]

                cards.append(
                    AnkiCard(
                        front=front,
                        back=back,
                        tags=tag_list,
                        deck_name=deck_name,
                    )
                )
        finally:
            conn.close()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    # Deck name for the container: prefer a real col deck, else first card's deck.
    deck_name = fallback_deck
    if deck_name == _DEFAULT_DECK_NAME and cards and cards[0].deck_name:
        deck_name = cards[0].deck_name

    return AnkiDeck(name=deck_name, cards=cards)


# ---------------------------------------------------------------------------
# Export (legacy collection.anki21 only)
# ---------------------------------------------------------------------------

# Minimal but valid schema for an Anki collection (schema v11). Mirrors the real
# Anki DDL closely enough that apkg_to_deck — and Anki itself — can read it.
_SCHEMA = """
CREATE TABLE col (
    id      integer primary key,
    crt     integer not null,
    mod     integer not null,
    scm     integer not null,
    ver     integer not null,
    dty     integer not null,
    usn     integer not null,
    ls      integer not null,
    conf    text    not null,
    models  text    not null,
    decks   text    not null,
    dconf   text    not null,
    tags    text    not null
);
CREATE TABLE notes (
    id    integer primary key,
    guid  text    not null,
    mid   integer not null,
    mod   integer not null,
    usn   integer not null,
    tags  text    not null,
    flds  text    not null,
    sfld  text    not null,
    csum  integer not null,
    flags integer not null,
    data  text    not null
);
CREATE TABLE cards (
    id     integer primary key,
    nid    integer not null,
    did    integer not null,
    ord    integer not null,
    mod    integer not null,
    usn    integer not null,
    type   integer not null,
    queue  integer not null,
    due    integer not null,
    ivl    integer not null,
    factor integer not null,
    reps   integer not null,
    lapses integer not null,
    left   integer not null,
    odue   integer not null,
    odid   integer not null,
    flags  integer not null,
    data   text    not null
);
CREATE TABLE revlog (
    id      integer primary key,
    cid     integer not null,
    usn     integer not null,
    ease    integer not null,
    ivl     integer not null,
    lastIvl integer not null,
    factor  integer not null,
    time    integer not null,
    type    integer not null
);
CREATE TABLE graves (
    usn  integer not null,
    oid  integer not null,
    type integer not null
);
CREATE INDEX ix_notes_usn ON notes (usn);
CREATE INDEX ix_cards_usn ON cards (usn);
CREATE INDEX ix_cards_nid ON cards (nid);
CREATE INDEX ix_cards_sched ON cards (did, queue, due);
CREATE INDEX ix_notes_csum ON notes (csum);
CREATE INDEX ix_revlog_cid ON revlog (cid);
CREATE INDEX ix_revlog_usn ON revlog (usn);
""".strip()

# Fixed ids so exports are deterministic. Real Anki uses epoch-ms timestamps;
# these are local export artifacts so a fixed base is fine and keeps tests stable.
_MODEL_ID = 1000000000000
_DECK_ID = 1000000000001
_BASE_TS = 1700000000  # fixed epoch seconds base; ids derive from this + index.


def _field_checksum(field: str) -> int:
    """Anki note csum: first 8 hex digits of SHA1(first field) as an int."""
    digest = hashlib.sha1(field.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _guid_for(index: int) -> str:
    """Deterministic, collision-free guid derived from the note index."""
    return hashlib.sha1(f"benger-anki-{index}".encode("utf-8")).hexdigest()[:10]


def _build_models_json(deck_name: str) -> str:
    """A single Basic note type (front/back) — the minimum Anki needs to render."""
    model = {
        str(_MODEL_ID): {
            "id": _MODEL_ID,
            "name": "Basic",
            "type": 0,
            "mod": _BASE_TS,
            "usn": -1,
            "sortf": 0,
            "did": _DECK_ID,
            "tmpls": [
                {
                    "name": "Card 1",
                    "ord": 0,
                    "qfmt": "{{Front}}",
                    "afmt": "{{FrontSide}}\n\n<hr id=answer>\n\n{{Back}}",
                    "bqfmt": "",
                    "bafmt": "",
                    "did": None,
                    "bfont": "",
                    "bsize": 0,
                }
            ],
            "flds": [
                {
                    "name": "Front",
                    "ord": 0,
                    "sticky": False,
                    "rtl": False,
                    "font": "Arial",
                    "size": 20,
                },
                {
                    "name": "Back",
                    "ord": 1,
                    "sticky": False,
                    "rtl": False,
                    "font": "Arial",
                    "size": 20,
                },
            ],
            "css": (
                ".card {\n font-family: arial;\n font-size: 20px;\n"
                " text-align: center;\n color: black;\n background-color: white;\n}\n"
            ),
            "latexPre": "",
            "latexPost": "",
            "latexsvg": False,
            "req": [[0, "any", [0]]],
            "vers": [],
            "tags": [],
        }
    }
    return json.dumps(model)


def _build_decks_json(deck_name: str) -> str:
    """Two decks: the mandatory Default (id 1) and our content deck."""
    decks = {
        "1": {
            "id": 1,
            "name": "Default",
            "mod": _BASE_TS,
            "usn": -1,
            "desc": "",
            "dyn": 0,
            "collapsed": False,
            "extendNew": 10,
            "extendRev": 50,
            "conf": 1,
            "newToday": [0, 0],
            "revToday": [0, 0],
            "lrnToday": [0, 0],
            "timeToday": [0, 0],
        },
        str(_DECK_ID): {
            "id": _DECK_ID,
            "name": deck_name,
            "mod": _BASE_TS,
            "usn": -1,
            "desc": "",
            "dyn": 0,
            "collapsed": False,
            "extendNew": 10,
            "extendRev": 50,
            "conf": 1,
            "newToday": [0, 0],
            "revToday": [0, 0],
            "lrnToday": [0, 0],
            "timeToday": [0, 0],
        },
    }
    return json.dumps(decks)


def _build_dconf_json() -> str:
    """Single default deck-configuration group (id 1)."""
    dconf = {
        "1": {
            "id": 1,
            "name": "Default",
            "mod": 0,
            "usn": 0,
            "maxTaken": 60,
            "autoplay": True,
            "timer": 0,
            "replayq": True,
            "new": {
                "bury": False,
                "delays": [1.0, 10.0],
                "initialFactor": 2500,
                "ints": [1, 4, 0],
                "order": 1,
                "perDay": 20,
            },
            "rev": {
                "bury": False,
                "ease4": 1.3,
                "ivlFct": 1.0,
                "maxIvl": 36500,
                "perDay": 200,
                "hardFactor": 1.2,
            },
            "lapse": {
                "delays": [10.0],
                "leechAction": 1,
                "leechFails": 8,
                "minInt": 1,
                "mult": 0.0,
            },
            "dyn": False,
        }
    }
    return json.dumps(dconf)


def _build_conf_json() -> str:
    """Collection-level config; ``curDeck`` points at our content deck."""
    conf = {
        "nextPos": 1,
        "estTimes": True,
        "activeDecks": [1],
        "sortType": "noteFld",
        "timeLim": 0,
        "sortBackwards": False,
        "addToCur": True,
        "curDeck": _DECK_ID,
        "newBury": True,
        "newSpread": 0,
        "dueCounts": True,
        "curModel": _MODEL_ID,
        "collapseTime": 1200,
    }
    return json.dumps(conf)


def deck_to_apkg(deck: AnkiDeck) -> bytes:
    """Export an :class:`AnkiDeck` to a legacy ``.apkg`` byte blob.

    Writes a schema-v11 ``collection.anki21`` SQLite database (single Basic note
    type, single deck) plus an empty ``media`` mapping into a ZIP. The result
    round-trips back through :func:`apkg_to_deck`.
    """
    deck_name = deck.name or _DEFAULT_DECK_NAME

    tmp = tempfile.NamedTemporaryFile(suffix=".anki21", delete=False)
    tmp.close()
    try:
        conn = sqlite3.connect(tmp.name)
        try:
            conn.executescript(_SCHEMA)

            conn.execute(
                "INSERT INTO col "
                "(id, crt, mod, scm, ver, dty, usn, ls, conf, models, decks, "
                " dconf, tags) "
                "VALUES (1, ?, ?, ?, 11, 0, 0, 0, ?, ?, ?, ?, ?)",
                (
                    _BASE_TS,
                    _BASE_TS * 1000,
                    _BASE_TS * 1000,
                    _build_conf_json(),
                    _build_models_json(deck_name),
                    _build_decks_json(deck_name),
                    _build_dconf_json(),
                    "{}",
                ),
            )

            for index, card in enumerate(deck.cards):
                note_id = _BASE_TS * 1000 + index * 2
                card_id = note_id + 1
                flds = card.front + _FIELD_SEP + card.back
                tags_str = " ".join(card.tags)
                # Anki stores tags space-padded (" tag1 tag2 ") when non-empty.
                stored_tags = f" {tags_str} " if tags_str else ""

                conn.execute(
                    "INSERT INTO notes "
                    "(id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, "
                    " data) "
                    "VALUES (?, ?, ?, ?, -1, ?, ?, ?, ?, 0, '')",
                    (
                        note_id,
                        _guid_for(index),
                        _MODEL_ID,
                        _BASE_TS,
                        stored_tags,
                        flds,
                        card.front,
                        _field_checksum(card.front),
                    ),
                )
                conn.execute(
                    "INSERT INTO cards "
                    "(id, nid, did, ord, mod, usn, type, queue, due, ivl, "
                    " factor, reps, lapses, left, odue, odid, flags, data) "
                    "VALUES (?, ?, ?, 0, ?, -1, 0, 0, ?, 0, 0, 0, 0, 0, 0, 0, "
                    " 0, '')",
                    (card_id, note_id, _DECK_ID, _BASE_TS, index + 1),
                )

            conn.commit()
        finally:
            conn.close()

        with open(tmp.name, "rb") as fh:
            collection_bytes = fh.read()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("collection.anki21", collection_bytes)
        # Empty media mapping — we export text only.
        zf.writestr("media", "{}")
    return buf.getvalue()

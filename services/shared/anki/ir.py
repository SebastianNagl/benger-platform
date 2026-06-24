"""
Neutral intermediate representation (IR) for Anki flashcards.

This module is provider-/storage-agnostic: it knows nothing about DB models,
projects, or tasks. Downstream code maps an :class:`AnkiDeck` onto a project and
its :class:`AnkiCard` entries onto tasks, but that translation lives elsewhere.

Only stdlib is used here so the package can be imported from both the api and
the workers (``services/shared`` is on ``sys.path`` for both).
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["AnkiCard", "AnkiDeck", "AnkiImportError"]


@dataclass
class AnkiCard:
    """A single flashcard.

    ``front`` and ``back`` are kept verbatim. Anki stores field content as HTML,
    so these strings may contain markup; we never strip or transform them. ``tags``
    follows the Anki convention of space-separated tokens (no embedded spaces per
    tag). ``deck_name`` is optional; when importing it carries the originating deck.
    """

    front: str
    back: str
    tags: list[str] = field(default_factory=list)
    deck_name: str | None = None


@dataclass
class AnkiDeck:
    """A named collection of :class:`AnkiCard` entries."""

    name: str
    cards: list[AnkiCard] = field(default_factory=list)


class AnkiImportError(Exception):
    """Raised when an Anki import cannot proceed.

    The message is user-facing (German is acceptable) and should explain the
    problem clearly enough for a non-technical user to act on it — for example,
    instructing them to re-export from Anki in a legacy-compatible format.
    """

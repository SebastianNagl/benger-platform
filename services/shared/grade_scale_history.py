"""The audit trail of an exam's Notenschlüssel (contract v5).

Unlike every other evaluation setting, the Notenschlüssel
(``project.evaluation_config.grade_scale``, contract v2) retroactively
rewrites grades people have already seen: change the key, press "Notenpunkte
aktualisieren" (contract v4), and a stored 10 becomes a 12. A grade must
never move without a record of who moved it, so every write of the key
appends an entry here.

Storage: ``project.evaluation_config.grade_scale_history`` — a JSONB list in
the same deep-merged document as the key itself. No migration, and the
project export carries it for free. Newest LAST; capped at
:data:`MAX_HISTORY_ENTRIES` (oldest dropped) so it cannot grow without
bound.

One entry::

    {"changed_at": "<iso8601, UTC>",
     "changed_by": "<user id|null>",
     "from": {"preset": …, "thresholds": […], …} | null,   # null = was the default
     "to":   {"preset": …, "thresholds": […], …} | null,    # null = back to the default
     "recomputed": <int|null>}                              # stamped by a later recompute

TWO writers of the key exist and BOTH must append through this module —
that is the whole reason it lives in ``/shared`` rather than in either
router:

1. platform ``PUT /api/evaluations/projects/{id}/evaluation-config``
   (the project page's Notenschlüssel card and the wizard's post-create hook)
2. extended ``benger_extended/api/routers/student_exams.py`` (exam create and
   the content PUT), which writes ``evaluation_config["grade_scale"]``
   straight onto the project

If only the platform path appended, the history would silently lie for every
exam edited in the Vertretbar modal.

Deliberately dependency-free (no pydantic, no SQLAlchemy, no
``rubric_structure``): the workers import ``/shared`` without pydantic, and
the extended stub test suite imports the extended routers without a platform
checkout. Every function is PURE — it returns a NEW ``evaluation_config``
dict and never mutates its input, so callers assign the result back onto the
ORM attribute and ``flag_modified`` it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

#: Key of the audit list inside ``evaluation_config``.
HISTORY_KEY = "grade_scale_history"

#: Key of the Notenschlüssel itself (contract v2), next to the history.
GRADE_SCALE_KEY = "grade_scale"

#: How many entries are kept. Older ones are dropped from the FRONT.
MAX_HISTORY_ENTRIES = 20


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _comparable(scale: Any) -> Optional[tuple]:
    """The semantic identity of a Notenschlüssel, or ``None`` for "unset".

    Compared instead of the raw dicts so that a re-save of the same key is
    not recorded as a change: ``50`` and ``50.0`` are the same threshold, and
    keys the contract does not define (a client's stray field) do not make
    two identical scales differ. ``preset`` IS part of the identity — naming
    a key "Übungsklausur" instead of "Eigener Schlüssel" is a change of
    assessment policy even when the numbers coincide.
    """
    if not isinstance(scale, dict):
        return None
    thresholds = scale.get("thresholds")
    if not isinstance(thresholds, list):
        return None
    return (
        str(scale.get("unit") or "").strip().lower(),
        tuple(float(t) if _is_number(t) else None for t in thresholds),
        scale.get("rounding"),
        scale.get("pass_grade"),
        scale.get("preset"),
    )


def _entries(evaluation_config: Any) -> List[Dict[str, Any]]:
    """The stored history as a plain list of entry dicts (never ``None``)."""
    if not isinstance(evaluation_config, dict):
        return []
    stored = evaluation_config.get(HISTORY_KEY)
    if not isinstance(stored, list):
        return []
    return [entry for entry in stored if isinstance(entry, dict)]


def _with_entries(
    evaluation_config: Any, entries: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """A shallow copy of the config carrying ``entries`` as its history.

    An empty list removes the key entirely rather than storing ``[]``, so a
    project that never had its key touched keeps a clean config document.
    """
    out = dict(evaluation_config) if isinstance(evaluation_config, dict) else {}
    if entries:
        out[HISTORY_KEY] = entries
    else:
        out.pop(HISTORY_KEY, None)
    return out


def _scale_snapshot(scale: Any) -> Optional[Dict[str, Any]]:
    """The value stored as an entry's ``from`` / ``to``.

    A copy of the scale as given (the writers have already validated and,
    on the extended side, normalized it), or ``None`` when there is no key
    — which is what "the platform default applies" looks like in storage.
    """
    if not isinstance(scale, dict) or not isinstance(scale.get("thresholds"), list):
        return None
    return dict(scale)


def append_grade_scale_change(
    evaluation_config: Any,
    *,
    old: Any,
    new: Any,
    actor_id: Optional[str],
) -> Dict[str, Any]:
    """Record a Notenschlüssel change on ``evaluation_config``.

    Returns a NEW config document with the entry appended (newest last) and
    the list trimmed to the most recent :data:`MAX_HISTORY_ENTRIES`. When the
    scale did not actually change (compared normalised), the config is
    returned unchanged — re-saving the same key, or saving an unrelated
    evaluation setting, writes no entry.

    ``old`` / ``new`` are the scale BEFORE and AFTER the write; either may be
    ``None`` (or anything that is not a scale) to mean "no key, the platform
    default applies".
    """
    if _comparable(old) == _comparable(new):
        return dict(evaluation_config) if isinstance(evaluation_config, dict) else {}

    entry: Dict[str, Any] = {
        "changed_at": datetime.now(timezone.utc).isoformat(),
        "changed_by": str(actor_id) if actor_id else None,
        "from": _scale_snapshot(old),
        "to": _scale_snapshot(new),
        "recomputed": None,
    }
    entries = _entries(evaluation_config) + [entry]
    return _with_entries(evaluation_config, entries[-MAX_HISTORY_ENTRIES:])


def mark_recomputed(evaluation_config: Any, count: int) -> Dict[str, Any]:
    """Stamp a finished recompute onto the NEWEST history entry.

    Returns a new config document. ``recomputed`` answers "how many stored
    grades has this key change moved so far", so repeated presses of
    "Notenpunkte aktualisieren" ACCUMULATE onto the same entry instead of
    overwriting it with the second run's (idempotent) zero. A recompute that
    moved nothing still turns a ``null`` stamp into ``0`` — the record then
    says the recompute ran.

    A no-op when there is no history (nothing has changed the key, so there
    is nothing a recompute belongs to).
    """
    entries = _entries(evaluation_config)
    if not entries:
        return dict(evaluation_config) if isinstance(evaluation_config, dict) else {}
    try:
        added = int(count)
    except (TypeError, ValueError):
        added = 0
    newest = dict(entries[-1])
    previous = newest.get("recomputed")
    newest["recomputed"] = (previous if isinstance(previous, int) else 0) + max(added, 0)
    return _with_entries(evaluation_config, entries[:-1] + [newest])


def latest_grade_scale_change(evaluation_config: Any) -> Optional[Dict[str, Any]]:
    """The most recent history entry, or ``None`` when the key was never changed."""
    entries = _entries(evaluation_config)
    return dict(entries[-1]) if entries else None


def carry_grade_scale_history(
    evaluation_config: Any, previous: Any
) -> Dict[str, Any]:
    """Copy the audit trail of ``previous`` onto a REBUILT config document.

    The extended exam editor rebuilds ``evaluation_config`` wholesale when
    the grading MODE changes (``build_exam_eval_config`` mints a fresh
    document). Without this, switching an exam between Falllösung and
    Bewertungsbogen grading would erase the record of every key change it
    ever had.
    """
    return _with_entries(evaluation_config, _entries(previous))


__all__ = [
    "GRADE_SCALE_KEY",
    "HISTORY_KEY",
    "MAX_HISTORY_ENTRIES",
    "append_grade_scale_change",
    "carry_grade_scale_history",
    "latest_grade_scale_change",
    "mark_recomputed",
]

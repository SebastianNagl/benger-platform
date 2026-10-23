"""Overlay-provided notes a rubric judge writes beside its scores.

The judge itself only scores. An overlay can have it also set notes on
passages of the answer (the extended edition's margin notes,
Randbemerkungen). It exposes::

    <package>.workers.get_judge_notes() -> JudgeNotes | None

(looked up through ``extension_registry``, gating class gated, so it only
answers while the package is active for the task), where a ``JudgeNotes``
provides

* ``enabled(metric_parameters) -> bool``: whether this grading gets notes
  (the overlay's own switches: feature flag, judge config).
* ``schema(refs, use_enum=True) -> dict``: the JSON schema of the
  ``annotations`` array in the judge's response, ``ref`` limited to
  ``refs`` (the scored step keys) while ``use_enum``.
* ``schema_cost(ref_count) -> (properties, enum_values)``: what
  ``schema`` adds, for the strict-mode budget of the response schema.
* ``rubric_rules() -> str``: the prompt block asking the rubric judge for
  the notes, appended after its closing rules.
* ``finalize(raw, answer, refs, *, index, zeroed_refs) -> list``: the
  notes as stored on the evaluation row (``details.annotations``) from the
  judge's raw ``annotations``; ``index`` is the answer's ``EvidenceIndex``,
  ``zeroed_refs`` the steps the evidence check zeroed.

Without an overlay (community edition) or while it is off for the task,
the judge asks for no notes and the row carries none. The platform keeps
the response plumbing and the row field; what a note is and how it is
checked belongs to the overlay.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def resolve_judge_notes() -> Optional[Any]:
    """The active overlay's notes provider, or None."""
    import extension_registry

    get_judge_notes = extension_registry.first_worker_attr("get_judge_notes")
    if get_judge_notes is None:
        return None
    try:
        return get_judge_notes()
    except Exception:  # pragma: no cover - a broken overlay must not stop grading
        logger.exception("judge notes lookup failed")
        return None


def judge_notes_enabled(metric_parameters: Any) -> bool:
    """Whether a judge with these parameters writes notes; False without a
    provider or when the provider cannot tell."""
    notes = resolve_judge_notes()
    if notes is None:
        return False
    try:
        return bool(notes.enabled(metric_parameters))
    except Exception:
        logger.warning("judge notes: enabled() failed, notes off", exc_info=True)
        return False

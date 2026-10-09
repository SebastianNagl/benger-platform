"""What a solver sees of their own task after submitting (pure helpers).

Two project switches decide it, both evaluated per task and only for a
solver with an own (non-cancelled) submission on that task:

- ``annotator_full_visibility_after_submit``: the REFERENCE, i.e. the
  reference solution (Musterlösung, Gliederung, Korrekturhinweise), the
  raw ``task.data`` and ``ground_truth``, and the guidance text of the
  grading sheet (step hints and section notes).
- ``annotator_step_detail_after_submit``: the STEP DETAIL of a grading, i.e.
  per-step scores, reasons and evidence and the outline of the grading sheet
  they render in. NULL follows the reference switch (the behaviour before
  migration 116); True/False decide it on their own.

The headline of a grading (total, grade, passed, overall assessment) is not
governed by either switch. Pure functions over the ORM row (or anything with
the same attributes), so the api, the workers and the extended overlay share
one rule.
"""

from __future__ import annotations

from typing import Any


def reference_revealed(project: Any) -> bool:
    """The project shows the reference to a solver after their submission."""
    return bool(getattr(project, "annotator_full_visibility_after_submit", False))


def step_detail_revealed(project: Any) -> bool:
    """The project shows the step detail of a grading after the submission.

    ``annotator_step_detail_after_submit`` when set, else the reference
    switch.
    """
    explicit = getattr(project, "annotator_step_detail_after_submit", None)
    if explicit is None:
        return reference_revealed(project)
    return bool(explicit)

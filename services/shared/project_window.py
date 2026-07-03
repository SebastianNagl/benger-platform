"""Project timed-access-window state — the pure, shared predicates.

A project carrying ``window_start_at`` / ``window_end_at`` is only writable
(annotate / generate / evaluate) between them, and its task data is hidden
before ``window_start_at`` — for the *access group* only; anyone who can edit
the project is exempt. Both columns NULL ⇒ no window ⇒ always open.

These three functions are pure (columns + ``now`` → answer, no DB, no raise) and
live in ``/shared`` so BOTH the api (request gating) and the workers
(auto-submit timer, which bypasses the API and must honor the window) compute
the state identically. The api-side *enforcement* wrappers that add the
editor-exemption check and raise ``HTTPException`` live in
``routers/projects/helpers.py`` and call these.
"""

from datetime import datetime, timezone
from typing import Optional


def project_window_state(project, now: Optional[datetime] = None) -> str:
    """Return ``"none" | "upcoming" | "open" | "closed"`` for a project's window.

    ``none`` when neither bound is set. Pure function of the two columns +
    ``now`` (defaults to UTC now).
    """
    start = getattr(project, "window_start_at", None)
    end = getattr(project, "window_end_at", None)
    if start is None and end is None:
        return "none"
    if now is None:
        now = datetime.now(timezone.utc)
    if start is not None and now < start:
        return "upcoming"
    if end is not None and now > end:
        return "closed"
    return "open"


def project_reads_allowed(project, now: Optional[datetime] = None) -> bool:
    """Whether task/annotation DATA may be read now (blocked only pre-open)."""
    return project_window_state(project, now) != "upcoming"


def project_writes_allowed(project, now: Optional[datetime] = None) -> bool:
    """Whether annotate / generate / evaluate WRITES are allowed now."""
    return project_window_state(project, now) in ("none", "open")

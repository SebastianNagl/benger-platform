"""Generic rules for the compliance records (migration 145, core 2.56).

The platform owns the persistence of compliance assessments, their suite runs
and the findings those runs produce (``models.ComplianceAssessment``,
``ComplianceSuiteRun``, ``ComplianceFinding``) and the generic CRUD over them
(``routers/compliance_records.py``). The meaning of a suite, a threshold or a
verdict, the assessment workflow and the scoring belong to the overlay that
writes the rows (benger-compliance). This module holds only the shape rules
both sides need, as plain data and pure functions over ORM objects, so the API
router, the overlay's routers and its Celery workers apply the same rules:

- the statuses of an assessment and the static table of allowed transitions
  (the overlay's workflow may refuse more; it may never allow more),
- the registration lock: once an assessment has left ``draft``, the fields
  that define what is tested and against which thresholds are fixed,
- terminal assessments (``attested``, ``superseded``, ``withdrawn``) and
  terminal suite runs are read-only, so the evidence they hold cannot change
  after the fact,
- the suite-run statuses and their transitions,
- the verdict vocabulary of a finding,
- :func:`canonical_sha256`, the hash of a JSON value in canonical form
  (sorted keys, compact separators, UTF-8), used for ``thresholds_hash``.

Nothing here touches the database session; callers load and commit.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

# --------------------------------------------------------------------------- #
# Assessments
# --------------------------------------------------------------------------- #

ASSESSMENT_DRAFT = "draft"
ASSESSMENT_REGISTERED = "registered"
ASSESSMENT_COLLECTING = "collecting"
ASSESSMENT_SCORING = "scoring"
ASSESSMENT_REVIEW = "review"
ASSESSMENT_ATTESTED = "attested"
ASSESSMENT_SUPERSEDED = "superseded"
ASSESSMENT_WITHDRAWN = "withdrawn"

ASSESSMENT_STATUSES = (
    ASSESSMENT_DRAFT,
    ASSESSMENT_REGISTERED,
    ASSESSMENT_COLLECTING,
    ASSESSMENT_SCORING,
    ASSESSMENT_REVIEW,
    ASSESSMENT_ATTESTED,
    ASSESSMENT_SUPERSEDED,
    ASSESSMENT_WITHDRAWN,
)

#: Static table of allowed status changes. ``scoring -> collecting`` and
#: ``review -> scoring`` let a workflow collect or score again before the
#: attestation; every open status can be withdrawn; only an attested
#: assessment can be superseded (by a newer one, ``supersedes_id``).
ASSESSMENT_TRANSITIONS: Mapping[str, frozenset] = {
    ASSESSMENT_DRAFT: frozenset({ASSESSMENT_REGISTERED, ASSESSMENT_WITHDRAWN}),
    ASSESSMENT_REGISTERED: frozenset({ASSESSMENT_COLLECTING, ASSESSMENT_WITHDRAWN}),
    ASSESSMENT_COLLECTING: frozenset({ASSESSMENT_SCORING, ASSESSMENT_WITHDRAWN}),
    ASSESSMENT_SCORING: frozenset(
        {ASSESSMENT_REVIEW, ASSESSMENT_COLLECTING, ASSESSMENT_WITHDRAWN}
    ),
    ASSESSMENT_REVIEW: frozenset(
        {ASSESSMENT_ATTESTED, ASSESSMENT_SCORING, ASSESSMENT_WITHDRAWN}
    ),
    ASSESSMENT_ATTESTED: frozenset({ASSESSMENT_SUPERSEDED}),
    ASSESSMENT_SUPERSEDED: frozenset(),
    ASSESSMENT_WITHDRAWN: frozenset(),
}

#: Statuses in which an assessment, its suite runs and its findings are
#: read-only.
TERMINAL_ASSESSMENT_STATUSES = frozenset(
    {ASSESSMENT_ATTESTED, ASSESSMENT_SUPERSEDED, ASSESSMENT_WITHDRAWN}
)

#: Fields fixed by the registration (any status other than ``draft``): what
#: is assessed, under which catalog, with which suites and thresholds.
REGISTRATION_LOCKED_FIELDS = (
    "catalog_version",
    "suites",
    "thresholds",
    "system_model_id",
    "release_id",
    "project_id",
)

# --------------------------------------------------------------------------- #
# Suite runs
# --------------------------------------------------------------------------- #

SUITE_RUN_QUEUED = "queued"
SUITE_RUN_RUNNING = "running"
SUITE_RUN_SUCCEEDED = "succeeded"
SUITE_RUN_FAILED = "failed"
SUITE_RUN_CANCELLED = "cancelled"

SUITE_RUN_STATUSES = (
    SUITE_RUN_QUEUED,
    SUITE_RUN_RUNNING,
    SUITE_RUN_SUCCEEDED,
    SUITE_RUN_FAILED,
    SUITE_RUN_CANCELLED,
)

SUITE_RUN_TRANSITIONS: Mapping[str, frozenset] = {
    SUITE_RUN_QUEUED: frozenset({SUITE_RUN_RUNNING, SUITE_RUN_FAILED, SUITE_RUN_CANCELLED}),
    SUITE_RUN_RUNNING: frozenset(
        {SUITE_RUN_SUCCEEDED, SUITE_RUN_FAILED, SUITE_RUN_CANCELLED}
    ),
    SUITE_RUN_SUCCEEDED: frozenset(),
    SUITE_RUN_FAILED: frozenset(),
    SUITE_RUN_CANCELLED: frozenset(),
}

#: A finished suite run (and its findings) is read-only.
TERMINAL_SUITE_RUN_STATUSES = frozenset(
    {SUITE_RUN_SUCCEEDED, SUITE_RUN_FAILED, SUITE_RUN_CANCELLED}
)

# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #

#: ``pass`` / ``fail`` / ``inconclusive`` are verdicts against a threshold;
#: ``informative`` is a reported figure without a verdict (a descriptive
#: rate, a diagnostic); ``not_applicable`` marks a requirement that does not
#: apply to the system or the data.
VERDICTS = ("pass", "fail", "inconclusive", "informative", "not_applicable")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ComplianceRecordConflict(Exception):
    """A write that the record's state does not allow (HTTP 409).

    ``code`` is a stable machine-readable reason, ``detail`` a sentence.
    """

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def canonical_json(value: Any) -> str:
    """``value`` as canonical JSON: sorted keys, compact separators, UTF-8
    text (non-ASCII kept), and non-finite floats refused."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def canonical_sha256(value: Any) -> str:
    """Hex SHA-256 of :func:`canonical_json` of ``value``."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def assessment_is_terminal(assessment) -> bool:
    return assessment.status in TERMINAL_ASSESSMENT_STATUSES


def assessment_is_registered(assessment) -> bool:
    """True once the assessment has left ``draft`` (the registration lock)."""
    return assessment.status != ASSESSMENT_DRAFT


def suite_run_is_terminal(suite_run) -> bool:
    return suite_run.status in TERMINAL_SUITE_RUN_STATUSES


def check_assessment_editable(assessment, fields) -> None:
    """Raise unless ``fields`` (names being changed) may be written now.

    A terminal assessment refuses every change; a registered one refuses the
    :data:`REGISTRATION_LOCKED_FIELDS`.
    """
    if assessment_is_terminal(assessment):
        raise ComplianceRecordConflict(
            "assessment_closed",
            f"The assessment is {assessment.status} and can no longer be changed.",
        )
    if assessment_is_registered(assessment):
        locked = sorted(set(fields) & set(REGISTRATION_LOCKED_FIELDS))
        if locked:
            raise ComplianceRecordConflict(
                "assessment_registered",
                "The assessment is registered; these fields are fixed: "
                + ", ".join(locked)
                + ".",
            )


def check_assessment_accepts_suite_runs(assessment) -> None:
    """Suite runs (and their findings) are written only while the assessment
    is open."""
    if assessment_is_terminal(assessment):
        raise ComplianceRecordConflict(
            "assessment_closed",
            f"The assessment is {assessment.status}; its suite runs and findings "
            "can no longer be changed.",
        )


def check_assessment_deletable(assessment) -> None:
    """Only a draft can be deleted; everything after the registration is
    evidence and stays (it can be withdrawn instead)."""
    if assessment.status != ASSESSMENT_DRAFT:
        raise ComplianceRecordConflict(
            "assessment_registered",
            "Only a draft assessment can be deleted; withdraw it instead.",
        )


def check_suite_run_deletable(assessment, suite_run) -> None:
    """A suite run can be deleted only while its assessment is a draft."""
    if assessment.status != ASSESSMENT_DRAFT:
        raise ComplianceRecordConflict(
            "assessment_registered",
            "Suite runs of a registered assessment are evidence and cannot be deleted.",
        )


def check_findings_writable(assessment, suite_run) -> None:
    """Findings are written, changed and deleted only while both their
    assessment and their suite run are open."""
    check_assessment_accepts_suite_runs(assessment)
    if suite_run_is_terminal(suite_run):
        raise ComplianceRecordConflict(
            "suite_run_finished",
            f"The suite run is {suite_run.status}; its findings are fixed.",
        )


def transition_assessment(
    assessment, to_status: str, *, now: Optional[datetime] = None
) -> None:
    """Move ``assessment`` to ``to_status`` if the static table allows it.

    Sets ``registered_at`` and ``thresholds_hash`` (canonical SHA-256 of
    ``thresholds``) on registration and ``attested_at`` on attestation. The
    caller commits. Raises :class:`ComplianceRecordConflict` (code
    ``invalid_transition``) otherwise, and ``ValueError`` for an unknown
    status.
    """
    if to_status not in ASSESSMENT_STATUSES:
        raise ValueError(f"Unknown assessment status {to_status!r}")
    allowed = ASSESSMENT_TRANSITIONS.get(assessment.status, frozenset())
    if to_status not in allowed:
        raise ComplianceRecordConflict(
            "invalid_transition",
            f"An assessment cannot move from {assessment.status} to {to_status}.",
        )
    stamp = now or _now()
    if to_status == ASSESSMENT_REGISTERED:
        assessment.registered_at = stamp
        assessment.thresholds_hash = canonical_sha256(assessment.thresholds or {})
    elif to_status == ASSESSMENT_ATTESTED:
        assessment.attested_at = stamp
    assessment.status = to_status


def transition_suite_run(
    suite_run, to_status: str, *, now: Optional[datetime] = None
) -> None:
    """Move ``suite_run`` to ``to_status`` if the static table allows it.

    Stamps ``started_at`` when it starts running (unless already set) and
    ``finished_at`` when it reaches a terminal status. Raises
    :class:`ComplianceRecordConflict` (code ``invalid_transition``) or
    ``ValueError`` for an unknown status.
    """
    if to_status not in SUITE_RUN_STATUSES:
        raise ValueError(f"Unknown suite run status {to_status!r}")
    if to_status == suite_run.status:
        return
    allowed = SUITE_RUN_TRANSITIONS.get(suite_run.status, frozenset())
    if to_status not in allowed:
        raise ComplianceRecordConflict(
            "invalid_transition",
            f"A suite run cannot move from {suite_run.status} to {to_status}.",
        )
    stamp = now or _now()
    if to_status == SUITE_RUN_RUNNING and suite_run.started_at is None:
        suite_run.started_at = stamp
    if to_status in TERMINAL_SUITE_RUN_STATUSES:
        suite_run.finished_at = stamp
    suite_run.status = to_status

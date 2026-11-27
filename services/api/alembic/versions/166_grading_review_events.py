"""Review history of gradings: the append-only ``grading_review_events``

New table ``grading_review_events``: one entry per review step of a grading
(a ``task_evaluations`` row), written by the overlay's review workflow from
core 2.92 on: project, task, the grading and the submission it grades
(``task_evaluation_id`` and ``annotation_id``, SET NULL), its config and
metric, the person (``actor_id``, SET NULL), the event, the time, the review
before and after, a diff, the app version and a context. A ``BEFORE UPDATE``
trigger refuses every UPDATE except setting ``task_evaluation_id``,
``annotation_id`` and/or ``actor_id`` to NULL (their ``ON DELETE SET NULL``
actions); DELETE stays allowed (project and task cascades, account
erasure). The trigger SQL is the same as
``models.GRADING_REVIEW_EVENTS_APPEND_ONLY_DDL``, kept verbatim here because
a migration never imports the models.

Backfill, exact: until now a grading's review lived only in the JSON of its
row (``metrics[<metric>].details.review``, or ``review`` in the flat
``<metric>_details`` sibling), with the last actor and times and no
history. For every such review, the facts it records become entries, with
``context.backfill`` true and nothing guessed:

- ``released`` at ``released_at``, with ``context.released_by`` (``judge``
  for a judge that released by itself, ``teacher`` for a teacher's release)
  and ``context.auto`` when set. The teacher is recorded only when the same
  call stamped them: ``checked_by`` when ``checked_at`` equals
  ``released_at``, else ``reviewed_by`` when ``updated_at`` equals it (one
  review call stamps all its fields with one time). A judge's release has
  no person.
- ``checked`` at ``checked_at`` by ``checked_by``, unless the release
  stamped it (then it is part of the ``released`` entry).
- ``updated`` at ``updated_at`` by ``reviewed_by`` when the last review call
  was neither the release nor the check (an edit, a check cleared, a release
  taken back: the JSON does not say which).
- The latest of a review's entries carries the review as ``review_after``:
  it is exactly the state that call left. ``context.reason`` keeps the
  review's ``reason`` (``regrade``).

A review without any recorded time (an untouched draft) gives no entry. A
time that does not parse is left out. Entry ids are derived from the row,
the metric and the event (uuid5), and inserted with ``ON CONFLICT DO
NOTHING``, so a re-run adds nothing twice.

Only rows that can hold such a review are read, not every grading blob
(1.36M rows on dev): a review with a time is written either at insert by
the feedback judge (rows holding ``llm_judge_feedback``, found through the
``task_evaluation_metric_keys`` mirror, complete since revision 139) or by a
later update of the row (a teacher's review call, a withdrawal), which sets
``task_evaluations.updated_at`` (stamped on every ORM update since revision
106, kept by imports). A re-grade draft gets its first time from such an
update too.

Idempotent: the table, indexes and trigger are created only when missing,
so a database built from the models (the test DB, which gets the trigger
from the model's ``after_create`` listener) runs the schema steps as a
no-op, and the backfill skips entries already present.

Revision ID: 166_grading_review_events
Revises: 165_project_questionnaires
Create Date: 2026-11-27
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional

from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa

revision = "166_grading_review_events"
down_revision = "165_project_questionnaires"
branch_labels = None
depends_on = None

_EVENTS = "grading_review_events"
_TRIGGER = "trg_grading_review_events_append_only"
_FUNCTION = "grading_review_events_append_only"

_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION grading_review_events_append_only() RETURNS trigger AS $fn$
BEGIN
    IF (to_jsonb(NEW) - 'task_evaluation_id' - 'annotation_id' - 'actor_id')
           IS DISTINCT FROM (to_jsonb(OLD) - 'task_evaluation_id' - 'annotation_id' - 'actor_id')
       OR (NEW.task_evaluation_id IS DISTINCT FROM OLD.task_evaluation_id AND NEW.task_evaluation_id IS NOT NULL)
       OR (NEW.annotation_id IS DISTINCT FROM OLD.annotation_id AND NEW.annotation_id IS NOT NULL)
       OR (NEW.actor_id IS DISTINCT FROM OLD.actor_id AND NEW.actor_id IS NOT NULL) THEN
        RAISE EXCEPTION 'grading_review_events is append-only'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql
"""
_APPEND_ONLY_TRIGGER = """
CREATE TRIGGER trg_grading_review_events_append_only
BEFORE UPDATE ON grading_review_events
FOR EACH ROW EXECUTE FUNCTION grading_review_events_append_only()
"""

_INDEXES = (
    ("ix_grading_review_events_project_id", ["project_id"]),
    ("ix_grading_review_events_task_id", ["task_id"]),
    ("ix_grading_review_events_task_evaluation_id", ["task_evaluation_id"]),
    ("ix_grading_review_events_annotation_id", ["annotation_id"]),
    ("ix_grading_review_events_created_at", ["created_at"]),
    ("ix_grading_review_events_project_created", ["project_id", "created_at"]),
    ("ix_grading_review_events_evaluation_created", ["task_evaluation_id", "created_at"]),
)

#: Namespace of the backfilled entry ids (uuid5 of row, metric and event).
BACKFILL_NAMESPACE = uuid.UUID("5d0f8a52-6c1e-4f0b-9a57-2b8f3c1d9e66")
_DETAILS_SUFFIX = "_details"
_FEEDBACK_METRIC = "llm_judge_feedback"

# Every review a row holds, one per metric: ``(row, metric, review)``. The
# review sits in ``details`` of a ``{value, method, details}`` blob or in the
# flat ``<metric>_details`` sibling. Only the small review object leaves the
# database.
_REVIEWS_SQL = """
SELECT te.id AS task_evaluation_id, te.task_id, t.project_id, te.annotation_id,
       te.evaluation_config_id,
       CASE WHEN right(j.key, 8) = '_details' THEN left(j.key, -8) ELSE j.key END AS metric,
       CASE WHEN right(j.key, 8) = '_details' THEN j.value -> 'review'
            ELSE j.value -> 'details' -> 'review' END AS review
FROM task_evaluations te
JOIN tasks t ON t.id = te.task_id
CROSS JOIN LATERAL jsonb_each(
    CASE WHEN jsonb_typeof(te.metrics) = 'object' THEN te.metrics ELSE '{}'::jsonb END
) AS j(key, value)
WHERE (te.updated_at IS NOT NULL
       OR te.id IN (SELECT k.task_evaluation_id FROM task_evaluation_metric_keys k
                    WHERE k.metric_keys ? :feedback))
  AND jsonb_typeof(j.value) = 'object'
  AND jsonb_typeof(
        CASE WHEN right(j.key, 8) = '_details' THEN j.value -> 'review'
             ELSE j.value -> 'details' -> 'review' END
      ) = 'object'
ORDER BY te.id, j.key
"""


def _insp():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _insp().get_indexes(table)}


def _has_trigger() -> bool:
    found = op.get_bind().execute(
        text("SELECT 1 FROM pg_trigger WHERE tgname = :name AND NOT tgisinternal"),
        {"name": _TRIGGER},
    )
    return found.first() is not None


def _parse(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _text(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def review_events(review: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The entries one stored review records exactly (see the module doc),
    oldest first: ``{"event", "at", "actor_id", "context"}``, the latest
    with ``review_after``. Pure."""
    if not isinstance(review, Mapping):
        return []
    released_at = _text(review.get("released_at"))
    checked_at = _text(review.get("checked_at"))
    updated_at = _text(review.get("updated_at"))
    checked_by = _text(review.get("checked_by"))
    reviewed_by = _text(review.get("reviewed_by"))
    released_by = _text(review.get("released_by"))
    base: Dict[str, Any] = {"backfill": True}
    if _text(review.get("reason")):
        base["reason"] = review["reason"]

    events: List[Dict[str, Any]] = []
    if released_at and _parse(released_at):
        context = dict(base)
        if released_by:
            context["released_by"] = released_by
        if review.get("auto") is True:
            context["auto"] = True
        # A teacher's release names its releaser; ``auto`` alone (a judge's
        # release from before ``released_by`` existed) does not, nor does
        # ``auto`` left over on a regrading a teacher released since.
        by_judge = released_by == "judge" or (
            released_by is None and review.get("auto") is True
        )
        actor = None
        if not by_judge:
            if checked_at == released_at and checked_by:
                actor = checked_by
            elif updated_at == released_at and reviewed_by:
                actor = reviewed_by
        events.append({"event": "released", "at": released_at, "actor_id": actor, "context": context})
    if checked_at and checked_at != released_at and _parse(checked_at):
        events.append(
            {"event": "checked", "at": checked_at, "actor_id": checked_by, "context": dict(base)}
        )
    if (
        updated_at
        and updated_at not in (released_at, checked_at)
        and _parse(updated_at)
    ):
        events.append(
            {"event": "updated", "at": updated_at, "actor_id": reviewed_by, "context": dict(base)}
        )
    if not events:
        return []
    events.sort(key=lambda e: _parse(e["at"]))
    events[-1]["review_after"] = dict(review)
    return events


def backfill_rows(rows: Iterable[Mapping[str, Any]], known_users: Iterable[str]) -> List[Dict[str, Any]]:
    """The ``grading_review_events`` rows for the reviews ``rows`` hold
    (``_REVIEWS_SQL`` shape). An actor that is no longer a user stays NULL,
    as an ``ON DELETE SET NULL`` would have left it. Pure."""
    users = set(known_users)
    out: List[Dict[str, Any]] = []
    for row in rows:
        review = row.get("review")
        if isinstance(review, str):
            try:
                review = json.loads(review)
            except ValueError:
                continue
        for entry in review_events(review):
            actor = entry["actor_id"] if entry["actor_id"] in users else None
            out.append(
                {
                    "id": str(
                        uuid.uuid5(
                            BACKFILL_NAMESPACE,
                            f"{row['task_evaluation_id']}|{row['metric']}|{entry['event']}",
                        )
                    ),
                    "project_id": row["project_id"],
                    "task_id": row["task_id"],
                    "task_evaluation_id": row["task_evaluation_id"],
                    "annotation_id": row.get("annotation_id"),
                    "evaluation_config_id": row.get("evaluation_config_id"),
                    "metric": (row["metric"] or "")[:64] or None,
                    "actor_id": actor,
                    "event": entry["event"],
                    "created_at": _parse(entry["at"]),
                    "review_after": entry.get("review_after"),
                    "context": entry["context"],
                }
            )
    return out


_INSERT_SQL = text(
    """
    INSERT INTO grading_review_events (
        id, project_id, task_id, task_evaluation_id, annotation_id,
        evaluation_config_id, metric, actor_id, event, created_at,
        review_after, context
    ) VALUES (
        :id, :project_id, :task_id, :task_evaluation_id, :annotation_id,
        :evaluation_config_id, :metric, :actor_id, :event, :created_at,
        CAST(:review_after AS jsonb), CAST(:context AS jsonb)
    )
    ON CONFLICT (id) DO NOTHING
    """
)
_BATCH = 1000


def backfill(connection) -> int:
    """Insert the backfilled entries (see the module doc); the number of
    entries the reviews gave (already present ones included)."""
    rows = [
        dict(r._mapping)
        for r in connection.execute(text(_REVIEWS_SQL), {"feedback": _FEEDBACK_METRIC})
    ]
    actors = {
        value
        for row in rows
        if isinstance(row.get("review"), Mapping)
        for value in (row["review"].get("checked_by"), row["review"].get("reviewed_by"))
        if isinstance(value, str) and value
    }
    known = set()
    actor_list = sorted(actors)
    for i in range(0, len(actor_list), _BATCH):
        chunk = actor_list[i : i + _BATCH]
        known.update(
            r[0]
            for r in connection.execute(
                text("SELECT id FROM users WHERE id = ANY(:ids)"), {"ids": chunk}
            )
        )
    entries = backfill_rows(rows, known)
    for i in range(0, len(entries), _BATCH):
        chunk = [
            {
                **entry,
                "review_after": (
                    json.dumps(entry["review_after"]) if entry["review_after"] is not None else None
                ),
                "context": json.dumps(entry["context"]),
            }
            for entry in entries[i : i + _BATCH]
        ]
        connection.execute(_INSERT_SQL, chunk)
    return len(entries)


def upgrade() -> None:
    if not _has_table(_EVENTS):
        op.create_table(
            _EVENTS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id", sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column(
                "task_id", sa.String(),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column(
                "task_evaluation_id", sa.String(),
                sa.ForeignKey("task_evaluations.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column(
                "annotation_id", sa.String(),
                sa.ForeignKey("annotations.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("evaluation_config_id", sa.String(), nullable=True),
            sa.Column("metric", sa.String(64), nullable=True),
            sa.Column(
                "actor_id", sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("event", sa.String(24), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column("review_before", postgresql.JSONB(), nullable=True),
            sa.Column("review_after", postgresql.JSONB(), nullable=True),
            sa.Column("diff", postgresql.JSONB(), nullable=True),
            sa.Column("app_version", sa.String(128), nullable=True),
            sa.Column("context", postgresql.JSONB(), nullable=True),
        )
    for name, columns in _INDEXES:
        if not _has_index(_EVENTS, name):
            op.create_index(name, _EVENTS, columns)

    op.execute(_APPEND_ONLY_FUNCTION)
    if not _has_trigger():
        op.execute(_APPEND_ONLY_TRIGGER)

    backfill(op.get_bind())


def downgrade() -> None:
    if _has_table(_EVENTS):
        op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON {_EVENTS}")
        op.drop_table(_EVENTS)
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")

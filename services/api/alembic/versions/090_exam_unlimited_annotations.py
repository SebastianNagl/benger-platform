"""lift the per-task annotation cap on exam projects

``projects.maximum_annotations`` defaults to 1 — a crowd-labeling knob
capping TOTAL annotations per task. Exam-kind projects are solved by many
participants (share links, org membership, LTI cohorts), each submitting
their own annotation to the same task, so the cap blocked every participant
after the first with "Maximum annotations limit reached (1)" (found by the
2026-08-06 ILIAS LTI spike when a second student submitted; every earlier
exam flow only ever had one submitter). 0 means unlimited.

The exam creation path (extended ``student_exams.create_exam``) now sets 0
explicitly; this migration backfills the exams that already exist. Per-user
duplicate protection is enforced separately (one active annotation per
task+user), so lifting the cap does not allow double submissions.

Data-only, idempotent, no schema change. Downgrade is a deliberate no-op —
restoring a cap of 1 on live exams would re-break their participants.

Revision ID: 090_exam_unlimited_annotations
Revises: 089_add_lti_lms_family
Create Date: 2026-08-06
"""

import sqlalchemy as sa

from alembic import op


revision = "090_exam_unlimited_annotations"
down_revision = "089_add_lti_lms_family"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE projects SET maximum_annotations = 0 "
            "WHERE kind = 'exam' AND maximum_annotations = 1"
        )
    )


def downgrade() -> None:
    # Deliberate no-op: see module docstring.
    pass

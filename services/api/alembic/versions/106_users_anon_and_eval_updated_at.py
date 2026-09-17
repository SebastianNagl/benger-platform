"""task_evaluations.updated_at, users.anonymized_at, LMS email state and origin, attachment origin

- ``task_evaluations.updated_at``: nullable, no backfill. The model stamps it
  on every ORM update, so in-place grade changes (human revisions,
  Notenschlüssel recomputes) are visible to the grade-transfer sweep.
- ``users.anonymized_at``: set when an account is anonymized. The row stays
  (answers and grades remain as anonymous records); the marker lets views
  and the reactivation guard tell such accounts apart.
- ``ix_users_email_lower``: case-insensitive email lookups (account-link
  proof, collision checks on LMS launches).
- ``users.lms_provisioned_at`` / ``users.lms_origin_org_id``: the account
  came from an LMS launch, and from which org's connection. The identity
  link is not enough: deleting a connection cascades its links away, and the
  kept accounts would lose their pseudonym masking (D8). Backfilled from the
  earliest ``provisioned`` link of each account. ``lms_origin_org_id`` is
  ``ON DELETE SET NULL`` (orgs are soft-deleted anyway).
- LMS email state backfill, restricted to accounts an LMS launch created
  (``lti_user_links.link_method = 'provisioned'``, migration 105) that still
  carry the old ``email_verification_method = 'system'``. Only the method
  changes:
  - with a password (the account was activated): method ``activation``;
  - without one: method ``lti_claim``. The address came from the LMS and was
    never proven. ``email_ownership_proven`` treats the method as unproven,
    and activation and password reset re-stamp it
    (``account_activation.verify_email_by_link``).
  ``email_verified`` and ``email_verified_at`` stay as they are. The older
  code activates an account without verifying its address, and login
  refuses unverified accounts. Clearing the flag would lock out every
  account activated by an old pod during the rolling update or after a
  ``helm rollback`` (which leaves this migration applied). A passwordless
  account cannot log in anyway, so the flag protects nothing here.
  Accounts the new code creates start unverified; after a rollback run the
  downgrade UPDATE below (not the schema downgrade) so old pods can
  activate them.
  The downgrade turns ``lti_claim`` accounts back into verified ``system``
  accounts, which is what the older code expects.
- ``project_organizations.attached_via`` (``manual`` | ``lti``; part of the
  LMS self-service schema of 105). Backfill ``lti`` for attachments an LTI
  link created:
  - every attachment of a private exam. Linking is the only writer of those
    rows (project create and the visibility PATCH never attach private
    projects, and "make private" deletes all attachments), so this also
    catches attachments a relink left behind;
  - an attachment of a non-private exam only when a resource link of a
    registration of the same org points at the exam, the teacher who bound
    that link made the attachment, and it was made when the link was bound
    (within a minute of ``linked_at``, which the app takes just after the
    transaction start that stamps ``created_at``). A share the author made
    at another time, for example between the first launch and the binding,
    stays ``manual``. When in doubt a row stays ``manual``: cleanup and
    conflict checks then leave it alone.

Lock order. 105 and 106 run in one transaction, so every lock is held until
the end. ``task_evaluations`` comes first: workers keep grading transactions
open during LLM calls, so this lock is the one most likely to time out. At
that point 105 holds only the quiet LTI tables plus a share lock on ``users``
and ``organizations`` (new foreign keys), which lets reads through.
``users`` and ``project_organizations`` are read by nearly every request, so
their exclusive locks come last and the transaction commits right after
them. Each step uses ``lock_timeout``; on a timeout the migration fails and
the pod retries (strict mode) instead of queueing requests behind the ALTER.
Before the rollout, check ``pg_stat_activity`` for long open transactions on
``task_evaluations``.

Revision ID: 106_users_anon_and_eval_updated_at
Revises: 105_lti_self_service
Create Date: 2026-09-16
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "106_users_anon_and_eval_updated_at"
down_revision = "105_lti_self_service"
branch_labels = None
depends_on = None

_EMAIL_INDEX = "ix_users_email_lower"
_ORIGIN_ORG_INDEX = "ix_users_lms_origin_org_id"
_ORIGIN_ORG_FK = "fk_users_lms_origin_org_id"
_ATTACHMENTS = "project_organizations"
_ATTACHED_VIA_CHECK = "ck_project_organizations_attached_via"


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return column in {col["name"] for col in insp.get_columns(table)}


def _index_exists(table: str, name: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def _check_exists(table: str, name: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {ck["name"] for ck in insp.get_check_constraints(table)}


def _upgrade_task_evaluations() -> None:
    if not _column_exists("task_evaluations", "updated_at"):
        op.add_column(
            "task_evaluations",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def _upgrade_users() -> None:
    if not _column_exists("users", "anonymized_at"):
        op.add_column(
            "users",
            sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _index_exists("users", _EMAIL_INDEX):
        op.create_index(_EMAIL_INDEX, "users", [sa.text("lower(email)")])
    if not _column_exists("users", "lms_provisioned_at"):
        op.add_column(
            "users",
            sa.Column("lms_provisioned_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _column_exists("users", "lms_origin_org_id"):
        op.add_column(
            "users",
            sa.Column(
                "lms_origin_org_id",
                sa.String(),
                sa.ForeignKey(
                    "organizations.id",
                    name=_ORIGIN_ORG_FK,
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
        )
    if not _index_exists("users", _ORIGIN_ORG_INDEX):
        op.create_index(_ORIGIN_ORG_INDEX, "users", ["lms_origin_org_id"])
    # Idempotent by construction: only 'system' rows are touched, and every
    # touched row leaves that state.
    if _column_exists("lti_user_links", "link_method"):
        op.execute(
            """
            UPDATE users AS u
            SET email_verification_method = CASE
                    WHEN COALESCE(u.hashed_password, '') <> '' THEN 'activation'
                    ELSE 'lti_claim'
                END
            WHERE u.email_verification_method = 'system'
              AND EXISTS (
                SELECT 1 FROM lti_user_links AS l
                WHERE l.user_id = u.id AND l.link_method = 'provisioned'
              )
            """
        )
        # Idempotent: only unmarked accounts are touched.
        op.execute(
            """
            UPDATE users AS u
            SET lms_provisioned_at = origin.created_at,
                lms_origin_org_id = origin.organization_id
            FROM (
                SELECT DISTINCT ON (l.user_id)
                    l.user_id, l.created_at, r.organization_id
                FROM lti_user_links AS l
                JOIN lti_platform_registrations AS r
                  ON r.id = l.registration_id
                WHERE l.link_method = 'provisioned'
                ORDER BY l.user_id, l.created_at, l.id
            ) AS origin
            WHERE u.id = origin.user_id
              AND u.lms_provisioned_at IS NULL
            """
        )


def _upgrade_attachments() -> None:
    added = False
    if not _column_exists(_ATTACHMENTS, "attached_via"):
        op.add_column(
            _ATTACHMENTS,
            sa.Column(
                "attached_via",
                sa.String(length=16),
                nullable=False,
                server_default="manual",
            ),
        )
        added = True
    if not _check_exists(_ATTACHMENTS, _ATTACHED_VIA_CHECK):
        op.create_check_constraint(
            _ATTACHED_VIA_CHECK,
            _ATTACHMENTS,
            "attached_via IN ('manual', 'lti')",
        )
    if not added:
        return
    op.execute(
        """
        UPDATE project_organizations AS po
        SET attached_via = 'lti'
        FROM projects AS p
        WHERE p.id = po.project_id
          AND (
            (p.is_private IS TRUE AND p.kind = 'exam')
            OR EXISTS (
              SELECT 1
              FROM lti_resource_links AS l
              JOIN lti_platform_registrations AS r
                ON r.id = l.registration_id
              WHERE l.project_id = po.project_id
                AND r.organization_id = po.organization_id
                AND l.created_at <= po.created_at
                AND l.linked_by = po.assigned_by
                AND l.linked_at IS NOT NULL
                AND po.created_at
                    BETWEEN l.linked_at - interval '1 minute'
                        AND l.linked_at + interval '1 minute'
            )
          )
        """
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    _upgrade_task_evaluations()
    _upgrade_users()
    _upgrade_attachments()


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _check_exists(_ATTACHMENTS, _ATTACHED_VIA_CHECK):
        op.drop_constraint(_ATTACHED_VIA_CHECK, _ATTACHMENTS, type_="check")
    if _column_exists(_ATTACHMENTS, "attached_via"):
        op.drop_column(_ATTACHMENTS, "attached_via")
    op.execute(
        """
        UPDATE users
        SET email_verification_method = 'system',
            email_verified = true,
            email_verified_at = COALESCE(email_verified_at, now())
        WHERE email_verification_method = 'lti_claim'
        """
    )
    if _index_exists("users", _EMAIL_INDEX):
        op.drop_index(_EMAIL_INDEX, table_name="users")
    if _index_exists("users", _ORIGIN_ORG_INDEX):
        op.drop_index(_ORIGIN_ORG_INDEX, table_name="users")
    # Dropping the column drops its foreign key too.
    for column in ("lms_origin_org_id", "lms_provisioned_at"):
        if _column_exists("users", column):
            op.drop_column("users", column)
    if _column_exists("users", "anonymized_at"):
        op.drop_column("users", "anonymized_at")
    if _column_exists("task_evaluations", "updated_at"):
        op.drop_column("task_evaluations", "updated_at")

"""LTI self-service: tool host, proof-based identity, grade columns, audit trail

Schema for org-admin run LMS connections. The schema is platform-owned (split
rule: ALL DB tables live in benger-platform); the protocol logic that reads and
writes these columns lives in ``benger_extended``. The community edition only
carries the forward-compatible schema.

- ``lti_platform_registrations.tool_host`` / ``lti_registration_invites.tool_host``:
  which public host a connection's tool URLs use (``student_locked`` | ``main``,
  resolved from the environment by ``shared/public_hosts.py``). Existing rows
  keep the student-locked host.
- ``lti_user_links``:
  - ``research_consent_at``: when the research-use consent was given.
  - ``link_method``: how the LMS identity reached the account
    (``provisioned`` | ``login_proof`` | ``email_proof`` | ``legacy_email``).
    Backfill: ``provisioned`` when the account's username is exactly the
    synthetic identity the launch derived for it,
    ``'lti-' || first 16 hex chars of sha256(issuer || '|' || sub)``, or when
    it has the synthetic shape (``lti-`` plus 16 hex chars) and was created
    in the same transaction as the link (equal ``created_at``; only the
    launch that provisioned an account does that). The second rule keeps
    accounts whose connection's issuer was edited later. Every other
    existing link was made by the old automatic email match and becomes
    ``legacy_email``. Nullable, so old pods can still insert during a
    rolling deploy (NULL counts as "not provisioned").
  - ``unlinked_at``: tombstone for an admin unlink.
- ``lti_resource_links.ai_lineitem_*``: the tool-created AI grade column
  (``ready`` | ``unavailable`` | ``error`` | ``deleted``) and its last error.
- ``lti_grade_syncs``: ``kind`` (``final`` | ``ai``, existing rows are
  ``final``), ``last_synced_source``, ``last_checked_at``. ``uq_lti_grade_sync``
  is recreated on (resource_link_id, user_id, kind) under the same name.
  The downgrade deletes the ``kind <> 'final'`` rows first; the sweep can
  rebuild them.
- New ``lti_resource_link_users``: who took part in which activity, and
  whether as instructor. Written only after consent. Backfill from consented
  user links of the same registration:
  - the teacher who bound a link gets an instructor row on it;
  - a learner (cached launch roles without an instructor marker) gets a row
    on each link whose project they launched into (grade sync row on the
    link, an annotation or an entitlement on its exam);
  - a consented learner without any such trace gets a row on every bound
    link of the registration, because the old schema cannot tell which
    activity they came from.
  Other instructors get no rows: the old consent step gave every consenting
  user an entitlement, so a teacher of one course would otherwise gain an
  instructor row on another course's link to the same exam. They get their
  row on their next launch.
- New ``lti_admin_events``: audit trail of connection changes. ``changes``
  holds ``{field: {old, new}}`` diffs, never personal data or secrets.
  ``group_id`` (SET NULL) is the group scope of the connection or invite an
  entry is about, so group admins can read their groups' history after a
  connection is deleted.

``project_organizations.attached_via`` belongs to the same feature but is
added at the end of 106 (see there for the lock ordering).

Every step is guarded (inspector checks) and safe to re-run; the data
backfills run only in the run that adds their column or table. The migration
sets ``lock_timeout`` and fails fast instead of queueing behind a long
transaction. 105 locks the LTI tables, which see little traffic. The foreign
keys of the two new tables also take a share lock on ``users`` and
``organizations``: reads go on, writes wait until the release commits. 105 and
106 run in one transaction; with ``SCHEMA_VALIDATION_MODE=strict`` a failed
run aborts the whole release.

Revision ID: 105_lti_self_service
Revises: 104_add_evaluation_received_notification_types
Create Date: 2026-09-16
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "105_lti_self_service"
down_revision = "104_add_evaluation_received_notification_types"
branch_labels = None
depends_on = None

TOOL_HOSTS = ("student_locked", "main")
LINK_METHODS = ("provisioned", "login_proof", "email_proof", "legacy_email")
AI_LINEITEM_STATUSES = ("ready", "unavailable", "error", "deleted")
GRADE_SYNC_KINDS = ("final", "ai")

# Snapshot of the IMS role markers the launch treats as "instructor" (LTI 1.3
# role vocabulary), used only by the participation backfill below.
_INSTRUCTOR_ROLE_REGEX = (
    "membership#(Instructor|ContentDeveloper|Administrator)"
    "|(institution|system)/person#Administrator"
)

_REGISTRATIONS = "lti_platform_registrations"
_INVITES = "lti_registration_invites"
_USER_LINKS = "lti_user_links"
_RESOURCE_LINKS = "lti_resource_links"
_GRADE_SYNCS = "lti_grade_syncs"
_LINK_USERS = "lti_resource_link_users"
_EVENTS = "lti_admin_events"

_GRADE_SYNC_UNIQUE = "uq_lti_grade_sync"


def _in_list(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _table_exists(table: str) -> bool:
    return table in inspect(op.get_bind()).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return column in {col["name"] for col in insp.get_columns(table)}


def _check_exists(table: str, name: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {ck["name"] for ck in insp.get_check_constraints(table)}


def _index_exists(table: str, name: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def _unique_columns(table: str, name: str):
    """Column list of the named unique constraint, or None if it is missing."""
    insp = inspect(op.get_bind())
    for uq in insp.get_unique_constraints(table):
        if uq["name"] == name:
            return list(uq["column_names"])
    return None


def _add_column(table: str, column: sa.Column) -> bool:
    """Add ``column`` unless it exists. True when this run added it."""
    if _column_exists(table, column.name):
        return False
    op.add_column(table, column)
    return True


def _add_check(table: str, name: str, condition: str) -> None:
    if not _check_exists(table, name):
        op.create_check_constraint(name, table, condition)


def _drop_check(table: str, name: str) -> None:
    if _check_exists(table, name):
        op.drop_constraint(name, table, type_="check")


def _drop_column(table: str, column: str) -> None:
    if _column_exists(table, column):
        op.drop_column(table, column)


def _tool_host_column() -> sa.Column:
    return sa.Column(
        "tool_host",
        sa.String(length=16),
        nullable=False,
        server_default="student_locked",
    )


def _upgrade_tool_host() -> None:
    for table in (_REGISTRATIONS, _INVITES):
        _add_column(table, _tool_host_column())
        _add_check(
            table, f"ck_{table}_tool_host", f"tool_host IN ({_in_list(TOOL_HOSTS)})"
        )


def _upgrade_user_links() -> None:
    _add_column(
        _USER_LINKS,
        sa.Column("research_consent_at", sa.DateTime(timezone=True), nullable=True),
    )
    method_added = _add_column(
        _USER_LINKS, sa.Column("link_method", sa.String(length=16), nullable=True)
    )
    _add_check(
        _USER_LINKS,
        "ck_lti_user_links_link_method",
        f"link_method IN ({_in_list(LINK_METHODS)})",
    )
    _add_column(
        _USER_LINKS,
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
    )
    if method_added:
        op.execute(
            """
            UPDATE lti_user_links AS l
            SET link_method = CASE
                WHEN u.username = 'lti-' || substr(
                    encode(
                        sha256(convert_to(r.issuer || '|' || l.sub, 'UTF8')),
                        'hex'
                    ),
                    1,
                    16
                )
                THEN 'provisioned'
                WHEN u.username ~ '^lti-[0-9a-f]{16}$'
                     AND u.created_at = l.created_at
                THEN 'provisioned'
                ELSE 'legacy_email'
            END
            FROM users AS u, lti_platform_registrations AS r
            WHERE u.id = l.user_id
              AND r.id = l.registration_id
              AND l.link_method IS NULL
            """
        )


def _upgrade_resource_links() -> None:
    _add_column(_RESOURCE_LINKS, sa.Column("ai_lineitem_url", sa.Text(), nullable=True))
    _add_column(
        _RESOURCE_LINKS,
        sa.Column("ai_lineitem_status", sa.String(length=16), nullable=True),
    )
    _add_check(
        _RESOURCE_LINKS,
        "ck_lti_resource_links_ai_lineitem_status",
        f"ai_lineitem_status IN ({_in_list(AI_LINEITEM_STATUSES)})",
    )
    _add_column(
        _RESOURCE_LINKS, sa.Column("ai_lineitem_error", sa.Text(), nullable=True)
    )


def _upgrade_grade_syncs() -> None:
    _add_column(
        _GRADE_SYNCS,
        sa.Column(
            "kind", sa.String(length=16), nullable=False, server_default="final"
        ),
    )
    _add_check(
        _GRADE_SYNCS,
        "ck_lti_grade_syncs_kind",
        f"kind IN ({_in_list(GRADE_SYNC_KINDS)})",
    )
    _add_column(
        _GRADE_SYNCS,
        sa.Column("last_synced_source", sa.String(length=16), nullable=True),
    )
    _add_column(
        _GRADE_SYNCS,
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Same constraint name, one more column (test_079 pins the name).
    wanted = ["resource_link_id", "user_id", "kind"]
    current = _unique_columns(_GRADE_SYNCS, _GRADE_SYNC_UNIQUE)
    if current == wanted:
        return
    if current is not None:
        op.drop_constraint(_GRADE_SYNC_UNIQUE, _GRADE_SYNCS, type_="unique")
    op.create_unique_constraint(_GRADE_SYNC_UNIQUE, _GRADE_SYNCS, wanted)


def _upgrade_link_users() -> None:
    created = False
    if not _table_exists(_LINK_USERS):
        op.create_table(
            _LINK_USERS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "resource_link_id",
                sa.String(),
                sa.ForeignKey("lti_resource_links.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "is_instructor",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "first_launch_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "last_launch_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "resource_link_id", "user_id", name="uq_lti_resource_link_user"
            ),
        )
        created = True
    if not _index_exists(_LINK_USERS, "ix_lti_resource_link_users_user_id"):
        op.create_index(
            "ix_lti_resource_link_users_user_id", _LINK_USERS, ["user_id"]
        )
    if not created:
        return

    # ``claims`` is a json column holding only the cached name, email and
    # roles of the last launch. Match the role markers against its raw text:
    # any json operator (``->``, a cast to jsonb) fails on a \u0000 escape
    # that json input accepts, and one such row would abort the whole
    # migration. A marker inside the name or email only makes a learner look
    # like an instructor, which grants fewer rows, never more.
    claims_text = "COALESCE(ul.claims::text, '')"
    # The teacher who bound the link (instructor), and learners who launched
    # into the link's project (a grade sync row on the link, an annotation or
    # an entitlement on its exam). Instructors are identified by the cached
    # roles and never get rows from an entitlement or annotation: the old
    # consent step gave every consenting user an entitlement, so that trace
    # does not tell which course a teacher came from.
    op.execute(
        sa.text(
            f"""
            INSERT INTO lti_resource_link_users
                (id, resource_link_id, user_id, is_instructor,
                 first_launch_at, last_launch_at)
            SELECT
                gen_random_uuid()::text,
                l.id,
                ul.user_id,
                (l.linked_by IS NOT DISTINCT FROM ul.user_id),
                GREATEST(ul.created_at, l.created_at),
                GREATEST(ul.created_at, l.created_at, ul.last_launch_at)
            FROM lti_user_links AS ul
            JOIN lti_resource_links AS l
              ON l.registration_id = ul.registration_id
            WHERE ul.consent_at IS NOT NULL
              AND l.project_id IS NOT NULL
              AND (
                l.linked_by = ul.user_id
                OR (
                  NOT ({claims_text} ~ :instructor_re)
                  AND (
                    EXISTS (
                      SELECT 1 FROM lti_grade_syncs AS gs
                      WHERE gs.resource_link_id = l.id
                        AND gs.user_id = ul.user_id
                    )
                    OR EXISTS (
                      SELECT 1 FROM annotations AS a
                      WHERE a.project_id = l.project_id
                        AND a.completed_by = ul.user_id
                    )
                    OR EXISTS (
                      SELECT 1 FROM marketplace_entitlements AS e
                      WHERE e.project_id = l.project_id
                        AND e.user_id = ul.user_id
                    )
                  )
                )
              )
            ON CONFLICT (resource_link_id, user_id) DO NOTHING
            """
        ).bindparams(instructor_re=_INSTRUCTOR_ROLE_REGEX)
    )
    # Fallback for consented learners without any trace: every bound link
    # of their registration.
    op.execute(
        sa.text(
            f"""
            INSERT INTO lti_resource_link_users
                (id, resource_link_id, user_id, is_instructor,
                 first_launch_at, last_launch_at)
            SELECT
                gen_random_uuid()::text,
                l.id,
                ul.user_id,
                false,
                GREATEST(ul.created_at, l.created_at),
                GREATEST(ul.created_at, l.created_at, ul.last_launch_at)
            FROM lti_user_links AS ul
            JOIN lti_resource_links AS l
              ON l.registration_id = ul.registration_id
            WHERE ul.consent_at IS NOT NULL
              AND l.project_id IS NOT NULL
              AND NOT ({claims_text} ~ :instructor_re)
              AND NOT EXISTS (
                SELECT 1
                FROM lti_resource_link_users AS x
                JOIN lti_resource_links AS xl ON xl.id = x.resource_link_id
                WHERE x.user_id = ul.user_id
                  AND xl.registration_id = ul.registration_id
              )
            ON CONFLICT (resource_link_id, user_id) DO NOTHING
            """
        ).bindparams(instructor_re=_INSTRUCTOR_ROLE_REGEX)
    )


def _upgrade_admin_events() -> None:
    if not _table_exists(_EVENTS):
        op.create_table(
            _EVENTS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "registration_id",
                sa.String(),
                sa.ForeignKey("lti_platform_registrations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("registration_name", sa.String(length=200), nullable=True),
            sa.Column(
                "group_id",
                sa.String(),
                sa.ForeignKey("organization_groups.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "actor_user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "actor_kind",
                sa.String(length=32),
                nullable=False,
                server_default="user",
            ),
            sa.Column("action", sa.String(length=48), nullable=False),
            sa.Column("changes", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    if not _column_exists(_EVENTS, "group_id"):
        # A table created by an earlier run of this revision.
        op.add_column(
            _EVENTS,
            sa.Column(
                "group_id",
                sa.String(),
                sa.ForeignKey(
                    "organization_groups.id",
                    ondelete="SET NULL",
                    name="lti_admin_events_group_id_fkey",
                ),
                nullable=True,
            ),
        )
    for column in ("organization_id", "registration_id", "group_id"):
        name = f"ix_lti_admin_events_{column}"
        if not _index_exists(_EVENTS, name):
            op.create_index(name, _EVENTS, [column])


def upgrade() -> None:
    # Fail fast instead of queueing every access check behind a blocked ALTER.
    op.execute("SET LOCAL lock_timeout = '5s'")
    _upgrade_tool_host()
    _upgrade_user_links()
    _upgrade_resource_links()
    _upgrade_grade_syncs()
    _upgrade_link_users()
    _upgrade_admin_events()


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _table_exists(_EVENTS):
        op.drop_table(_EVENTS)
    if _table_exists(_LINK_USERS):
        op.drop_table(_LINK_USERS)

    if _column_exists(_GRADE_SYNCS, "kind"):
        # The two-column constraint cannot hold a second row per student.
        op.execute("DELETE FROM lti_grade_syncs WHERE kind <> 'final'")
    current = _unique_columns(_GRADE_SYNCS, _GRADE_SYNC_UNIQUE)
    if current is not None and "kind" in current:
        op.drop_constraint(_GRADE_SYNC_UNIQUE, _GRADE_SYNCS, type_="unique")
        current = None
    if current is None:
        op.create_unique_constraint(
            _GRADE_SYNC_UNIQUE, _GRADE_SYNCS, ["resource_link_id", "user_id"]
        )
    _drop_check(_GRADE_SYNCS, "ck_lti_grade_syncs_kind")
    for column in ("kind", "last_synced_source", "last_checked_at"):
        _drop_column(_GRADE_SYNCS, column)

    _drop_check(_RESOURCE_LINKS, "ck_lti_resource_links_ai_lineitem_status")
    for column in ("ai_lineitem_url", "ai_lineitem_status", "ai_lineitem_error"):
        _drop_column(_RESOURCE_LINKS, column)

    _drop_check(_USER_LINKS, "ck_lti_user_links_link_method")
    for column in ("research_consent_at", "link_method", "unlinked_at"):
        _drop_column(_USER_LINKS, column)

    for table in (_INVITES, _REGISTRATIONS):
        _drop_check(table, f"ck_{table}_tool_host")
        _drop_column(table, "tool_host")

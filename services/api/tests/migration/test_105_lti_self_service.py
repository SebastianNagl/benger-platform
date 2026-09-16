"""Shape and backfill tests for migration 105 (LMS self-service schema).

The shared test DB already carries the new columns and tables (models plus
the fixture backstops), so ``upgrade()`` must be a no-op through its guards,
twice. ``downgrade()`` must remove everything; a re-run ``upgrade()`` must
rebuild the shape and run the data backfills. Rows are seeded through the
ORM before the downgrade, so the backfills see exactly the old schema's data.
Everything runs on the fixture's outer transaction and is rolled back.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "105_lti_self_service.py",
    )
)

NEW_COLUMNS = {
    "lti_platform_registrations": {"tool_host"},
    "lti_registration_invites": {"tool_host"},
    "lti_user_links": {"research_consent_at", "link_method", "unlinked_at"},
    "lti_resource_links": {"ai_lineitem_url", "ai_lineitem_status", "ai_lineitem_error"},
    "lti_grade_syncs": {"kind", "last_synced_source", "last_checked_at"},
}
NEW_CHECKS = {
    "lti_platform_registrations": "ck_lti_platform_registrations_tool_host",
    "lti_registration_invites": "ck_lti_registration_invites_tool_host",
    "lti_user_links": "ck_lti_user_links_link_method",
    "lti_resource_links": "ck_lti_resource_links_ai_lineitem_status",
    "lti_grade_syncs": "ck_lti_grade_syncs_kind",
}
NEW_TABLES = {"lti_resource_link_users", "lti_admin_events"}

INSTRUCTOR_ROLE = "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
LEARNER_ROLE = "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_105", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    """Install the alembic ``op`` proxy bound to the test connection."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


def _uid(prefix="x") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _columns(conn, table) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns(table)}


def _checks(conn, table) -> set:
    return {c["name"] for c in inspect(conn).get_check_constraints(table)}


def _grade_sync_unique(conn):
    for uq in inspect(conn).get_unique_constraints("lti_grade_syncs"):
        if uq["name"] == "uq_lti_grade_sync":
            return list(uq["column_names"])
    return None


def _synthetic_username(issuer: str, sub: str) -> str:
    """The launch's synthetic identity (benger_extended provisioning)."""
    return "lti-" + hashlib.sha256(f"{issuer}|{sub}".encode()).hexdigest()[:16]


def _assert_full_shape(conn):
    tables = set(inspect(conn).get_table_names())
    assert NEW_TABLES <= tables
    for table, columns in NEW_COLUMNS.items():
        assert columns <= set(_columns(conn, table)), table
        assert NEW_CHECKS[table] in _checks(conn, table), table
    assert _grade_sync_unique(conn) == ["resource_link_id", "user_id", "kind"]

    link_users = inspect(conn)
    fks = {
        fk["constrained_columns"][0]: fk
        for fk in link_users.get_foreign_keys("lti_resource_link_users")
    }
    assert fks["resource_link_id"]["referred_table"] == "lti_resource_links"
    assert fks["resource_link_id"]["options"].get("ondelete") == "CASCADE"
    assert fks["user_id"]["referred_table"] == "users"
    assert fks["user_id"]["options"].get("ondelete") == "CASCADE"
    uqs = {
        uq["name"]: uq["column_names"]
        for uq in link_users.get_unique_constraints("lti_resource_link_users")
    }
    assert uqs["uq_lti_resource_link_user"] == ["resource_link_id", "user_id"]
    assert "ix_lti_resource_link_users_user_id" in {
        ix["name"] for ix in link_users.get_indexes("lti_resource_link_users")
    }

    event_fks = {
        fk["constrained_columns"][0]: fk
        for fk in link_users.get_foreign_keys("lti_admin_events")
    }
    assert event_fks["organization_id"]["options"].get("ondelete") == "CASCADE"
    assert event_fks["registration_id"]["options"].get("ondelete") == "SET NULL"
    assert event_fks["actor_user_id"]["options"].get("ondelete") == "SET NULL"
    assert {
        "ix_lti_admin_events_organization_id",
        "ix_lti_admin_events_registration_id",
    } <= {ix["name"] for ix in link_users.get_indexes("lti_admin_events")}

    defaults = {
        ("lti_platform_registrations", "tool_host"): "student_locked",
        ("lti_registration_invites", "tool_host"): "student_locked",
        ("lti_grade_syncs", "kind"): "final",
    }
    for (table, column), value in defaults.items():
        col = _columns(conn, table)[column]
        assert col["nullable"] is False, (table, column)
        assert value in str(col["default"]), (table, column)


# --------------------------------------------------------------------------- #
# Seed helpers (ORM, before the downgrade).
# --------------------------------------------------------------------------- #
class _Seed:
    def __init__(self, db: Session):
        from models import Organization

        self.db = db
        self.org = Organization(
            id=_uid("org"), name="Uni", display_name="Uni", slug=_uid("uni")
        )
        self.other_org = Organization(
            id=_uid("org"), name="Other", display_name="Other", slug=_uid("oth")
        )
        db.add_all([self.org, self.other_org])
        db.flush()
        self.owner = self.user("owner")

    def user(
        self, key, *, username=None, password=None, method="self", created_at=None
    ):
        from models import User

        uid = _uid(key)
        row = User(
            id=uid,
            username=username or uid,
            email=f"{uid}@example.com",
            name=key,
            hashed_password=password,
            email_verified=True,
            email_verification_method=method,
            email_verified_at=datetime.now(timezone.utc),
        )
        if created_at is not None:
            row.created_at = created_at
        self.db.add(row)
        self.db.flush()
        return row

    def registration(self, issuer=None, org=None):
        from models import LtiPlatformRegistration

        reg = LtiPlatformRegistration(
            id=_uid("reg"),
            organization_id=(org or self.org).id,
            name="Moodle",
            issuer=issuer or f"https://{_uid('lms')}.example.com",
            client_id=_uid("client"),
            auth_login_url="https://lms.example.com/auth",
            auth_token_url="https://lms.example.com/token",
            jwks_uri="https://lms.example.com/jwks",
        )
        self.db.add(reg)
        self.db.flush()
        return reg

    def project(self, *, private, kind="exam", created_at=None):
        from project_models import Project, Task

        project = Project(
            id=_uid("proj"),
            title="Exam",
            created_by=self.owner.id,
            is_private=private,
            kind=kind,
        )
        if created_at is not None:
            project.created_at = created_at
        self.db.add(project)
        self.db.flush()
        task = Task(id=_uid("task"), project_id=project.id, inner_id=1, data={"q": 1})
        self.db.add(task)
        self.db.flush()
        project.task = task
        return project

    def link(self, reg, project=None, linked_by=None, created_at=None):
        from models import LtiResourceLink

        row = LtiResourceLink(
            id=_uid("rl"),
            registration_id=reg.id,
            deployment_id="1",
            resource_link_id=_uid("activity"),
            project_id=project.id if project is not None else None,
            linked_by=linked_by.id if linked_by is not None else None,
        )
        if created_at is not None:
            row.created_at = created_at
        self.db.add(row)
        self.db.flush()
        return row

    def user_link(self, reg, user, *, sub=None, consented=True, roles=(LEARNER_ROLE,)):
        from models import LtiUserLink

        row = LtiUserLink(
            id=_uid("ul"),
            registration_id=reg.id,
            sub=sub or _uid("sub"),
            user_id=user.id,
            claims={"name": user.name, "email": user.email, "roles": list(roles)},
            consent_at=datetime.now(timezone.utc) if consented else None,
            consent_version="lti-1" if consented else None,
            last_launch_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def annotation(self, project, user):
        from project_models import Annotation

        self.db.add(
            Annotation(
                id=_uid("ann"),
                task_id=project.task.id,
                project_id=project.id,
                completed_by=user.id,
                result=[{"from_name": "a", "value": {"text": ["x"]}}],
            )
        )
        self.db.flush()

    def entitlement(self, project, user, source="lti"):
        from project_models import MarketplaceEntitlement

        self.db.add(
            MarketplaceEntitlement(
                id=_uid("ent"), user_id=user.id, project_id=project.id, source=source
            )
        )
        self.db.flush()

    def grade_sync(self, link, user, kind="final"):
        from models import LtiGradeSync

        row = LtiGradeSync(
            id=_uid("gs"), resource_link_id=link.id, user_id=user.id, kind=kind
        )
        self.db.add(row)
        self.db.flush()
        return row


def _scalar(conn, sql, **params):
    return conn.execute(text(sql), params).scalar()


def _link_users(conn, user_id):
    rows = conn.execute(
        text(
            "SELECT resource_link_id, is_instructor FROM lti_resource_link_users "
            "WHERE user_id = :u"
        ),
        {"u": user_id},
    ).all()
    return {r[0]: r[1] for r in rows}


class TestMigration105Shape:
    def test_revision_chains_after_104(self):
        mig = _load_migration()
        assert mig.revision == "105_lti_self_service"
        assert mig.down_revision == "104_add_evaluation_received_notification_types"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        _assert_full_shape(conn)

    def test_downgrade_then_upgrade_rebuilds_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
        assert not NEW_TABLES & set(inspect(conn).get_table_names())
        for table, columns in NEW_COLUMNS.items():
            assert not columns & set(_columns(conn, table)), table
            assert NEW_CHECKS[table] not in _checks(conn, table), table
        assert _grade_sync_unique(conn) == ["resource_link_id", "user_id"]

        # A second downgrade finds nothing left to remove.
        with _op_context(conn):
            mig.downgrade()

        with _op_context(conn):
            mig.upgrade()
        _assert_full_shape(conn)


class TestMigration105Constraints:
    @pytest.mark.parametrize(
        "table,column",
        [
            ("lti_platform_registrations", "tool_host"),
            ("lti_registration_invites", "tool_host"),
            ("lti_user_links", "link_method"),
            ("lti_resource_links", "ai_lineitem_status"),
            ("lti_grade_syncs", "kind"),
        ],
    )
    def test_checks_reject_unknown_values(self, test_db: Session, table, column):
        seed = _Seed(test_db)
        reg = seed.registration()
        project = seed.project(private=True)
        link = seed.link(reg, project)
        student = seed.user("student")
        user_link = seed.user_link(reg, student)
        sync = seed.grade_sync(link, student)

        from models import LtiRegistrationInvite

        invite = LtiRegistrationInvite(
            id=_uid("inv"),
            organization_id=seed.org.id,
            token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        test_db.add(invite)
        test_db.flush()
        row_ids = {
            "lti_platform_registrations": reg.id,
            "lti_registration_invites": invite.id,
            "lti_user_links": user_link.id,
            "lti_resource_links": link.id,
            "lti_grade_syncs": sync.id,
        }
        conn = test_db.get_bind()
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    text(f"UPDATE {table} SET {column} = 'bogus' WHERE id = :id"),
                    {"id": row_ids[table]},
                )

    def test_valid_values_and_defaults(self, test_db: Session):
        seed = _Seed(test_db)
        reg = seed.registration()
        project = seed.project(private=True)
        link = seed.link(reg, project)
        student = seed.user("student")
        user_link = seed.user_link(reg, student)
        conn = test_db.get_bind()

        assert _scalar(
            conn, "SELECT tool_host FROM lti_platform_registrations WHERE id = :i", i=reg.id
        ) == "student_locked"
        assert _scalar(
            conn, "SELECT link_method FROM lti_user_links WHERE id = :i", i=user_link.id
        ) is None
        for status in ("ready", "unavailable", "error", "deleted", None):
            conn.execute(
                text("UPDATE lti_resource_links SET ai_lineitem_status = :s WHERE id = :i"),
                {"s": status, "i": link.id},
            )
        for method in ("provisioned", "login_proof", "email_proof", "legacy_email"):
            conn.execute(
                text("UPDATE lti_user_links SET link_method = :m WHERE id = :i"),
                {"m": method, "i": user_link.id},
            )
        conn.execute(
            text("UPDATE lti_platform_registrations SET tool_host = 'main' WHERE id = :i"),
            {"i": reg.id},
        )

    def test_one_sync_row_per_column(self, test_db: Session):
        seed = _Seed(test_db)
        reg = seed.registration()
        link = seed.link(reg, seed.project(private=True))
        student = seed.user("student")
        final = seed.grade_sync(link, student, "final")
        ai = seed.grade_sync(link, student, "ai")
        assert final.kind == "final" and ai.kind == "ai"

        conn = test_db.get_bind()
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    text(
                        "INSERT INTO lti_grade_syncs (id, resource_link_id, user_id, kind) "
                        "VALUES (:i, :l, :u, 'ai')"
                    ),
                    {"i": _uid("gs"), "l": link.id, "u": student.id},
                )
        # The column default is 'final', so a kind-less insert collides too.
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    text(
                        "INSERT INTO lti_grade_syncs (id, resource_link_id, user_id) "
                        "VALUES (:i, :l, :u)"
                    ),
                    {"i": _uid("gs"), "l": link.id, "u": student.id},
                )

    def test_downgrade_drops_ai_rows_and_keeps_final_rows(self, test_db: Session):
        seed = _Seed(test_db)
        reg = seed.registration()
        link = seed.link(reg, seed.project(private=True))
        student = seed.user("student")
        final = seed.grade_sync(link, student, "final")
        ai = seed.grade_sync(link, student, "ai")
        conn = test_db.get_bind()

        with _op_context(conn):
            _load_migration().downgrade()

        ids = set(
            conn.execute(
                text("SELECT id FROM lti_grade_syncs WHERE resource_link_id = :l"),
                {"l": link.id},
            ).scalars()
        )
        assert ids == {final.id}
        assert ai.id not in ids


class TestMigration105Backfills:
    def _upgrade_after_downgrade(self, conn):
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
            mig.upgrade()

    def test_link_method_uses_the_exact_synthetic_identity(self, test_db: Session):
        seed = _Seed(test_db)
        issuer = f"https://{_uid('moodle')}.example.com"
        reg = seed.registration(issuer=issuer)
        sub = "7"
        # Everything seeded here shares the test transaction's now(), so the
        # accounts that must not count as created with their link get an
        # earlier created_at.
        earlier = datetime.now(timezone.utc) - timedelta(days=30)
        provisioned = seed.user(
            "prov", username=_synthetic_username(issuer, sub), created_at=earlier
        )
        prov_link = seed.user_link(reg, provisioned, sub=sub)
        # Looks synthetic, but for another identity: not provisioned here.
        lookalike = seed.user(
            "look", username=_synthetic_username(issuer, "8"), created_at=earlier
        )
        look_link = seed.user_link(reg, lookalike, sub="9")
        # A regular account the old automatic email match linked.
        regular = seed.user("regular", created_at=earlier)
        email_link = seed.user_link(reg, regular)
        # Same sub on another registration with another issuer.
        other_reg = seed.registration()
        other_link = seed.user_link(other_reg, provisioned, sub=sub)
        # Provisioned under the connection's old issuer (edited since): the
        # hash no longer matches, but account and link were created together.
        drifted = seed.user(
            "drift", username=_synthetic_username("https://old.example.com", "5")
        )
        drift_link = seed.user_link(reg, drifted, sub="5")
        # Created in the same transaction as its link, but not synthetic.
        same_tx = seed.user("same_tx")
        same_tx_link = seed.user_link(reg, same_tx)
        conn = test_db.get_bind()
        link_created = _scalar(
            conn, "SELECT created_at FROM lti_user_links WHERE id = :i", i=drift_link.id
        )
        assert _scalar(
            conn, "SELECT created_at FROM users WHERE id = :i", i=drifted.id
        ) == link_created

        self._upgrade_after_downgrade(conn)

        link_ids = [
            prov_link.id,
            look_link.id,
            email_link.id,
            other_link.id,
            drift_link.id,
            same_tx_link.id,
        ]
        methods = dict(
            conn.execute(
                text("SELECT id, link_method FROM lti_user_links WHERE id = ANY(:ids)"),
                {"ids": link_ids},
            ).all()
        )
        assert methods == {
            prov_link.id: "provisioned",
            look_link.id: "legacy_email",
            email_link.id: "legacy_email",
            other_link.id: "legacy_email",
            drift_link.id: "provisioned",
            same_tx_link.id: "legacy_email",
        }

    def test_participation_rows_come_from_launch_traces(self, test_db: Session):
        seed = _Seed(test_db)
        reg = seed.registration()
        exam_a = seed.project(private=True)
        exam_b = seed.project(private=True)
        teacher = seed.user("teacher")
        link_a = seed.link(reg, exam_a, linked_by=teacher)
        link_a2 = seed.link(reg, exam_a)  # same exam in a second course
        link_b = seed.link(reg, exam_b)
        unbound = seed.link(reg, None)

        seed.user_link(reg, teacher, roles=(INSTRUCTOR_ROLE,))
        # The old consent step gave the teacher an entitlement on the exam,
        # which must not pull in the other course's link to it.
        seed.entitlement(exam_a, teacher)

        annotating = seed.user("annotating")
        seed.user_link(reg, annotating)
        seed.annotation(exam_a, annotating)

        entitled = seed.user("entitled")
        seed.user_link(reg, entitled)
        seed.entitlement(exam_b, entitled)

        synced = seed.user("synced")
        seed.user_link(reg, synced)
        seed.grade_sync(link_b, synced)

        no_trace = seed.user("no_trace")
        seed.user_link(reg, no_trace)

        co_teacher = seed.user("co_teacher")
        seed.user_link(reg, co_teacher, roles=(INSTRUCTOR_ROLE,))
        # A teacher of the second course with an entitlement and an
        # annotation on the exam (e.g. a test submission) but no binding.
        seed.entitlement(exam_a, co_teacher)
        seed.annotation(exam_a, co_teacher)

        # Learner roles, but the claims hold a NUL escape (valid json, not
        # valid jsonb); the role read must not abort the migration.
        odd_claims = seed.user("odd_claims")
        odd_link = seed.user_link(reg, odd_claims)
        test_db.execute(
            text(
                "UPDATE lti_user_links SET claims = CAST(:c AS json) WHERE id = :i"
            ),
            {
                "c": '{"name": "a\\u0000b", "roles": ["%s"]}' % LEARNER_ROLE,
                "i": odd_link.id,
            },
        )
        seed.grade_sync(link_b, odd_claims)

        unconsented = seed.user("unconsented")
        seed.user_link(reg, unconsented, consented=False)
        seed.annotation(exam_a, unconsented)

        # A consented user of another registration never lands on these links.
        other_reg = seed.registration()
        stranger = seed.user("stranger")
        seed.user_link(other_reg, stranger)
        seed.annotation(exam_a, stranger)
        conn = test_db.get_bind()

        self._upgrade_after_downgrade(conn)

        # Only the link the teacher bound, although the entitlement matches
        # the second course's link to the same exam too.
        assert _link_users(conn, teacher.id) == {link_a.id: True}
        # One exam in two courses: both activities count.
        assert _link_users(conn, annotating.id) == {link_a.id: False, link_a2.id: False}
        assert _link_users(conn, entitled.id) == {link_b.id: False}
        assert _link_users(conn, synced.id) == {link_b.id: False}
        # No trace: every bound link of the registration, never the unbound one.
        assert _link_users(conn, no_trace.id) == {
            link_a.id: False,
            link_a2.id: False,
            link_b.id: False,
        }
        assert unbound.id not in _link_users(conn, no_trace.id)
        # Instructors get no rows from entitlements, annotations or the
        # fallback (the course role would leak into other courses).
        assert _link_users(conn, co_teacher.id) == {}
        assert _link_users(conn, odd_claims.id) == {link_b.id: False}
        assert _link_users(conn, unconsented.id) == {}
        assert _link_users(conn, stranger.id) == {}

        first, last = conn.execute(
            text(
                "SELECT first_launch_at, last_launch_at FROM lti_resource_link_users "
                "WHERE user_id = :u"
            ),
            {"u": teacher.id},
        ).one()
        assert first is not None and last is not None and last >= first

    def test_backfills_do_not_rerun_on_an_upgraded_schema(self, test_db: Session):
        seed = _Seed(test_db)
        reg = seed.registration()
        project = seed.project(private=True)
        seed.link(reg, project)  # a bound link the fallback would pick
        learner = seed.user("learner")
        user_link = seed.user_link(reg, learner)
        conn = test_db.get_bind()
        # Values the application wrote after the migration ran.
        conn.execute(
            text("UPDATE lti_user_links SET link_method = 'email_proof' WHERE id = :i"),
            {"i": user_link.id},
        )

        with _op_context(conn):
            _load_migration().upgrade()

        assert _scalar(
            conn, "SELECT link_method FROM lti_user_links WHERE id = :i", i=user_link.id
        ) == "email_proof"
        assert _link_users(conn, learner.id) == {}

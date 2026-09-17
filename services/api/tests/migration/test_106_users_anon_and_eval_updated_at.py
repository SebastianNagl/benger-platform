"""Shape and backfill tests for migration 106.

``task_evaluations.updated_at``, ``users.anonymized_at``,
``ix_users_email_lower``, the email state of LMS-provisioned accounts and
``project_organizations.attached_via``. The shared test DB already carries the
columns and the index, so ``upgrade()`` must be a no-op, twice;
``downgrade()`` removes them and a re-run ``upgrade()`` rebuilds them and runs
the attachment backfill. Everything runs on the fixture's outer transaction.
"""

from __future__ import annotations

import importlib.util
import os
import re
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
        "106_users_anon_and_eval_updated_at.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_106", MIGRATION_PATH)
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


NO_LINK = object()


def _uid(prefix="x") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _columns(conn, table) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns(table)}


def _email_index(conn):
    for ix in inspect(conn).get_indexes("users"):
        if ix["name"] == "ix_users_email_lower":
            return ix
    return None


def _checks(conn, table) -> set:
    return {c["name"] for c in inspect(conn).get_check_constraints(table)}


def _assert_full_shape(conn):
    attached_via = _columns(conn, "project_organizations")["attached_via"]
    assert attached_via["nullable"] is False
    assert "manual" in str(attached_via["default"])
    assert "ck_project_organizations_attached_via" in _checks(
        conn, "project_organizations"
    )
    anonymized = _columns(conn, "users")["anonymized_at"]
    assert anonymized["nullable"] is True
    users = _columns(conn, "users")
    assert users["lms_provisioned_at"]["nullable"] is True
    assert users["lms_origin_org_id"]["nullable"] is True
    (origin_fk,) = [
        fk
        for fk in inspect(conn).get_foreign_keys("users")
        if fk["constrained_columns"] == ["lms_origin_org_id"]
    ]
    assert origin_fk["referred_table"] == "organizations"
    assert origin_fk["options"].get("ondelete") == "SET NULL"
    assert "ix_users_lms_origin_org_id" in {
        ix["name"] for ix in inspect(conn).get_indexes("users")
    }
    updated = _columns(conn, "task_evaluations")["updated_at"]
    assert updated["nullable"] is True
    assert updated["default"] is None
    index = _email_index(conn)
    assert index is not None
    assert not index["unique"]
    # PG renders it as lower(email::text) or lower((email)::text).
    (expression,) = index["expressions"]
    assert re.fullmatch(r"lower\(\(?email\)?(::text)?\)", expression), expression


class _Accounts:
    """Users with and without LMS links, seeded through the ORM."""

    def __init__(self, db: Session):
        from models import LtiPlatformRegistration, Organization

        self.db = db
        org = Organization(id=_uid("org"), name="Uni", display_name="Uni", slug=_uid("u"))
        db.add(org)
        db.flush()
        self.reg = LtiPlatformRegistration(
            id=_uid("reg"),
            organization_id=org.id,
            name="Moodle",
            issuer=f"https://{_uid('lms')}.example.com",
            client_id=_uid("client"),
            auth_login_url="https://lms.example.com/auth",
            auth_token_url="https://lms.example.com/token",
            jwks_uri="https://lms.example.com/jwks",
        )
        db.add(self.reg)
        db.flush()
        self.verified_at = datetime(2026, 7, 1, tzinfo=timezone.utc)

    def add(
        self, key, *, method="system", password=None, link_method=NO_LINK, verified=True
    ):
        from models import LtiUserLink, User

        uid = _uid(key)
        self.db.add(
            User(
                id=uid,
                username=uid,
                email=f"{uid}@example.com",
                name=key,
                hashed_password=password,
                email_verified=verified,
                email_verification_method=method,
                email_verified_at=self.verified_at if verified else None,
            )
        )
        self.db.flush()
        if link_method is not NO_LINK:
            self.db.add(
                LtiUserLink(
                    id=_uid("ul"),
                    registration_id=self.reg.id,
                    sub=_uid("sub"),
                    user_id=uid,
                    link_method=link_method,
                )
            )
            self.db.flush()
        return uid


def _email_state(conn, user_id):
    return tuple(
        conn.execute(
            text(
                "SELECT email_verified, email_verification_method, email_verified_at "
                "FROM users WHERE id = :u"
            ),
            {"u": user_id},
        ).one()
    )


class TestMigration106Shape:
    def test_revision_chains_after_105(self):
        mig = _load_migration()
        assert mig.revision == "106_users_anon_and_eval_updated_at"
        assert mig.down_revision == "105_lti_self_service"

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
        assert "anonymized_at" not in _columns(conn, "users")
        assert "lms_provisioned_at" not in _columns(conn, "users")
        assert "lms_origin_org_id" not in _columns(conn, "users")
        assert "updated_at" not in _columns(conn, "task_evaluations")
        assert _email_index(conn) is None
        assert "attached_via" not in _columns(conn, "project_organizations")
        assert "ck_project_organizations_attached_via" not in _checks(
            conn, "project_organizations"
        )

        with _op_context(conn):
            mig.downgrade()
            mig.upgrade()
        _assert_full_shape(conn)

    def test_hot_tables_are_locked_in_order(self, monkeypatch):
        """task_evaluations (long worker transactions) first, then the
        tables nearly every request reads, right before the commit."""
        mig = _load_migration()
        calls = []
        monkeypatch.setattr(mig.op, "execute", lambda *a, **k: calls.append("timeout"))
        for step in ("task_evaluations", "users", "attachments"):
            monkeypatch.setattr(
                mig, f"_upgrade_{step}", lambda step=step: calls.append(step)
            )

        mig.upgrade()

        assert calls == ["timeout", "task_evaluations", "users", "attachments"]


class TestMigration106EmailBackfill:
    def test_only_provisioned_system_accounts_change(self, test_db: Session):
        accounts = _Accounts(test_db)
        passwordless = accounts.add("passwordless", link_method="provisioned")
        activated = accounts.add("activated", password="hash", link_method="provisioned")
        proof_linked = accounts.add("proof", link_method="login_proof")
        legacy = accounts.add("legacy", link_method="legacy_email")
        # A link written by an old pod during the rollout (method unknown).
        unknown = accounts.add("unknown", link_method=None)
        admin_verified = accounts.add(
            "admin_verified", method="admin", link_method="provisioned"
        )
        # No LMS link at all (e.g. a seeded account).
        seed_user = accounts.add("seeded", method="system")
        conn = test_db.get_bind()

        with _op_context(conn):
            _load_migration().upgrade()

        verified = (True, "system", accounts.verified_at)
        # The LMS address was never proven: the method says so. The verified
        # flag stays, so an old pod that activates the account during the
        # rollout (or after a rollback) still lets it log in.
        assert _email_state(conn, passwordless) == (
            True,
            "lti_claim",
            accounts.verified_at,
        )
        # The account holder set a password through the activation mail.
        assert _email_state(conn, activated) == (True, "activation", accounts.verified_at)
        for untouched in (proof_linked, legacy, unknown, seed_user):
            assert _email_state(conn, untouched) == verified
        assert _email_state(conn, admin_verified) == (
            True,
            "admin",
            accounts.verified_at,
        )

        # Running it again changes nothing.
        with _op_context(conn):
            _load_migration().upgrade()
        assert _email_state(conn, passwordless) == (
            True,
            "lti_claim",
            accounts.verified_at,
        )
        assert _email_state(conn, activated) == (True, "activation", accounts.verified_at)

    def test_downgrade_makes_lms_claims_verified_again(self, test_db: Session):
        accounts = _Accounts(test_db)
        passwordless = accounts.add("passwordless", link_method="provisioned")
        activated = accounts.add("activated", password="hash", link_method="provisioned")
        # An account the new code created: unverified LMS claim.
        fresh = accounts.add(
            "fresh", method="lti_claim", link_method="provisioned", verified=False
        )
        conn = test_db.get_bind()
        with _op_context(conn):
            _load_migration().upgrade()

        with _op_context(conn):
            _load_migration().downgrade()

        assert _email_state(conn, passwordless) == (True, "system", accounts.verified_at)
        assert _email_state(conn, activated) == (True, "activation", accounts.verified_at)
        verified, method, verified_at = _email_state(conn, fresh)
        assert (verified, method) == (True, "system")
        assert verified_at is not None


def _origin(conn, user_id):
    return tuple(
        conn.execute(
            text(
                "SELECT lms_provisioned_at, lms_origin_org_id FROM users WHERE id = :u"
            ),
            {"u": user_id},
        ).one()
    )


class TestMigration106LmsOriginBackfill:
    def test_provisioned_accounts_get_the_earliest_link(self, test_db: Session):
        from models import LtiPlatformRegistration, LtiUserLink, Organization

        accounts = _Accounts(test_db)
        later_org = Organization(
            id=_uid("org"), name="Later", display_name="Later", slug=_uid("l")
        )
        test_db.add(later_org)
        test_db.flush()
        later_reg = LtiPlatformRegistration(
            id=_uid("reg"),
            organization_id=later_org.id,
            name="ILIAS",
            issuer=f"https://{_uid('lms')}.example.com",
            client_id=_uid("client"),
            auth_login_url="https://lms.example.com/auth",
            auth_token_url="https://lms.example.com/token",
            jwks_uri="https://lms.example.com/jwks",
        )
        test_db.add(later_reg)
        test_db.flush()
        provisioned = accounts.add("provisioned", link_method="provisioned")
        first_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        test_db.query(LtiUserLink).filter(LtiUserLink.user_id == provisioned).update(
            {"created_at": first_at}
        )
        test_db.add(
            LtiUserLink(
                id=_uid("ul"),
                registration_id=later_reg.id,
                sub=_uid("sub"),
                user_id=provisioned,
                link_method="provisioned",
                created_at=first_at + timedelta(days=30),
            )
        )
        proof_linked = accounts.add("proof", link_method="login_proof")
        unknown = accounts.add("unknown", link_method=None)
        already = accounts.add("already", link_method="provisioned")
        kept_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        test_db.execute(
            text(
                "UPDATE users SET lms_provisioned_at = :at, lms_origin_org_id = NULL "
                "WHERE id = :u"
            ),
            {"at": kept_at, "u": already},
        )
        test_db.flush()
        conn = test_db.get_bind()

        with _op_context(conn):
            _load_migration().upgrade()
            _load_migration().upgrade()

        assert _origin(conn, provisioned) == (first_at, accounts.reg.organization_id)
        assert _origin(conn, proof_linked) == (None, None)
        assert _origin(conn, unknown) == (None, None)
        # Marked rows are left alone.
        assert _origin(conn, already) == (kept_at, None)

    def test_origin_org_is_cleared_with_its_org(self, test_db: Session):
        from models import Organization

        accounts = _Accounts(test_db)
        doomed = Organization(
            id=_uid("org"), name="Gone", display_name="Gone", slug=_uid("g")
        )
        test_db.add(doomed)
        test_db.flush()
        uid = accounts.add("kept")
        conn = test_db.get_bind()
        conn.execute(
            text(
                "UPDATE users SET lms_provisioned_at = now(), "
                "lms_origin_org_id = :o WHERE id = :u"
            ),
            {"o": doomed.id, "u": uid},
        )
        conn.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": doomed.id})

        provisioned_at, origin = _origin(conn, uid)
        assert provisioned_at is not None
        assert origin is None


class TestTaskEvaluationUpdatedAt:
    def test_orm_updates_stamp_updated_at(self, test_db: Session):
        """The column is NULL on insert and set by every ORM update."""
        from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation, User
        from project_models import Project, Task

        owner = User(
            id=_uid("u"), username=_uid("u"), email=f"{_uid('u')}@example.com", name="o"
        )
        test_db.add(owner)
        test_db.flush()
        project = Project(id=_uid("p"), title="Exam", created_by=owner.id)
        test_db.add(project)
        test_db.flush()
        task = Task(id=_uid("t"), project_id=project.id, inner_id=1, data={"q": 1})
        run = EvaluationRun(
            id=_uid("run"),
            project_id=project.id,
            model_id="human",
            evaluation_type_ids=["korrektur_custom"],
            metrics={},
            status="completed",
            created_by=owner.id,
        )
        test_db.add_all([task, run])
        test_db.flush()
        judge_run = EvaluationJudgeRun(
            id=_uid("jr"), evaluation_id=run.id, run_index=0, status="completed"
        )
        test_db.add(judge_run)
        test_db.flush()
        row = TaskEvaluation(
            id=_uid("te"),
            evaluation_id=run.id,
            judge_run_id=judge_run.id,
            task_id=task.id,
            field_name="loesung",
            answer_type="text",
            ground_truth={},
            prediction={},
            metrics={"score": {"value": 10}},
            passed=True,
        )
        test_db.add(row)
        test_db.flush()
        test_db.refresh(row)
        assert row.updated_at is None

        row.metrics = {"score": {"value": 12}}
        test_db.flush()
        test_db.refresh(row)
        assert row.updated_at is not None


# --------------------------------------------------------------------------- #
# project_organizations.attached_via
# --------------------------------------------------------------------------- #
class _Attachments:
    """Exams, attachments and resource links, seeded through the ORM."""

    def __init__(self, db: Session):
        from models import LtiPlatformRegistration, Organization, User

        self.db = db
        self.org = Organization(
            id=_uid("org"), name="Uni", display_name="Uni", slug=_uid("u")
        )
        self.other_org = Organization(
            id=_uid("org"), name="Other", display_name="Other", slug=_uid("o")
        )
        db.add_all([self.org, self.other_org])
        db.flush()
        self.owner, self.colleague = (
            User(
                id=uid,
                username=uid,
                email=f"{uid}@example.com",
                name=key,
            )
            for key, uid in (("owner", _uid("owner")), ("colleague", _uid("col")))
        )
        db.add_all([self.owner, self.colleague])
        db.flush()
        self.reg = LtiPlatformRegistration(
            id=_uid("reg"),
            organization_id=self.org.id,
            name="Moodle",
            issuer=f"https://{_uid('lms')}.example.com",
            client_id=_uid("client"),
            auth_login_url="https://lms.example.com/auth",
            auth_token_url="https://lms.example.com/token",
            jwks_uri="https://lms.example.com/jwks",
        )
        db.add(self.reg)
        db.flush()

    def exam(self, *, private, kind="exam"):
        from project_models import Project

        project = Project(
            id=_uid("proj"),
            title="Exam",
            created_by=self.owner.id,
            is_private=private,
            kind=kind,
        )
        self.db.add(project)
        self.db.flush()
        return project

    def attach(self, project, *, created_at, org=None, by=None):
        from project_models import ProjectOrganization

        row = ProjectOrganization(
            id=_uid("po"),
            project_id=project.id,
            organization_id=(org or self.org).id,
            assigned_by=(by or self.owner).id,
            created_at=created_at,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def link(self, project, *, created_at, linked_at=None, by=None):
        from models import LtiResourceLink

        row = LtiResourceLink(
            id=_uid("rl"),
            registration_id=self.reg.id,
            deployment_id="1",
            resource_link_id=_uid("activity"),
            project_id=project.id,
            linked_by=(by or self.owner).id if linked_at is not None else None,
            linked_at=linked_at,
            created_at=created_at,
        )
        self.db.add(row)
        self.db.flush()
        return row


def _origins(conn, rows) -> dict:
    return dict(
        conn.execute(
            text(
                "SELECT id, attached_via FROM project_organizations "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": [row.id for row in rows]},
        ).all()
    )


class TestMigration106AttachedVia:
    def _upgrade_after_downgrade(self, conn):
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
            mig.upgrade()

    def test_backfill_marks_only_attachments_made_by_linking(
        self, test_db: Session
    ):
        seed = _Attachments(test_db)
        now = datetime.now(timezone.utc)
        first_launch = now - timedelta(days=3)
        conn = test_db.get_bind()

        # Private exam, currently linked.
        linked_private = seed.exam(private=True)
        seed.link(linked_private, created_at=first_launch, linked_at=now)
        a_linked_private = seed.attach(linked_private, created_at=now)
        # Private exam a relink left behind (no link points at it any more).
        orphan_private = seed.exam(private=True)
        a_orphan = seed.attach(orphan_private, created_at=now)
        # Org-visible exam the binding attached (same user, same moment; the
        # attachment's timestamp is the transaction start, a bit earlier).
        linked_visible = seed.exam(private=False)
        seed.link(linked_visible, created_at=first_launch, linked_at=now)
        a_linked_visible = seed.attach(
            linked_visible, created_at=now - timedelta(seconds=2)
        )
        # Shared org-wide by hand after the first launch, bound an hour later:
        # the binding found and kept this row.
        shared_first = seed.exam(private=False)
        seed.link(shared_first, created_at=first_launch, linked_at=now)
        a_shared_first = seed.attach(
            shared_first, created_at=now - timedelta(hours=1)
        )
        # Detached and shared again by hand a day after the binding.
        reshared = seed.exam(private=False)
        seed.link(reshared, created_at=first_launch, linked_at=first_launch)
        a_reshared = seed.attach(reshared, created_at=now - timedelta(days=2))
        # Attached by a colleague at binding time, bound by the owner.
        colleague_share = seed.exam(private=False)
        seed.link(colleague_share, created_at=first_launch, linked_at=now)
        a_colleague = seed.attach(colleague_share, created_at=now, by=seed.colleague)
        # Attached long before the activity existed.
        preexisting = seed.exam(private=False)
        a_preexisting = seed.attach(preexisting, created_at=first_launch)
        seed.link(preexisting, created_at=now, linked_at=now)
        # A link that points at the exam but was never bound by a teacher.
        unbound = seed.exam(private=False)
        seed.link(unbound, created_at=first_launch)
        a_unbound = seed.attach(unbound, created_at=now)
        # Attachment to an org without a connection pointing at the exam.
        a_other_org = seed.attach(linked_visible, org=seed.other_org, created_at=now)
        # Plain org project, never linked.
        plain = seed.exam(private=False, kind=None)
        a_plain = seed.attach(plain, created_at=now)

        self._upgrade_after_downgrade(conn)

        assert _origins(
            conn,
            [
                a_linked_private,
                a_orphan,
                a_linked_visible,
                a_shared_first,
                a_reshared,
                a_colleague,
                a_preexisting,
                a_unbound,
                a_other_org,
                a_plain,
            ],
        ) == {
            a_linked_private.id: "lti",
            a_orphan.id: "lti",
            a_linked_visible.id: "lti",
            a_shared_first.id: "manual",
            a_reshared.id: "manual",
            a_colleague.id: "manual",
            a_preexisting.id: "manual",
            a_unbound.id: "manual",
            a_other_org.id: "manual",
            a_plain.id: "manual",
        }

    def test_check_rejects_unknown_values(self, test_db: Session):
        seed = _Attachments(test_db)
        row = seed.attach(
            seed.exam(private=False), created_at=datetime.now(timezone.utc)
        )
        conn = test_db.get_bind()
        assert _origins(conn, [row]) == {row.id: "manual"}
        conn.execute(
            text("UPDATE project_organizations SET attached_via = 'lti' WHERE id = :i"),
            {"i": row.id},
        )
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    text(
                        "UPDATE project_organizations SET attached_via = 'bogus' "
                        "WHERE id = :i"
                    ),
                    {"i": row.id},
                )

    def test_backfill_does_not_rerun_on_an_upgraded_schema(self, test_db: Session):
        seed = _Attachments(test_db)
        project = seed.exam(private=True)
        row = seed.attach(project, created_at=datetime.now(timezone.utc))
        conn = test_db.get_bind()
        assert _origins(conn, [row]) == {row.id: "manual"}

        with _op_context(conn):
            _load_migration().upgrade()

        # A private exam would be backfilled, but the column already exists.
        assert _origins(conn, [row]) == {row.id: "manual"}

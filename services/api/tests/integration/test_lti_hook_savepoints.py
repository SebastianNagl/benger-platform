"""LMS hooks that query through the caller's session fail safe on a real
database.

A failed query aborts the Postgres transaction. The hook wrappers in
``extensions.py`` (and the shared ``NameVisibility``) answer with their safe
value; these tests prove that the caller can keep using its session
afterwards, because the hook ran in a savepoint. Without it the next
statement raised ``InFailedSqlTransaction`` and the request failed with a
500 instead of the documented degraded answer.
"""

import uuid

import pytest
from sqlalchemy import text

import extensions
from lms_name_masking import NameVisibility

pytestmark = pytest.mark.integration


class _FakeExtended:
    COMPATIBLE_CORE_VERSIONS = ("2.20",)

    def __init__(self, hooks):
        self._hooks = hooks

    def get_hooks(self):
        return self._hooks


def _failing_query(db, *args, **kwargs):
    db.execute(text("SELECT 1 / 0"))
    raise AssertionError("the query above must fail")


def _session_still_works(db):
    assert db.execute(text("SELECT 1")).scalar() == 1


@pytest.fixture
def broken_hooks(monkeypatch):
    monkeypatch.setattr(
        extensions,
        "_extended",
        _FakeExtended(
            {
                "privacy_protected_member_ids": _failing_query,
                "project_real_name_viewer": _failing_query,
                "project_real_name_user_ids": _failing_query,
                "projects_real_name_user_ids": _failing_query,
                "lti_anonymization_policy": _failing_query,
            }
        ),
    )


def test_wrappers_answer_safely_and_keep_the_session_usable(test_db, broken_hooks):
    viewer = object()

    assert extensions.privacy_protected_member_ids(test_db, None, ["u1"]) == {"u1"}
    _session_still_works(test_db)
    assert extensions.privacy_protected_member_ids(test_db, "org", ["u1"]) == set()
    _session_still_works(test_db)
    assert (
        extensions.privacy_protected_member_ids(
            test_db, "org", ["u1"], group_ids=["g1"]
        )
        == set()
    )
    _session_still_works(test_db)
    assert extensions.project_real_name_viewer(test_db, viewer, "p1") is False
    _session_still_works(test_db)
    assert extensions.project_real_name_user_ids(test_db, viewer, "p1", ["u1"]) == set()
    _session_still_works(test_db)
    assert extensions.projects_real_name_user_ids(test_db, viewer, {"p1": ["u1"]}) == {
        "p1": set()
    }
    _session_still_works(test_db)
    assert extensions.lti_anonymization_policy(test_db, "u1") == {
        "implicit_org_ids": set(),
        "blockers": ["policy_unavailable"],
    }
    _session_still_works(test_db)


def test_anonymization_check_reports_the_policy_blocker(test_db, broken_hooks):
    """The check keeps querying after the policy hook failed; before the
    savepoint that raised and the preview answered 500."""
    from models import Organization, User
    from services.user_anonymization import (
        AnonymizationScope,
        anonymization_check_sync,
    )

    suffix = uuid.uuid4().hex[:8]
    org = Organization(
        id=f"org-{suffix}",
        name=f"Uni {suffix}",
        display_name=f"Uni {suffix}",
        slug=f"uni-{suffix}",
    )
    user = User(
        id=f"u-{suffix}",
        username=f"u-{suffix}",
        email=f"u-{suffix}@uni.example",
        name="Student",
        is_active=True,
    )
    test_db.add_all([org, user])
    test_db.flush()

    check = anonymization_check_sync(
        test_db,
        user,
        actor_id=None,
        scope=AnonymizationScope(organization_id=org.id),
    )

    assert "policy_unavailable" in check.blockers
    _session_still_works(test_db)


def test_worker_name_visibility_falls_back_on_a_usable_session(test_db):
    """A failed LMS-user hook falls back to the link table. That lookup must
    run on a usable session, or everyone would be masked by the error path
    instead of the link table deciding."""
    policy = NameVisibility(_failing_query, _failing_query)
    user_id = f"nobody-{uuid.uuid4().hex[:8]}"

    # No link rows: the link table says "not an LMS user".
    assert policy.lms_user_ids(test_db, [user_id]) == set()
    viewer = type("Viewer", (), {"id": "v", "is_superadmin": False})()
    assert policy.real_name_user_ids(test_db, viewer, "p1", [user_id]) == set()
    _session_still_works(test_db)

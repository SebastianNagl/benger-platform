"""Integration tests for the sync ``get_student_read_access`` participant gate
and the ``create_annotation`` submit-gate fallback that uses it.

The gate lets a consented share member (private exam) OR an entitled/enrolled
student (vendor purchase / vendor grant / discovery enrollment) submit an
annotation even though ``check_project_accessible`` is owner-only for a private
project — fixing the pre-existing mismatch where a joined member could see the
attempt button but 403'd on submit. Real Postgres via the sync ``test_db``.
"""

import inspect
import uuid
from datetime import datetime, timezone

from models import User
from project_models import (
    MarketplaceEntitlement,
    Project,
    ProjectShareLink,
    ProjectShareMember,
)
from routers.projects.helpers import get_student_read_access


def _user(test_db, tag):
    u = User(
        id=f"sra-{tag}-{uuid.uuid4().hex[:8]}",
        username=f"sra-{uuid.uuid4().hex[:8]}",
        email=f"sra-{uuid.uuid4().hex[:8]}@test.com",
        name=f"SRA {tag}",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(u)
    test_db.flush()
    return u


def _private_project(test_db, owner_id):
    p = Project(
        id=str(uuid.uuid4()),
        title="SRA private exam",
        created_by=owner_id,
        is_private=True,
        is_public=False,
    )
    test_db.add(p)
    test_db.flush()
    return p


class TestGetStudentReadAccess:
    def test_no_grant_is_false(self, test_db):
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        project = _private_project(test_db, owner.id)
        assert get_student_read_access(test_db, student, project.id) is False

    def test_active_entitlement_grants_access(self, test_db):
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        project = _private_project(test_db, owner.id)
        test_db.add(
            MarketplaceEntitlement(
                id=str(uuid.uuid4()),
                user_id=student.id,
                project_id=project.id,
                source="discovered",
            )
        )
        test_db.flush()
        assert get_student_read_access(test_db, student, project.id) is True

    def test_revoked_entitlement_is_false(self, test_db):
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        project = _private_project(test_db, owner.id)
        test_db.add(
            MarketplaceEntitlement(
                id=str(uuid.uuid4()),
                user_id=student.id,
                project_id=project.id,
                source="discovered",
                revoked_at=datetime.now(timezone.utc),
            )
        )
        test_db.flush()
        assert get_student_read_access(test_db, student, project.id) is False

    def test_consented_share_member_grants_access(self, test_db):
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        project = _private_project(test_db, owner.id)
        link = ProjectShareLink(
            id=str(uuid.uuid4()),
            token=uuid.uuid4().hex,
            project_id=project.id,
            created_by=owner.id,
            password_hash="x",
        )
        test_db.add(link)
        test_db.flush()
        test_db.add(
            ProjectShareMember(
                id=str(uuid.uuid4()),
                share_link_id=link.id,
                project_id=project.id,
                user_id=student.id,
                gdpr_consent_at=datetime.now(timezone.utc),
            )
        )
        test_db.flush()
        assert get_student_read_access(test_db, student, project.id) is True

    def test_unconsented_share_member_is_false(self, test_db):
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        project = _private_project(test_db, owner.id)
        link = ProjectShareLink(
            id=str(uuid.uuid4()),
            token=uuid.uuid4().hex,
            project_id=project.id,
            created_by=owner.id,
            password_hash="x",
        )
        test_db.add(link)
        test_db.flush()
        test_db.add(
            ProjectShareMember(
                id=str(uuid.uuid4()),
                share_link_id=link.id,
                project_id=project.id,
                user_id=student.id,
                gdpr_consent_at=None,  # joined but not consented
            )
        )
        test_db.flush()
        assert get_student_read_access(test_db, student, project.id) is False


def test_create_annotation_falls_back_to_participant_gate():
    """Guard: create_annotation must consult get_student_read_access when
    check_project_accessible refuses, so a consented share member / entitled
    student can submit on a private exam (read + submit gates agree)."""
    from routers.projects.annotations import create_annotation

    source = inspect.getsource(create_annotation)
    assert "get_student_read_access" in source, (
        "create_annotation must fall back to the participant gate so a joined "
        "member / entitled student isn't 403'd on submit"
    )

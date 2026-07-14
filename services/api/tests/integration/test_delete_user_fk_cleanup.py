"""Regression test for delete_user FK cleanup against a real database.

Deleting a user used to 500 with a ForeignKeyViolation when the user had
authored rows in tables whose ``users.id`` FK had no ON DELETE rule — the
reported case was ``korrektur_comments`` (constraint still named
``feedback_comments_*``). The mock-based unit tests in
``tests/unit/test_user_service_uncovered.py`` cannot catch this because they
never hit Postgres. This test exercises the real FK constraints.
"""

import pytest
from sqlalchemy.orm import Session

from auth_module.user_service import delete_user
from models import (
    CustomModelCredential,
    LLMModel,
    ModelOrganization,
    Notification,
    NotificationType,
    Organization,
    Tag,
    User,
)
from project_models import KorrekturComment, Project, Task


@pytest.fixture(scope="module", autouse=True)
def _ensure_byom_schema():
    """Backstop for long-lived test DBs bootstrapped before migration 080:
    the custom llm_models row below needs the BYOM columns (and the
    created_by FK with its ON DELETE SET NULL rule). Same pattern as
    tests/integration/test_project_visibility_constraints.py.
    """
    from tests.fixtures.database import _get_engine
    from tests.utils.byom_schema import ensure_byom_llm_schema

    engine, _ = _get_engine()
    ensure_byom_llm_schema(engine)
    yield


@pytest.fixture
def target_with_authored_rows(test_db: Session, test_users):
    """A non-superadmin user with rows across the three cleanup strategies.

    Returns a dict of ids so the test can re-fetch the authored rows after
    deletion. The fallback superadmin that ``delete_user`` reassigns to is not
    pinned here — the shared test DB may carry other superadmins, so the test
    asserts reassignment to *a* surviving superadmin rather than a fixed id.
    """
    target = next(u for u in test_users if not u.is_superadmin)

    project = Project(id="del-fk-project", title="Delete FK Project", created_by=target.id)
    task = Task(id="del-fk-task", project_id=project.id, inner_id=1, data={"text": "x"})
    # REASSIGN (created_by NOT NULL) + NULLIFY (resolved_by nullable) in one row.
    comment = KorrekturComment(
        id="del-fk-comment",
        project_id=project.id,
        task_id=task.id,
        target_type="annotation",
        target_id="del-fk-target",
        text="needs review",
        is_resolved=True,
        resolved_by=target.id,
        created_by=target.id,
    )
    tag = Tag(name="del-fk-tag", normalized_name="del-fk-tag", created_by=target.id)
    notification = Notification(
        id="del-fk-notif",
        user_id=target.id,
        type=NotificationType.PROJECT_CREATED,
        title="hi",
        message="hi",
    )

    # BYOM rows (migration 080). All three FKs carry DB-level ON DELETE
    # rules (CASCADE / SET NULL / SET NULL), so delete_user's manual
    # cleanup lists deliberately don't mention these tables — this fixture
    # proves the rules actually fire.
    org = Organization(
        id="del-fk-org",
        name="del-fk-org",
        display_name="Delete FK Org",
        slug="del-fk-org",
        is_active=True,
    )
    custom_model = LLMModel(
        id="custom-del-fk-model",
        name="Delete FK Custom Model",
        provider="Custom",
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=False,
        created_by=target.id,
        is_private=False,
        is_public=False,
        base_url="http://localhost:11434/v1",
        endpoint_model_name="llama3:8b",
        requires_api_key=True,
    )
    model_org = ModelOrganization(
        id="del-fk-model-org",
        model_id=custom_model.id,
        organization_id=org.id,
        assigned_by=target.id,
    )
    test_db.add_all(
        [project, task, comment, tag, notification, org, custom_model, model_org]
    )
    # CustomModelCredential declares no ORM relationship to LLMModel, so the
    # unit of work can't infer the insert ordering — flush the model row
    # first, then the credential referencing it.
    test_db.flush()
    credential = CustomModelCredential(
        id="del-fk-credential",
        user_id=target.id,
        model_id=custom_model.id,
        encrypted_api_key="ciphertext",
    )
    test_db.add(credential)
    test_db.commit()

    return {
        "target_id": target.id,
        "comment_id": comment.id,
        "tag_id": tag.id,
        "notification_id": notification.id,
        "project_id": project.id,
        "custom_model_id": custom_model.id,
        "model_org_id": model_org.id,
        "credential_id": credential.id,
    }


def test_delete_user_cleans_all_fk_references(test_db: Session, target_with_authored_rows):
    ids = target_with_authored_rows

    result = delete_user(test_db, ids["target_id"])

    assert result is True
    test_db.expire_all()

    # User row is gone.
    assert test_db.query(User).filter(User.id == ids["target_id"]).first() is None

    # korrektur_comments.created_by (NOT NULL) reassigned to a surviving fallback
    # superadmin; resolved_by (nullable) nulled. The comment itself is preserved.
    comment = test_db.query(KorrekturComment).filter_by(id=ids["comment_id"]).first()
    assert comment is not None
    fallback_id = comment.created_by
    assert fallback_id != ids["target_id"]
    fallback = test_db.query(User).filter_by(id=fallback_id).first()
    assert fallback is not None and fallback.is_superadmin
    assert comment.resolved_by is None

    # tags.created_by (nullable) nulled, row preserved.
    tag = test_db.query(Tag).filter_by(id=ids["tag_id"]).first()
    assert tag is not None
    assert tag.created_by is None

    # notifications belong to the deleted user → row removed.
    assert (
        test_db.query(Notification).filter_by(id=ids["notification_id"]).first() is None
    )

    # Existing behaviour: project ownership reassigned to the same fallback, not
    # destroyed.
    project = test_db.query(Project).filter_by(id=ids["project_id"]).first()
    assert project is not None
    assert project.created_by == fallback_id

    # custom_model_credentials.user_id (ON DELETE CASCADE): credentials are
    # personal — the row goes with the user.
    assert (
        test_db.query(CustomModelCredential).filter_by(id=ids["credential_id"]).first()
        is None
    )

    # llm_models.created_by (ON DELETE SET NULL): shared/public custom models
    # outlive their creator; only superadmins can edit them afterwards.
    model = test_db.query(LLMModel).filter_by(id=ids["custom_model_id"]).first()
    assert model is not None
    assert model.created_by is None
    assert model.is_active is True

    # model_organizations.assigned_by (ON DELETE SET NULL): deleting the user
    # who shared a model must not revoke the org's access.
    model_org = test_db.query(ModelOrganization).filter_by(id=ids["model_org_id"]).first()
    assert model_org is not None
    assert model_org.assigned_by is None

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
from models import Notification, NotificationType, Tag, User
from project_models import KorrekturComment, Project, Task


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

    test_db.add_all([project, task, comment, tag, notification])
    test_db.commit()

    return {
        "target_id": target.id,
        "comment_id": comment.id,
        "tag_id": tag.id,
        "notification_id": notification.id,
        "project_id": project.id,
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

"""Withdrawing a submission (core 2.79, migration 155).

``POST /api/projects/annotations/{id}/withdraw`` is the one way to take a
handed-in submission back: its author withdraws it, or a project editor
returns it to the author. Nothing is deleted. The row is marked cancelled
and records who withdrew it, when and why; the author can hand in again; a
return notifies the author. The overlay may refuse a withdrawal
(``before_annotation_withdraw``) and withdraws its own results in the same
transaction (``on_annotation_withdrawn``). ``PATCH`` no longer changes
``was_cancelled``.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import extension_activation as activation
import extensions
from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Notification,
    NotificationType,
    Organization,
    OrganizationMembership,
    User,
)
from project_models import Annotation, Project, ProjectOrganization, Task

RESULT = [
    {"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["answer"]}}
]
REJECTION = {"code": "withdrawal_closed", "message": "already graded"}


def _uid():
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _mute_celery():
    """Report refresh and notification e-mail go through Celery; keep them offline."""
    with patch("celery_client.get_celery_app", return_value=MagicMock()), patch(
        "notification_service.get_celery_app", return_value=MagicMock()
    ):
        yield


@pytest.fixture(autouse=True)
def _no_overlay(monkeypatch):
    """No package loaded unless a test installs one."""
    monkeypatch.setattr(extensions, "_packages", lambda: [])


class _FakePackage:
    def __init__(self, hooks):
        self._hooks = hooks

    def get_hooks(self):
        return self._hooks


def _install(monkeypatch, hooks):
    monkeypatch.setattr(
        extensions, "_packages", lambda: [("benger_extended", _FakePackage(hooks))]
    )


@contextmanager
def _as_user(db_user):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


def _user(db, name):
    user = User(
        id=_uid(),
        username=f"{name}-{_uid()[:8]}",
        email=f"{name}-{_uid()[:8]}@example.com",
        name=name.title(),
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    return user


async def _seed(db, *, min_annotations_per_task=1, **project_fields):
    """A project of ``editor`` in an organization where ``author`` and
    ``peer`` are annotators, one task and ``author``'s submission."""
    editor, author, peer, outsider = (
        _user(db, "editor"),
        _user(db, "author"),
        _user(db, "peer"),
        _user(db, "outsider"),
    )
    org = Organization(
        id=_uid(),
        name="Withdrawal Org",
        slug=f"withdrawal-{_uid()[:8]}",
        display_name="Withdrawal Org",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    for member, role in ((editor, "ORG_ADMIN"), (author, "ANNOTATOR"), (peer, "ANNOTATOR")):
        db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=member.id,
                organization_id=org.id,
                role=role,
                joined_at=datetime.now(timezone.utc),
            )
        )
    project = Project(
        id=_uid(),
        title="Withdrawal Project",
        created_by=editor.id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        maximum_annotations=0,
        min_annotations_per_task=min_annotations_per_task,
        assignment_mode="open",
        **project_fields,
    )
    db.add(project)
    await db.flush()
    db.add(
        ProjectOrganization(
            id=_uid(), project_id=project.id, organization_id=org.id, assigned_by=editor.id
        )
    )
    task = Task(
        id=_uid(),
        project_id=project.id,
        data={"text": "t"},
        inner_id=1,
        total_annotations=1,
        cancelled_annotations=0,
        is_labeled=True,
    )
    db.add(task)
    await db.flush()
    annotation = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        completed_by=author.id,
        result=RESULT,
    )
    db.add(annotation)
    await db.commit()
    seed = {
        "editor": editor,
        "author": author,
        "peer": peer,
        "outsider": outsider,
        "project": project,
        "task": task,
        "annotation": annotation,
    }
    # Plain ids: requests expire the ORM objects, and an expired attribute
    # would lazy-load outside the async context (MissingGreenlet).
    seed.update({f"{key}_id": obj.id for key, obj in list(seed.items())})
    return seed


async def _row(db, annotation_id):
    db.expire_all()
    return (
        await db.execute(select(Annotation).where(Annotation.id == annotation_id))
    ).scalar_one()


async def _task(db, task_id):
    db.expire_all()
    return (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()


async def _withdraw(client, annotation_id, reason="Wrong file uploaded"):
    return await client.post(
        f"/api/projects/annotations/{annotation_id}/withdraw", json={"reason": reason}
    )


async def _returned_notices(db, user_id):
    db.expire_all()
    return (
        (
            await db.execute(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.type == NotificationType.SUBMISSION_RETURNED,
                )
            )
        )
        .scalars()
        .all()
    )


# --------------------------------------------------------------------------- #
# Hook contract
# --------------------------------------------------------------------------- #
class TestHookContract:
    @pytest.mark.parametrize("key", ["before_annotation_withdraw", "on_annotation_withdrawn"])
    def test_spec_and_gating(self, key):
        assert extensions.HOOK_SPECS[key] == extensions.CALL_ALL
        assert extensions.HOOK_GATING[key] == activation.ALWAYS
        assert key not in extensions.PENDING_HOOK_KEYS
        extensions._validate_hook_gating()

    def test_wrappers_are_noops_without_a_package(self):
        assert extensions.before_annotation_withdraw(None, object(), "u", by_author=True) is None
        assert (
            extensions.on_annotation_withdrawn(None, object(), "u", by_author=False, reason="r")
            is None
        )


# --------------------------------------------------------------------------- #
# The author withdraws
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
class TestAuthorWithdraws:
    async def test_row_is_kept_and_records_the_withdrawal(
        self, async_test_client, async_test_db
    ):
        seed = await _seed(async_test_db)
        annotation_id, task_id = seed["annotation_id"], seed["task_id"]
        author_id = seed["author_id"]
        before = datetime.now(timezone.utc) - timedelta(seconds=5)
        with _as_user(seed["author"]):
            resp = await _withdraw(async_test_client, annotation_id, "  Wrong project  ")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["was_cancelled"] is True
        assert body["withdrawn_by"] == author_id
        assert body["withdrawal_reason"] == "Wrong project"
        assert body["withdrawn_at"] is not None

        row = await _row(async_test_db, annotation_id)
        assert row.result == RESULT  # nothing deleted
        assert row.was_cancelled is True
        assert row.withdrawn_by == author_id
        assert row.withdrawal_reason == "Wrong project"
        assert row.withdrawn_at >= before
        task = await _task(async_test_db, task_id)
        assert task.cancelled_annotations == 1
        assert task.total_annotations == 1
        assert task.is_labeled is False
        # The author withdrew it: no notice to anybody.
        assert await _returned_notices(async_test_db, author_id) == []

    async def test_author_can_hand_in_again(self, async_test_client, async_test_db):
        from annotation_submission import persist_submission

        seed = await _seed(async_test_db)
        annotation_id, task_id = seed["annotation_id"], seed["task_id"]
        author_id = seed["author_id"]
        with _as_user(seed["author"]):
            assert (await _withdraw(async_test_client, annotation_id)).status_code == 200

        # The persistence core of POST /tasks/{id}/annotations.
        new_id = await async_test_db.run_sync(
            lambda session: persist_submission(
                session,
                task=session.get(Task, seed["task_id"]),
                project=session.get(Project, seed["project_id"]),
                user_id=author_id,
                fields={"result": RESULT},
            ).id
        )
        assert new_id != annotation_id
        rows = (
            (
                await async_test_db.execute(
                    select(Annotation).where(Annotation.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )
        assert {(r.id, r.was_cancelled) for r in rows} == {
            (annotation_id, True),
            (new_id, False),
        }
        assert (await _task(async_test_db, task_id)).is_labeled is True

    async def test_reason_is_required(self, async_test_client, async_test_db):
        seed = await _seed(async_test_db)
        with _as_user(seed["author"]):
            blank = await _withdraw(async_test_client, seed["annotation_id"], "   ")
            missing = await async_test_client.post(
                f"/api/projects/annotations/{seed['annotation_id']}/withdraw", json={}
            )
            too_long = await _withdraw(async_test_client, seed["annotation_id"], "x" * 2001)
        assert blank.status_code == 422
        assert missing.status_code == 422
        assert too_long.status_code == 422
        assert (await _row(async_test_db, seed["annotation_id"])).was_cancelled is False

    async def test_a_second_withdrawal_is_refused(self, async_test_client, async_test_db):
        seed = await _seed(async_test_db)
        with _as_user(seed["author"]):
            assert (await _withdraw(async_test_client, seed["annotation_id"])).status_code == 200
            again = await _withdraw(async_test_client, seed["annotation_id"], "again")
        assert again.status_code == 409
        assert again.json()["detail"]["code"] == "annotation_withdrawn"
        row = await _row(async_test_db, seed["annotation_id"])
        assert row.withdrawal_reason == "Wrong file uploaded"
        assert (await _task(async_test_db, seed["task_id"])).cancelled_annotations == 1

    async def test_closed_access_window_refuses_the_author(
        self, async_test_client, async_test_db
    ):
        seed = await _seed(
            async_test_db,
            window_end_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        with _as_user(seed["author"]):
            resp = await _withdraw(async_test_client, seed["annotation_id"])
        assert resp.status_code == 403
        assert (await _row(async_test_db, seed["annotation_id"])).was_cancelled is False

    async def test_write_hook_runs_for_the_author(
        self, monkeypatch, async_test_client, async_test_db
    ):
        seed = await _seed(async_test_db)

        def timer_expired(db, task_id, user_id, project_id, **kwargs):
            raise extensions.AnnotationWriteRejected(
                {"code": "exam_timer_expired", "message": "time is up"}
            )

        _install(monkeypatch, {"before_annotation_write": timer_expired})
        with _as_user(seed["author"]):
            resp = await _withdraw(async_test_client, seed["annotation_id"])
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "exam_timer_expired"
        assert (await _row(async_test_db, seed["annotation_id"])).was_cancelled is False


# --------------------------------------------------------------------------- #
# Someone else: an editor returns it, anybody else cannot see it
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
class TestEditorReturns:
    async def test_editor_returns_and_the_author_is_notified(
        self, async_test_client, async_test_db
    ):
        seed = await _seed(async_test_db)
        annotation_id, author_id = seed["annotation_id"], seed["author_id"]
        editor_id, project_id = seed["editor_id"], seed["project_id"]
        with _as_user(seed["editor"]):
            resp = await _withdraw(async_test_client, annotation_id, "Please hand in the full text")
        assert resp.status_code == 200, resp.text
        assert resp.json()["withdrawn_by"] == editor_id
        row = await _row(async_test_db, annotation_id)
        assert row.was_cancelled is True
        assert row.completed_by == author_id
        assert row.withdrawn_by == editor_id

        notices = await _returned_notices(async_test_db, author_id)
        assert len(notices) == 1
        data = notices[0].data
        assert data["project_id"] == project_id
        assert data["annotation_id"] == annotation_id
        assert data["task_id"] == seed["task_id"]
        assert data["reason"] == "Please hand in the full text"
        assert "Please hand in the full text" in notices[0].message
        assert await _returned_notices(async_test_db, editor_id) == []

    async def test_closed_window_does_not_stop_the_editor(
        self, async_test_client, async_test_db
    ):
        seed = await _seed(
            async_test_db,
            window_end_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        with _as_user(seed["editor"]):
            resp = await _withdraw(async_test_client, seed["annotation_id"])
        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize("who", ["peer", "outsider"])
    async def test_without_edit_rights_it_is_not_found(
        self, who, async_test_client, async_test_db
    ):
        seed = await _seed(async_test_db)
        with _as_user(seed[who]):
            resp = await _withdraw(async_test_client, seed["annotation_id"])
        assert resp.status_code == 404
        assert (await _row(async_test_db, seed["annotation_id"])).was_cancelled is False

    async def test_unknown_annotation(self, async_test_client, async_test_db):
        seed = await _seed(async_test_db)
        with _as_user(seed["editor"]):
            resp = await _withdraw(async_test_client, _uid())
        assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Overlay hooks
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
class TestOverlayHooks:
    async def test_policy_hook_refuses_and_nothing_is_written(
        self, monkeypatch, async_test_client, async_test_db
    ):
        seed = await _seed(async_test_db)
        calls = []

        def refuse(db, annotation, actor_id, *, by_author):
            calls.append((annotation.id, annotation.was_cancelled, actor_id, by_author))
            raise extensions.AnnotationWriteRejected(REJECTION)

        _install(monkeypatch, {"before_annotation_withdraw": refuse})
        with _as_user(seed["author"]):
            resp = await _withdraw(async_test_client, seed["annotation_id"])
        assert resp.status_code == 409
        assert resp.json()["detail"] == REJECTION
        assert calls == [(seed["annotation_id"], False, seed["author_id"], True)]
        assert (await _row(async_test_db, seed["annotation_id"])).was_cancelled is False
        assert (await _task(async_test_db, seed["task_id"])).cancelled_annotations == 0

    async def test_policy_hook_tells_a_return_apart(
        self, monkeypatch, async_test_client, async_test_db
    ):
        seed = await _seed(async_test_db)
        calls = []
        _install(
            monkeypatch,
            {
                "before_annotation_withdraw": lambda db, annotation, actor_id, *, by_author: calls.append(
                    (actor_id, by_author)
                )
            },
        )
        with _as_user(seed["editor"]):
            assert (await _withdraw(async_test_client, seed["annotation_id"])).status_code == 200
        assert calls == [(seed["editor_id"], False)]

    async def test_consequence_hook_sees_the_marked_row_in_the_same_transaction(
        self, monkeypatch, async_test_client, async_test_db
    ):
        seed = await _seed(async_test_db)
        seen = []

        def consequences(db, annotation, actor_id, *, by_author, reason):
            # Same transaction: the row is already marked when read through db.
            fresh = db.get(Annotation, annotation.id)
            seen.append(
                (fresh.was_cancelled, fresh.withdrawn_by, fresh.withdrawal_reason, by_author, reason)
            )

        _install(monkeypatch, {"on_annotation_withdrawn": consequences})
        with _as_user(seed["editor"]):
            assert (await _withdraw(async_test_client, seed["annotation_id"], "Returned")).status_code == 200
        assert seen == [(True, seed["editor_id"], "Returned", False, "Returned")]

    async def test_failing_consequence_hook_rolls_the_withdrawal_back(
        self, monkeypatch, async_test_client, async_test_db
    ):
        seed = await _seed(async_test_db)
        annotation_id, task_id = seed["annotation_id"], seed["task_id"]

        def broken(db, annotation, actor_id, *, by_author, reason):
            raise RuntimeError("feedback withdrawal failed")

        _install(monkeypatch, {"on_annotation_withdrawn": broken})
        with _as_user(seed["editor"]):
            with pytest.raises(RuntimeError, match="feedback withdrawal failed"):
                await _withdraw(async_test_client, annotation_id)
        row = await _row(async_test_db, annotation_id)
        assert row.was_cancelled is False
        assert row.withdrawn_at is None
        assert (await _task(async_test_db, task_id)).cancelled_annotations == 0
        assert await _returned_notices(async_test_db, seed["author_id"]) == []


# --------------------------------------------------------------------------- #
# PATCH no longer toggles was_cancelled
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
class TestPatchLeavesWithdrawalAlone:
    async def test_withdrawn_submission_cannot_be_edited(
        self, async_test_client, async_test_db
    ):
        seed = await _seed(async_test_db)
        with _as_user(seed["author"]):
            assert (await _withdraw(async_test_client, seed["annotation_id"])).status_code == 200
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{seed['annotation_id']}",
                json={"result": RESULT, "was_cancelled": False},
            )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "annotation_withdrawn"
        assert (await _row(async_test_db, seed["annotation_id"])).was_cancelled is True

    async def test_patch_cannot_cancel(self, async_test_client, async_test_db):
        seed = await _seed(async_test_db)
        with _as_user(seed["author"]):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{seed['annotation_id']}",
                json={"result": RESULT, "was_cancelled": True},
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "withdrawal_reason_required"
        assert (await _row(async_test_db, seed["annotation_id"])).was_cancelled is False

    async def test_plain_edit_still_works(self, async_test_client, async_test_db):
        seed = await _seed(async_test_db)
        edited = [{**RESULT[0], "value": {"text": ["edited"]}}]
        with _as_user(seed["author"]):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{seed['annotation_id']}",
                json={"result": edited},
            )
        assert resp.status_code == 200, resp.text
        row = await _row(async_test_db, seed["annotation_id"])
        assert row.result == edited
        assert row.was_cancelled is False

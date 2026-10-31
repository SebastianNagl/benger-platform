"""Task counters move atomically on annotation submit (audit E12).

``persist_annotation_submission`` used to do ``task.total_annotations += 1``
on the ORM object. The advisory lock it holds is per (task, user), so two
users submitting to the same task both read the same count and one increment
was lost. The counters are now incremented in SQL. The tests simulate the
concurrent submitter by moving the row in the database while the handler's
``task`` object still holds the old values.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from project_models import Annotation, Project, Task
from project_schemas import AnnotationCreate
from routers.projects.annotations import persist_annotation_submission


@pytest.fixture(autouse=True)
def _mute_celery():
    with patch("celery_client.get_celery_app", return_value=MagicMock()):
        yield


def _make_project(db, created_by, *, min_annotations=1):
    project = Project(
        id=str(uuid.uuid4()),
        title="Atomic counter test",
        created_by=created_by,
        assignment_mode="open",
        maximum_annotations=0,
        min_annotations_per_task=min_annotations,
    )
    db.add(project)
    db.flush()
    return project


def _make_task(db, project):
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        inner_id=1,
        data={"text": "Some legal text"},
    )
    db.add(task)
    db.commit()
    return task


def _submission(**overrides):
    payload = {
        "result": [{"value": {"choices": ["positive"]}, "from_name": "label"}],
        "was_cancelled": False,
    }
    payload.update(overrides)
    return AnnotationCreate(**payload)


def _concurrent_submit(db, task, other_user_id, *, total, cancelled=0):
    """Another user's submit that committed after ``task`` was loaded."""
    db.add(
        Annotation(
            id=str(uuid.uuid4()),
            task_id=task.id,
            project_id=task.project_id,
            completed_by=other_user_id,
            result=[{"value": {"choices": ["negative"]}}],
            was_cancelled=False,
        )
    )
    db.flush()
    db.execute(
        text(
            "UPDATE tasks SET total_annotations = :t, cancelled_annotations = :c "
            "WHERE id = :id"
        ),
        {"t": total, "c": cancelled, "id": task.id},
    )


def _db_counters(db, task_id):
    return db.execute(
        text(
            "SELECT total_annotations, cancelled_annotations, is_labeled "
            "FROM tasks WHERE id = :id"
        ),
        {"id": task_id},
    ).one()


def test_increment_is_not_lost_against_a_stale_task_row(test_db, test_users):
    admin, other = test_users[0], test_users[1]
    project = _make_project(test_db, admin.id, min_annotations=5)
    task = _make_task(test_db, project)
    assert task.total_annotations == 0  # loaded, now stale

    _concurrent_submit(test_db, task, other.id, total=1)

    persist_annotation_submission(
        test_db, task=task, project=project, user_id=admin.id, annotation=_submission()
    )

    total, cancelled, labeled = _db_counters(test_db, task.id)
    # The Python read-modify-write wrote 0 + 1 = 1 and lost the other submit.
    assert total == 2
    assert cancelled == 0
    assert labeled is False
    assert task.total_annotations == 2  # RETURNING values synced onto the object


def test_cancelled_counter_is_atomic_too(test_db, test_users):
    admin, other = test_users[0], test_users[1]
    project = _make_project(test_db, admin.id)
    task = _make_task(test_db, project)

    _concurrent_submit(test_db, task, other.id, total=3, cancelled=2)

    persist_annotation_submission(
        test_db,
        task=task,
        project=project,
        user_id=admin.id,
        annotation=_submission(was_cancelled=True),
    )

    total, cancelled, _ = _db_counters(test_db, task.id)
    assert (total, cancelled) == (4, 3)


def test_is_labeled_counts_the_concurrent_submitter(test_db, test_users):
    """min 2: the other user's committed annotation plus ours reach the
    threshold even though our ``task`` object never saw the first one."""
    admin, other = test_users[0], test_users[1]
    project = _make_project(test_db, admin.id, min_annotations=2)
    task = _make_task(test_db, project)

    _concurrent_submit(test_db, task, other.id, total=1)

    persist_annotation_submission(
        test_db, task=task, project=project, user_id=admin.id, annotation=_submission()
    )

    total, _, labeled = _db_counters(test_db, task.id)
    assert total == 2
    assert labeled is True


def test_resubmit_in_place_does_not_move_counters(test_db, test_users):
    admin = test_users[0]
    project = _make_project(test_db, admin.id)
    task = _make_task(test_db, project)

    persist_annotation_submission(
        test_db, task=task, project=project, user_id=admin.id, annotation=_submission()
    )
    persist_annotation_submission(
        test_db, task=task, project=project, user_id=admin.id, annotation=_submission()
    )

    total, cancelled, labeled = _db_counters(test_db, task.id)
    assert (total, cancelled, labeled) == (1, 0, True)

"""Draft save (``PUT /projects/{id}/tasks/{task_id}/draft``) integrity.

- The access checks run against the project in the URL, so a task of another
  project is refused (404) instead of getting a draft filed under the wrong
  project.
- The save is one ``INSERT ... ON CONFLICT`` statement: two saves of the same
  (task, user) at once (two tabs, a retry overtaking the original) no longer
  race into ``unique_task_draft`` (500), and repeated saves keep one row.
  Real parallelism cannot run inside the shared test session; it was checked
  against the dev stack (500 parallel saves from 50 accounts, no error).
"""

import uuid
import pytest

from project_models import Project, Task, TaskDraft

EXAM_CONFIG = (
    '<View><Text name="sv" value="$sachverhalt"/>'
    '<TextArea name="loesung" toName="sv"/></View>'
)


def _uid() -> str:
    return str(uuid.uuid4())


def _project_with_task(test_db, owner_id):
    project = Project(id=_uid(), title="Draft", created_by=owner_id, label_config=EXAM_CONFIG)
    test_db.add(project)
    test_db.flush()
    task = Task(id=_uid(), project_id=project.id, inner_id=1, data={"sachverhalt": "x"})
    test_db.add(task)
    test_db.commit()
    return project, task


def _draft(text):
    return {"result": [{"from_name": "loesung", "value": {"text": [text]}}]}


@pytest.mark.integration
class TestDraftSaveIntegrity:
    def test_refuses_task_of_other_project(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        a, _ = _project_with_task(test_db, admin.id)
        _, task_b = _project_with_task(test_db, admin.id)
        r = client.put(
            f"/api/projects/{a.id}/tasks/{task_b.id}/draft",
            json=_draft("a"),
            headers=auth_headers["admin"],
        )
        assert r.status_code == 404, r.text
        test_db.expire_all()
        assert test_db.query(TaskDraft).filter(TaskDraft.task_id == task_b.id).count() == 0

    def test_repeated_saves_keep_one_row_with_the_latest_text(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        project, task = _project_with_task(test_db, admin.id)
        url = f"/api/projects/{project.id}/tasks/{task.id}/draft"
        for text in ("eins", "zwei", "drei"):
            r = client.put(url, json=_draft(text), headers=auth_headers["admin"])
            assert r.status_code == 200, r.text
        test_db.expire_all()
        rows = test_db.query(TaskDraft).filter(TaskDraft.task_id == task.id).all()
        assert len(rows) == 1
        assert rows[0].draft_result[0]["value"]["text"] == ["drei"]

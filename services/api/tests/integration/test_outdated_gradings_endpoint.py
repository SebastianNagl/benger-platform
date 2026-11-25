"""GET /api/evaluations/projects/{id}/outdated-gradings.

How many current gradings rest on an older sheet or grading scheme
(shared/grading_basis.py). Edit-gated like the Notenschlüssel drift count
and 404 on a missing project. The rule itself is covered by
``tests/unit/test_grading_basis.py`` and the worker suite
(``tests/integration/test_grading_basis_sheet.py``,
``test_regrade_outdated_e2e.py``); this file pins the wiring. The handler
is SYNC, so the tests use the legacy ``client`` / ``test_db`` fixtures.
"""

import uuid

import pytest

from grading_basis import scheme_fingerprint, stamp_grading_basis
from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation
from project_models import Project, ProjectOrganization, Task

BASE = "/api/evaluations"


def _uid():
    return str(uuid.uuid4())


def _judge(template):
    return {
        "id": "judge",
        "metric": "llm_judge_custom",
        "display_name": "Judge",
        "prediction_fields": ["answer"],
        "reference_fields": [],
        "metric_parameters": {"custom_prompt_template": template},
        "enabled": True,
    }


def _seed(test_db, test_users, test_org, graded_with, current):
    project = Project(
        id=_uid(),
        title="Outdated gradings",
        created_by=test_users[0].id,
        label_config='<View><Text name="text" value="$text"/></View>',
        evaluation_config={"evaluation_configs": [current]},
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(ProjectOrganization(
        id=_uid(), project_id=project.id, organization_id=test_org.id,
        assigned_by=test_users[0].id,
    ))
    task = Task(id=_uid(), project_id=project.id, data={"text": "t"}, inner_id=1,
                created_by=test_users[0].id)
    test_db.add(task)
    run = EvaluationRun(id=_uid(), project_id=project.id, model_id="gpt-5-mini",
                        evaluation_type_ids=[], metrics={}, status="completed",
                        created_by=test_users[0].id)
    test_db.add(run)
    test_db.flush()
    judge_run = EvaluationJudgeRun(id=_uid(), evaluation_id=run.id, judge_model_id="gpt-5-mini",
                                   run_index=0, status="completed")
    test_db.add(judge_run)
    test_db.flush()
    test_db.add(TaskEvaluation(
        id=_uid(), evaluation_id=run.id, judge_run_id=judge_run.id, task_id=task.id,
        field_name="judge|model:answer|", evaluation_config_id="judge", answer_type="text",
        ground_truth={}, prediction={},
        metrics=stamp_grading_basis({"llm_judge_custom": {"value": 0.7}}, graded_with),
        passed=True,
    ))
    test_db.commit()
    return project


@pytest.mark.integration
class TestOutdatedGradings:
    def test_counts_rows_graded_on_an_older_scheme(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed(test_db, test_users, test_org, _judge("old"), _judge("new"))
        resp = client.get(
            f"{BASE}/projects/{project.id}/outdated-gradings", headers=auth_headers["admin"]
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "project_id": project.id,
            "total": 1,
            "ai": 1,
            "human": 0,
            "configs": [{
                "config_id": "judge",
                "metric": "llm_judge_custom",
                "display_name": "Judge",
                "human": False,
                "graded": 1,
                "outdated": 1,
                "reasons": {"sheet": 0, "scheme": 1},
            }],
        }

    def test_a_current_grading_is_not_counted(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed(test_db, test_users, test_org, _judge("same"), _judge("same"))
        assert scheme_fingerprint(_judge("same"))
        body = client.get(
            f"{BASE}/projects/{project.id}/outdated-gradings", headers=auth_headers["admin"]
        ).json()
        assert (body["total"], body["configs"][0]["graded"]) == (0, 1)

    def test_a_viewer_without_edit_rights_is_denied(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed(test_db, test_users, test_org, _judge("old"), _judge("new"))
        resp = client.get(
            f"{BASE}/projects/{project.id}/outdated-gradings", headers=auth_headers["annotator"]
        )
        assert resp.status_code == 403

    def test_missing_project_404(self, client, auth_headers):
        resp = client.get(
            f"{BASE}/projects/{_uid()}/outdated-gradings", headers=auth_headers["admin"]
        )
        assert resp.status_code == 404

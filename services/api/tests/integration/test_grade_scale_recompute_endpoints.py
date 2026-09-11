"""The two Notenschlüssel-recompute endpoints (contract v4).

    GET  /api/evaluations/projects/{id}/grade-scale/drift
         -> {"stale": int, "graded": int, "scale_source": ...,
             "last_change": {...}|null}
    POST /api/evaluations/projects/{id}/grade-scale/recompute
         -> {"updated": int, "scanned": int}

Both are edit-gated (``Permission.PROJECT_EDIT``) and 404 on a missing
project. The planner itself is unit-tested in
``tests/unit/test_grade_scale_recompute.py``; this file pins the wiring:
the SQL prefilter really finds the graded rows, the rewrite lands in
Postgres, it is idempotent, and the permission gate holds.

Both handlers are SYNC (psycopg2 lane), so these tests use the legacy
``client`` / ``test_db`` fixtures, which share one session.
"""

import copy
import itertools
import uuid

import pytest

from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation
from project_models import Project, ProjectOrganization, Task, TaskRubric
from rubric_structure import GRADE_SCALE_PRESETS, PERCENT_GRADE_UNIT

BASE = "/api/evaluations"


def _uid():
    return str(uuid.uuid4())


def _percent_key(preset):
    return {
        "unit": PERCENT_GRADE_UNIT,
        "preset": preset,
        "thresholds": list(GRADE_SCALE_PRESETS[preset]),
        "rounding": "floor",
        "pass_grade": 4,
    }


def _seed_project(test_db, test_users, test_org, evaluation_config=None):
    project = Project(
        id=_uid(),
        title="Notenschlüssel Recompute",
        created_by=test_users[0].id,
        label_config='<View><Text name="text" value="$text"/></View>',
        evaluation_config=evaluation_config,
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=test_users[0].id,
        )
    )
    test_db.commit()
    return project


_next_inner_id = itertools.count(1)


def _seed_graded_row(test_db, project, user_id, *, metrics, passed=True, rubric=None):
    """One graded TaskEvaluation under its own run/judge-run/task."""
    task = Task(
        id=_uid(),
        project_id=project.id,
        data={"text": "Sachverhalt"},
        inner_id=next(_next_inner_id),
        created_by=user_id,
    )
    test_db.add(task)
    test_db.flush()
    if rubric is not None:
        rubric.task_id = task.id
        rubric.project_id = project.id
        test_db.add(rubric)
        test_db.flush()
    run = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id="gpt-5-mini",
        evaluation_type_ids=[],
        metrics={},
        created_by=user_id,
    )
    test_db.add(run)
    test_db.flush()
    judge_run = EvaluationJudgeRun(
        id=_uid(), evaluation_id=run.id, judge_model_id="gpt-5-mini", run_index=0,
        status="completed",
    )
    test_db.add(judge_run)
    test_db.flush()
    record = TaskEvaluation(
        id=_uid(),
        evaluation_id=run.id,
        judge_run_id=judge_run.id,
        task_id=task.id,
        field_name="answer",
        answer_type="text",
        ground_truth={"text": ""},
        prediction={"text": "Gutachten"},
        metrics=metrics,
        passed=passed,
    )
    test_db.add(record)
    test_db.commit()
    return record


def _rubric_metrics(grade_points, rubric_id, *, total_score=73.5, siblings=False, source="default"):
    metrics = {
        "llm_judge_rubric": {
            "value": total_score / 100.0,
            "method": "llm_judge_rubric",
            "details": {
                "scores": {"a": total_score},
                "rubric_id": rubric_id,
                "total_max": 100.0,
                "total_score": total_score,
                "raw_output": "<verbatim>",
                "grade_points": grade_points,
                "passed": True,
                "grade_scale_source": source,
            },
            "error": None,
        },
        "raw_score": total_score / 100.0,
    }
    if siblings:
        metrics["llm_judge_rubric_grade_points"] = float(grade_points)
        metrics["llm_judge_rubric_passed"] = 1.0
    return metrics


def _falloesung_metrics(grade_points, raw_score=58.5):
    return {
        "llm_judge_falloesung": {
            "value": raw_score / 100.0,
            "method": "llm_judge_falloesung",
            "details": {
                "passed": True,
                "raw_score": raw_score,
                "grade_points": grade_points,
                "judge_response": {"score": raw_score, "reasoning": "Aufbau ok."},
            },
            "error": None,
        }
    }


def _ungraded_metrics():
    """A legacy ``llm_judge_custom`` row: totals, but never a Notenpunkt."""
    return {
        "llm_judge_custom": {
            "value": 0.4,
            "method": "llm_judge_custom",
            "details": {"total_score": 40.0, "total_max": 100.0, "scores": {}},
            "error": None,
        },
        "raw_score": 0.4,
    }


def _headers(auth_headers, test_org, role="admin"):
    return {**auth_headers[role], "X-Organization-Context": test_org.id}


def _reload(test_db, record_id):
    test_db.expire_all()
    return test_db.query(TaskEvaluation).filter(TaskEvaluation.id == record_id).first()


@pytest.mark.integration
class TestGradeScaleDrift:
    def test_counts_only_rows_whose_grade_moved(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """The live dev shape: an AI grading computed under the standard key
        and a human grading already on the Übungsklausur key, same 73.5 of
        100 BE — exactly one of them is stale."""
        project = _seed_project(
            test_db, test_users, test_org, {"grade_scale": _percent_key("uebungsklausur")}
        )
        rubric_id = _uid()
        _seed_graded_row(
            test_db, project, test_users[0].id,
            metrics=_rubric_metrics(10, rubric_id),
            rubric=TaskRubric(id=rubric_id, criteria={}, total_points=100.0, status="active"),
        )
        _seed_graded_row(
            test_db, project, test_users[0].id,
            metrics=_rubric_metrics(12, _uid(), source="project"),
        )
        # An ungraded row is invisible to the scan in both counts.
        _seed_graded_row(
            test_db, project, test_users[0].id, metrics=_ungraded_metrics(), passed=False
        )

        resp = client.get(
            f"{BASE}/projects/{project.id}/grade-scale/drift",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "stale": 1,
            "graded": 2,
            "scale_source": "project",
            "last_change": None,
        }

    def test_a_project_without_gradings_reports_zero(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        resp = client.get(
            f"{BASE}/projects/{project.id}/grade-scale/drift",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "stale": 0,
            "graded": 0,
            "scale_source": "default",
            "last_change": None,
        }

    def test_scale_source_names_the_sheets_key_when_the_exam_has_none(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        rubric_id = _uid()
        _seed_graded_row(
            test_db, project, test_users[0].id,
            metrics=_rubric_metrics(12, rubric_id, source="rubric"),
            rubric=TaskRubric(
                id=rubric_id, criteria={}, total_points=100.0, status="active",
                grade_scale=_percent_key("uebungsklausur"),
            ),
        )
        body = client.get(
            f"{BASE}/projects/{project.id}/grade-scale/drift",
            headers=_headers(auth_headers, test_org),
        ).json()
        assert body["scale_source"] == "rubric"
        assert body == {
            "stale": 0,
            "graded": 1,
            "scale_source": "rubric",
            "last_change": None,
        }

    def test_missing_project_404(self, client, auth_headers, test_org):
        resp = client.get(
            f"{BASE}/projects/{_uid()}/grade-scale/drift",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_a_viewer_without_edit_rights_is_denied(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        resp = client.get(
            f"{BASE}/projects/{project.id}/grade-scale/drift",
            headers=_headers(auth_headers, test_org, role="annotator"),
        )
        assert resp.status_code == 403


@pytest.mark.integration
class TestGradeScaleRecompute:
    def test_rewrites_the_stale_rows_and_is_idempotent(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(
            test_db, test_users, test_org, {"grade_scale": _percent_key("uebungsklausur")}
        )
        rubric_id = _uid()
        stale = _seed_graded_row(
            test_db, project, test_users[0].id,
            metrics=_rubric_metrics(10, rubric_id, siblings=True),
            rubric=TaskRubric(id=rubric_id, criteria={}, total_points=100.0, status="active"),
        )
        current = _seed_graded_row(
            test_db, project, test_users[0].id,
            metrics=_rubric_metrics(12, _uid(), source="project"),
        )
        untouched = _seed_graded_row(
            test_db, project, test_users[0].id, metrics=_ungraded_metrics(), passed=False
        )
        stale_id, current_id, untouched_id = stale.id, current.id, untouched.id
        current_before = copy.deepcopy(current.metrics)
        untouched_before = copy.deepcopy(untouched.metrics)

        resp = client.post(
            f"{BASE}/projects/{project.id}/grade-scale/recompute",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"updated": 1, "scanned": 2}

        rewritten = _reload(test_db, stale_id).metrics
        details = rewritten["llm_judge_rubric"]["details"]
        assert details["grade_points"] == 12
        assert details["passed"] is True
        assert details["grade_scale_source"] == "project"
        # Siblings follow; evidence does not move.
        assert rewritten["llm_judge_rubric_grade_points"] == 12.0
        assert rewritten["llm_judge_rubric_passed"] == 1.0
        assert details["raw_output"] == "<verbatim>"
        assert details["total_score"] == 73.5

        # The already-correct row and the ungraded row come back unchanged.
        assert _reload(test_db, current_id).metrics == current_before
        assert _reload(test_db, untouched_id).metrics == untouched_before

        # Idempotent: nothing left to do, and the drift line agrees.
        again = client.post(
            f"{BASE}/projects/{project.id}/grade-scale/recompute",
            headers=_headers(auth_headers, test_org),
        )
        assert again.json() == {"updated": 0, "scanned": 2}
        drift = client.get(
            f"{BASE}/projects/{project.id}/grade-scale/drift",
            headers=_headers(auth_headers, test_org),
        )
        assert drift.json()["stale"] == 0

    def test_the_row_level_pass_flag_follows_a_failing_grade(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """22.5 raw of 100 is Notenpunkt 1 on the standard key — below the
        pass mark, so the row flips to failed."""
        project = _seed_project(
            test_db, test_users, test_org, {"grade_scale": _percent_key("standard")}
        )
        record = _seed_graded_row(
            test_db, project, test_users[0].id,
            metrics=_falloesung_metrics(9, raw_score=22.5),
            passed=True,
        )
        record_id = record.id
        resp = client.post(
            f"{BASE}/projects/{project.id}/grade-scale/recompute",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.json() == {"updated": 1, "scanned": 1}
        reloaded = _reload(test_db, record_id)
        assert reloaded.passed is False
        blob = reloaded.metrics["llm_judge_falloesung"]["details"]
        assert blob["grade_points"] == 1
        assert blob["passed"] is False
        # The model's own answer is evidence and is never rewritten.
        assert blob["judge_response"] == {"score": 22.5, "reasoning": "Aufbau ok."}

    def test_missing_project_404(self, client, auth_headers, test_org):
        resp = client.post(
            f"{BASE}/projects/{_uid()}/grade-scale/recompute",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_a_viewer_without_edit_rights_cannot_rewrite_grades(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(
            test_db, test_users, test_org, {"grade_scale": _percent_key("uebungsklausur")}
        )
        record = _seed_graded_row(
            test_db, project, test_users[0].id, metrics=_rubric_metrics(10, _uid())
        )
        record_id = record.id
        resp = client.post(
            f"{BASE}/projects/{project.id}/grade-scale/recompute",
            headers=_headers(auth_headers, test_org, role="annotator"),
        )
        assert resp.status_code == 403
        assert _reload(test_db, record_id).metrics["llm_judge_rubric"]["details"][
            "grade_points"
        ] == 10


@pytest.mark.integration
class TestGradeScaleAudit:
    """The key's audit trail (contract v5) as the two endpoints expose it.

    The trail itself is written by the eval-config PUT (and by the extended
    exam router, through the same shared helper). Here: the drift read
    projects the newest entry with a server-resolved name, and a recompute
    stamps how many grades it moved onto it.
    """

    def _save_key(self, client, auth_headers, test_org, project_id, preset, role="admin"):
        return client.put(
            f"{BASE}/projects/{project_id}/evaluation-config",
            json={"grade_scale": _percent_key(preset)},
            headers=_headers(auth_headers, test_org, role=role),
        )

    def test_an_untouched_project_reports_no_last_change(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(
            test_db, test_users, test_org, {"grade_scale": _percent_key("standard")}
        )
        body = client.get(
            f"{BASE}/projects/{project.id}/grade-scale/drift",
            headers=_headers(auth_headers, test_org),
        ).json()
        assert body["last_change"] is None

    def test_saving_the_key_is_recorded_and_read_back_with_a_name(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        assert self._save_key(
            client, auth_headers, test_org, project.id, "uebungsklausur"
        ).status_code == 200

        body = client.get(
            f"{BASE}/projects/{project.id}/grade-scale/drift",
            headers=_headers(auth_headers, test_org),
        ).json()
        change = body["last_change"]
        assert change["changed_by"] == test_users[0].id
        # Resolved server-side from the users table, not echoed as an id.
        assert change["changed_by_name"] == "Test Admin"
        assert change["from_preset"] is None
        assert change["to_preset"] == "uebungsklausur"
        assert change["recomputed"] is None
        assert change["changed_at"]

    def test_the_stored_trail_carries_the_full_scales(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        self._save_key(client, auth_headers, test_org, project.id, "standard")
        self._save_key(client, auth_headers, test_org, project.id, "uebungsklausur")

        test_db.expire_all()
        history = (
            test_db.query(Project)
            .filter(Project.id == project.id)
            .first()
            .evaluation_config["grade_scale_history"]
        )
        assert len(history) == 2
        assert history[0]["from"] is None
        assert history[0]["to"]["preset"] == "standard"
        assert history[1]["from"]["preset"] == "standard"
        assert history[1]["to"]["preset"] == "uebungsklausur"

    def test_resaving_the_same_key_adds_nothing(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        self._save_key(client, auth_headers, test_org, project.id, "standard")
        self._save_key(client, auth_headers, test_org, project.id, "standard")
        # An unrelated eval-config save must not plant an entry either.
        client.put(
            f"{BASE}/projects/{project.id}/evaluation-config",
            json={"runs_per_task": 2},
            headers=_headers(auth_headers, test_org),
        )
        test_db.expire_all()
        config = (
            test_db.query(Project).filter(Project.id == project.id).first().evaluation_config
        )
        assert len(config["grade_scale_history"]) == 1
        assert config["runs_per_task"] == 2

    def test_a_client_cannot_rewrite_the_trail_through_the_put(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        self._save_key(client, auth_headers, test_org, project.id, "standard")
        client.put(
            f"{BASE}/projects/{project.id}/evaluation-config",
            json={
                "grade_scale_history": [
                    {"changed_at": "1999-01-01T00:00:00+00:00", "changed_by": "someone-else"}
                ]
            },
            headers=_headers(auth_headers, test_org),
        )
        test_db.expire_all()
        history = (
            test_db.query(Project)
            .filter(Project.id == project.id)
            .first()
            .evaluation_config["grade_scale_history"]
        )
        assert len(history) == 1
        assert history[0]["changed_by"] == test_users[0].id

    def test_a_recompute_stamps_how_many_grades_it_moved(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        rubric_id = _uid()
        _seed_graded_row(
            test_db, project, test_users[0].id,
            metrics=_rubric_metrics(12, rubric_id),
            rubric=TaskRubric(
                id=rubric_id, criteria={}, total_points=100.0, status="active"
            ),
        )
        # 73.5 / 100 is 12 Notenpunkte on the Übungsklausur key and 10 on the
        # standard one, so switching the key makes the stored row stale.
        self._save_key(client, auth_headers, test_org, project.id, "standard")

        resp = client.post(
            f"{BASE}/projects/{project.id}/grade-scale/recompute",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["updated"] == 1

        body = client.get(
            f"{BASE}/projects/{project.id}/grade-scale/drift",
            headers=_headers(auth_headers, test_org),
        ).json()
        assert body["stale"] == 0
        assert body["last_change"]["recomputed"] == 1

        # A second, idempotent run keeps the count it already recorded.
        client.post(
            f"{BASE}/projects/{project.id}/grade-scale/recompute",
            headers=_headers(auth_headers, test_org),
        )
        body = client.get(
            f"{BASE}/projects/{project.id}/grade-scale/drift",
            headers=_headers(auth_headers, test_org),
        ).json()
        assert body["last_change"]["recomputed"] == 1

    def test_a_recompute_without_any_key_change_stamps_nothing(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(
            test_db, test_users, test_org, {"grade_scale": _percent_key("standard")}
        )
        resp = client.post(
            f"{BASE}/projects/{project.id}/grade-scale/recompute",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        test_db.expire_all()
        config = (
            test_db.query(Project).filter(Project.id == project.id).first().evaluation_config
        )
        assert "grade_scale_history" not in config

    def test_a_deleted_actor_falls_back_to_the_raw_id(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        self._save_key(client, auth_headers, test_org, project.id, "standard")
        test_db.expire_all()
        row = test_db.query(Project).filter(Project.id == project.id).first()
        config = dict(row.evaluation_config)
        history = [dict(e) for e in config["grade_scale_history"]]
        history[-1]["changed_by"] = "gone-user-id"
        config["grade_scale_history"] = history
        row.evaluation_config = config
        test_db.commit()

        body = client.get(
            f"{BASE}/projects/{project.id}/grade-scale/drift",
            headers=_headers(auth_headers, test_org),
        ).json()
        assert body["last_change"]["changed_by"] == "gone-user-id"
        assert body["last_change"]["changed_by_name"] == "gone-user-id"

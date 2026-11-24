"""The comprehensive exports mark the score the teacher views show for each
method (``is_method_current``, shared/evaluation_methods.py
``teacher_current_rows``): the official config's current score, else the
current score of another config of the group, which carries the official
config it stands in for (``stands_in_for_config_id``)."""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation
from project_models import Annotation, Project, ProjectOrganization, Task
from routers.projects._export_stream import (
    stream_comprehensive_project_data_json,
    stream_export_ndjson,
)

CFG_A = "llm_judge_custom-a"
CFG_B = "llm_judge_custom-b"
T0 = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)
ANSWER = {"groups": {"score": {"config_ids": [CFG_A, CFG_B]}}}


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def grouped_project(test_db, test_users, test_org):
    """Two accounts answered one task. CFG_A (the default official config)
    graded the first answer twice (its first grading is history) and CFG_B
    graded both; the second answer has no CFG_A grading."""
    admin, other = test_users[0], test_users[1]
    project = Project(
        id=_uid(),
        title=f"Method marker {_uid()[:8]}",
        label_config='<View><Text name="text" value="$text"/>'
        '<TextArea name="loesung" toName="text"/></View>',
        created_by=admin.id,
        evaluation_config={
            "evaluation_configs": [
                {
                    "id": cid, "metric": "llm_judge_custom",
                    "prediction_fields": ["human:loesung"],
                    "reference_fields": ["task.musterloesung"],
                    "enabled": True,
                }
                for cid in (CFG_A, CFG_B)
            ]
        },
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(ProjectOrganization(
        id=_uid(), project_id=project.id, organization_id=test_org.id, assigned_by=admin.id,
    ))
    task = Task(
        id=_uid(), project_id=project.id, inner_id=1,
        data={"text": "Fall", "musterloesung": "M"}, created_by=admin.id,
    )
    test_db.add(task)
    test_db.flush()
    answers = {}
    for user in (admin, other):
        ann = Annotation(
            id=_uid(), task_id=task.id, project_id=project.id, completed_by=user.id,
            result=[{"from_name": "loesung", "to_name": "text", "type": "textarea",
                     "value": {"text": ["Antwort"]}}],
            was_cancelled=False,
        )
        test_db.add(ann)
        answers[user.id] = ann
    test_db.flush()
    run = EvaluationRun(
        id=_uid(), project_id=project.id, model_id="annotator:x",
        evaluation_type_ids=["llm_judge_custom"], metrics={}, status="completed",
        samples_evaluated=4, created_by=admin.id,
    )
    test_db.add(run)
    test_db.flush()
    rows = {}
    plan = [
        ("a1_old", admin.id, CFG_A, 0.7, T0),
        ("a1", admin.id, CFG_A, 0.9, T0 + timedelta(minutes=5)),
        ("b1", admin.id, CFG_B, 0.8, T0),
        ("b2", other.id, CFG_B, 0.6, T0),
    ]
    for index, (name, user_id, cid, score, created_at) in enumerate(plan):
        judge = EvaluationJudgeRun(
            id=_uid(), evaluation_id=run.id, judge_model_id="gpt-4o",
            run_index=index, status="completed",
        )
        test_db.add(judge)
        test_db.flush()
        row = TaskEvaluation(
            id=_uid(), evaluation_id=run.id, judge_run_id=judge.id, task_id=task.id,
            annotation_id=answers[user_id].id,
            field_name=f"{cid}|human:loesung|task.musterloesung", evaluation_config_id=cid,
            answer_type="text", ground_truth="M", prediction="Antwort",
            metrics={"llm_judge_custom": score}, passed=True, created_at=created_at,
        )
        test_db.add(row)
        rows[name] = row
    test_db.commit()
    return project, rows


def _records(db, project_id, fmt, method_answer):
    if fmt == "ndjson":
        body = "".join(stream_export_ndjson(db, project_id, method_answer=method_answer))
        records = [json.loads(line) for line in body.splitlines()]
        return [r for r in records if r.get("_type") == "task_evaluation"]
    body = "".join(
        stream_comprehensive_project_data_json(db, project_id, method_answer=method_answer)
    )
    return json.loads(body)["task_evaluations"]


@pytest.mark.integration
@pytest.mark.parametrize("fmt", ["comprehensive", "ndjson"])
class TestMethodCurrentMarker:
    def test_group_marks_the_official_score_and_the_stand_in(self, test_db, grouped_project, fmt):
        project, rows = grouped_project
        records = {r["id"]: r for r in _records(test_db, project.id, fmt, ANSWER)}
        name_of = {row.id: name for name, row in rows.items()}
        marks = {
            name_of[i]: (r["is_current"], r["is_method_current"], r["stands_in_for_config_id"])
            for i, r in records.items()
        }
        assert marks == {
            "a1_old": (False, False, None),
            "a1": (True, True, None),
            # Research data for the first answer: CFG_A has a score there.
            "b1": (True, False, None),
            # CFG_A never graded the second answer.
            "b2": (True, True, CFG_A),
        }

    def test_without_an_answer_every_config_is_its_own_method(
        self, test_db, grouped_project, fmt
    ):
        project, _rows = grouped_project
        records = _records(test_db, project.id, fmt, None)
        assert all(r["is_method_current"] == r["is_current"] for r in records)
        assert all(r["stands_in_for_config_id"] is None for r in records)

    def test_per_account_official_choice(self, test_db, grouped_project, fmt, test_users):
        project, rows = grouped_project
        answer = dict(ANSWER, official_by_user={test_users[0].id: {"score": CFG_B}})
        records = {r["id"]: r for r in _records(test_db, project.id, fmt, answer)}
        current = {name for name, row in rows.items() if records[row.id]["is_method_current"]}
        assert current == {"b1", "b2"}
        assert records[rows["b2"].id]["stands_in_for_config_id"] == CFG_A
        assert records[rows["b1"].id]["stands_in_for_config_id"] is None

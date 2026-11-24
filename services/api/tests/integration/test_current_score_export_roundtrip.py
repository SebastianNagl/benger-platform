"""The full exports mark each task evaluation current or superseded, and the
importer still reads files with and without the marker.

``is_current`` (shared/current_scores.py) is additive: True on the one
current row of each (subject, evaluation config, prediction field), False
on the history rows. The importer ignores it and the re-export recomputes it
from the imported rows, so a round trip keeps the same answer, and a file
written before the marker existed imports as before.
"""

import io
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
from routers.projects._import_stream import run_full_project_import

CFG = "llm_judge_custom-rt"
T0 = datetime(2026, 11, 21, 12, 54, tzinfo=timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def graded_project(test_db, test_users, test_org):
    admin = test_users[0]
    project = Project(
        id=_uid(),
        title=f"Current score RT {_uid()[:8]}",
        label_config='<View><Text name="text" value="$text"/>'
        '<TextArea name="loesung" toName="text"/></View>',
        created_by=admin.id,
        evaluation_config={
            "evaluation_configs": [
                {
                    "id": CFG, "metric": "llm_judge_custom",
                    "prediction_fields": ["human:loesung"],
                    "reference_fields": ["task.musterloesung", "task.bewertungsbogen"],
                    "enabled": True,
                }
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
        data={"text": "Fall", "musterloesung": "M", "bewertungsbogen": "B"},
        created_by=admin.id,
    )
    test_db.add(task)
    test_db.flush()
    ann = Annotation(
        id=_uid(), task_id=task.id, project_id=project.id, completed_by=admin.id,
        result=[{"from_name": "loesung", "to_name": "text", "type": "textarea",
                 "value": {"text": ["Antwort"]}}],
        was_cancelled=False,
    )
    test_db.add(ann)
    test_db.flush()

    rows = []
    for model_id, entries in (
        ("immediate", [("human:loesung", 0.75, T0)]),
        ("annotator:x", [
            (f"{CFG}|human:loesung|task.musterloesung", 0.82, T0 + timedelta(minutes=20)),
            (f"{CFG}|human:loesung|task.bewertungsbogen", 0.80, T0 + timedelta(minutes=21)),
        ]),
    ):
        run = EvaluationRun(
            id=_uid(), project_id=project.id, model_id=model_id,
            evaluation_type_ids=["llm_judge_custom"], metrics={}, status="completed",
            samples_evaluated=len(entries), created_by=admin.id,
        )
        test_db.add(run)
        test_db.flush()
        for index, (field_name, score, created_at) in enumerate(entries):
            judge = EvaluationJudgeRun(
                id=_uid(), evaluation_id=run.id, judge_model_id="gpt-4o",
                run_index=index, status="completed",
            )
            test_db.add(judge)
            test_db.flush()
            row = TaskEvaluation(
                id=_uid(), evaluation_id=run.id, judge_run_id=judge.id, task_id=task.id,
                annotation_id=ann.id, field_name=field_name, evaluation_config_id=CFG,
                answer_type="text", ground_truth="M", prediction="Antwort",
                metrics={"llm_judge_custom": score}, passed=True, created_at=created_at,
            )
            test_db.add(row)
            rows.append(row)
    test_db.commit()
    return project, admin, rows


def _records(body: str, fmt: str):
    if fmt == "ndjson":
        return [
            r for r in (json.loads(line) for line in body.splitlines())
            if r.get("_type") == "task_evaluation"
        ]
    return json.loads(body)["task_evaluations"]


def _export(db, project_id, fmt):
    if fmt == "ndjson":
        return "".join(stream_export_ndjson(db, project_id))
    return "".join(stream_comprehensive_project_data_json(db, project_id))


def _marks(records):
    return {r["field_name"]: r["is_current"] for r in records}


EXPECTED = {
    "human:loesung": False,
    f"{CFG}|human:loesung|task.musterloesung": False,
    f"{CFG}|human:loesung|task.bewertungsbogen": True,
}


@pytest.mark.integration
@pytest.mark.parametrize("fmt", ["comprehensive", "ndjson"])
class TestCurrentScoreRoundTrip:
    def test_export_marks_current_and_superseded(self, test_db, graded_project, fmt):
        project, _admin, _rows = graded_project
        records = _records(_export(test_db, project.id, fmt), fmt)
        # Every row is still in the full backup; one per cell is current.
        assert len(records) == 3
        assert _marks(records) == EXPECTED

    def test_round_trip_keeps_rows_and_marker(self, test_db, graded_project, fmt):
        project, admin, _rows = graded_project
        body = _export(test_db, project.id, fmt)
        new_pid = run_full_project_import(test_db, io.BytesIO(body.encode("utf-8")), admin.id)[
            "project_id"
        ]
        assert new_pid != project.id
        again = _records(_export(test_db, new_pid, fmt), fmt)
        assert _marks(again) == EXPECTED
        assert sorted(r["metrics"]["llm_judge_custom"] for r in again) == [0.75, 0.8, 0.82]

    def test_file_without_the_marker_still_imports(self, test_db, graded_project, fmt):
        project, admin, _rows = graded_project
        body = _export(test_db, project.id, fmt)
        if fmt == "ndjson":
            lines = []
            for line in body.splitlines():
                record = json.loads(line)
                record.pop("is_current", None)
                lines.append(json.dumps(record, ensure_ascii=False))
            old_body = "\n".join(lines) + "\n"
        else:
            doc = json.loads(body)
            for record in doc["task_evaluations"]:
                record.pop("is_current")
            old_body = json.dumps(doc, ensure_ascii=False)
        assert "is_current" not in old_body
        new_pid = run_full_project_import(
            test_db, io.BytesIO(old_body.encode("utf-8")), admin.id
        )["project_id"]
        task_ids = [t.id for t in test_db.query(Task).filter(Task.project_id == new_pid)]
        imported = test_db.query(TaskEvaluation).filter(TaskEvaluation.task_id.in_(task_ids)).count()
        assert imported == 3
        assert _marks(_records(_export(test_db, new_pid, fmt), fmt)) == EXPECTED

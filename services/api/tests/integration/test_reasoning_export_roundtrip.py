"""Model and judge reasoning survive project export and import.

``generations.reasoning`` (the model's reasoning beside its answer) and
``task_evaluations.raw_reasoning`` (the judge model's) are research data, so
every project export carries them and every importer restores them: the full
formats (NDJSON and comprehensive JSON, through ``run_full_project_import``)
and the nested task export (``stream_export_json``, through
``run_nested_import``). A generation without reasoning stays NULL.
"""

import io
import json
import uuid

import pytest

from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import Project, ProjectOrganization, Task
from routers.projects._export_stream import (
    stream_comprehensive_project_data_json,
    stream_export_ndjson,
)
from routers.projects._import_stream import run_full_project_import, run_nested_import
from export_stream import stream_export_json  # noqa: E402

MODEL_REASONING = "Erst die Anspruchsgrundlage § 433 Abs. 2 BGB, dann Einwendungen."
JUDGE_REASONING = "Die Antwort trifft den Kern; Abzug für fehlende Einwendungen."


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def reasoning_project(test_db, test_users, test_org):
    admin = test_users[0]
    project = Project(
        id=_uid(),
        title=f"Reasoning RT {_uid()[:8]}",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=admin.id,
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(ProjectOrganization(
        id=_uid(), project_id=project.id, organization_id=test_org.id, assigned_by=admin.id,
    ))

    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id="gpt-4o",
        evaluation_type_ids=["llm_judge_correctness"],
        metrics={"llm_judge_correctness": 0.75},
        status="completed",
        samples_evaluated=2,
        created_by=admin.id,
    )
    test_db.add(er)
    test_db.flush()
    judge = EvaluationJudgeRun(
        id=_uid(), evaluation_id=er.id, judge_model_id="gpt-4o", run_index=0, status="completed",
    )
    test_db.add(judge)
    test_db.flush()

    for i, (model_reasoning, judge_reasoning) in enumerate(
        [(MODEL_REASONING, JUDGE_REASONING), (None, None)]
    ):
        task = Task(
            id=_uid(), project_id=project.id, inner_id=i + 1,
            data={"text": f"Fall {i}"}, created_by=admin.id,
        )
        test_db.add(task)
        test_db.flush()
        rg = ResponseGeneration(
            id=_uid(), task_id=task.id, project_id=project.id, model_id="gpt-4o",
            status="completed", responses_generated=1, created_by=admin.id,
        )
        test_db.add(rg)
        test_db.flush()
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=task.id, model_id="gpt-4o", run_index=0,
            case_data=json.dumps(task.data), response_content=f"Antwort {i}",
            reasoning=model_reasoning, status="completed",
        )
        test_db.add(gen)
        test_db.flush()
        test_db.add(TaskEvaluation(
            id=_uid(), evaluation_id=er.id, judge_run_id=judge.id, task_id=task.id,
            generation_id=gen.id, field_name="answer", evaluation_config_id="jcfg",
            answer_type="text", ground_truth="ref", prediction=f"Antwort {i}",
            metrics={"llm_judge_correctness": 0.75}, passed=True,
            raw_output='{"score": 0.75}', raw_reasoning=judge_reasoning,
        ))
    test_db.commit()
    return project, admin


def _imported(test_db, project_id):
    task_ids = [t.id for t in test_db.query(Task).filter(Task.project_id == project_id)]
    gens = test_db.query(Generation).filter(Generation.task_id.in_(task_ids)).all()
    tes = test_db.query(TaskEvaluation).filter(TaskEvaluation.task_id.in_(task_ids)).all()
    return (
        {g.response_content: g.reasoning for g in gens},
        {te.prediction: te.raw_reasoning for te in tes},
    )


EXPECTED_GENERATIONS = {"Antwort 0": MODEL_REASONING, "Antwort 1": None}
EXPECTED_EVALUATIONS = {"Antwort 0": JUDGE_REASONING, "Antwort 1": None}


@pytest.mark.integration
class TestReasoningRoundTrip:
    @pytest.mark.parametrize("fmt", ["ndjson", "comprehensive"])
    def test_full_export_import(self, test_db, reasoning_project, fmt):
        project, admin = reasoning_project
        if fmt == "ndjson":
            body = "".join(stream_export_ndjson(test_db, project.id))
            records = [json.loads(line) for line in body.splitlines()]
            gen_records = [r for r in records if r.get("_type") == "generation"]
            te_records = [r for r in records if r.get("_type") == "task_evaluation"]
        else:
            body = "".join(stream_comprehensive_project_data_json(test_db, project.id))
            doc = json.loads(body)
            gen_records = doc["generations"]
            te_records = doc["task_evaluations"]
        # The export itself carries both fields, None where there is none.
        assert {g["response_content"]: g["reasoning"] for g in gen_records} == EXPECTED_GENERATIONS
        assert {t["prediction"]: t["raw_reasoning"] for t in te_records} == EXPECTED_EVALUATIONS

        new_pid = run_full_project_import(test_db, io.BytesIO(body.encode("utf-8")), admin.id)[
            "project_id"
        ]
        assert new_pid != project.id
        gens, tes = _imported(test_db, new_pid)
        assert gens == EXPECTED_GENERATIONS
        assert tes == EXPECTED_EVALUATIONS

    def test_nested_task_export_import(self, test_db, test_users, test_org, reasoning_project):
        project, admin = reasoning_project
        body = "".join(stream_export_json(test_db, project.id, None, {"project_id": project.id}))
        doc = json.loads(body)
        exported = {
            g["response_content"]: g["reasoning"]
            for task in doc["tasks"]
            for g in task.get("generations", [])
        }
        assert exported == EXPECTED_GENERATIONS

        target = Project(
            id=_uid(), title=f"Reasoning target {_uid()[:8]}",
            label_config=project.label_config, created_by=admin.id,
        )
        test_db.add(target)
        test_db.flush()
        test_db.add(ProjectOrganization(
            id=_uid(), project_id=target.id, organization_id=test_org.id, assigned_by=admin.id,
        ))
        test_db.commit()

        # The nested importer reads the task list under ``data`` (the shape
        # the Projektdaten import sends); the other top-level blocks pass as is.
        payload = {k: v for k, v in doc.items() if k != "tasks"}
        payload["data"] = doc["tasks"]
        run_nested_import(
            test_db, target.id, io.BytesIO(json.dumps(payload).encode("utf-8")), admin.id
        )
        gens, tes = _imported(test_db, target.id)
        assert gens == EXPECTED_GENERATIONS
        assert tes == EXPECTED_EVALUATIONS

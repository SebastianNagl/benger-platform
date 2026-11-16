"""POST /api/admin/evaluation-runs/relabel: stored runs labelled with the
models their rows graded (routers/evaluation_run_relabel.py).

Runs that finished before the worker labelled runs from their rows say
"unknown" although they graded one model, or name the project's most common
model although they graded several or another one. The route applies the
finalization rule (``label_run_from_rows``) to them, keeps what it replaced
in ``eval_metadata["relabel_history"]`` and can revert it. Requests run
through the real app, key gate and superadmin check.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import Project, Task

URL = "/api/admin/evaluation-runs/relabel"
T0 = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def world(test_db, test_users):
    """A project with two tasks and answers of two models, plus a run maker."""
    admin = test_users[0]
    project = Project(
        id=_uid(),
        title="ZJS Fälle",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=admin.id,
    )
    test_db.add(project)
    test_db.flush()
    gens = {"model-a": [], "model-b": []}
    for i in range(2):
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"Fall {i}"},
            created_by=admin.id,
        )
        test_db.add(task)
        test_db.flush()
        for model in gens:
            job = ResponseGeneration(
                id=_uid(),
                project_id=project.id,
                task_id=task.id,
                model_id=model,
                status="completed",
                created_by=admin.id,
            )
            test_db.add(job)
            test_db.flush()
            gen = Generation(
                id=_uid(),
                generation_id=job.id,
                task_id=task.id,
                model_id=model,
                case_data="{}",
                response_content=f"{model} answer {i}",
                status="completed",
            )
            test_db.add(gen)
            gens[model].append(gen)
    test_db.flush()

    def make_run(label, graded, *, status="completed", eval_metadata=None, minutes=0):
        run = EvaluationRun(
            id=_uid(),
            project_id=project.id,
            model_id=label,
            evaluation_type_ids=["bleu"],
            metrics={"bleu": 0.4},
            eval_metadata=eval_metadata
            if eval_metadata is not None
            else {"model_ids": ["model-a", "model-b"], "evaluated_model_id": label},
            status=status,
            created_by=admin.id,
            created_at=T0 + timedelta(minutes=minutes),
        )
        test_db.add(run)
        test_db.flush()
        judge_run = EvaluationJudgeRun(
            id=_uid(),
            evaluation_id=run.id,
            judge_model_id=None,
            run_index=0,
            status="completed",
        )
        test_db.add(judge_run)
        test_db.flush()
        for model, count in graded.items():
            for gen in gens[model][:count]:
                test_db.add(
                    TaskEvaluation(
                        id=_uid(),
                        evaluation_id=run.id,
                        judge_run_id=judge_run.id,
                        task_id=gen.task_id,
                        generation_id=gen.id,
                        field_name="answer",
                        answer_type="text",
                        ground_truth="expected",
                        prediction=gen.response_content,
                        metrics={"bleu": 0.4},
                        passed=False,
                    )
                )
        test_db.commit()
        return run

    return {"project": project, "admin": admin, "make_run": make_run}


def _post(client, headers, **body):
    resp = client.post(URL, json=body, headers=headers["admin"])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _by_run(payload):
    return {r["run_id"]: r for r in payload["results"]}


def _reload(db, run):
    db.expire_all()
    return db.get(EvaluationRun, run.id)


@pytest.mark.integration
class TestRelabelEvaluationRuns:
    def test_dry_run_lists_old_and_new_label_and_writes_nothing(
        self, client, test_db, auth_headers, world
    ):
        make = world["make_run"]
        unknown_one = make("unknown", {"model-a": 2})
        common_several = make("model-a", {"model-a": 1, "model-b": 2}, minutes=1)
        before = [
            (r.model_id, dict(r.eval_metadata)) for r in (unknown_one, common_several)
        ]

        payload = _post(
            client, auth_headers, project_id=world["project"].id, dry_run=True
        )

        assert payload["dry_run"] is True
        assert payload["changed"] == 2
        results = _by_run(payload)
        assert results[unknown_one.id]["before"]["model_id"] == "unknown"
        assert results[unknown_one.id]["after"] == {
            "model_id": "model-a",
            "evaluated_model_ids": ["model-a"],
            "evaluated_model_id": "model-a",
        }
        assert results[common_several.id]["before"]["model_id"] == "model-a"
        assert results[common_several.id]["after"] == {
            "model_id": "unknown",
            "evaluated_model_ids": ["model-b", "model-a"],
            "evaluated_model_id": "unknown",
        }
        assert results[common_several.id]["graded_rows"] == {"model-b": 2, "model-a": 1}
        after = [
            (r.model_id, r.eval_metadata)
            for r in (_reload(test_db, unknown_one), _reload(test_db, common_several))
        ]
        assert after == before

    def test_dry_run_is_the_default(self, client, test_db, auth_headers, world):
        run = world["make_run"]("unknown", {"model-b": 1})
        payload = _post(client, auth_headers, run_ids=[run.id])
        assert payload["dry_run"] is True and payload["changed"] == 1
        assert _reload(test_db, run).model_id == "unknown"

    def test_apply_relabels_and_keeps_the_previous_label(
        self, client, test_db, auth_headers, world
    ):
        make = world["make_run"]
        other_model = make("model-a", {"model-b": 2})
        meta_before = dict(other_model.eval_metadata)

        payload = _post(client, auth_headers, run_ids=[other_model.id], dry_run=False)

        assert payload["changed"] == 1
        run = _reload(test_db, other_model)
        assert run.model_id == "model-b"
        assert run.eval_metadata["evaluated_model_ids"] == ["model-b"]
        assert run.eval_metadata["evaluated_model_id"] == "model-b"
        assert run.eval_metadata["model_ids"] == ["model-a", "model-b"]
        (entry,) = run.eval_metadata["relabel_history"]
        assert entry["relabeled_by"] == world["admin"].id
        assert datetime.fromisoformat(entry["relabeled_at"]).tzinfo is not None
        assert entry["superseded"] == {
            "model_id": "model-a",
            "eval_metadata": meta_before,
        }
        assert entry["applied"]["model_id"] == "model-b"

        again = _post(client, auth_headers, run_ids=[other_model.id], dry_run=False)
        assert again["changed"] == 0 and again["unchanged"] == 1
        assert len(_reload(test_db, other_model).eval_metadata["relabel_history"]) == 1

    def test_revert_restores_the_previous_label_and_metadata(
        self, client, test_db, auth_headers, world
    ):
        run = world["make_run"]("model-a", {"model-a": 1, "model-b": 1})
        original = (run.model_id, dict(run.eval_metadata))
        _post(client, auth_headers, run_ids=[run.id], dry_run=False)
        assert _reload(test_db, run).model_id == "unknown"

        preview = _post(
            client, auth_headers, run_ids=[run.id], revert=True, dry_run=True
        )
        assert preview["changed"] == 1
        assert _by_run(preview)[run.id]["after"]["model_id"] == "model-a"
        assert _reload(test_db, run).model_id == "unknown"

        reverted = _post(
            client, auth_headers, run_ids=[run.id], revert=True, dry_run=False
        )
        assert reverted["changed"] == 1
        restored = _reload(test_db, run)
        assert (restored.model_id, restored.eval_metadata) == original

        nothing = _post(
            client, auth_headers, run_ids=[run.id], revert=True, dry_run=False
        )
        assert nothing["changed"] == 0 and nothing["skipped"] == 1

    def test_revert_leaves_a_run_changed_after_its_relabel(
        self, client, test_db, auth_headers, world
    ):
        run = world["make_run"]("unknown", {"model-a": 1})
        _post(client, auth_headers, run_ids=[run.id], dry_run=False)
        stored = _reload(test_db, run)
        stored.model_id = "model-x"
        test_db.commit()

        payload = _post(
            client, auth_headers, run_ids=[run.id], revert=True, dry_run=False
        )
        assert payload["skipped"] == 1
        assert _reload(test_db, run).model_id == "model-x"

    def test_runs_without_graded_generations_are_left_alone(
        self, client, test_db, auth_headers, world
    ):
        make = world["make_run"]
        answers_only = make(
            "unknown", {}, eval_metadata={"evaluation_type": "evaluation"}
        )
        running = make("unknown", {"model-a": 1}, status="running", minutes=1)
        human = make("human", {"model-a": 1}, minutes=2)
        immediate = make("immediate", {}, minutes=3)
        snapshot = {
            r.id: (r.model_id, dict(r.eval_metadata))
            for r in (answers_only, running, human, immediate)
        }

        payload = _post(
            client, auth_headers, project_id=world["project"].id, dry_run=False
        )

        results = _by_run(payload)
        assert results[answers_only.id]["outcome"] == "no_graded_generations"
        assert results[running.id]["outcome"] == "skipped"
        assert results[human.id]["outcome"] == "skipped"
        assert results[immediate.id]["outcome"] == "skipped"
        assert payload["changed"] == 0
        for run_id, (label, meta) in snapshot.items():
            stored = _reload(test_db, test_db.get(EvaluationRun, run_id))
            assert (stored.model_id, stored.eval_metadata) == (label, meta)

    def test_run_ids_outside_the_project_are_not_found(
        self, client, test_db, auth_headers, world
    ):
        run = world["make_run"]("unknown", {"model-a": 1})
        payload = _post(
            client,
            auth_headers,
            project_id="another-project",
            run_ids=[run.id, "no-such-run"],
        )
        assert payload["not_found"] == 2 and payload["changed"] == 0

    def test_needs_a_scope(self, client, auth_headers, world):
        resp = client.post(URL, json={"dry_run": True}, headers=auth_headers["admin"])
        assert resp.status_code == 422

    def test_superadmin_only(self, client, auth_headers, world):
        resp = client.post(
            URL,
            json={"project_id": world["project"].id},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 403

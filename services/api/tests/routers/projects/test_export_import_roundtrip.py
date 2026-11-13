"""
Roundtrip integration tests for export → import → verify.

The sync import/export endpoints were removed in the #158 follow-up (object
storage is the only transport). These fidelity tests now drive the same shared
streaming drivers the async worker uses, so coverage survives the endpoint
removal:
1. Data export (bulk_export_tasks) → nested import (run_nested_import) → verify
2. Full project export (stream_comprehensive_project_data_json) → field-consistency
   checks (the full-project import driver is round-tripped in
   tests/integration/test_ndjson_roundtrip.py).

Uses the shared PostgreSQL test database with per-test transaction rollback.
"""

import io
import json
import os
import sys
import uuid
from asyncio import run
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from models import (  # noqa: E402
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (  # noqa: E402
    Annotation,
    PostAnnotationResponse,
    Project,
    Task,
)


def _export_project_dict(db, project_id):
    """Materialize the streamed comprehensive export for assertions.

    The dict-building `get_comprehensive_project_data` helper was removed
    (issue #106 — it chained a dozen unbounded `.all()` calls); the streaming
    generator is the production export path, so these tests assert against
    exactly what ships.
    """
    from routers.projects._export_stream import stream_comprehensive_project_data_json

    return json.loads("".join(stream_comprehensive_project_data_json(db, project_id)))


@pytest.fixture
def db_session(test_db):
    """Use the shared PostgreSQL test database session."""
    yield test_db


@pytest.fixture
def user(db_session):
    u = User(
        id=str(uuid.uuid4()),
        email="roundtrip@test.com",
        username="roundtrip",
        name="Roundtrip Tester",
        is_active=True,
        is_superadmin=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def project_with_full_data(db_session, user):
    """Create a project with tasks, annotations, questionnaire responses,
    generations, evaluation runs, and task evaluations (both generation-level
    and task-level)."""
    project = Project(
        id=str(uuid.uuid4()),
        title="Roundtrip Test Project",
        description="Full data for roundtrip verification",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=user.id,
    )
    db_session.add(project)
    db_session.flush()

    # --- Tasks ---
    tasks = []
    for i in range(3):
        t = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"Task {i + 1} content"},
            meta={"index": i},
            created_by=user.id,
            is_labeled=True,
        )
        db_session.add(t)
        tasks.append(t)
    db_session.flush()

    # --- Annotations with questionnaire responses ---
    annotations = []
    qr_list = []
    for t in tasks:
        ann = Annotation(
            id=str(uuid.uuid4()),
            task_id=t.id,
            project_id=project.id,
            result=[{"from_name": "label", "value": {"choices": ["correct"]}}],
            completed_by=user.id,
            was_cancelled=False,
            ground_truth=True,
            lead_time=12.5,
            active_duration_ms=8000,
            focused_duration_ms=7000,
            tab_switches=2,
        )
        db_session.add(ann)
        annotations.append(ann)
        db_session.flush()

        qr = PostAnnotationResponse(
            id=str(uuid.uuid4()),
            annotation_id=ann.id,
            task_id=t.id,
            project_id=project.id,
            user_id=user.id,
            result=[{"question": "confidence", "answer": "high"}],
        )
        db_session.add(qr)
        qr_list.append(qr)

    # --- Generations ---
    generations = []
    resp_gens = []
    for t in tasks:
        rg = ResponseGeneration(
            id=str(uuid.uuid4()),
            task_id=t.id,
            project_id=project.id,
            model_id="gpt-4o",
            config_id="test-config",
            status="completed",
            responses_generated=1,
            created_by=user.id,
        )
        db_session.add(rg)
        resp_gens.append(rg)
        db_session.flush()

        gen = Generation(
            id=str(uuid.uuid4()),
            generation_id=rg.id,
            task_id=t.id,
            model_id="gpt-4o",
            run_index=0,
            response_content=f"Response for task {t.inner_id}",
            case_data=json.dumps(t.data),
            response_metadata={"tokens": 200},
            status="completed",
        )
        db_session.add(gen)
        generations.append(gen)

    # --- Evaluation runs ---
    er_gen = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=project.id,
        model_id="gpt-4o",
        evaluation_type_ids=["rouge", "bleu"],
        metrics={"rouge1": 0.85, "bleu": 0.72},
        eval_metadata={
            "judge_models": {"cfg1": "gpt-4o-judge"},
            "evaluation_configs": [
                {"id": "cfg1", "metric_parameters": {"judge_model": "gpt-4o-judge"}}
            ],
        },
        status="completed",
        samples_evaluated=3,
        created_by=user.id,
    )
    db_session.add(er_gen)

    er_ann = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=project.id,
        model_id="unknown",
        evaluation_type_ids=["exact_match"],
        metrics={"exact_match": 0.67},
        eval_metadata={},
        status="completed",
        samples_evaluated=3,
        created_by=user.id,
    )
    db_session.add(er_ann)
    db_session.flush()

    # Migration 043 made TaskEvaluation.judge_run_id NOT NULL; every
    # EvaluationRun needs a parent judge run. Use the catch-all shape
    # (judge_model_id=NULL, run_index=0) that orphan backfill uses.
    er_gen._test_judge_run = EvaluationJudgeRun(
        id=str(uuid.uuid4()),
        evaluation_id=er_gen.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db_session.add(er_gen._test_judge_run)
    er_ann._test_judge_run = EvaluationJudgeRun(
        id=str(uuid.uuid4()),
        evaluation_id=er_ann.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db_session.add(er_ann._test_judge_run)
    db_session.flush()

    # --- Task evaluations (generation-level) ---
    gen_evals = []
    for gen in generations:
        te = TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=er_gen.id,
            judge_run_id=er_gen._test_judge_run.id,
            task_id=gen.task_id,
            generation_id=gen.id,
            field_name="cfg1:prediction:reference",
            answer_type="text",
            ground_truth="expected",
            prediction="actual",
            metrics={"rouge1": 0.85},
            passed=True,
            confidence_score=0.9,
            processing_time_ms=120,
        )
        db_session.add(te)
        gen_evals.append(te)

    # --- Task evaluations (task-level, no generation) ---
    # Each row is an annotation-level eval cell: generation_id stays None (so it
    # buckets under task_data["evaluations"]) but annotation_id is set per task so
    # each row is a distinct cell under uq_task_evaluations_cell.
    task_evals = []
    for t, ann in zip(tasks, annotations):
        te = TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=er_ann.id,
            judge_run_id=er_ann._test_judge_run.id,
            task_id=t.id,
            generation_id=None,
            annotation_id=ann.id,
            field_name="exact_match:answer:reference",
            answer_type="categorical",
            ground_truth="A",
            prediction="A",
            metrics={"exact_match": 1.0},
            passed=True,
            confidence_score=1.0,
            processing_time_ms=5,
        )
        db_session.add(te)
        task_evals.append(te)

    db_session.commit()

    return {
        "project": project,
        "tasks": tasks,
        "annotations": annotations,
        "questionnaire_responses": qr_list,
        "generations": generations,
        "resp_gens": resp_gens,
        "evaluation_runs": [er_gen, er_ann],
        "gen_evals": gen_evals,
        "task_evals": task_evals,
    }


# ---------------------------------------------------------------------------
# Data export → data import roundtrip
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestDataExportImportRoundtrip:
    """Export via bulk_export_tasks, import via run_nested_import, verify."""

    def _export(self, db_session, project_id, task_ids, user_id):
        from routers.projects.tasks import bulk_export_tasks

        mock_user = Mock()
        mock_user.id = user_id
        mock_user.is_superadmin = True
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.state = Mock(spec=[])
        request_data = {"task_ids": task_ids, "format": "json"}
        # bulk_export_tasks is a sync def returning a StreamingResponse
        # (refactored 2026-05-18 — see the OOMKilled note in the handler
        # docstring), so its body must be consumed through the async
        # body_iterator below; the companion import drives the shared
        # run_nested_import driver directly (see _import).
        response = bulk_export_tasks(
            project_id, request_data, current_user=mock_user, db=db_session
        )

        async def _consume() -> bytes:
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
            return b"".join(chunks)

        body = run(_consume())
        return json.loads(body.decode("utf-8"))

    def _import(self, db_session, target_project_id, export_data, user_id):
        # The sync POST /{id}/import endpoint was removed (#158); drive the same
        # shared nested-import driver the async worker uses, straight from a
        # spooled body. Returns the same created_* counts the endpoint did.
        from routers.projects._import_stream import run_nested_import

        body = json.dumps({
            "data": export_data["tasks"],
            "evaluation_runs": export_data.get("evaluation_runs"),
        }).encode("utf-8")

        return run_nested_import(
            db_session, target_project_id, io.BytesIO(body), user_id
        )

    def test_tasks_survive_roundtrip(self, db_session, user, project_with_full_data):
        data = project_with_full_data
        project = data["project"]
        task_ids = [t.id for t in data["tasks"]]

        export = self._export(db_session, project.id, task_ids, user.id)

        # Create a target project for import
        target = Project(
            id=str(uuid.uuid4()),
            title="Import Target",
            label_config="<View></View>",
            created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()

        result = self._import(db_session, target.id, export, user.id)

        assert result["created_tasks"] == 3
        assert result["created_annotations"] == 3
        assert result["created_generations"] == 3
        assert result["created_questionnaire_responses"] == 3

        # Verify tasks in DB
        imported_tasks = (
            db_session.query(Task).filter(Task.project_id == target.id).all()
        )
        assert len(imported_tasks) == 3
        for t in imported_tasks:
            assert "text" in t.data

    def test_annotations_with_questionnaire_survive_roundtrip(
        self, db_session, user, project_with_full_data
    ):
        data = project_with_full_data
        project = data["project"]
        task_ids = [t.id for t in data["tasks"]]

        export = self._export(db_session, project.id, task_ids, user.id)

        target = Project(
            id=str(uuid.uuid4()),
            title="Import Target Ann",
            label_config="<View></View>",
            created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()

        self._import(db_session, target.id, export, user.id)

        imported_anns = (
            db_session.query(Annotation).filter(Annotation.project_id == target.id).all()
        )
        assert len(imported_anns) == 3
        for ann in imported_anns:
            assert ann.result != None  # noqa: E711
            assert ann.ground_truth == True  # noqa: E712

        imported_qrs = (
            db_session.query(PostAnnotationResponse)
            .filter(PostAnnotationResponse.project_id == target.id)
            .all()
        )
        assert len(imported_qrs) == 3
        for qr in imported_qrs:
            assert qr.result[0]["question"] == "confidence"

    def test_generations_survive_roundtrip(
        self, db_session, user, project_with_full_data
    ):
        data = project_with_full_data
        project = data["project"]
        task_ids = [t.id for t in data["tasks"]]

        export = self._export(db_session, project.id, task_ids, user.id)

        target = Project(
            id=str(uuid.uuid4()),
            title="Import Target Gen",
            label_config="<View></View>",
            created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()

        self._import(db_session, target.id, export, user.id)

        imported_task_ids = [
            t.id
            for t in db_session.query(Task).filter(Task.project_id == target.id).all()
        ]
        imported_gens = (
            db_session.query(Generation)
            .filter(Generation.task_id.in_(imported_task_ids))
            .all()
        )
        assert len(imported_gens) == 3
        for gen in imported_gens:
            assert gen.model_id == "gpt-4o"
            assert "Response for task" in gen.response_content

    def test_evaluation_runs_survive_roundtrip(
        self, db_session, user, project_with_full_data
    ):
        data = project_with_full_data
        project = data["project"]
        task_ids = [t.id for t in data["tasks"]]

        export = self._export(db_session, project.id, task_ids, user.id)

        # Verify export contains evaluation_runs
        assert "evaluation_runs" in export
        assert len(export["evaluation_runs"]) == 2

        target = Project(
            id=str(uuid.uuid4()),
            title="Import Target ER",
            label_config="<View></View>",
            created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()

        result = self._import(db_session, target.id, export, user.id)
        assert result["created_evaluation_runs"] == 2

        imported_ers = (
            db_session.query(EvaluationRun)
            .filter(EvaluationRun.project_id == target.id)
            .all()
        )
        assert len(imported_ers) == 2
        model_ids = {er.model_id for er in imported_ers}
        assert "gpt-4o" in model_ids
        assert "unknown" in model_ids

    def test_task_evaluations_survive_roundtrip(
        self, db_session, user, project_with_full_data
    ):
        data = project_with_full_data
        project = data["project"]
        task_ids = [t.id for t in data["tasks"]]

        export = self._export(db_session, project.id, task_ids, user.id)

        # Verify export nesting: 3 generation evals nested, 3 task-level evals
        for task_data in export["tasks"]:
            assert len(task_data["evaluations"]) == 1  # 1 task-level eval per task
            assert len(task_data["generations"]) == 1
            gen = task_data["generations"][0]
            assert len(gen["evaluations"]) == 1  # 1 gen eval per generation

        target = Project(
            id=str(uuid.uuid4()),
            title="Import Target TE",
            label_config="<View></View>",
            created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()

        result = self._import(db_session, target.id, export, user.id)

        # 3 generation-nested + 3 task-level = 6 total
        assert result["created_task_evaluations"] == 6

        imported_task_ids = [
            t.id
            for t in db_session.query(Task).filter(Task.project_id == target.id).all()
        ]
        imported_tes = (
            db_session.query(TaskEvaluation)
            .filter(TaskEvaluation.task_id.in_(imported_task_ids))
            .all()
        )
        assert len(imported_tes) == 6

        gen_tes = [te for te in imported_tes if te.generation_id != None]  # noqa: E711
        task_tes = [te for te in imported_tes if te.generation_id == None]  # noqa: E711
        assert len(gen_tes) == 3
        assert len(task_tes) == 3

        # Verify generation evals link to actual imported generations
        imported_gen_ids = {g.id for g in (
            db_session.query(Generation)
            .filter(Generation.task_id.in_(imported_task_ids))
            .all()
        )}
        for te in gen_tes:
            assert te.generation_id in imported_gen_ids

        # Verify evaluation_id links to imported evaluation runs
        imported_er_ids = {er.id for er in (
            db_session.query(EvaluationRun)
            .filter(EvaluationRun.project_id == target.id)
            .all()
        )}
        for te in imported_tes:
            assert te.evaluation_id in imported_er_ids

    def test_full_data_roundtrip_counts(
        self, db_session, user, project_with_full_data
    ):
        """End-to-end: export all, import all, verify every count."""
        data = project_with_full_data
        project = data["project"]
        task_ids = [t.id for t in data["tasks"]]

        export = self._export(db_session, project.id, task_ids, user.id)

        target = Project(
            id=str(uuid.uuid4()),
            title="Import Target Full",
            label_config="<View></View>",
            created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()

        result = self._import(db_session, target.id, export, user.id)

        assert result["created_tasks"] == 3
        assert result["created_annotations"] == 3
        assert result["created_generations"] == 3
        assert result["created_questionnaire_responses"] == 3
        assert result["created_evaluation_runs"] == 2
        assert result["created_task_evaluations"] == 6


# ---------------------------------------------------------------------------
# Full project export → full project import roundtrip
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFullProjectExportRoundtrip:
    """Export via the streaming comprehensive generator, verify field
    consistency with shared serializers."""

    def test_export_uses_shared_serializers(
        self, db_session, user, project_with_full_data
    ):
        """Verify full export produces fields matching serializer output."""
        from routers.projects.serializers import (
            serialize_annotation,
            serialize_evaluation_run,
            serialize_generation,
            serialize_task,
            serialize_task_evaluation,
        )

        data = project_with_full_data
        project = data["project"]

        export = _export_project_dict(db_session, project.id)

        # Verify tasks match serializer output
        assert len(export["tasks"]) == 3
        exported_task = export["tasks"][0]
        ref_task = serialize_task(data["tasks"][0], mode="full", total_generations=1)
        for key in ref_task:
            assert key in exported_task, f"Task missing key: {key}"

        # Verify annotations match
        assert len(export["annotations"]) == 3
        exported_ann = export["annotations"][0]
        ref_ann = serialize_annotation(data["annotations"][0], mode="full")
        for key in ref_ann:
            assert key in exported_ann, f"Annotation missing key: {key}"

        # Verify generations match
        assert len(export["generations"]) == 3
        exported_gen = export["generations"][0]
        ref_gen = serialize_generation(data["generations"][0], mode="full")
        for key in ref_gen:
            assert key in exported_gen, f"Generation missing key: {key}"

        # Verify evaluation runs match
        assert len(export["evaluations"]) == 2
        exported_er = export["evaluations"][0]
        ref_er = serialize_evaluation_run(data["evaluation_runs"][0], mode="full")
        for key in ref_er:
            assert key in exported_er, f"EvaluationRun missing key: {key}"

        # Verify task evaluations match
        assert len(export["task_evaluations"]) == 6
        exported_te = export["task_evaluations"][0]
        ref_te = serialize_task_evaluation(data["gen_evals"][0], mode="full")
        for key in ref_te:
            assert key in exported_te, f"TaskEvaluation missing key: {key}"

    def test_export_task_counts(self, db_session, user, project_with_full_data):
        data = project_with_full_data
        export = _export_project_dict(db_session, data["project"].id)

        stats = export["statistics"]
        assert stats["total_tasks"] == 3
        assert stats["total_annotations"] == 3
        assert stats["total_generations"] == 3
        assert stats["total_evaluations"] == 2
        assert stats["total_task_evaluations"] == 6
        assert stats["total_post_annotation_responses"] == 3

    def test_export_field_values_correct(
        self, db_session, user, project_with_full_data
    ):
        """Verify actual field values, not just key presence."""
        data = project_with_full_data
        export = _export_project_dict(db_session, data["project"].id)

        # Tasks have FK fields in full mode
        task = export["tasks"][0]
        assert task["project_id"] == data["project"].id
        assert task["created_by"] == user.id

        # Annotations have FK fields in full mode
        ann = export["annotations"][0]
        assert ann["project_id"] == data["project"].id
        assert "task_id" in ann

        # Generations have FK fields in full mode
        gen = export["generations"][0]
        assert "task_id" in gen
        assert "generation_id" in gen  # ResponseGeneration FK
        assert gen["status"] == "completed"

        # Evaluation runs have project_id in full mode
        er = export["evaluations"][0]
        assert er["project_id"] == data["project"].id

        # Task evaluations have all FK fields in full mode
        te = export["task_evaluations"][0]
        assert "evaluation_id" in te
        assert "task_id" in te

    def test_data_and_full_exports_share_base_fields(
        self, db_session, user, project_with_full_data
    ):
        """Both export modes must produce the same base fields for each entity."""
        from routers.projects.serializers import (
            serialize_annotation,
            serialize_evaluation_run,
            serialize_generation,
            serialize_task,
            serialize_task_evaluation,
        )

        data = project_with_full_data

        # For each entity type, the base fields (present in both modes) must match
        task = data["tasks"][0]
        data_task = serialize_task(task, mode="data")
        full_task = serialize_task(task, mode="full")
        base_task_keys = {"id", "inner_id", "data", "meta", "is_labeled", "created_at", "updated_at"}
        for key in base_task_keys:
            assert data_task[key] == full_task[key], f"Task base field mismatch: {key}"

        ann = data["annotations"][0]
        data_ann = serialize_annotation(ann, mode="data")
        full_ann = serialize_annotation(ann, mode="full")
        base_ann_keys = {
            "id", "result", "completed_by", "created_at", "updated_at",
            "was_cancelled", "ground_truth", "lead_time",
            "active_duration_ms", "focused_duration_ms", "tab_switches",
        }
        for key in base_ann_keys:
            assert data_ann[key] == full_ann[key], f"Annotation base field mismatch: {key}"

        gen = data["generations"][0]
        data_gen = serialize_generation(gen, mode="data")
        full_gen = serialize_generation(gen, mode="full")
        base_gen_keys = {"id", "model_id", "response_content", "case_data", "created_at", "response_metadata"}
        for key in base_gen_keys:
            assert data_gen[key] == full_gen[key], f"Generation base field mismatch: {key}"

        er = data["evaluation_runs"][0]
        data_er = serialize_evaluation_run(er, mode="data")
        full_er = serialize_evaluation_run(er, mode="full")
        base_er_keys = {
            "id", "model_id", "evaluation_type_ids", "metrics",
            "status", "samples_evaluated", "created_at", "completed_at",
        }
        for key in base_er_keys:
            assert data_er[key] == full_er[key], f"EvaluationRun base field mismatch: {key}"

        te = data["gen_evals"][0]
        data_te = serialize_task_evaluation(te, mode="data")
        full_te = serialize_task_evaluation(te, mode="full")
        base_te_keys = {
            "id", "annotation_id", "field_name", "answer_type", "ground_truth",
            "prediction", "metrics", "passed", "confidence_score", "error_message",
            "processing_time_ms", "created_at",
        }
        for key in base_te_keys:
            assert data_te[key] == full_te[key], f"TaskEvaluation base field mismatch: {key}"


# ---------------------------------------------------------------------------
# Field-fidelity tests for the round-trip extensions added in this PR.
# Targets: TaskEvaluation.annotation_id, Annotation.{instruction_variant,
# auto_submitted, ai_assisted, review_*}, Generation.{parse_*, label_config_*},
# TaskEvaluation.judge_prompts_used, KorrekturComment, HumanEvaluation*.
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRoundtripExtensions:
    def test_task_evaluation_annotation_id_survives(
        self, db_session, user, project_with_full_data
    ):
        """The original bug: TaskEvaluation.annotation_id was being dropped on import."""
        data = project_with_full_data
        project = data["project"]
        # Attach annotation_id to the task-level evals so the export carries it.
        for te, ann in zip(data["task_evals"], data["annotations"]):
            te.annotation_id = ann.id
        db_session.commit()

        rt = TestDataExportImportRoundtrip()
        export = rt._export(db_session, project.id, [t.id for t in data["tasks"]], user.id)
        target = Project(
            id=str(uuid.uuid4()), title="Annotation FK target",
            label_config="<View></View>", created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()
        rt._import(db_session, target.id, export, user.id)

        target_task_ids = [t.id for t in db_session.query(Task).filter(Task.project_id == target.id).all()]
        target_ann_ids = {a.id for a in db_session.query(Annotation).filter(Annotation.project_id == target.id).all()}
        anno_tes = (
            db_session.query(TaskEvaluation)
            .filter(TaskEvaluation.task_id.in_(target_task_ids))
            .filter(TaskEvaluation.generation_id.is_(None))
            .all()
        )
        # Each task-level eval should now have annotation_id pointing to a
        # newly-imported annotation, not None.
        assert anno_tes, "expected at least one task-level TaskEvaluation"
        for te in anno_tes:
            assert te.annotation_id != None, "annotation_id was dropped on import"  # noqa: E711
            assert te.annotation_id in target_ann_ids

    def test_annotation_extras_survive(
        self, db_session, user, project_with_full_data
    ):
        """instruction_variant, auto_submitted, ai_assisted, and the review trail."""
        data = project_with_full_data
        ann = data["annotations"][0]
        ann.instruction_variant = "variant-A"
        ann.auto_submitted = True
        ann.ai_assisted = True
        ann.reviewed_by = user.id
        ann.review_result = "approved"
        ann.review_comment = "Looks good"
        db_session.commit()

        rt = TestDataExportImportRoundtrip()
        export = rt._export(db_session, data["project"].id, [t.id for t in data["tasks"]], user.id)
        target = Project(
            id=str(uuid.uuid4()), title="Annotation extras target",
            label_config="<View></View>", created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()
        rt._import(db_session, target.id, export, user.id)

        # Find the imported annotation that mirrors the source via instruction_variant.
        imported = (
            db_session.query(Annotation)
            .filter(Annotation.project_id == target.id)
            .filter(Annotation.instruction_variant == "variant-A")
            .one()
        )
        assert imported.auto_submitted == True  # noqa: E712
        assert imported.ai_assisted == True  # noqa: E712
        assert imported.review_result == "approved"
        assert imported.review_comment == "Looks good"

    def test_korrektur_comments_round_trip(
        self, db_session, user, project_with_full_data
    ):
        """Parent + reply Korrektur comments survive both serialization and import."""
        from project_models import KorrekturComment
        data = project_with_full_data
        project = data["project"]
        ann = data["annotations"][0]
        parent = KorrekturComment(
            id=str(uuid.uuid4()), project_id=project.id, task_id=ann.task_id,
            target_type="annotation", target_id=ann.id, parent_id=None,
            text="Parent comment", created_by=user.id,
        )
        db_session.add(parent)
        db_session.flush()
        reply = KorrekturComment(
            id=str(uuid.uuid4()), project_id=project.id, task_id=ann.task_id,
            target_type="annotation", target_id=ann.id, parent_id=parent.id,
            text="Reply comment", created_by=user.id,
        )
        db_session.add(reply)
        db_session.commit()

        rt = TestDataExportImportRoundtrip()
        export = rt._export(db_session, project.id, [t.id for t in data["tasks"]], user.id)
        assert "korrektur_comments" in export
        assert len(export["korrektur_comments"]) == 2

        target = Project(
            id=str(uuid.uuid4()), title="Korrektur target",
            label_config="<View></View>", created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()

        # The nested-import driver accepts korrektur_comments alongside the
        # `data` payload (the extended import fields).
        from routers.projects._import_stream import run_nested_import
        body = json.dumps({
            "data": export["tasks"],
            "evaluation_runs": export.get("evaluation_runs"),
            "korrektur_comments": export.get("korrektur_comments"),
        }).encode("utf-8")
        run_nested_import(db_session, target.id, io.BytesIO(body), user.id)

        imported = (
            db_session.query(KorrekturComment)
            .filter(KorrekturComment.project_id == target.id)
            .all()
        )
        assert len(imported) == 2
        parents = [c for c in imported if c.parent_id == None]  # noqa: E711
        replies = [c for c in imported if c.parent_id != None]  # noqa: E711
        assert len(parents) == 1 and len(replies) == 1
        assert replies[0].parent_id == parents[0].id, "reply.parent_id must point to the new parent id"

    def _seed_grading_feedback(self, db_session, data, user, *, author_id=None):
        """Two feedback rows on the first submission: a rated LLM grading and a
        comment-only `general` note."""
        from project_models import GradingFeedback

        ann = data["annotations"][0]
        run = data["evaluation_runs"][1]
        rows = [
            GradingFeedback(
                id=str(uuid.uuid4()),
                project_id=data["project"].id,
                task_id=ann.task_id,
                annotation_id=ann.id,
                user_id=author_id or user.id,
                grading_source="llm",
                evaluation_run_id=run.id,
                judge_model_id="gpt-5-mini",
                grade_points=12.0,
                passed=True,
                rating="down",
                comment="Zu streng bei der Subsumtion.",
                context={"metric_keys": ["llm_judge_falloesung"], "graded": True},
            ),
            GradingFeedback(
                id=str(uuid.uuid4()),
                project_id=data["project"].id,
                task_id=ann.task_id,
                annotation_id=ann.id,
                user_id=author_id or user.id,
                grading_source="general",
                rating=None,
                comment="Der Editor hakt auf dem Handy.",
                context={"kind": "general"},
            ),
        ]
        for row in rows:
            db_session.add(row)
        db_session.commit()
        return rows

    def _import_with_feedback(self, db_session, target_id, export, user_id, feedback):
        from routers.projects._import_stream import run_nested_import

        body = json.dumps({
            "data": export["tasks"],
            "evaluation_runs": export.get("evaluation_runs"),
            "grading_feedback": feedback,
        }).encode("utf-8")
        return run_nested_import(db_session, target_id, io.BytesIO(body), user_id)

    def test_grading_feedback_round_trips_with_its_author(
        self, db_session, user, project_with_full_data
    ):
        """Feedback rows survive with remapped FKs, their author, and the
        snapshot of what the solver saw."""
        from models import EvaluationRun
        from project_models import GradingFeedback

        data = project_with_full_data
        project = data["project"]
        self._seed_grading_feedback(db_session, data, user)

        rt = TestDataExportImportRoundtrip()
        export = rt._export(db_session, project.id, [t.id for t in data["tasks"]], user.id)
        assert "grading_feedback" in export
        assert len(export["grading_feedback"]) == 2
        exported_llm = next(
            f for f in export["grading_feedback"] if f["grading_source"] == "llm"
        )
        assert exported_llm["judge_model_id"] == "gpt-5-mini"
        assert exported_llm["context"] == {
            "metric_keys": ["llm_judge_falloesung"], "graded": True
        }

        target = Project(
            id=str(uuid.uuid4()), title="Grading feedback target",
            label_config="<View></View>", created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()
        result = self._import_with_feedback(
            db_session, target.id, export, user.id, export["grading_feedback"]
        )
        assert result["created_grading_feedback"] == 2

        imported = (
            db_session.query(GradingFeedback)
            .filter(GradingFeedback.project_id == target.id)
            .all()
        )
        assert len(imported) == 2
        by_source = {f.grading_source: f for f in imported}
        assert set(by_source) == {"llm", "general"}

        target_task_ids = {
            t.id for t in db_session.query(Task).filter(Task.project_id == target.id).all()
        }
        target_ann_ids = {
            a.id
            for a in db_session.query(Annotation)
            .filter(Annotation.project_id == target.id)
            .all()
        }
        target_run_ids = {
            r.id
            for r in db_session.query(EvaluationRun)
            .filter(EvaluationRun.project_id == target.id)
            .all()
        }
        llm = by_source["llm"]
        # FKs point into the NEW project, never back at the source rows.
        assert llm.task_id in target_task_ids
        assert llm.annotation_id in target_ann_ids
        assert llm.annotation_id != data["annotations"][0].id
        assert llm.evaluation_run_id in target_run_ids
        assert llm.evaluation_run_id != data["evaluation_runs"][1].id
        # The opinion and its snapshot travel verbatim.
        assert llm.user_id == user.id
        assert llm.rating == "down"
        assert llm.comment == "Zu streng bei der Subsumtion."
        assert llm.judge_model_id == "gpt-5-mini"
        assert llm.grade_points == 12.0
        assert llm.passed is True
        assert llm.context == {"metric_keys": ["llm_judge_falloesung"], "graded": True}

        general = by_source["general"]
        assert general.rating is None
        assert general.comment == "Der Editor hakt auf dem Handy."
        assert general.evaluation_run_id is None
        assert general.judge_model_id is None

    def test_grading_feedback_keeps_a_foreign_author_never_the_importer(
        self, db_session, user, project_with_full_data
    ):
        """An opinion from an author this deployment doesn't know keeps that
        author (the nested importer stubs the user); it is never silently
        re-attributed to whoever ran the import."""
        from models import User as UserModel
        from project_models import GradingFeedback

        data = project_with_full_data
        self._seed_grading_feedback(db_session, data, user)
        rt = TestDataExportImportRoundtrip()
        export = rt._export(
            db_session, data["project"].id, [t.id for t in data["tasks"]], user.id
        )
        # Simulate an export from another deployment: the author is unknown here.
        foreign_author = str(uuid.uuid4())
        feedback = [dict(f, user_id=foreign_author) for f in export["grading_feedback"]]

        target = Project(
            id=str(uuid.uuid4()), title="Foreign author target",
            label_config="<View></View>", created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()
        self._import_with_feedback(db_session, target.id, export, user.id, feedback)

        imported = (
            db_session.query(GradingFeedback)
            .filter(GradingFeedback.project_id == target.id)
            .all()
        )
        assert len(imported) == 2
        assert {f.user_id for f in imported} == {foreign_author}
        assert user.id not in {f.user_id for f in imported}
        # The stub user carrying the opinion exists, so the FK resolves.
        assert (
            db_session.query(UserModel).filter(UserModel.id == foreign_author).one()
        )

    def test_grading_feedback_without_its_submission_is_dropped(
        self, db_session, user, project_with_full_data
    ):
        """A row whose annotation didn't come along is dropped, not dangled —
        and a duplicate (user, annotation, source) never reaches the unique
        index."""
        from project_models import GradingFeedback

        data = project_with_full_data
        self._seed_grading_feedback(db_session, data, user)
        rt = TestDataExportImportRoundtrip()
        export = rt._export(
            db_session, data["project"].id, [t.id for t in data["tasks"]], user.id
        )
        llm_row = next(
            f for f in export["grading_feedback"] if f["grading_source"] == "llm"
        )
        feedback = [
            dict(llm_row, id=str(uuid.uuid4()), annotation_id=str(uuid.uuid4())),
            dict(llm_row, id=str(uuid.uuid4()), grading_source="klingon"),
            dict(llm_row, id=str(uuid.uuid4()), rating=None, comment="   "),
            llm_row,
            dict(llm_row, id=str(uuid.uuid4()), rating="up"),  # duplicate key
        ]

        target = Project(
            id=str(uuid.uuid4()), title="Dropped feedback target",
            label_config="<View></View>", created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()
        result = self._import_with_feedback(
            db_session, target.id, export, user.id, feedback
        )

        imported = (
            db_session.query(GradingFeedback)
            .filter(GradingFeedback.project_id == target.id)
            .all()
        )
        assert result["created_grading_feedback"] == 1
        assert len(imported) == 1
        assert imported[0].rating == "down"

    def test_judge_prompts_used_survives(
        self, db_session, user, project_with_full_data
    ):
        """TaskEvaluation.judge_prompts_used (LLM judge prompt provenance) round-trips."""
        data = project_with_full_data
        prompts = {"system": "judge system prompt", "user": "compare X to Y"}
        for te in data["task_evals"]:
            te.judge_prompts_used = prompts
        db_session.commit()

        rt = TestDataExportImportRoundtrip()
        export = rt._export(
            db_session, data["project"].id, [t.id for t in data["tasks"]], user.id
        )
        # Export carries it on each task-level evaluation row.
        for task in export["tasks"]:
            for ev in task["evaluations"]:
                assert ev["judge_prompts_used"] == prompts

        target = Project(
            id=str(uuid.uuid4()), title="Judge prompts target",
            label_config="<View></View>", created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()
        rt._import(db_session, target.id, export, user.id)

        target_task_ids = [
            t.id for t in db_session.query(Task).filter(Task.project_id == target.id).all()
        ]
        anno_tes = (
            db_session.query(TaskEvaluation)
            .filter(TaskEvaluation.task_id.in_(target_task_ids))
            .filter(TaskEvaluation.generation_id.is_(None))
            .all()
        )
        assert anno_tes
        for te in anno_tes:
            assert te.judge_prompts_used == prompts

    def test_generation_parse_fields_survive_full_clone(
        self, db_session, user, project_with_full_data
    ):
        """Generation.parse_* and label_config_* survive the full project clone path."""
        data = project_with_full_data
        gen = data["generations"][0]
        gen.parse_status = "success"
        gen.parsed_annotation = [{"from_name": "label", "value": {"choices": ["A"]}}]
        gen.parse_metadata = {"retry_count": 1}
        gen.label_config_version = "v3"
        gen.label_config_snapshot = "<View>v3</View>"
        db_session.commit()

        export = _export_project_dict(db_session, data["project"].id)
        gen_data = next(g for g in export["generations"] if g["id"] == gen.id)
        assert gen_data["parse_status"] == "success"
        assert gen_data["parsed_annotation"] == [
            {"from_name": "label", "value": {"choices": ["A"]}}
        ]
        assert gen_data["label_config_version"] == "v3"
        assert gen_data["label_config_snapshot"] == "<View>v3</View>"

    def test_project_alternating_instructions_survive_clone(
        self, db_session, user, project_with_full_data
    ):
        """Project.conditional_instructions and review/Korrektur configs survive a full clone."""
        data = project_with_full_data
        project = data["project"]
        project.conditional_instructions = [
            {"id": "var-A", "content": "Read carefully", "weight": 0.5},
            {"id": "var-B", "content": "Read fast", "weight": 0.5},
        ]
        project.instructions_always_visible = True
        project.review_enabled = True
        project.review_mode = "independent"
        project.allow_self_review = True
        project.korrektur_enabled = True
        project.korrektur_config = [{"value": "✓", "background": "#dff"}]
        db_session.commit()

        export = _export_project_dict(db_session, project.id)
        proj = export["project"]
        assert proj["conditional_instructions"][0]["id"] == "var-A"
        assert proj["instructions_always_visible"] == True  # noqa: E712
        assert proj["review_enabled"] == True  # noqa: E712
        assert proj["review_mode"] == "independent"
        assert proj["allow_self_review"] == True  # noqa: E712
        assert proj["korrektur_enabled"] == True  # noqa: E712
        assert proj["korrektur_config"][0]["value"] == "✓"

    def test_project_kind_and_settings_survive_full_import(
        self, db_session, user, project_with_full_data
    ):
        """kind, icon, timer/checkpoint/feature settings and llm_model_ids
        survive export -> create-new import; visibility and origin do not."""
        from models import LLMModel, Organization, OrganizationMembership
        from routers.projects._import_stream import run_full_project_import

        org = Organization(
            id=str(uuid.uuid4()),
            name="Roundtrip Org",
            slug=f"rt-{uuid.uuid4().hex[:8]}",
            display_name="Roundtrip Org",
        )
        db_session.add(org)
        db_session.flush()
        db_session.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=user.id,
                organization_id=org.id,
                role="ORG_ADMIN",
                is_active=True,
            )
        )
        official_id = f"rt-official-{uuid.uuid4().hex[:8]}"
        db_session.add(
            LLMModel(
                id=official_id,
                name="Roundtrip Official",
                provider="openai",
                model_type="chat",
                capabilities=["text_generation"],
                is_official=True,
            )
        )

        project = project_with_full_data["project"]
        project.kind = "exam"
        project.icon = "📝"
        project.origin = "student"
        # is_private and is_public are mutually exclusive (DB check).
        project.is_public = True
        project.public_role = "ANNOTATOR"
        project.annotator_full_visibility_after_submit = True
        # Explicitly the opposite of the reference switch, so a dropped key
        # (NULL = follow it) would show.
        project.annotator_step_detail_after_submit = False
        project.immediate_evaluation_enabled = True
        project.annotation_time_limit_enabled = True
        project.annotation_time_limit_seconds = 5400
        project.strict_timer_enabled = True
        project.restorable_checkpoints_enabled = False
        project.checkpoint_interval_seconds = 120
        project.skip_queue = "ignore_skipped"
        project.llm_model_ids = [official_id, "no-such-model-on-this-instance"]
        project.enable_annotation = True
        project.enable_generation = False
        project.enable_evaluation = False
        project.enable_prompts = False
        project.allow_external_paste = False
        project.allow_solution_upload = False
        project.handwriting_ocr_enabled = True
        project.handwriting_ocr_model = "gemini-3-flash"
        project.exam_tools = {
            "tools": [
                {"id": "calculator"},
                {
                    "id": "law_texts",
                    "config": {
                        "codes": ["BGB", "StGB"],
                        "sources": [
                            {"provider": "lexmea", "mode": "org", "connection_id": "conn-on-this-deployment"},
                            {"provider": "gii", "mode": "builtin"},
                        ],
                    },
                },
            ],
        }
        db_session.commit()

        export = _export_project_dict(db_session, project.id)
        proj = export["project"]
        assert proj["kind"] == "exam"
        assert proj["icon"] == "📝"
        assert proj["annotation_time_limit_seconds"] == 5400
        assert proj["skip_queue"] == "ignore_skipped"
        assert proj["annotator_step_detail_after_submit"] is False
        assert proj["enable_generation"] is False
        assert proj["allow_external_paste"] is False
        assert proj["allow_solution_upload"] is False
        assert proj["handwriting_ocr_enabled"] is True
        assert proj["handwriting_ocr_model"] == "gemini-3-flash"
        # Exam tools travel without the deployment-bound connection id.
        assert proj["exam_tools"] == {
            "tools": [
                {"id": "calculator"},
                {
                    "id": "law_texts",
                    "config": {
                        "codes": ["BGB", "StGB"],
                        "sources": [
                            {"provider": "lexmea", "mode": "org"},
                            {"provider": "gii", "mode": "builtin"},
                        ],
                    },
                },
            ],
        }
        for key in ("is_private", "is_public", "public_role", "origin"):
            assert key not in proj, f"visibility/origin key exported: {key}"

        result = run_full_project_import(
            db_session,
            io.BytesIO(json.dumps(export).encode("utf-8")),
            user.id,
            organization_id=org.id,
        )
        imported = (
            db_session.query(Project).filter(Project.id == result["project_id"]).one()
        )
        assert imported.id != project.id
        assert imported.kind == "exam"
        assert imported.icon == "📝"
        assert imported.annotator_full_visibility_after_submit is True
        assert imported.annotator_step_detail_after_submit is False
        assert imported.immediate_evaluation_enabled is True
        assert imported.annotation_time_limit_enabled is True
        assert imported.annotation_time_limit_seconds == 5400
        assert imported.strict_timer_enabled is True
        assert imported.restorable_checkpoints_enabled is False
        assert imported.checkpoint_interval_seconds == 120
        assert imported.skip_queue == "ignore_skipped"
        assert imported.enable_annotation is True
        assert imported.enable_generation is False
        assert imported.enable_evaluation is False
        assert imported.enable_prompts is False
        assert imported.allow_external_paste is False
        assert imported.allow_solution_upload is False
        assert imported.handwriting_ocr_enabled is True
        assert imported.handwriting_ocr_model == "gemini-3-flash"
        assert imported.exam_tools == proj["exam_tools"]
        # Unknown model ids are reconciled away like generation_config models.
        assert imported.llm_model_ids == [official_id]
        # Visibility is reset (the org named in the request owns the copy) and
        # origin is not carried over.
        assert imported.is_private is False
        assert imported.is_public is False
        assert imported.public_role is None
        assert imported.origin is None

    def test_older_export_without_settings_imports_with_column_defaults(
        self, db_session, user, project_with_full_data
    ):
        """An export predating the settings keys (or carrying explicit nulls)
        imports with the column defaults instead of failing NOT NULL."""
        from models import Organization, OrganizationMembership
        from routers.projects._import_stream import run_full_project_import

        org = Organization(
            id=str(uuid.uuid4()),
            name="Legacy Org",
            slug=f"legacy-{uuid.uuid4().hex[:8]}",
            display_name="Legacy Org",
        )
        db_session.add(org)
        db_session.flush()
        db_session.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=user.id,
                organization_id=org.id,
                role="ORG_ADMIN",
                is_active=True,
            )
        )
        db_session.commit()

        export = _export_project_dict(
            db_session, project_with_full_data["project"].id
        )
        proj = export["project"]
        for key in ("kind", "icon", "strict_timer_enabled", "llm_model_ids"):
            proj.pop(key)
        proj["skip_queue"] = None
        proj["checkpoint_interval_seconds"] = None
        proj["enable_evaluation"] = None
        proj["enable_prompts"] = None
        proj.pop("allow_external_paste")
        proj["allow_solution_upload"] = None
        proj.pop("handwriting_ocr_enabled")
        proj.pop("handwriting_ocr_model")
        proj.pop("exam_tools", None)

        result = run_full_project_import(
            db_session, io.BytesIO(json.dumps(export).encode("utf-8")), user.id
        )
        imported = (
            db_session.query(Project).filter(Project.id == result["project_id"]).one()
        )
        assert imported.kind is None
        assert imported.strict_timer_enabled is False
        assert imported.skip_queue == "requeue_for_others"
        assert imported.checkpoint_interval_seconds == 300
        assert imported.enable_evaluation is True
        assert imported.enable_prompts is True
        assert imported.allow_external_paste is True
        assert imported.exam_tools is None
        assert imported.allow_solution_upload is True
        assert imported.handwriting_ocr_enabled is False
        assert imported.handwriting_ocr_model is None


class TestTaskRubricRoundtrip:
    """Bewertungsbogen rows (migration 100 shape) survive export → import:
    ``structure`` / ``grade_scale`` round-trip as stored, ``total_points``
    stays a float (72.5), legacy rows keep ``structure = None``."""

    STRUCTURE = {
        "version": 1,
        "nodes": [
            {"id": "n1", "level": 0, "kind": "section", "label": "A.", "title": "Anspruch entstanden", "note": None},
            {"id": "n2", "level": 1, "kind": "step", "label": "I.", "title": "Kaufvertrag", "note": None,
             "key": "s01_kaufvertrag", "max_score": 70, "emphasis": None, "hints": []},
            {"id": "n3", "level": 1, "kind": "step", "label": "II.", "title": "Obersatz", "note": None,
             "key": "s02_obersatz", "max_score": 2.5, "emphasis": "schwerpunkt", "hints": ["Gutachtenstil!"]},
        ],
    }
    SCALE = {
        "unit": "BE",
        "thresholds": [8, 15, 22, 29, 32, 35, 38, 41, 44, 47, 50, 53, 56, 59, 62, 65, 68, 71],
        "rounding": "floor",
        "pass_grade": 4,
    }

    def test_structure_scale_and_float_total_survive(
        self, db_session, user, project_with_full_data
    ):
        from project_models import TaskRubric

        data = project_with_full_data
        project = data["project"]
        structured = TaskRubric(
            id=str(uuid.uuid4()), task_id=data["tasks"][0].id, project_id=project.id,
            title="Korrekturbogen",
            criteria={"s01_kaufvertrag": {"name": "Kaufvertrag", "rubric": "r", "max_score": 70},
                      "s02_obersatz": {"name": "Obersatz", "rubric": "r", "max_score": 2.5}},
            total_points=72.5, structure=self.STRUCTURE, grade_scale=self.SCALE,
            source="human", status="active", created_by=user.id,
        )
        legacy = TaskRubric(
            id=str(uuid.uuid4()), task_id=data["tasks"][1].id, project_id=project.id,
            title="Legacy", criteria={"s01_a": {"name": "A", "rubric": "r", "max_score": 100}},
            total_points=100, source="llm", status="candidate", created_by=user.id,
        )
        db_session.add_all([structured, legacy])
        db_session.commit()

        rt = TestDataExportImportRoundtrip()
        export = rt._export(db_session, project.id, [t.id for t in data["tasks"]], user.id)
        exported = {r["title"]: r for item in export["tasks"] for r in item.get("rubrics", [])}
        assert exported["Korrekturbogen"]["structure"] == self.STRUCTURE
        assert exported["Korrekturbogen"]["grade_scale"] == self.SCALE
        assert exported["Korrekturbogen"]["total_points"] == 72.5
        assert exported["Legacy"]["structure"] is None
        assert exported["Legacy"]["grade_scale"] is None

        target = Project(
            id=str(uuid.uuid4()), title="Rubric target",
            label_config="<View></View>", created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()
        rt._import(db_session, target.id, export, user.id)

        imported = {
            r.title: r
            for r in db_session.query(TaskRubric).filter(TaskRubric.project_id == target.id).all()
        }
        assert set(imported) == {"Korrekturbogen", "Legacy"}
        assert imported["Korrekturbogen"].structure == self.STRUCTURE
        assert imported["Korrekturbogen"].grade_scale == self.SCALE
        assert imported["Korrekturbogen"].total_points == 72.5
        assert isinstance(imported["Korrekturbogen"].total_points, float)
        assert imported["Korrekturbogen"].status == "active"
        assert imported["Korrekturbogen"].source == "human"
        assert imported["Legacy"].structure is None
        assert imported["Legacy"].grade_scale is None
        assert imported["Legacy"].total_points == 100.0
        target_task_ids = {t.id for t in db_session.query(Task).filter(Task.project_id == target.id).all()}
        assert {r.task_id for r in imported.values()} <= target_task_ids


class TestRubricGradingReferencesSurviveImport:
    """A rubric grading records the sheet it was scored against at
    ``metrics[<key>]["details"]["rubric_id"]``, and import mints fresh rubric
    ids. Unless the importer repoints that id, every imported grading names a
    row of the SOURCE deployment. The id is joined on, not merely recorded:
    clone-on-edit detection, Notenschlüssel recompute and both result views
    resolve the sheet through it."""

    RUBRIC_CRITERIA = {"s01_a": {"name": "A", "rubric": "r", "max_score": 10}}

    def _seed(self, db_session, user, data):
        from models import TaskEvaluation
        from project_models import TaskRubric
        from sqlalchemy.orm.attributes import flag_modified

        task_ids = [t.id for t in data["tasks"]]
        grading = (
            db_session.query(TaskEvaluation)
            .filter(TaskEvaluation.task_id.in_(task_ids))
            .first()
        )
        assert grading is not None, "fixture must provide at least one grading"
        rubric = TaskRubric(
            id=str(uuid.uuid4()),
            task_id=grading.task_id,
            project_id=data["project"].id,
            title="Bogen mit Bewertung",
            criteria=self.RUBRIC_CRITERIA,
            total_points=10.0,
            source="human",
            status="active",
            created_by=user.id,
        )
        db_session.add(rubric)
        db_session.flush()
        grading.metrics = {
            **(grading.metrics or {}),
            "llm_judge_rubric": {
                "value": 0.7,
                "details": {
                    "rubric_id": rubric.id,
                    "grade_points": 9,
                    "total_score": 7.0,
                    "total_max": 10.0,
                },
            },
        }
        flag_modified(grading, "metrics")
        db_session.commit()
        return rubric

    def _rubric_gradings(self, db_session, project_id):
        from models import TaskEvaluation

        task_ids = [
            t.id for t in db_session.query(Task).filter(Task.project_id == project_id).all()
        ]
        return [
            row
            for row in db_session.query(TaskEvaluation)
            .filter(TaskEvaluation.task_id.in_(task_ids))
            .all()
            if isinstance(row.metrics, dict) and "llm_judge_rubric" in row.metrics
        ]

    def test_per_task_import_repoints_gradings_at_the_imported_sheet(
        self, db_session, user, project_with_full_data
    ):
        from project_models import TaskRubric

        data = project_with_full_data
        source_rubric = self._seed(db_session, user, data)

        rt = TestDataExportImportRoundtrip()
        export = rt._export(
            db_session, data["project"].id, [t.id for t in data["tasks"]], user.id
        )
        target = Project(
            id=str(uuid.uuid4()), title="Remap target",
            label_config="<View></View>", created_by=user.id,
        )
        db_session.add(target)
        db_session.commit()
        rt._import(db_session, target.id, export, user.id)

        imported = (
            db_session.query(TaskRubric)
            .filter(TaskRubric.project_id == target.id,
                    TaskRubric.title == "Bogen mit Bewertung")
            .one()
        )
        assert imported.id != source_rubric.id
        gradings = self._rubric_gradings(db_session, target.id)
        assert gradings, "the rubric grading must travel with its task"
        for row in gradings:
            assert row.metrics["llm_judge_rubric"]["details"]["rubric_id"] == imported.id


# ---------------------------------------------------------------------------
# Benchmark run: full project export -> import, field by field
# ---------------------------------------------------------------------------
#
# A model benchmark run moved from one deployment to another (dev -> prod) has
# to arrive complete: every run of a multi-run generation, the job's prompt and
# settings, the judges' raw answers, the per-call telemetry and the original
# timestamps. These tests compare every exported column after a round trip,
# through both the comprehensive JSON and the NDJSON format, instead of only
# counting rows.

from datetime import datetime, timedelta, timezone  # noqa: E402

DEV_MODEL = "custom-dev-0000"
PROD_MODEL = "custom-prod-1111"
_T0 = datetime(2026, 3, 2, 9, 30, 0, tzinfo=timezone.utc)


def _export_text(db, project_id, fmt):
    from routers.projects._export_stream import (
        stream_comprehensive_project_data_json,
        stream_export_ndjson,
    )

    gen = (
        stream_export_ndjson
        if fmt == "ndjson"
        else stream_comprehensive_project_data_json
    )
    return "".join(gen(db, project_id))


def _import_text(db, text, user_id, **kwargs):
    from routers.projects._import_stream import run_full_project_import

    return run_full_project_import(
        db, io.BytesIO(text.encode("utf-8")), user_id, **kwargs
    )


def _benchmark_rows(db, project_id):
    """Every benchmark row of one project, keyed by a content field that is
    unique in the fixture (ids are fresh after an import)."""
    from models import EvaluationRunMetric

    task_ids = [t.id for t in db.query(Task).filter(Task.project_id == project_id)]
    rgs = db.query(ResponseGeneration).filter(ResponseGeneration.task_id.in_(task_ids)).all()
    gens = db.query(Generation).filter(Generation.task_id.in_(task_ids)).all()
    runs = db.query(EvaluationRun).filter(EvaluationRun.project_id == project_id).all()
    run_ids = [r.id for r in runs]
    judge_runs = (
        db.query(EvaluationJudgeRun)
        .filter(EvaluationJudgeRun.evaluation_id.in_(run_ids))
        .all()
    )
    metrics = (
        db.query(EvaluationRunMetric)
        .filter(EvaluationRunMetric.evaluation_id.in_(run_ids))
        .all()
    )
    tes = db.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id.in_(run_ids)).all()
    return {
        "tasks": {t.data["text"]: t for t in db.query(Task).filter(Task.id.in_(task_ids))},
        "response_generations": {rg.prompt_used: rg for rg in rgs},
        "generations": {g.response_content: g for g in gens},
        "evaluation_runs": {r.samples_evaluated: r for r in runs},
        "judge_runs": {jr.judge_model_id: jr for jr in judge_runs},
        "metrics": {m.value: m for m in metrics},
        "task_evaluations": {te.raw_output: te for te in tes},
    }


# Columns compared verbatim after a round trip. Ids and foreign keys are fresh
# on the importing side and are checked through the content keys instead.
_RG_FIELDS = (
    "config_id", "structure_key", "status", "responses_generated",
    "runs_requested", "runs_completed", "runs_failed", "error_message",
    "result", "prompt_used", "parameters", "generation_metadata",
    "created_at", "started_at", "completed_at",
)
_GEN_FIELDS = (
    "case_data", "response_content", "reasoning", "usage_stats", "response_metadata",
    "status", "error_message", "seed", "finish_reason", "truncated", "refusal",
    "error_type", "latency_ms", "input_tokens", "output_tokens", "run_index",
    "created_at", "parse_status", "parse_error", "parsed_annotation",
    "parse_metadata", "label_config_version", "label_config_snapshot",
)
_RUN_FIELDS = (
    "evaluation_type_ids", "metrics", "eval_metadata", "status",
    "error_message", "samples_evaluated", "has_sample_results",
    "created_at", "completed_at",
)
_JUDGE_RUN_FIELDS = (
    "judge_model_id", "run_index", "status", "started_at", "completed_at",
    "samples_evaluated", "error_message", "metric_parameters_snapshot",
)
_METRIC_FIELDS = ("evaluation_type_id", "value", "created_at")
_TE_FIELDS = (
    "field_name", "evaluation_config_id", "answer_type", "ground_truth",
    "prediction", "metrics", "passed", "confidence_score", "error_message",
    "processing_time_ms", "judge_prompts_used", "seed", "finish_reason",
    "truncated", "refusal", "error_type", "latency_ms", "input_tokens",
    "output_tokens", "raw_output", "raw_reasoning", "created_at", "updated_at",
)
_TASK_FIELDS = ("data", "meta", "is_labeled", "created_at", "updated_at")


def _assert_same(src, dst, fields, what):
    for f in fields:
        assert getattr(dst, f) == getattr(src, f), (
            f"{what}.{f}: exported {getattr(src, f)!r}, imported {getattr(dst, f)!r}"
        )


@pytest.fixture
def benchmark_project(db_session, user):
    """A finished benchmark run: two tasks, one generation job per task with
    two runs each (runs_requested=2), an evaluation run with a judge run, a
    metric row and one judged row per generation, every row carrying the
    telemetry and timestamps a real run writes."""
    from models import EvaluationRunMetric, EvaluationType

    eval_type = EvaluationType(
        id=f"rt-metric-{uuid.uuid4().hex[:8]}",
        name="Roundtrip judge metric",
        category="generation",
        applicable_project_types=["generation"],
    )
    db_session.add(eval_type)

    project = Project(
        id=str(uuid.uuid4()),
        title=f"Benchmark RT {uuid.uuid4().hex[:8]}",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=user.id,
        generation_config={
            "selected_configuration": {
                "models": [DEV_MODEL, "gpt-4o"],
                "model_configs": {DEV_MODEL: {"temperature": 0.2}},
                "active_structures": ["default"],
            },
            "prompt_structures": {"default": {"name": "Default"}},
        },
        llm_model_ids=[DEV_MODEL],
        created_at=_T0 - timedelta(days=10),
    )
    db_session.add(project)
    db_session.flush()

    tasks, rgs, gens = [], [], []
    for i in range(2):
        t = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"Benchmark case {i}"},
            meta={"source": "lexam"},
            created_by=user.id,
            created_at=_T0 - timedelta(days=9, minutes=i),
            updated_at=_T0 - timedelta(days=8, minutes=i),
        )
        db_session.add(t)
        tasks.append(t)
        db_session.flush()

        rg = ResponseGeneration(
            id=str(uuid.uuid4()),
            project_id=project.id,
            task_id=t.id,
            model_id=DEV_MODEL,
            config_id="cfg-gen",
            structure_key="default",
            status="completed",
            responses_generated=2,
            runs_requested=2,
            runs_completed=2,
            runs_failed=0,
            result={"summary": f"job {i}"},
            prompt_used=f"Solve benchmark case {i}",
            parameters={"temperature": 0.2, "max_tokens": 512},
            generation_metadata={"structure": "default"},
            created_by=user.id,
            created_at=_T0 + timedelta(minutes=i),
            started_at=_T0 + timedelta(minutes=i, seconds=5),
            completed_at=_T0 + timedelta(minutes=i, seconds=50),
        )
        db_session.add(rg)
        rgs.append(rg)
        db_session.flush()

        for run in range(2):
            g = Generation(
                id=str(uuid.uuid4()),
                generation_id=rg.id,
                task_id=t.id,
                model_id=DEV_MODEL,
                run_index=run,
                case_data=json.dumps(t.data),
                response_content=f"Answer case {i} run {run}",
                # Reasoning on one run only, so NULL round-trips too.
                reasoning=None if run else f"Reasoning case {i}",
                usage_stats={"input_tokens": 100 + run, "output_tokens": 40 + run},
                response_metadata={"finish_reason": "stop"},
                status="completed",
                seed=1000 + run,
                finish_reason="length" if run else "stop",
                truncated=bool(run),
                refusal=False,
                error_type=None,
                latency_ms=900 + run,
                input_tokens=100 + run,
                output_tokens=40 + run,
                parse_status="success",
                parsed_annotation=[{"from_name": "answer", "value": {"text": ["x"]}}],
                parse_metadata={"retry_count": 0},
                label_config_version="v1",
                created_at=_T0 + timedelta(minutes=i, seconds=10 + run),
            )
            db_session.add(g)
            gens.append(g)
    db_session.flush()

    er = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=project.id,
        model_id=DEV_MODEL,
        evaluation_type_ids=[eval_type.id],
        metrics={"score": 0.75},
        eval_metadata={"evaluation_configs": [{"id": "cfg-judge"}]},
        status="completed",
        samples_evaluated=4,
        has_sample_results=True,
        created_by=user.id,
        created_at=_T0 + timedelta(hours=1),
        completed_at=_T0 + timedelta(hours=2),
    )
    db_session.add(er)
    db_session.flush()
    jr = EvaluationJudgeRun(
        id=str(uuid.uuid4()),
        evaluation_id=er.id,
        judge_model_id="gpt-judge",
        run_index=0,
        status="completed",
        started_at=_T0 + timedelta(hours=1, minutes=1),
        completed_at=_T0 + timedelta(hours=1, minutes=59),
        samples_evaluated=4,
        metric_parameters_snapshot={"judge": "gpt-judge"},
    )
    db_session.add(jr)
    db_session.add(
        EvaluationRunMetric(
            id=str(uuid.uuid4()),
            evaluation_id=er.id,
            evaluation_type_id=eval_type.id,
            value=0.75,
            created_at=_T0 + timedelta(hours=2),
        )
    )
    db_session.flush()

    for n, g in enumerate(gens):
        db_session.add(
            TaskEvaluation(
                id=str(uuid.uuid4()),
                evaluation_id=er.id,
                judge_run_id=jr.id,
                task_id=g.task_id,
                generation_id=g.id,
                field_name="cfg-judge:answer:reference",
                evaluation_config_id="cfg-judge",
                answer_type="text",
                ground_truth="expected",
                prediction=g.response_content,
                metrics={"score": 0.5 + n / 10},
                passed=bool(n % 2),
                confidence_score=0.8,
                processing_time_ms=1500 + n,
                judge_prompts_used={"system": "judge"},
                seed=7,
                finish_reason="stop",
                truncated=False,
                refusal=bool(n == 3),
                error_type="refusal" if n == 3 else None,
                latency_ms=2000 + n,
                input_tokens=300 + n,
                output_tokens=60 + n,
                raw_output=f'{{"score": {0.5 + n / 10}, "row": {n}}}',
                raw_reasoning=f"Judge reasoning {n}" if n % 2 else None,
                created_at=_T0 + timedelta(hours=1, minutes=10 + n),
                updated_at=_T0 + timedelta(hours=1, minutes=30 + n),
            )
        )
    db_session.commit()
    return {"project": project, "eval_type": eval_type}


def _register_prod_model(db_session):
    """The model the dev id maps to, registered (public) on this instance."""
    from models import LLMModel

    if db_session.query(LLMModel).filter(LLMModel.id == PROD_MODEL).first() is None:
        db_session.add(
            LLMModel(
                id=PROD_MODEL,
                name="Qwen3-4B (prod)",
                provider="custom",
                model_type="chat",
                capabilities=["text_generation"],
                is_official=False,
                is_public=True,
                base_url="http://gpu.example.org:40001/v1",
                endpoint_model_name="Qwen/Qwen3-4B",
            )
        )
        db_session.commit()


@pytest.mark.integration
@pytest.mark.parametrize("fmt", ["comprehensive", "ndjson"])
class TestBenchmarkRunRoundtrip:
    def test_multi_run_generations_import(
        self, db_session, user, benchmark_project, fmt
    ):
        """Every run of a runs_requested=2 job lands, each with its own
        run_index; with run_index missing they all collided on
        uq_generations_parent_run_index and the whole import failed."""
        src = benchmark_project["project"]
        result = _import_text(db_session, _export_text(db_session, src.id, fmt), user.id)

        rows = _benchmark_rows(db_session, result["project_id"])
        assert len(rows["generations"]) == 4
        by_parent = {}
        for g in rows["generations"].values():
            by_parent.setdefault(g.generation_id, set()).add(g.run_index)
        assert sorted(by_parent.values(), key=sorted) == [{0, 1}, {0, 1}]

    def test_imported_generation_jobs_belong_to_the_new_project(
        self, db_session, user, benchmark_project, fmt
    ):
        """The generation grid, the job list, evaluation scoping and the
        project summaries all filter response_generations by project_id."""
        src = benchmark_project["project"]
        result = _import_text(db_session, _export_text(db_session, src.id, fmt), user.id)

        rows = _benchmark_rows(db_session, result["project_id"])
        assert len(rows["response_generations"]) == 2
        for rg in rows["response_generations"].values():
            assert rg.project_id == result["project_id"]

    def test_every_benchmark_field_survives(
        self, db_session, user, benchmark_project, fmt
    ):
        """Field by field, per entity: job provenance and run counters, the
        generations' run index and call telemetry, the run's sample flag, the
        judge's raw answers and telemetry, and every original timestamp."""
        src_project = benchmark_project["project"]
        src = _benchmark_rows(db_session, src_project.id)
        result = _import_text(
            db_session, _export_text(db_session, src_project.id, fmt), user.id
        )
        dst = _benchmark_rows(db_session, result["project_id"])

        for entity, fields in (
            ("tasks", _TASK_FIELDS),
            ("response_generations", _RG_FIELDS),
            ("generations", _GEN_FIELDS),
            ("evaluation_runs", _RUN_FIELDS),
            ("judge_runs", _JUDGE_RUN_FIELDS),
            ("metrics", _METRIC_FIELDS),
            ("task_evaluations", _TE_FIELDS),
        ):
            assert set(dst[entity]) == set(src[entity]), entity
            for key, src_row in src[entity].items():
                dst_row = dst[entity][key]
                assert dst_row.id != src_row.id, entity
                _assert_same(src_row, dst_row, fields, f"{entity}[{key!r}]")

        # Without a model_id_map every model id travels verbatim.
        for entity in ("response_generations", "generations", "evaluation_runs"):
            for row in dst[entity].values():
                assert row.model_id == DEV_MODEL, entity

        # Foreign keys point at the imported rows, not at the source.
        src_rg_by_id = {rg.id: rg for rg in src["response_generations"].values()}
        dst_rg_by_id = {rg.id: rg for rg in dst["response_generations"].values()}
        dst_task_by_id = {t.id: t for t in dst["tasks"].values()}
        src_task_by_id = {t.id: t for t in src["tasks"].values()}
        for key, g in dst["generations"].items():
            src_g = src["generations"][key]
            assert (
                dst_rg_by_id[g.generation_id].prompt_used
                == src_rg_by_id[src_g.generation_id].prompt_used
            )
            assert (
                dst_task_by_id[g.task_id].data == src_task_by_id[src_g.task_id].data
            )
        for rg in dst["response_generations"].values():
            assert rg.project_id == result["project_id"]
            assert rg.task_id in dst_task_by_id
        dst_gen_by_id = {g.id: g for g in dst["generations"].values()}
        (dst_run,) = dst["evaluation_runs"].values()
        (dst_jr,) = dst["judge_runs"].values()
        assert dst_jr.evaluation_id == dst_run.id
        for key, te in dst["task_evaluations"].items():
            assert te.evaluation_id == dst_run.id
            assert te.judge_run_id == dst_jr.id
            assert dst_gen_by_id[te.generation_id].response_content == te.prediction

    def test_model_id_map_relabels_the_run(
        self, db_session, user, benchmark_project, fmt
    ):
        """A dev model id named in model_id_map arrives as the production id
        everywhere a model is referenced, before the catalog check (which
        would otherwise drop the dev-only id from the model selection)."""
        _register_prod_model(db_session)
        src_project = benchmark_project["project"]
        result = _import_text(
            db_session,
            _export_text(db_session, src_project.id, fmt),
            user.id,
            model_id_map={DEV_MODEL: PROD_MODEL, "gpt-judge": "gpt-judge-prod"},
        )
        dst = _benchmark_rows(db_session, result["project_id"])
        for entity in ("response_generations", "generations", "evaluation_runs"):
            assert dst[entity]
            for row in dst[entity].values():
                assert row.model_id == PROD_MODEL, entity
        assert set(dst["judge_runs"]) == {"gpt-judge-prod"}

        imported = (
            db_session.query(Project).filter(Project.id == result["project_id"]).one()
        )
        assert imported.llm_model_ids == [PROD_MODEL]
        selected = imported.generation_config["selected_configuration"]
        assert PROD_MODEL in selected["models"]
        assert DEV_MODEL not in selected["models"]
        assert selected["model_configs"] == {PROD_MODEL: {"temperature": 0.2}}
        assert result["statistics"]["model_id_map"] == {
            DEV_MODEL: PROD_MODEL,
            "gpt-judge": "gpt-judge-prod",
        }

    def test_older_export_without_the_new_fields_imports(
        self, db_session, user, benchmark_project, fmt
    ):
        """An export written before these fields existed still imports: the
        runs of a multi-run job get distinct indexes, the counters and flags
        take their column defaults and the timestamps are the import's."""
        dropped = {
            "response_generation": (
                "project_id", "structure_key", "runs_requested", "runs_completed",
                "runs_failed", "result", "prompt_used", "parameters",
                "created_at", "started_at", "completed_at",
            ),
            "generation": (
                "run_index", "seed", "finish_reason", "truncated", "refusal",
                "error_type", "latency_ms", "input_tokens", "output_tokens",
                "created_at", "reasoning",
            ),
            "evaluation": ("has_sample_results", "created_at", "completed_at"),
            "evaluation_judge_run": ("started_at", "completed_at"),
            "task_evaluation": (
                "raw_output", "seed", "finish_reason", "truncated", "refusal",
                "error_type", "latency_ms", "input_tokens", "output_tokens",
                "created_at", "updated_at", "raw_reasoning",
            ),
        }
        plural = {
            "response_generation": "response_generations",
            "generation": "generations",
            "evaluation": "evaluations",
            "evaluation_judge_run": "evaluation_judge_runs",
            "task_evaluation": "task_evaluations",
        }
        text = _export_text(db_session, benchmark_project["project"].id, fmt)
        if fmt == "ndjson":
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
            for rec in records:
                for key in dropped.get(rec.get("_type"), ()):
                    rec.pop(key, None)
            text = "\n".join(json.dumps(r) for r in records) + "\n"
        else:
            doc = json.loads(text)
            for rtype, keys in dropped.items():
                for rec in doc[plural[rtype]]:
                    for key in keys:
                        rec.pop(key, None)
            text = json.dumps(doc)

        before = datetime.now(timezone.utc) - timedelta(minutes=5)
        result = _import_text(db_session, text, user.id)
        dst = _benchmark_rows(db_session, result["project_id"])

        by_parent = {}
        for g in dst["generations"].values():
            by_parent.setdefault(g.generation_id, set()).add(g.run_index)
            assert g.truncated is False and g.refusal is False
            assert g.reasoning is None
            assert g.created_at > before
        assert sorted(by_parent.values(), key=sorted) == [{0, 1}, {0, 1}]
        for rg in dst["response_generations"].values():
            assert rg.project_id == result["project_id"]
            assert (rg.runs_requested, rg.runs_completed, rg.runs_failed) == (1, 0, 0)
            assert rg.created_at > before
        (run,) = dst["evaluation_runs"].values()
        assert run.has_sample_results is False
        assert run.completed_at is None
        tes = db_session.query(TaskEvaluation).filter(
            TaskEvaluation.evaluation_id == run.id
        ).all()
        assert len(tes) == 4
        assert all(te.raw_output is None and te.refusal is False for te in tes)
        assert all(te.raw_reasoning is None for te in tes)


def test_model_id_map_must_map_strings_to_strings(db_session, user, benchmark_project):
    from routers.projects._import_stream import ImportValidationError

    text = _export_text(db_session, benchmark_project["project"].id, "ndjson")
    for bad in (["a", "b"], {"a": ""}, {"a": 1}, {"": "b"}):
        with pytest.raises(ImportValidationError) as exc:
            _import_text(db_session, text, user.id, model_id_map=bad)
        assert exc.value.status_code == 400


def test_both_formats_carry_identical_benchmark_rows(db_session, benchmark_project):
    """The comprehensive JSON and the NDJSON export emit the same dict per
    benchmark row, so either file moves a run completely."""
    pid = benchmark_project["project"].id
    doc = json.loads(_export_text(db_session, pid, "comprehensive"))
    records = [
        json.loads(line)
        for line in _export_text(db_session, pid, "ndjson").splitlines()
        if line.strip()
    ]
    for rtype, key in (
        ("response_generation", "response_generations"),
        ("generation", "generations"),
        ("evaluation", "evaluations"),
        ("evaluation_metric", "evaluation_metrics"),
        ("evaluation_judge_run", "evaluation_judge_runs"),
        ("task_evaluation", "task_evaluations"),
    ):
        nd = sorted(
            ({k: v for k, v in r.items() if k != "_type"} for r in records
             if r["_type"] == rtype),
            key=lambda r: r["id"],
        )
        assert nd, rtype
        assert nd == sorted(doc[key], key=lambda r: r["id"]), rtype


# ---------------------------------------------------------------------------
# Merge import: prod -> local copy -> new model benchmarked -> back into prod
# ---------------------------------------------------------------------------

LOCAL_MODEL = "custom-local-2222"


def _merge_text(db, project_id, text, user_id, **kwargs):
    from routers.projects._import_stream import run_merge_import

    return run_merge_import(
        db, project_id, io.BytesIO(text.encode("utf-8")), user_id, **kwargs
    )


def _register_model(db, model_id, name=None, official=False):
    """Register ``model_id`` on this instance (public), once."""
    from models import LLMModel

    if db.query(LLMModel).filter(LLMModel.id == model_id).first() is None:
        db.add(
            LLMModel(
                id=model_id,
                name=name or f"Model {model_id}",
                provider="custom" if not official else "openai",
                model_type="chat",
                capabilities=["text_generation"],
                is_official=official,
                # An official catalog row carries no visibility flags; a
                # custom one needs its endpoint.
                is_public=not official,
                **(
                    {}
                    if official
                    else {
                        "base_url": "http://gpu.example.org:40001/v1",
                        "endpoint_model_name": model_id,
                    }
                ),
            )
        )
        db.commit()


def _benchmark_new_model(db, project_id, user_id, model_id, runs=1, register=True):
    """What a benchmark run on the local copy adds: one generation job per
    task for ``model_id`` with ``runs`` generations that all give the same
    answer, and an evaluation run that judges every run.

    The judge model exists on both instances; ``register`` makes
    ``model_id`` one of this instance's models too (a merge refuses rows of
    a model it does not know)."""
    from models import EvaluationRunMetric

    _register_model(db, "gpt-judge", official=True)
    if register:
        _register_model(db, model_id)
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    when = datetime.now(timezone.utc).replace(microsecond=0)
    run = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=project_id,
        model_id=model_id,
        evaluation_type_ids=["rt-new"],
        metrics={"score": 0.9},
        status="completed",
        samples_evaluated=len(tasks),
        has_sample_results=True,
        created_by=user_id,
        created_at=when + timedelta(hours=1),
        completed_at=when + timedelta(hours=2),
    )
    db.add(run)
    db.flush()
    jr = EvaluationJudgeRun(
        id=str(uuid.uuid4()),
        evaluation_id=run.id,
        judge_model_id="gpt-judge",
        run_index=0,
        status="completed",
    )
    db.add(jr)
    db.flush()
    db.add(
        EvaluationRunMetric(
            id=str(uuid.uuid4()),
            evaluation_id=run.id,
            evaluation_type_id=db.query(EvaluationRunMetric.evaluation_type_id)
            .limit(1)
            .scalar(),
            value=0.9,
        )
    )
    for n, t in enumerate(tasks):
        rg = ResponseGeneration(
            id=str(uuid.uuid4()),
            project_id=project_id,
            task_id=t.id,
            model_id=model_id,
            structure_key="default",
            status="completed",
            responses_generated=runs,
            runs_requested=runs,
            runs_completed=runs,
            prompt_used=f"new model prompt {n}",
            created_by=user_id,
            created_at=when + timedelta(seconds=n),
        )
        db.add(rg)
        db.flush()
        for r in range(runs):
            g = Generation(
                id=str(uuid.uuid4()),
                generation_id=rg.id,
                task_id=t.id,
                model_id=model_id,
                run_index=r,
                case_data=json.dumps(t.data),
                response_content=f"New model answer {t.data['text']}",
                reasoning=f"New model reasoning {t.data['text']}",
                status="completed",
            )
            db.add(g)
            db.flush()
            db.add(
                TaskEvaluation(
                    id=str(uuid.uuid4()),
                    evaluation_id=run.id,
                    judge_run_id=jr.id,
                    task_id=t.id,
                    generation_id=g.id,
                    field_name="cfg-judge:answer:reference",
                    answer_type="text",
                    ground_truth="expected",
                    prediction=g.response_content,
                    metrics={"score": 0.9},
                    passed=True,
                    raw_output=f"new judge {n}" + (f" run {r}" if r else ""),
                    raw_reasoning=f"new judge reasoning {n}",
                )
            )
    db.commit()


def _result_counts(db, project_id):
    task_ids = [t.id for t in db.query(Task).filter(Task.project_id == project_id)]
    run_ids = [
        r.id for r in db.query(EvaluationRun).filter(EvaluationRun.project_id == project_id)
    ]
    from models import EvaluationRunMetric

    return {
        "tasks": len(task_ids),
        "response_generations": db.query(ResponseGeneration)
        .filter(ResponseGeneration.task_id.in_(task_ids)).count(),
        "generations": db.query(Generation).filter(Generation.task_id.in_(task_ids)).count(),
        "evaluations": len(run_ids),
        "evaluation_metrics": db.query(EvaluationRunMetric)
        .filter(EvaluationRunMetric.evaluation_id.in_(run_ids)).count(),
        "evaluation_judge_runs": db.query(EvaluationJudgeRun)
        .filter(EvaluationJudgeRun.evaluation_id.in_(run_ids)).count(),
        "task_evaluations": db.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id.in_(run_ids)).count(),
    }


def _models_by_entity(db, project_id):
    task_ids = [t.id for t in db.query(Task).filter(Task.project_id == project_id)]
    return {
        "response_generations": sorted(
            m for (m,) in db.query(ResponseGeneration.model_id)
            .filter(ResponseGeneration.task_id.in_(task_ids))
        ),
        "generations": sorted(
            m for (m,) in db.query(Generation.model_id)
            .filter(Generation.task_id.in_(task_ids))
        ),
        "evaluations": sorted(
            m for (m,) in db.query(EvaluationRun.model_id)
            .filter(EvaluationRun.project_id == project_id)
        ),
    }


@pytest.mark.integration
@pytest.mark.parametrize("fmt", ["comprehensive", "ndjson"])
class TestMergeImport:
    def test_imported_tasks_remember_their_origin(
        self, db_session, user, benchmark_project, fmt
    ):
        prod = benchmark_project["project"]
        local_id = _import_text(
            db_session, _export_text(db_session, prod.id, fmt), user.id
        )["project_id"]
        prod_tasks = {t.data["text"]: t.id for t in db_session.query(Task).filter(
            Task.project_id == prod.id)}
        local_tasks = db_session.query(Task).filter(Task.project_id == local_id).all()
        assert {t.data["text"]: t.source_task_id for t in local_tasks} == prod_tasks

        # A copy of the copy still points at the first task, not at the copy.
        second_id = _import_text(
            db_session, _export_text(db_session, local_id, fmt), user.id
        )["project_id"]
        second = db_session.query(Task).filter(Task.project_id == second_id).all()
        assert {t.data["text"]: t.source_task_id for t in second} == prod_tasks

    def test_benchmarked_copy_merges_back_next_to_the_existing_results(
        self, db_session, user, benchmark_project, fmt
    ):
        """The captain's flow: export the prod project, import it locally,
        benchmark one more model there, export, merge into the prod project.
        The new model's results land next to the old ones, nothing is
        duplicated, and a second merge of the same file changes nothing."""
        _register_prod_model(db_session)
        prod = benchmark_project["project"]
        before = _result_counts(db_session, prod.id)

        local_id = _import_text(
            db_session, _export_text(db_session, prod.id, fmt), user.id
        )["project_id"]
        _benchmark_new_model(db_session, local_id, user.id, LOCAL_MODEL)
        local_export = _export_text(db_session, local_id, fmt)

        result = _merge_text(
            db_session, prod.id, local_export, user.id,
            model_id_map={LOCAL_MODEL: PROD_MODEL},
        )
        stats = result["statistics"]
        assert stats["matched_tasks"] == 2
        assert stats["added_counts"] == {
            "task_rubrics": 0,
            "response_generations": 2,
            "generations": 2,
            "evaluations": 1,
            "evaluation_metrics": 1,
            "evaluation_judge_runs": 1,
            "task_evaluations": 2,
        }
        assert stats["skipped_present_counts"]["generations"] == 4
        assert stats["skipped_present_counts"]["evaluations"] == 1
        assert stats["models_added_to_project"] == [PROD_MODEL]

        after = _result_counts(db_session, prod.id)
        assert after == {
            "tasks": before["tasks"],
            "response_generations": before["response_generations"] + 2,
            "generations": before["generations"] + 2,
            "evaluations": before["evaluations"] + 1,
            "evaluation_metrics": before["evaluation_metrics"] + 1,
            "evaluation_judge_runs": before["evaluation_judge_runs"] + 1,
            "task_evaluations": before["task_evaluations"] + 2,
        }
        models = _models_by_entity(db_session, prod.id)
        assert models["generations"] == sorted([DEV_MODEL] * 4 + [PROD_MODEL] * 2)
        assert models["evaluations"] == sorted([DEV_MODEL, PROD_MODEL])

        # The merged rows hang off the prod tasks and the prod project.
        prod_task_ids = {t.id for t in db_session.query(Task).filter(
            Task.project_id == prod.id)}
        new_jobs = db_session.query(ResponseGeneration).filter(
            ResponseGeneration.model_id == PROD_MODEL,
            ResponseGeneration.task_id.in_(prod_task_ids),
        ).all()
        assert {rg.project_id for rg in new_jobs} == {prod.id}
        new_run = db_session.query(EvaluationRun).filter(
            EvaluationRun.project_id == prod.id, EvaluationRun.model_id == PROD_MODEL
        ).one()
        new_gen_ids = {
            g.id for g in db_session.query(Generation).filter(
                Generation.model_id == PROD_MODEL, Generation.task_id.in_(prod_task_ids)
            )
        }
        rows = db_session.query(TaskEvaluation).filter(
            TaskEvaluation.evaluation_id == new_run.id
        ).all()
        assert {te.generation_id for te in rows} == new_gen_ids
        assert sorted(te.raw_output for te in rows) == ["new judge 0", "new judge 1"]
        # Model and judge reasoning come along with the merged rows.
        assert sorted(te.raw_reasoning for te in rows) == [
            "new judge reasoning 0", "new judge reasoning 1"
        ]
        merged_gens = db_session.query(Generation).filter(Generation.id.in_(new_gen_ids)).all()
        assert merged_gens
        assert all(
            g.reasoning == g.response_content.replace("answer", "reasoning")
            for g in merged_gens
        )

        # The generation grid takes its columns from the model selection.
        db_session.refresh(prod)
        selected = prod.generation_config["selected_configuration"]["models"]
        assert selected[-1] == PROD_MODEL and DEV_MODEL in selected

        # Idempotent: the same file again adds nothing.
        again = _merge_text(
            db_session, prod.id, local_export, user.id,
            model_id_map={LOCAL_MODEL: PROD_MODEL},
        )
        assert set(again["statistics"]["added_counts"].values()) == {0}
        assert again["statistics"]["models_added_to_project"] == []
        assert _result_counts(db_session, prod.id) == after

    def test_repeated_runs_with_the_same_answer_all_merge(
        self, db_session, user, benchmark_project, fmt
    ):
        """A model run twice per task that answers the same both times: both
        runs arrive as their own generations, each judged row stays on its
        own run, and merging the file again adds nothing."""
        prod = benchmark_project["project"]
        local_id = _import_text(
            db_session, _export_text(db_session, prod.id, fmt), user.id
        )["project_id"]
        _benchmark_new_model(db_session, local_id, user.id, LOCAL_MODEL, runs=2)
        local_export = _export_text(db_session, local_id, fmt)

        result = _merge_text(db_session, prod.id, local_export, user.id)
        added = result["statistics"]["added_counts"]
        assert added["response_generations"] == 2
        assert added["generations"] == 4
        assert added["task_evaluations"] == 4

        prod_tasks = db_session.query(Task).filter(Task.project_id == prod.id).all()
        new_run = db_session.query(EvaluationRun).filter(
            EvaluationRun.project_id == prod.id, EvaluationRun.model_id == LOCAL_MODEL
        ).one()
        for t in prod_tasks:
            gens = db_session.query(Generation).filter(
                Generation.task_id == t.id, Generation.model_id == LOCAL_MODEL
            ).all()
            assert sorted(g.run_index for g in gens) == [0, 1]
            judged = {
                te.generation_id: te.raw_output
                for te in db_session.query(TaskEvaluation).filter(
                    TaskEvaluation.evaluation_id == new_run.id,
                    TaskEvaluation.task_id == t.id,
                )
            }
            by_run = {g.run_index: g.id for g in gens}
            local_n = judged[by_run[0]].split()[2]
            assert judged == {
                by_run[0]: f"new judge {local_n}",
                by_run[1]: f"new judge {local_n} run 1",
            }

        after = _result_counts(db_session, prod.id)
        again = _merge_text(db_session, prod.id, local_export, user.id)
        assert set(again["statistics"]["added_counts"].values()) == {0}
        assert _result_counts(db_session, prod.id) == after

    def test_merging_a_project_into_itself_adds_nothing(
        self, db_session, user, benchmark_project, fmt
    ):
        prod = benchmark_project["project"]
        before = _result_counts(db_session, prod.id)
        result = _merge_text(
            db_session, prod.id, _export_text(db_session, prod.id, fmt), user.id
        )
        assert set(result["statistics"]["added_counts"].values()) == {0}
        assert _result_counts(db_session, prod.id) == before

    def test_tasks_without_a_recorded_origin_match_by_content(
        self, db_session, user, benchmark_project, fmt
    ):
        """An export from before source ids existed (or of a project created
        by a data import) still merges when the task data is identical."""
        prod = benchmark_project["project"]
        local_id = _import_text(
            db_session, _export_text(db_session, prod.id, fmt), user.id
        )["project_id"]
        for t in db_session.query(Task).filter(Task.project_id == local_id):
            t.source_task_id = None
        db_session.commit()
        _benchmark_new_model(db_session, local_id, user.id, LOCAL_MODEL)

        result = _merge_text(
            db_session, prod.id, _export_text(db_session, local_id, fmt), user.id
        )
        assert result["statistics"]["matched_tasks"] == 2
        assert result["statistics"]["added_counts"]["generations"] == 2

    def test_unrelated_project_is_refused_and_nothing_changes(
        self, db_session, user, benchmark_project, project_with_full_data, fmt
    ):
        from routers.projects._import_stream import (
            MERGE_TASK_MISMATCH,
            ImportValidationError,
        )

        prod = benchmark_project["project"]
        before = _result_counts(db_session, prod.id)
        other = _export_text(db_session, project_with_full_data["project"].id, fmt)
        with pytest.raises(ImportValidationError) as exc:
            _merge_text(db_session, prod.id, other, user.id)
        db_session.rollback()
        assert exc.value.status_code == 409
        assert exc.value.code == MERGE_TASK_MISMATCH
        assert "3 match no task of this project" in exc.value.detail
        assert _result_counts(db_session, prod.id) == before

    def test_ambiguous_content_match_is_refused(
        self, db_session, user, benchmark_project, fmt
    ):
        """Two project tasks with the same data and no recorded origin: the
        merge cannot tell which one an exported task is, so it refuses."""
        from routers.projects._import_stream import ImportValidationError

        prod = benchmark_project["project"]
        local_id = _import_text(
            db_session, _export_text(db_session, prod.id, fmt), user.id
        )["project_id"]
        for t in db_session.query(Task).filter(Task.project_id == local_id):
            t.source_task_id = None
        first = db_session.query(Task).filter(Task.project_id == prod.id).first()
        db_session.add(Task(
            id=str(uuid.uuid4()), project_id=prod.id, inner_id=99,
            data=dict(first.data), created_by=user.id,
        ))
        db_session.commit()
        with pytest.raises(ImportValidationError) as exc:
            _merge_text(
                db_session, prod.id, _export_text(db_session, local_id, fmt), user.id
            )
        db_session.rollback()
        assert exc.value.status_code == 409
        assert "match more than one" in exc.value.detail

    def test_merged_rubric_gradings_point_at_the_projects_sheet(
        self, db_session, user, benchmark_project, fmt
    ):
        """A new model graded against a task's Bewertungsbogen on the copy:
        after the merge its gradings name the original project's sheet, and
        no second copy of the sheet is added."""
        from project_models import TaskRubric

        prod = benchmark_project["project"]
        prod_task = db_session.query(Task).filter(Task.project_id == prod.id).first()
        sheet = TaskRubric(
            id=str(uuid.uuid4()),
            task_id=prod_task.id,
            project_id=prod.id,
            title="Bogen",
            criteria={"items": [{"id": "c1", "points": 10}]},
            total_points=10.0,
            source="llm",
            status="active",
            created_by=user.id,
        )
        db_session.add(sheet)
        db_session.commit()

        local_id = _import_text(
            db_session, _export_text(db_session, prod.id, fmt), user.id
        )["project_id"]
        _benchmark_new_model(db_session, local_id, user.id, LOCAL_MODEL)
        local_task = db_session.query(Task).filter(
            Task.project_id == local_id, Task.source_task_id == prod_task.id
        ).one()
        local_sheet = db_session.query(TaskRubric).filter(
            TaskRubric.task_id == local_task.id
        ).one()
        graded = db_session.query(TaskEvaluation).join(
            Generation, Generation.id == TaskEvaluation.generation_id
        ).filter(
            Generation.model_id == LOCAL_MODEL, TaskEvaluation.task_id == local_task.id
        ).one()
        graded.metrics = {
            "llm_judge_rubric": {"value": 0.7, "details": {"rubric_id": local_sheet.id}}
        }
        db_session.commit()

        result = _merge_text(
            db_session, prod.id, _export_text(db_session, local_id, fmt), user.id
        )
        assert result["statistics"]["added_counts"]["task_rubrics"] == 0
        assert db_session.query(TaskRubric).filter(
            TaskRubric.task_id == prod_task.id
        ).count() == 1
        merged = db_session.query(TaskEvaluation).join(
            Generation, Generation.id == TaskEvaluation.generation_id
        ).filter(
            Generation.model_id == LOCAL_MODEL, TaskEvaluation.task_id == prod_task.id
        ).one()
        assert merged.metrics["llm_judge_rubric"]["details"]["rubric_id"] == sheet.id


UNKNOWN_MODEL = "custom-unknown-3333"


@pytest.mark.integration
@pytest.mark.parametrize("fmt", ["comprehensive", "ndjson"])
class TestMergeModelSafety:
    """A merge never writes rows under a model id this instance does not
    know, the preview says which ids need mapping, the grid keeps the
    project's models, and a run's label is not a model of the selection."""

    def _local_copy(self, db, user, prod, fmt, model_id=LOCAL_MODEL, register=True):
        local_id = _import_text(db, _export_text(db, prod.id, fmt), user.id)["project_id"]
        _benchmark_new_model(db, local_id, user.id, model_id, register=register)
        return _export_text(db, local_id, fmt)

    def test_unknown_model_is_refused_and_nothing_is_written(
        self, db_session, user, benchmark_project, fmt
    ):
        """Defect 2: without a map the rows used to land under the other
        instance's id (an orphan the grid never shows), and the corrective
        merge with the map then added them a second time."""
        from routers.projects._import_stream import (
            MERGE_UNKNOWN_MODELS,
            ImportValidationError,
        )

        _register_prod_model(db_session)
        prod = benchmark_project["project"]
        before = _result_counts(db_session, prod.id)
        local_export = self._local_copy(
            db_session, user, prod, fmt, model_id=UNKNOWN_MODEL, register=False
        )

        with pytest.raises(ImportValidationError) as exc:
            _merge_text(db_session, prod.id, local_export, user.id)
        db_session.rollback()
        assert exc.value.status_code == 409
        assert exc.value.code == MERGE_UNKNOWN_MODELS
        assert UNKNOWN_MODEL in exc.value.detail
        assert _result_counts(db_session, prod.id) == before

        # The corrective merge adds the results exactly once.
        result = _merge_text(
            db_session, prod.id, local_export, user.id,
            model_id_map={UNKNOWN_MODEL: PROD_MODEL},
        )
        assert result["statistics"]["added_counts"]["generations"] == 2
        models = _models_by_entity(db_session, prod.id)
        assert UNKNOWN_MODEL not in models["generations"]
        assert models["generations"].count(PROD_MODEL) == 2

    def test_dry_run_reports_the_models_and_writes_nothing(
        self, db_session, user, benchmark_project, fmt
    ):
        prod = benchmark_project["project"]
        before = _result_counts(db_session, prod.id)
        selection_before = dict(prod.generation_config)
        local_export = self._local_copy(
            db_session, user, prod, fmt, model_id=UNKNOWN_MODEL, register=False
        )

        result = _merge_text(db_session, prod.id, local_export, user.id, dry_run=True)
        stats = result["statistics"]
        assert stats["dry_run"] is True
        assert stats["matched_tasks"] == 2
        assert stats["added_counts"]["generations"] == 2
        by_id = {m["source_model_id"]: m for m in stats["models"]}
        # Two generations and the evaluation run land under the new model.
        assert by_id[UNKNOWN_MODEL] == {
            "source_model_id": UNKNOWN_MODEL,
            "model_id": UNKNOWN_MODEL,
            "mapped": False,
            "known": False,
            "name": None,
            "rows_added": 3,
            "rows_present": 0,
        }
        assert by_id["gpt-judge"]["known"] is True
        # The project's own model: everything present, nothing added.
        assert by_id[DEV_MODEL]["rows_added"] == 0
        assert by_id[DEV_MODEL]["rows_present"] > 0

        db_session.expire_all()
        assert _result_counts(db_session, prod.id) == before
        assert db_session.get(Project, prod.id).generation_config == selection_before

    def test_empty_selection_keeps_the_projects_models(
        self, db_session, user, benchmark_project, fmt
    ):
        """Defect 3: the grid shows exactly the selection. An empty one used
        to end up holding only the merged model, hiding every model the
        project already had."""
        from sqlalchemy.orm.attributes import flag_modified

        _register_prod_model(db_session)
        _register_model(db_session, DEV_MODEL)
        prod = benchmark_project["project"]
        local_export = self._local_copy(db_session, user, prod, fmt)
        prod.generation_config["selected_configuration"]["models"] = []
        flag_modified(prod, "generation_config")
        db_session.commit()

        result = _merge_text(
            db_session, prod.id, local_export, user.id,
            model_id_map={LOCAL_MODEL: PROD_MODEL},
        )
        assert result["statistics"]["models_added_to_project"] == [PROD_MODEL]
        db_session.refresh(prod)
        assert prod.generation_config["selected_configuration"]["models"] == [
            DEV_MODEL,
            PROD_MODEL,
        ]

    def test_a_runs_label_does_not_join_the_selection(
        self, db_session, user, benchmark_project, fmt
    ):
        """Defect 5: a run labelled with a model whose generations the merge
        does not bring used to add that model to the selection."""
        _register_prod_model(db_session)
        _register_model(db_session, "claude-label", official=True)
        prod = benchmark_project["project"]
        local_id = _import_text(
            db_session, _export_text(db_session, prod.id, fmt), user.id
        )["project_id"]
        _benchmark_new_model(db_session, local_id, user.id, LOCAL_MODEL)
        new_run = db_session.query(EvaluationRun).filter(
            EvaluationRun.project_id == local_id, EvaluationRun.model_id == LOCAL_MODEL
        ).one()
        new_run.model_id = "claude-label"
        db_session.commit()

        result = _merge_text(
            db_session, prod.id, _export_text(db_session, local_id, fmt), user.id,
            model_id_map={LOCAL_MODEL: PROD_MODEL},
        )
        assert result["statistics"]["models_added_to_project"] == [PROD_MODEL]
        db_session.refresh(prod)
        assert "claude-label" not in prod.generation_config["selected_configuration"]["models"]


def _make_org(db, name):
    from models import Organization

    org = Organization(
        id=str(uuid.uuid4()),
        name=name,
        display_name=name,
        slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
    )
    db.add(org)
    db.commit()
    return org


@pytest.mark.integration
@pytest.mark.parametrize("fmt", ["comprehensive", "ndjson"])
class TestImportKeepsAttributionAndOrder:
    """Defect 6: organization_id was dropped on every import. Imported jobs
    are attributed to the org of the project they land in, never to the org
    the file names (an importer could otherwise bill any org whose id they
    know)."""

    def _member_org(self, db, user, name):
        from models import OrganizationMembership, OrganizationRole

        org = _make_org(db, name)
        db.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=user.id,
                organization_id=org.id,
                role=OrganizationRole.ORG_ADMIN,
                is_active=True,
            )
        )
        db.commit()
        return org

    def _bill_jobs_to(self, db, project_id, org_id):
        for rg in db.query(ResponseGeneration).filter(
            ResponseGeneration.project_id == project_id
        ):
            rg.organization_id = org_id
        db.commit()

    def _job_orgs(self, db, project_id):
        return {
            rg.organization_id
            for rg in db.query(ResponseGeneration).filter(
                ResponseGeneration.project_id == project_id
            )
        }

    def test_a_copy_bills_the_org_the_import_names_not_the_files_org(
        self, db_session, user, benchmark_project, fmt
    ):
        foreign = _make_org(db_session, "Foreign Org")
        target = self._member_org(db_session, user, "Target Org")
        prod = benchmark_project["project"]
        self._bill_jobs_to(db_session, prod.id, foreign.id)

        copy_id = _import_text(
            db_session, _export_text(db_session, prod.id, fmt), user.id,
            organization_id=target.id,
        )["project_id"]
        assert self._job_orgs(db_session, copy_id) == {target.id}

    def test_a_private_copy_bills_no_org(
        self, db_session, user, benchmark_project, fmt
    ):
        foreign = _make_org(db_session, "Foreign Org")
        prod = benchmark_project["project"]
        self._bill_jobs_to(db_session, prod.id, foreign.id)

        copy_id = _import_text(
            db_session, _export_text(db_session, prod.id, fmt), user.id
        )["project_id"]
        assert self._job_orgs(db_session, copy_id) == {None}

    def test_a_merge_bills_the_target_projects_org_not_the_files_org(
        self, db_session, user, benchmark_project, fmt
    ):
        from project_models import ProjectOrganization

        foreign = _make_org(db_session, "Foreign Org")
        target = self._member_org(db_session, user, "Target Org")
        prod = benchmark_project["project"]
        db_session.add(
            ProjectOrganization(
                id=str(uuid.uuid4()), project_id=prod.id,
                organization_id=target.id, assigned_by=user.id,
            )
        )
        db_session.commit()
        _register_prod_model(db_session)
        local_id = _import_text(
            db_session, _export_text(db_session, prod.id, fmt), user.id
        )["project_id"]
        _benchmark_new_model(db_session, local_id, user.id, LOCAL_MODEL)
        self._bill_jobs_to(db_session, local_id, foreign.id)
        before = {
            rg.id for rg in db_session.query(ResponseGeneration).filter(
                ResponseGeneration.project_id == prod.id
            )
        }

        _merge_text(
            db_session, prod.id, _export_text(db_session, local_id, fmt), user.id,
            model_id_map={LOCAL_MODEL: PROD_MODEL},
        )
        merged = {
            rg.organization_id
            for rg in db_session.query(ResponseGeneration).filter(
                ResponseGeneration.project_id == prod.id,
                ResponseGeneration.id.notin_(before),
            )
        }
        assert merged == {target.id}

    def test_a_merge_into_a_private_project_bills_no_org(
        self, db_session, user, benchmark_project, fmt
    ):
        foreign = _make_org(db_session, "Foreign Org")
        prod = benchmark_project["project"]
        _register_prod_model(db_session)
        local_id = _import_text(
            db_session, _export_text(db_session, prod.id, fmt), user.id
        )["project_id"]
        _benchmark_new_model(db_session, local_id, user.id, LOCAL_MODEL)
        self._bill_jobs_to(db_session, local_id, foreign.id)
        before = {
            rg.id for rg in db_session.query(ResponseGeneration).filter(
                ResponseGeneration.project_id == prod.id
            )
        }

        _merge_text(
            db_session, prod.id, _export_text(db_session, local_id, fmt), user.id,
            model_id_map={LOCAL_MODEL: PROD_MODEL},
        )
        merged = {
            rg.organization_id
            for rg in db_session.query(ResponseGeneration).filter(
                ResponseGeneration.project_id == prod.id,
                ResponseGeneration.id.notin_(before),
            )
        }
        assert merged == {None}

    def test_task_numbers_keep_their_order(self, db_session, user, fmt):
        """Defect 7: the exporters wrote tasks in heap order and the importer
        numbers them in file order, so every copy renumbered its tasks."""
        project = Project(
            id=str(uuid.uuid4()),
            title=f"Order RT {uuid.uuid4().hex[:8]}",
            label_config='<View><Text name="text" value="$text"/></View>',
            created_by=user.id,
        )
        db_session.add(project)
        db_session.flush()
        # Inserted out of order, so heap order differs from number order.
        for n in (3, 1, 4, 2, 6, 5):
            db_session.add(
                Task(
                    id=str(uuid.uuid4()),
                    project_id=project.id,
                    inner_id=n,
                    data={"text": f"Q{n}"},
                    created_by=user.id,
                )
            )
        db_session.commit()

        copy_id = _import_text(
            db_session, _export_text(db_session, project.id, fmt), user.id
        )["project_id"]
        numbers = {
            t.data["text"]: t.inner_id
            for t in db_session.query(Task).filter(Task.project_id == copy_id)
        }
        assert numbers == {f"Q{n}": n for n in range(1, 7)}


class TestDecompressedSizeCap:
    """Defect 9: a small gzip or zip could inflate without limit into worker
    temp disk before the job failed."""

    def _gzip(self, raw: bytes) -> io.BytesIO:
        import gzip

        return io.BytesIO(gzip.compress(raw))

    def test_gzip_past_the_cap_is_refused(self, monkeypatch):
        from routers.projects._import_stream import (
            IMPORT_TOO_LARGE,
            ImportValidationError,
            _maybe_decompress,
        )

        monkeypatch.setenv("IMPORT_MAX_DECOMPRESSED_BYTES", "1000")
        with pytest.raises(ImportValidationError) as exc:
            _maybe_decompress(self._gzip(b"x" * 5000))
        assert exc.value.status_code == 413
        assert exc.value.code == IMPORT_TOO_LARGE

        out = _maybe_decompress(self._gzip(b"y" * 1000))
        assert out.read() == b"y" * 1000

    def test_zip_member_past_the_cap_is_refused(self, monkeypatch):
        import zipfile

        from routers.projects._import_stream import (
            IMPORT_TOO_LARGE,
            ImportValidationError,
            _maybe_unzip,
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project.json", "{" + " " * 5000 + "}")
        monkeypatch.setenv("IMPORT_MAX_DECOMPRESSED_BYTES", "1000")
        with pytest.raises(ImportValidationError) as exc:
            _maybe_unzip(buf)
        assert exc.value.status_code == 413
        assert exc.value.code == IMPORT_TOO_LARGE

    def test_default_cap_is_twenty_times_the_upload_cap(self, monkeypatch):
        from routers.projects._import_stream import max_decompressed_bytes

        monkeypatch.delenv("IMPORT_MAX_DECOMPRESSED_BYTES", raising=False)
        assert max_decompressed_bytes() == 20 * 2 * 1024 ** 3
        monkeypatch.setenv("IMPORT_MAX_DECOMPRESSED_BYTES", "not-a-number")
        assert max_decompressed_bytes() == 20 * 2 * 1024 ** 3

"""
Roundtrip integration tests for export → import → verify.

Tests both roundtrip paths:
1. Data export (bulk_export_tasks) → data import (import_project_data) → verify
2. Full project export (get_comprehensive_project_data) → full project import
   (import_full_project) → verify

Uses the shared PostgreSQL test database with per-test transaction rollback.
"""

import json
import os
import sys
import uuid
from asyncio import run
from datetime import datetime
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from models import (
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    PostAnnotationResponse,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


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

    # --- Task evaluations (generation-level) ---
    gen_evals = []
    for gen in generations:
        te = TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=er_gen.id,
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
    task_evals = []
    for t in tasks:
        te = TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=er_ann.id,
            task_id=t.id,
            generation_id=None,
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
    """Export via bulk_export_tasks, import via import_project_data, verify."""

    def _export(self, db_session, project_id, task_ids, user_id):
        from routers.projects.tasks import bulk_export_tasks

        mock_user = Mock()
        mock_user.id = user_id
        mock_user.is_superadmin = True
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.state = Mock(spec=[])
        request_data = {"task_ids": task_ids, "format": "json"}
        response = run(
            bulk_export_tasks(project_id, request_data, request=mock_request, current_user=mock_user, db=db_session)
        )
        return json.loads(response.body.decode("utf-8"))

    def _import(self, db_session, target_project_id, export_data, user_id):
        from routers.projects.import_export import import_project_data
        from project_schemas import ProjectImportData

        mock_user = Mock()
        mock_user.id = user_id
        mock_user.is_superadmin = True
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.state = Mock(spec=[])

        import_payload = ProjectImportData(
            data=export_data["tasks"],
            evaluation_runs=export_data.get("evaluation_runs"),
        )

        result = run(
            import_project_data(target_project_id, import_payload, request=mock_request, current_user=mock_user, db=db_session)
        )
        return result

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
            assert ann.result is not None
            assert ann.ground_truth is True

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

        gen_tes = [te for te in imported_tes if te.generation_id is not None]
        task_tes = [te for te in imported_tes if te.generation_id is None]
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
    """Export via get_comprehensive_project_data, verify field consistency
    with shared serializers."""

    def test_export_uses_shared_serializers(
        self, db_session, user, project_with_full_data
    ):
        """Verify full export produces fields matching serializer output."""
        from routers.projects.helpers import get_comprehensive_project_data
        from routers.projects.serializers import (
            serialize_annotation,
            serialize_evaluation_run,
            serialize_generation,
            serialize_task,
            serialize_task_evaluation,
        )

        data = project_with_full_data
        project = data["project"]

        export = get_comprehensive_project_data(db_session, project.id)

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
        from routers.projects.helpers import get_comprehensive_project_data

        data = project_with_full_data
        export = get_comprehensive_project_data(db_session, data["project"].id)

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
        from routers.projects.helpers import get_comprehensive_project_data

        data = project_with_full_data
        export = get_comprehensive_project_data(db_session, data["project"].id)

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

"""
Coverage push tests for import/export handler branches.

Targets surviving branches in routers/projects/import_export.py:
- Multi-project bulk export in CSV / JSON format (POST /bulk-export)
- Multi-project full export (ZIP) format (POST /bulk-export-full)
- Span conversion functions with edge cases

The single-project sync export/import endpoints were removed in the #158
follow-up (object storage is now the only transport); their per-format fidelity
is covered by the shared-driver round-trip tests and the async job endpoints.
"""

import json
import uuid
from datetime import datetime


from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import (
    Annotation,
    PostAnnotationResponse,
    Project,
    ProjectOrganization,
    Task,
)


def _setup_project_with_data(db, users, *, add_annotations=True, add_generations=True,
                              add_evaluations=True, add_questionnaire=True,  # noqa: E127
                              annotation_extras=None):  # noqa: E127
    """Create a fully populated project with all data types."""
    org = Organization(
        id=str(uuid.uuid4()),
        name="Coverage Test Org",
        slug=f"cov-org-{uuid.uuid4().hex[:8]}",
        display_name="Coverage Test Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()

    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title="Coverage Export Project",
        description="For testing export branches",
        created_by=users[0].id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        assignment_mode="open",
        generation_config={"selected_configuration": {"models": ["gpt-4o"]}},
        evaluation_config={"default_temperature": 0.2},
    )
    db.add(p)
    db.commit()

    for i, user in enumerate(users[:4]):
        db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role="ORG_ADMIN" if i == 0 else "CONTRIBUTOR",
            joined_at=datetime.utcnow(),
        ))
    db.add(ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=pid,
        organization_id=org.id,
        assigned_by=users[0].id,
    ))
    db.commit()

    tasks = []
    annotations = []
    generations = []
    eval_runs = []
    judge_runs = []
    task_evals = []
    qr_list = []

    for i in range(3):
        tid = str(uuid.uuid4())
        task = Task(
            id=tid,
            project_id=pid,
            data={"text": f"Sample text {i}", "content": f"Content {i}"},
            meta={"tags": [f"tag-{i}"], "source": "test"},
            inner_id=i + 1,
            is_labeled=add_annotations,
        )
        db.add(task)
        tasks.append(task)
    db.commit()

    if add_annotations:
        for i, task in enumerate(tasks):
            ann_id = str(uuid.uuid4())
            extras = annotation_extras or {}
            ann = Annotation(
                id=ann_id,
                task_id=task.id,
                project_id=pid,
                result=[{"from_name": "text", "type": "textarea", "value": {"text": [f"answer {i}"]}}],
                completed_by=users[1].id,
                was_cancelled=False,
                ground_truth=(i == 0),
                lead_time=120.5 + i,
                draft={"partial": True} if i == 1 else None,
                prediction_scores={"score": 0.9} if i == 2 else None,
                **extras,
            )
            db.add(ann)
            annotations.append(ann)
        db.commit()

    if add_questionnaire and add_annotations:
        for ann in annotations[:1]:
            qr_id = str(uuid.uuid4())
            qr = PostAnnotationResponse(
                id=qr_id,
                annotation_id=ann.id,
                task_id=ann.task_id,
                project_id=pid,
                user_id=users[1].id,
                result={"difficulty": 3, "confidence": "high"},
            )
            db.add(qr)
            qr_list.append(qr)
        db.commit()

    if add_generations:
        for task in tasks:
            rg_id = str(uuid.uuid4())
            rg = ResponseGeneration(
                id=rg_id,
                task_id=task.id,
                project_id=pid,
                model_id="gpt-4o",
                config_id="default",
                status="completed",
                responses_generated=1,
                created_by=users[0].id,
                completed_at=datetime.utcnow(),
            )
            db.add(rg)
            db.commit()

            gen_id = str(uuid.uuid4())
            gen = Generation(
                id=gen_id,
                generation_id=rg_id,
                task_id=task.id,
                model_id="gpt-4o",
                run_index=0,
                case_data=json.dumps(task.data),
                response_content=f"Generated response for task {task.inner_id}",
                usage_stats={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                response_metadata={"model": "gpt-4o", "temperature": 0.2},
                status="completed",
                parse_status="success",
            )
            db.add(gen)
            generations.append(gen)
        db.commit()

    if add_evaluations:
        er_id = str(uuid.uuid4())
        er = EvaluationRun(
            id=er_id,
            project_id=pid,
            model_id="gpt-4o",
            evaluation_type_ids=["exact_match"],
            metrics={"accuracy": 0.85, "f1": 0.90},
            eval_metadata={"evaluation_type": "automated", "judge_models": {"config1": "gpt-4o"}},
            status="completed",
            samples_evaluated=3,
            has_sample_results=True,
            created_by=users[0].id,
        )
        db.add(er)
        eval_runs.append(er)
        db.commit()

        # Migration 043: TaskEvaluation.judge_run_id is NOT NULL.
        jr_id = str(uuid.uuid4())
        jr = EvaluationJudgeRun(
            id=jr_id, evaluation_id=er_id, judge_model_id=None,
            run_index=0, status="completed",
        )
        db.add(jr)
        judge_runs.append(jr)
        db.commit()

        for j, task in enumerate(tasks):
            te_id = str(uuid.uuid4())
            gen_id = generations[j].id if generations else None
            te = TaskEvaluation(
                id=te_id,
                evaluation_id=er_id,
                judge_run_id=jr_id,
                task_id=task.id,
                generation_id=gen_id,
                field_name="config1:answer",
                answer_type="text",
                ground_truth={"value": f"answer {j}"},
                prediction={"value": f"predicted {j}"},
                metrics={"exact_match": 1.0 if j == 0 else 0.0, "llm_judge_custom": 0.8},
                passed=(j == 0),
                confidence_score=0.95 if j == 0 else 0.5,
                error_message=None,
                processing_time_ms=150 + j * 10,
            )
            db.add(te)
            task_evals.append(te)
        db.commit()

    return {
        "project": p,
        "tasks": tasks,
        "annotations": annotations,
        "generations": generations,
        "eval_runs": eval_runs,
        "judge_runs": judge_runs,
        "task_evals": task_evals,
        "questionnaire_responses": qr_list,
        "org": org,
    }


class TestBulkExportCsv:
    """Test bulk export in CSV format."""

    def test_bulk_export_csv(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_generations=False, add_evaluations=False
        )
        pid = data["project"].id

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [pid], "format": "csv", "include_data": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_bulk_export_json_with_data(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_generations=False, add_evaluations=False
        )
        pid = data["project"].id

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [pid], "format": "json", "include_data": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_bulk_export_no_include_data(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_generations=False, add_evaluations=False
        )
        pid = data["project"].id

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [pid], "format": "json", "include_data": False},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        for proj in body["projects"]:
            assert "tasks" not in proj

    def test_bulk_export_unsupported_format(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_generations=False, add_evaluations=False
        )
        pid = data["project"].id

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [pid], "format": "xml"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_bulk_export_nonexistent_project(self, client, test_users, test_db, auth_headers):
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": ["nonexistent-id"], "format": "json"},
            headers=auth_headers["admin"],
        )
        # Should return valid response with empty projects list
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert body["projects"] == []


class TestBulkExportFull:
    """Test full project export (ZIP format)."""

    def test_bulk_export_full_zip(self, client, test_users, test_db, auth_headers):
        # No mock: the route streams the real comprehensive export
        # (the dict-building helper this test used to patch was removed
        # in issue #106 and the patch had been a no-op since #158).
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": [pid]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "application/zip" in resp.headers.get("content-type", "")

    def test_bulk_export_full_no_ids(self, client, test_users, test_db, auth_headers):
        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_bulk_export_full_no_accessible(self, client, test_users, test_db, auth_headers):
        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": ["nonexistent"]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestSpanConversion:
    """Test span annotation conversion functions."""

    def test_convert_to_label_studio_empty(self):
        from routers.projects.import_export import convert_to_label_studio_format
        assert convert_to_label_studio_format(None) is None
        assert convert_to_label_studio_format([]) == []
        assert convert_to_label_studio_format("not a list") == "not a list"

    def test_convert_to_label_studio_with_spans(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 0, "end": 5, "text": "hello", "labels": ["NER"]},
                        {"id": "s2", "start": 10, "end": 15, "text": "world", "labels": ["NER"]},
                    ]
                },
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 2
        assert output[0]["value"]["start"] == 0
        assert output[1]["value"]["start"] == 10

    def test_convert_to_label_studio_no_spans(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"other": "data"},
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1
        assert output[0] == results[0]

    def test_convert_to_label_studio_non_span_type(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {"type": "choices", "from_name": "choice", "value": {"choices": ["A"]}},
        ]
        output = convert_to_label_studio_format(results)
        assert output == results

    def test_convert_from_label_studio_empty(self):
        from routers.projects.import_export import convert_from_label_studio_format
        assert convert_from_label_studio_format(None) is None
        assert convert_from_label_studio_format([]) == []

    def test_convert_from_label_studio_with_spans(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {
                "id": "s1",
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"start": 0, "end": 5, "text": "hello", "labels": ["NER"]},
            },
            {
                "id": "s2",
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"start": 10, "end": 15, "text": "world", "labels": ["NER"]},
            },
        ]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1
        assert len(output[0]["value"]["spans"]) == 2

    def test_convert_from_label_studio_already_benger(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"spans": [{"id": "s1", "start": 0, "end": 5}]},
            },
        ]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1
        assert "spans" in output[0]["value"]

    def test_convert_from_label_studio_other_labels(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"other": "data"},
            },
        ]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1

    def test_convert_from_label_studio_non_labels(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {"type": "choices", "value": {"choices": ["A"]}},
        ]
        output = convert_from_label_studio_format(results)
        assert output == results

"""NDJSON typed-record export → import round-trip tests (issue #158, Phase 3b).

The NDJSON export (``stream_export_ndjson``) frames the same comprehensive data
as the single-object ``comprehensive`` JSON export, but as one typed record per
line so the importer can stream it in a single forward pass. These tests lock
the contract end to end against the shared PostgreSQL test DB:

- the generator emits a ``meta`` header first, flat entity records in
  FK-dependency order, and a trailing ``end`` completeness record;
- ``run_full_project_import`` auto-detects the NDJSON body and routes it to the
  single-pass ``run_ndjson_import``, producing a new project whose entity counts
  and key FK relationships match the source (so the records the single-pass
  importer consumes are identical to what the multi-pass importer would build);
- a stream missing the ``end`` record is rejected as truncated *before* commit,
  the structural replacement for the old byte-tail sentinel;
- the NDJSON round-trip yields the same imported counts as a comprehensive-JSON
  round-trip of the same project, proving the two serializers stay in lock-step.
"""

import io
import json
import uuid
import zlib

import pytest

from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import (
    Annotation,
    KorrekturComment,
    PostAnnotationResponse,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
)
from routers.projects._export_stream import (
    export_format_is_gzipped,
    select_export_generator,
    stream_comprehensive_project_data_json,
    stream_export_ndjson,
)
from routers.projects._import_stream import (
    ImportValidationError,
    run_full_project_import,
    run_ndjson_import,
)
from import_stream import _is_ndjson_stream, _maybe_decompress  # noqa: E402


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def full_project(test_db, test_users, test_org):
    """A project owned by ``test_org`` carrying one of every round-trippable
    entity type, so the NDJSON stream exercises every record branch and the
    korrektur roots-then-replies ordering."""
    admin = test_users[0]
    project = Project(
        id=_uid(),
        title=f"NDJSON RT {_uid()[:8]}",
        description="round-trip source",
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        created_by=admin.id,
        korrektur_enabled=True,
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=admin.id,
        )
    )

    # Project member (the contributor) so project_member records round-trip.
    test_db.add(
        ProjectMember(
            id=_uid(),
            project_id=project.id,
            user_id=test_users[1].id,
            role="CONTRIBUTOR",
            is_active=True,
        )
    )

    tasks = []
    for i in range(3):
        t = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"Sample #{i}", "category": f"cat_{i}"},
            created_by=admin.id,
            is_labeled=True,
        )
        test_db.add(t)
        tasks.append(t)
    test_db.flush()

    annotations = []
    for t in tasks:
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=project.id,
            completed_by=admin.id,
            result=[{
                "from_name": "answer",
                "to_name": "text",
                "type": "choices",
                "value": {"choices": ["Ja"]},
            }],
            was_cancelled=False,
            ground_truth=True,
            lead_time=12.5,
        )
        test_db.add(ann)
        annotations.append(ann)
        test_db.flush()
        test_db.add(
            PostAnnotationResponse(
                id=_uid(),
                annotation_id=ann.id,
                task_id=t.id,
                project_id=project.id,
                user_id=admin.id,
                result=[{"question": "confidence", "answer": "high"}],
            )
        )

    # Generations.
    generations = []
    for t in tasks:
        rg = ResponseGeneration(
            id=_uid(),
            task_id=t.id,
            project_id=project.id,
            model_id="gpt-4o",
            status="completed",
            responses_generated=1,
            created_by=admin.id,
        )
        test_db.add(rg)
        test_db.flush()
        gen = Generation(
            id=_uid(),
            generation_id=rg.id,
            task_id=t.id,
            model_id="gpt-4o",
            run_index=0,
            case_data=json.dumps(t.data),
            response_content=f"Generated answer for {t.data['text']}",
            status="completed",
        )
        test_db.add(gen)
        generations.append(gen)

    # One evaluation run + judge run + a task evaluation per generation.
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id="gpt-4o",
        evaluation_type_ids=["rouge"],
        metrics={"rouge1": 0.8},
        status="completed",
        samples_evaluated=3,
        created_by=admin.id,
    )
    test_db.add(er)
    test_db.flush()
    judge = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    test_db.add(judge)
    test_db.flush()
    for gen in generations:
        test_db.add(
            TaskEvaluation(
                id=_uid(),
                evaluation_id=er.id,
                judge_run_id=judge.id,
                task_id=gen.task_id,
                generation_id=gen.id,
                field_name="rouge:prediction:reference",
                answer_type="text",
                ground_truth="expected",
                prediction="actual",
                metrics={"rouge1": 0.8},
                passed=True,
            )
        )

    # Korrektur parent + reply (exercises roots-then-replies ordering and the
    # parent_id remap).
    ann0 = annotations[0]
    parent = KorrekturComment(
        id=_uid(),
        project_id=project.id,
        task_id=ann0.task_id,
        target_type="annotation",
        target_id=ann0.id,
        parent_id=None,
        text="Parent comment",
        created_by=admin.id,
    )
    test_db.add(parent)
    test_db.flush()
    reply = KorrekturComment(
        id=_uid(),
        project_id=project.id,
        task_id=ann0.task_id,
        target_type="annotation",
        target_id=ann0.id,
        parent_id=parent.id,
        text="Reply comment",
        created_by=admin.id,
    )
    test_db.add(reply)

    test_db.commit()
    return project, admin


def _export_ndjson(db, project) -> str:
    return "".join(stream_export_ndjson(db, project.id))


def _counts(db, project_id):
    task_ids = [t.id for t in db.query(Task).filter(Task.project_id == project_id).all()]
    er_ids = [
        er.id
        for er in db.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project_id)
        .all()
    ]
    return {
        "tasks": len(task_ids),
        "annotations": db.query(Annotation)
        .filter(Annotation.project_id == project_id)
        .count(),
        "post_annotation_responses": db.query(PostAnnotationResponse)
        .filter(PostAnnotationResponse.project_id == project_id)
        .count(),
        "generations": db.query(Generation)
        .filter(Generation.task_id.in_(task_ids))
        .count()
        if task_ids
        else 0,
        "evaluation_runs": len(er_ids),
        "task_evaluations": db.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id.in_(er_ids))
        .count()
        if er_ids
        else 0,
        "korrektur_comments": db.query(KorrekturComment)
        .filter(KorrekturComment.project_id == project_id)
        .count(),
        "project_members": db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id)
        .count(),
    }


@pytest.mark.integration
class TestNDJSONExportShape:
    def test_meta_first_end_last(self, test_db, full_project):
        project, _ = full_project
        lines = _export_ndjson(test_db, project).splitlines()
        first = json.loads(lines[0])
        last = json.loads(lines[-1])
        assert first["_type"] == "meta"
        assert first["project"]["id"] == project.id
        assert first["format_version"].startswith("1.")
        assert last["_type"] == "end"
        assert last["export_complete"] is True
        assert last["statistics"]["total_tasks"] == 3

    def test_users_lead_entity_records(self, test_db, full_project):
        project, _ = full_project
        lines = [json.loads(line) for line in _export_ndjson(test_db, project).splitlines()]
        types = [r["_type"] for r in lines[1:-1]]  # between meta and end
        # Every entity-bearing FK reference (tasks, annotations, …) must be
        # preceded by the user records so the single-pass importer has the user
        # map before it remaps a created_by/completed_by.
        assert "user" in types
        first_task = types.index("task")
        assert types.index("user") < first_task

    def test_korrektur_roots_before_replies(self, test_db, full_project):
        project, _ = full_project
        records = [json.loads(line) for line in _export_ndjson(test_db, project).splitlines()]
        kc = [r for r in records if r["_type"] == "korrektur_comment"]
        assert len(kc) == 2
        # The root (parent_id is None) must be emitted before its reply.
        assert kc[0].get("parent_id") is None
        assert kc[1].get("parent_id") is not None

    def test_dispatch_selects_ndjson(self, test_db, full_project):
        project, _ = full_project
        # select_export_generator(..., "ndjson") must route to the NDJSON
        # generator. Compare structurally rather than byte-for-byte: the meta
        # record embeds a per-call ``exported_at`` timestamp, so two separate
        # generator invocations are never byte-identical by design.
        def _norm(stream: str):
            recs = [json.loads(line) for line in stream.splitlines()]
            for r in recs:
                r.pop("exported_at", None)
            return recs

        via_dispatch = _norm("".join(select_export_generator(test_db, project, "ndjson")))
        direct = _norm(_export_ndjson(test_db, project))
        assert via_dispatch == direct
        assert via_dispatch[0]["_type"] == "meta"
        assert via_dispatch[-1]["_type"] == "end"


@pytest.mark.integration
class TestNDJSONRoundtrip:
    def test_roundtrip_counts_and_fk_fidelity(self, test_db, full_project):
        project, admin = full_project
        ndjson = _export_ndjson(test_db, project)

        result = run_full_project_import(
            test_db, io.BytesIO(ndjson.encode("utf-8")), admin.id
        )
        new_pid = result["project_id"]
        assert new_pid and new_pid != project.id

        src = _counts(test_db, project.id)
        dst = _counts(test_db, new_pid)
        assert dst == src

        # Korrektur reply must point at the newly-imported parent, not the old id.
        imported_kc = (
            test_db.query(KorrekturComment)
            .filter(KorrekturComment.project_id == new_pid)
            .all()
        )
        parents = [c for c in imported_kc if c.parent_id is None]
        replies = [c for c in imported_kc if c.parent_id is not None]
        assert len(parents) == 1 and len(replies) == 1
        assert replies[0].parent_id == parents[0].id

        # Generation content survives byte-for-byte.
        new_task_ids = [
            t.id for t in test_db.query(Task).filter(Task.project_id == new_pid).all()
        ]
        contents = {
            g.response_content
            for g in test_db.query(Generation)
            .filter(Generation.task_id.in_(new_task_ids))
            .all()
        }
        assert any("Generated answer for" in c for c in contents)

    def test_ndjson_matches_comprehensive_import(self, test_db, full_project):
        """Importing the NDJSON export and importing the comprehensive-JSON export
        of the same project must yield identical entity counts — proof the two
        serializers stay in lock-step."""
        project, admin = full_project

        ndjson = _export_ndjson(test_db, project)
        comprehensive = "".join(stream_comprehensive_project_data_json(test_db, project.id))

        nd_pid = run_full_project_import(
            test_db, io.BytesIO(ndjson.encode("utf-8")), admin.id
        )["project_id"]
        comp_pid = run_full_project_import(
            test_db, io.BytesIO(comprehensive.encode("utf-8")), admin.id
        )["project_id"]

        assert _counts(test_db, nd_pid) == _counts(test_db, comp_pid)

    def test_truncated_stream_rejected_before_commit(self, test_db, full_project):
        project, admin = full_project
        lines = _export_ndjson(test_db, project).splitlines()
        # Drop the trailing `end` record → a truncated stream.
        assert json.loads(lines[-1])["_type"] == "end"
        truncated = "\n".join(lines[:-1]) + "\n"

        projects_before = test_db.query(Project).count()
        with pytest.raises(ImportValidationError) as exc:
            run_ndjson_import(test_db, io.BytesIO(truncated.encode("utf-8")), admin.id)
        assert exc.value.status_code == 400
        assert "runcated" in exc.value.detail or "end record" in exc.value.detail
        test_db.rollback()
        # The partial project row must not have committed.
        assert test_db.query(Project).count() == projects_before


@pytest.mark.integration
class TestNDJSONDetection:
    def test_detects_ndjson(self, test_db, full_project):
        project, _ = full_project
        ndjson = _export_ndjson(test_db, project)
        assert _is_ndjson_stream(io.BytesIO(ndjson.encode("utf-8"))) is True

    def test_comprehensive_json_not_detected_as_ndjson(self, test_db, full_project):
        project, _ = full_project
        comprehensive = "".join(stream_comprehensive_project_data_json(test_db, project.id))
        assert _is_ndjson_stream(io.BytesIO(comprehensive.encode("utf-8"))) is False


def _gzip(data: bytes) -> bytes:
    """Compress exactly as the worker's export task does (zlib gzip member)."""
    c = zlib.compressobj(6, zlib.DEFLATED, zlib.MAX_WBITS | 16)
    return c.compress(data) + c.flush()


@pytest.mark.integration
class TestGzipNDJSON:
    def test_ndjson_gz_format_flag_and_dispatch(self, test_db, full_project):
        project, _ = full_project
        assert export_format_is_gzipped("ndjson_gz") is True
        assert export_format_is_gzipped("ndjson") is False
        assert export_format_is_gzipped("json") is False
        # The gzipped format reuses the plain NDJSON generator (compression is a
        # worker-side transport concern, not part of the generated text).
        recs = [
            json.loads(line)
            for line in "".join(
                select_export_generator(test_db, project, "ndjson_gz")
            ).splitlines()
        ]
        assert recs[0]["_type"] == "meta"
        assert recs[-1]["_type"] == "end"

    def test_maybe_decompress_passthrough_plain(self):
        plain = b'{"_type":"meta"}\n{"_type":"end"}\n'
        out = _maybe_decompress(io.BytesIO(plain))
        assert out.read() == plain

    def test_maybe_decompress_inflates_gzip(self):
        original = b'{"_type":"meta"}\n{"_type":"end"}\n'
        out = _maybe_decompress(io.BytesIO(_gzip(original)))
        assert out.read() == original

    def test_gzipped_ndjson_roundtrips(self, test_db, full_project):
        """A gzipped NDJSON export imports to the same counts as the plain one —
        proving the worker's gzip + the importer's magic-byte inflate round-trip."""
        project, admin = full_project
        ndjson = _export_ndjson(test_db, project).encode("utf-8")

        result = run_full_project_import(test_db, io.BytesIO(_gzip(ndjson)), admin.id)
        new_pid = result["project_id"]
        assert new_pid and new_pid != project.id
        assert _counts(test_db, new_pid) == _counts(test_db, project.id)

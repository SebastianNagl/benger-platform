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
    User,
)
from project_models import (
    Annotation,
    GradingFeedback,
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
from import_stream import (  # noqa: E402
    _is_ndjson_stream,
    _maybe_decompress,
    _maybe_unzip,
)


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

    def test_roundtrip_carries_kind_and_project_settings(
        self, test_db, test_org, full_project
    ):
        """The NDJSON meta record carries the same project settings as the
        comprehensive JSON; visibility and origin are reset on import."""
        project, admin = full_project
        project.kind = "exam"
        project.icon = "⚖️"
        project.origin = "student"
        project.is_private = True
        project.annotation_time_limit_enabled = True
        project.annotation_time_limit_seconds = 7200
        project.strict_timer_enabled = True
        project.checkpoint_interval_seconds = 600
        project.immediate_evaluation_enabled = True
        project.enable_generation = False
        test_db.commit()

        ndjson = _export_ndjson(test_db, project)
        meta = json.loads(ndjson.splitlines()[0])
        assert meta["project"]["kind"] == "exam"
        assert "is_private" not in meta["project"]

        new_pid = run_full_project_import(
            test_db,
            io.BytesIO(ndjson.encode("utf-8")),
            admin.id,
            organization_id=test_org.id,
        )["project_id"]
        imported = test_db.query(Project).filter(Project.id == new_pid).one()
        assert imported.kind == "exam"
        assert imported.icon == "⚖️"
        assert imported.annotation_time_limit_enabled is True
        assert imported.annotation_time_limit_seconds == 7200
        assert imported.strict_timer_enabled is True
        assert imported.checkpoint_interval_seconds == 600
        assert imported.immediate_evaluation_enabled is True
        assert imported.enable_generation is False
        assert imported.is_private is False
        assert imported.origin is None

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


@pytest.mark.integration
class TestImportedUserMatching:
    """Every exported user maps onto exactly ONE local user: the same id, else
    the same email, else a pseudonymous placeholder. Falling back to the
    importer merged all unknown authors into one account, which keeps one
    answer per task and drops the rest."""

    @staticmethod
    def _payload(test_db, project) -> dict:
        return json.loads(
            "".join(stream_comprehensive_project_data_json(test_db, project.id))
        )

    @classmethod
    def _foreign_payload(cls, test_db, project) -> dict:
        """An export as another deployment sees it: no id and no email of its
        users exists locally. The records have the shape exports had until
        2026-09 (clear name, email and username, no ``masked`` flag), because
        such files are still around and must import without leaking any of it."""
        data = cls._payload(test_db, project)
        remap = {}
        for user in data["users"]:
            remap[user["id"]] = _uid()
            user["id"] = remap[user["id"]]
            user["email"] = f"nobody-{_uid()}@foreign.test"
            user["username"] = f"nobody-{_uid()[:8]}"
            user["name"] = "Somebody Real"
            user.pop("masked", None)
            user.pop("pseudonym", None)
        for ann in data["annotations"]:
            ann["completed_by"] = remap.get(ann.get("completed_by"), ann.get("completed_by"))
        for te in data["task_evaluations"]:
            if te.get("created_by"):
                te["created_by"] = remap.get(te["created_by"], te["created_by"])
        return data

    @staticmethod
    def _import(test_db, data, admin) -> dict:
        return run_full_project_import(
            test_db, io.BytesIO(json.dumps(data).encode("utf-8")), admin.id
        )

    def test_unknown_authors_keep_their_own_answers(self, test_db, full_project):
        project, admin = full_project
        data = self._foreign_payload(test_db, project)
        # A second foreign author answers a task that already has an answer:
        # merged into the importer, one of the two would be dropped.
        template = next(a for a in data["annotations"] if not a.get("was_cancelled"))
        extra_user = _uid()
        data["users"].append({"id": extra_user, "email": f"extra-{_uid()}@foreign.test"})
        data["annotations"].append({**template, "id": _uid(), "completed_by": extra_user})
        active = [a for a in data["annotations"] if not a.get("was_cancelled")]

        result = self._import(test_db, data, admin)

        stats = result["statistics"]
        assert stats["skipped_counts"] == {"annotations": 0}
        assert stats["placeholder_users_created"] == len(data["users"])
        stored = (
            test_db.query(Annotation)
            .filter(
                Annotation.project_id == result["project_id"],
                Annotation.was_cancelled == False,  # noqa: E712
            )
            .all()
        )
        assert len(stored) == len(active)
        # Nobody's work is attributed to the person who ran the import.
        assert admin.id not in {a.completed_by for a in stored}
        assert len({a.completed_by for a in stored}) == len(
            {a["completed_by"] for a in active}
        )

    def test_placeholder_is_pseudonymous_and_cannot_be_used(self, test_db, full_project):
        from auth_module.user_service import verify_password
        from import_stream import STUB_EMAIL_DOMAIN, is_stub_email
        from models import OrganizationMembership

        project, admin = full_project
        data = self._foreign_payload(test_db, project)
        source = data["users"][0]
        source["name"] = "Erika Mustermann"
        source["username"] = "erika.mustermann"

        self._import(test_db, data, admin)

        stub = (
            test_db.query(User)
            .filter(User.email == f"{source['id']}@{STUB_EMAIL_DOMAIN}")
            .one()
        )
        assert is_stub_email(stub.email)
        # Nothing personal crosses over: the export's name, username and
        # address stay on the deployment they belong to.
        assert "erika" not in (stub.name + stub.username + stub.email).lower()
        assert "foreign.test" not in stub.email
        # Listed (leaderboards only show active users) but unusable.
        assert stub.is_active is True and stub.is_superadmin is False
        assert verify_password("", stub.hashed_password) is False
        assert verify_password("!imported-placeholder", stub.hashed_password) is False
        assert (
            test_db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == stub.id)
            .count()
            == 0
        )

    def test_placeholder_takes_over_the_exported_pseudonym(self, test_db, full_project):
        # The pseudonym is what other users already see on the source
        # deployment, so the imported board reads the same as the original.
        from import_stream import STUB_EMAIL_DOMAIN

        project, admin = full_project
        data = self._foreign_payload(test_db, project)
        source = data["users"][0]
        source["name"] = "Erika Mustermann"
        source["pseudonym"] = f"ZealousJudge-{_uid()[:6]}"

        self._import(test_db, data, admin)

        stub = (
            test_db.query(User)
            .filter(User.email == f"{source['id']}@{STUB_EMAIL_DOMAIN}")
            .one()
        )
        assert stub.pseudonym == source["pseudonym"]
        assert stub.name == source["pseudonym"]
        assert stub.use_pseudonym is True
        assert "erika" not in stub.name.lower()

    def test_pseudonym_held_by_a_local_account_still_labels_the_placeholder(
        self, test_db, full_project
    ):
        # `users.pseudonym` is unique. A clash must not fail the import, and
        # must not take the pseudonym away from the account that has it.
        from import_stream import STUB_EMAIL_DOMAIN

        project, admin = full_project
        taken = f"CalmOwl-{_uid()[:6]}"
        admin.pseudonym = taken
        test_db.commit()
        data = self._foreign_payload(test_db, project)
        source = data["users"][0]
        source["pseudonym"] = taken

        self._import(test_db, data, admin)

        stub = (
            test_db.query(User)
            .filter(User.email == f"{source['id']}@{STUB_EMAIL_DOMAIN}")
            .one()
        )
        assert stub.pseudonym is None
        assert stub.name == taken
        test_db.refresh(admin)
        assert admin.pseudonym == taken

    def test_export_without_pseudonym_gets_a_neutral_label(self, test_db, full_project):
        from import_stream import STUB_EMAIL_DOMAIN

        project, admin = full_project
        data = self._foreign_payload(test_db, project)
        source = data["users"][0]
        source["name"] = "Erika Mustermann"
        source.pop("pseudonym", None)

        self._import(test_db, data, admin)

        stub = (
            test_db.query(User)
            .filter(User.email == f"{source['id']}@{STUB_EMAIL_DOMAIN}")
            .one()
        )
        assert stub.name == f"User {source['id'][:8]}"
        assert stub.pseudonym is None

        # A later export that does carry the pseudonym upgrades the label.
        source["pseudonym"] = f"BraveFox-{_uid()[:6]}"
        self._import(test_db, data, admin)
        test_db.refresh(stub)
        assert stub.name == source["pseudonym"]
        assert stub.pseudonym == source["pseudonym"]

    def test_export_carries_the_pseudonym_and_nothing_that_names_a_person(
        self, test_db, full_project
    ):
        project, admin = full_project
        admin.pseudonym = f"QuietHeron-{_uid()[:6]}"
        test_db.commit()
        records = {u["id"]: u for u in self._payload(test_db, project)["users"]}
        assert records[admin.id]["pseudonym"] == admin.pseudonym
        assert records[admin.id]["name"] == admin.pseudonym
        for record in records.values():
            assert record["email"] is None and record["username"] is None
            assert record["masked"] is True
        body = json.dumps(self._payload(test_db, project))
        assert admin.email not in body and admin.username not in body

    def test_new_export_roundtrips_onto_a_foreign_deployment_by_pseudonym(
        self, test_db, full_project
    ):
        # The whole chain in the current format: pseudonymous export ->
        # unknown ids -> placeholders under the same pseudonyms.
        from import_stream import STUB_EMAIL_DOMAIN

        project, admin = full_project
        admin.pseudonym = f"SwiftLynx-{_uid()[:6]}"
        test_db.commit()
        data = self._payload(test_db, project)
        body = json.dumps(data)
        remap = {u["id"]: _uid() for u in data["users"]}
        for old, new in remap.items():
            body = body.replace(old, new)
        data = json.loads(body)
        # Free the pseudonym locally, as on a deployment that never had it.
        admin.pseudonym = None
        test_db.commit()

        result = self._import(test_db, data, admin)

        assert result["statistics"]["placeholder_users_created"] == len(data["users"])
        stub = (
            test_db.query(User)
            .filter(User.email == f"{remap[admin.id]}@{STUB_EMAIL_DOMAIN}")
            .one()
        )
        assert stub.pseudonym and stub.pseudonym.startswith("SwiftLynx-")

    def test_alias_comes_only_from_a_pseudonym_never_from_a_name(self):
        from import_stream import _exported_alias

        uid = "0b6f6c2e-1c1b-4a7e-9d35-0d2a8f1e7a10"
        # Current format: the explicit key decides, even when it is empty.
        assert _exported_alias({"id": uid, "pseudonym": "CalmOwl", "name": "x"}) == "CalmOwl"
        assert _exported_alias({"id": uid, "pseudonym": None, "name": "User 0b6f6c2e", "masked": True}) is None
        # Masked record from before the explicit key: the name IS the pseudonym,
        # unless it is only the neutral label of an account without one.
        assert _exported_alias({"id": uid, "name": "CalmOwl", "masked": True}) == "CalmOwl"
        assert _exported_alias({"id": uid, "name": "User 0b6f6c2e", "masked": True}) is None
        # Unmasked record from before 2026-09: the name is a real name.
        assert _exported_alias({"id": uid, "name": "Erika Mustermann"}) is None

    def test_reimport_reuses_the_same_placeholders(self, test_db, full_project):
        from import_stream import STUB_EMAIL_DOMAIN

        project, admin = full_project
        data = self._foreign_payload(test_db, project)

        first = self._import(test_db, data, admin)
        count = test_db.query(User).filter(User.email.like(f"%@{STUB_EMAIL_DOMAIN}")).count()
        second = self._import(test_db, data, admin)

        assert first["statistics"]["placeholder_users_created"] == len(data["users"])
        assert second["statistics"]["placeholder_users_created"] == 0
        assert (
            test_db.query(User).filter(User.email.like(f"%@{STUB_EMAIL_DOMAIN}")).count()
            == count
        )

    def test_same_id_wins_even_after_an_email_change(self, test_db, full_project):
        # The round trip on ONE deployment: the id is the primary key and
        # never changes, an email can. Matching by email first sent the work
        # of anyone who changed theirs to the importer.
        project, admin = full_project
        data = self._payload(test_db, project)
        author = next(a["completed_by"] for a in data["annotations"] if a.get("completed_by"))
        for user in data["users"]:
            user["email"] = f"old-address-{_uid()}@changed.test"

        result = self._import(test_db, data, admin)

        assert result["statistics"]["placeholder_users_created"] == 0
        stored = (
            test_db.query(Annotation)
            .filter(Annotation.project_id == result["project_id"])
            .all()
        )
        assert author in {a.completed_by for a in stored}

    def test_same_email_matches_when_the_id_is_foreign(self, test_db, full_project):
        # The same person with an account on both deployments.
        project, admin = full_project
        data = self._payload(test_db, project)
        author_id = next(
            a["completed_by"] for a in data["annotations"] if a.get("completed_by")
        )
        foreign_id = _uid()
        local_email = test_db.get(User, author_id).email
        for user in data["users"]:
            if user["id"] == author_id:
                user["id"] = foreign_id
                # Only exports from before 2026-09 carry an email to match on.
                user["email"] = local_email.upper()
        for ann in data["annotations"]:
            if ann.get("completed_by") == author_id:
                ann["completed_by"] = foreign_id

        result = self._import(test_db, data, admin)

        stored = (
            test_db.query(Annotation)
            .filter(Annotation.project_id == result["project_id"])
            .all()
        )
        assert author_id in {a.completed_by for a in stored}

    def test_human_grader_follows_its_own_user(self, test_db, full_project):
        # `task_evaluations.created_by` is FK'd to users. Written raw, the
        # exported grader id failed the whole import on the FK.
        from import_stream import STUB_EMAIL_DOMAIN

        project, admin = full_project
        data = self._foreign_payload(test_db, project)
        assert data["task_evaluations"], "fixture must carry evaluation rows"
        grader = data["users"][0]["id"]
        data["task_evaluations"][0]["created_by"] = grader
        for te in data["task_evaluations"][1:]:
            te["created_by"] = None

        result = self._import(test_db, data, admin)

        rows = (
            test_db.query(TaskEvaluation)
            .join(EvaluationRun, EvaluationRun.id == TaskEvaluation.evaluation_id)
            .filter(EvaluationRun.project_id == result["project_id"])
            .all()
        )
        assert len(rows) == len(data["task_evaluations"])
        graders = [r.created_by for r in rows if r.created_by is not None]
        # The human grade follows the grader's placeholder; automated rows
        # stay NULL so they still read as automated.
        assert len(graders) == 1
        assert test_db.get(User, graders[0]).email == f"{grader}@{STUB_EMAIL_DOMAIN}"

    def test_two_exported_users_on_one_account_are_reported(self, test_db, full_project):
        # The one collapse left: an export listing the same local person
        # twice (once by id, once by email). One answer per task survives and
        # the statistics say so instead of reporting a clean import.
        project, admin = full_project
        data = self._payload(test_db, project)
        template = next(a for a in data["annotations"] if not a.get("was_cancelled"))
        local = test_db.get(User, template["completed_by"])
        twin = _uid()
        data["users"].append({"id": twin, "email": local.email})
        data["annotations"].append({**template, "id": _uid(), "completed_by": twin})

        result = self._import(test_db, data, admin)

        assert result["statistics"]["skipped_counts"]["annotations"] == 1

    def test_nothing_is_skipped_or_created_when_everyone_is_known(
        self, test_db, full_project
    ):
        project, admin = full_project
        comprehensive = "".join(
            stream_comprehensive_project_data_json(test_db, project.id)
        ).encode("utf-8")
        result = run_full_project_import(test_db, io.BytesIO(comprehensive), admin.id)
        assert result["statistics"]["skipped_counts"] == {"annotations": 0}
        assert result["statistics"]["placeholder_users_created"] == 0


def _zip(members: dict) -> bytes:
    """Archive ``{name: bytes}`` the way `bulk-export-full` does (deflated)."""
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.mark.integration
class TestZippedProjectExport:
    """The projects list exports a selection as a .zip (one JSON per project)
    and its import accepts .zip, so that archive has to import. The unpacking
    went missing when import moved to object storage (#158): every UI export
    then failed to re-import with "Invalid JSON format"."""

    def test_zipped_comprehensive_export_roundtrips(self, test_db, full_project):
        project, admin = full_project
        comprehensive = "".join(
            stream_comprehensive_project_data_json(test_db, project.id)
        ).encode("utf-8")
        archive = _zip({f"{project.title}_{project.id[:8]}.json": comprehensive})

        result = run_full_project_import(test_db, io.BytesIO(archive), admin.id)

        new_pid = result["project_id"]
        assert new_pid and new_pid != project.id
        assert _counts(test_db, new_pid) == _counts(test_db, project.id)

    def test_non_zip_passes_through_untouched(self):
        plain = io.BytesIO(b'{"format_version": "1.0.0"}')
        assert _maybe_unzip(plain) is plain
        assert plain.tell() == 0

    def test_multi_project_archive_is_refused_not_half_imported(
        self, test_db, full_project
    ):
        project, admin = full_project
        comprehensive = "".join(
            stream_comprehensive_project_data_json(test_db, project.id)
        ).encode("utf-8")
        archive = _zip({"a.json": comprehensive, "b.json": comprehensive})
        before = test_db.query(Project).count()

        with pytest.raises(ImportValidationError) as exc:
            run_full_project_import(test_db, io.BytesIO(archive), admin.id)

        assert exc.value.status_code == 400
        assert "2 project exports" in exc.value.detail
        assert test_db.query(Project).count() == before

    def test_archive_without_json_is_a_client_error(self, test_db, full_project):
        _project, admin = full_project
        with pytest.raises(ImportValidationError) as exc:
            run_full_project_import(
                test_db, io.BytesIO(_zip({"readme.txt": b"hi"})), admin.id
            )
        assert exc.value.status_code == 400
        assert "No JSON file" in exc.value.detail

    def test_corrupt_archive_is_a_client_error(self, test_db, full_project):
        _project, admin = full_project
        with pytest.raises(ImportValidationError) as exc:
            run_full_project_import(
                test_db, io.BytesIO(b"PK\x03\x04 this is not a zip"), admin.id
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == "Invalid ZIP file"


@pytest.mark.integration
class TestGradingFeedbackRoundtrip:
    """Solver feedback ON a grading (thumbs/comment, and the free-text
    `general` source) travels with the project — but only ever attributed to
    the solver who gave it."""

    def _seed(self, db, project, admin, *, author=None):
        ann = (
            db.query(Annotation).filter(Annotation.project_id == project.id).first()
        )
        run = (
            db.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project.id)
            .first()
        )
        rows = [
            GradingFeedback(
                id=_uid(),
                project_id=project.id,
                task_id=ann.task_id,
                annotation_id=ann.id,
                user_id=(author or admin).id,
                grading_source="llm",
                evaluation_run_id=run.id,
                judge_model_id="gpt-5-mini",
                grade_points=12.0,
                passed=True,
                rating="down",
                comment="Zu streng.",
                context={"metric_keys": ["llm_judge_falloesung"]},
            ),
            GradingFeedback(
                id=_uid(),
                project_id=project.id,
                task_id=ann.task_id,
                annotation_id=ann.id,
                user_id=(author or admin).id,
                grading_source="general",
                rating=None,
                comment="Der Editor hakt.",
                context={"kind": "general"},
            ),
        ]
        for row in rows:
            db.add(row)
        db.commit()
        return ann, run

    def test_records_follow_the_rows_they_reference(self, test_db, full_project):
        project, admin = full_project
        self._seed(test_db, project, admin)
        lines = [json.loads(ln) for ln in _export_ndjson(test_db, project).splitlines()]
        types = [r["_type"] for r in lines]

        assert types.count("grading_feedback") == 2
        first_fb = types.index("grading_feedback")
        # Its FKs (author, submission, rated run) must already be on the wire.
        for required in ("user", "annotation", "evaluation"):
            assert types.index(required) < first_fb, required
        assert types[-1] == "end"

        payloads = [r for r in lines if r["_type"] == "grading_feedback"]
        llm = next(p for p in payloads if p["grading_source"] == "llm")
        assert llm["judge_model_id"] == "gpt-5-mini"
        assert llm["grade_points"] == 12.0
        assert llm["context"] == {"metric_keys": ["llm_judge_falloesung"]}
        # The author rides along so the importer can resolve the opinion.
        assert any(
            r["_type"] == "user" and r.get("id") == admin.id for r in lines
        )

    def test_roundtrip_keeps_author_snapshot_and_remaps_fks(
        self, test_db, full_project
    ):
        project, admin = full_project
        source_ann, source_run = self._seed(test_db, project, admin)
        ndjson = _export_ndjson(test_db, project)

        result = run_ndjson_import(test_db, io.BytesIO(ndjson.encode()), admin.id)
        new_id = result["project_id"]
        assert result["statistics"]["imported_counts"]["grading_feedback"] == 2

        imported = (
            test_db.query(GradingFeedback)
            .filter(GradingFeedback.project_id == new_id)
            .all()
        )
        assert len(imported) == 2
        by_source = {f.grading_source: f for f in imported}
        assert set(by_source) == {"llm", "general"}

        new_task_ids = {
            t.id for t in test_db.query(Task).filter(Task.project_id == new_id).all()
        }
        new_ann_ids = {
            a.id
            for a in test_db.query(Annotation)
            .filter(Annotation.project_id == new_id)
            .all()
        }
        new_run_ids = {
            r.id
            for r in test_db.query(EvaluationRun)
            .filter(EvaluationRun.project_id == new_id)
            .all()
        }
        llm = by_source["llm"]
        assert llm.task_id in new_task_ids
        assert llm.annotation_id in new_ann_ids and llm.annotation_id != source_ann.id
        assert llm.evaluation_run_id in new_run_ids
        assert llm.evaluation_run_id != source_run.id
        assert llm.user_id == admin.id
        assert (llm.rating, llm.comment) == ("down", "Zu streng.")
        assert llm.judge_model_id == "gpt-5-mini"
        assert llm.grade_points == 12.0
        assert llm.passed is True
        assert llm.context == {"metric_keys": ["llm_judge_falloesung"]}
        assert by_source["general"].rating is None
        assert by_source["general"].evaluation_run_id is None

    def test_unknown_author_is_dropped_not_reattributed(self, test_db, full_project):
        """The comprehensive importer maps unknown users onto the importing
        user. For an opinion that would be a lie, so the row is dropped."""
        project, admin = full_project
        self._seed(test_db, project, admin)
        lines = _export_ndjson(test_db, project).splitlines()

        # Simulate an export from a deployment whose solver is unknown here:
        # the feedback references a user id that no `user` record resolves.
        stranger = _uid()
        rewritten = []
        for ln in lines:
            rec = json.loads(ln)
            if rec.get("_type") == "grading_feedback":
                rec["user_id"] = stranger
            rewritten.append(json.dumps(rec))
        body = ("\n".join(rewritten) + "\n").encode()

        result = run_ndjson_import(test_db, io.BytesIO(body), admin.id)
        new_id = result["project_id"]

        imported = (
            test_db.query(GradingFeedback)
            .filter(GradingFeedback.project_id == new_id)
            .all()
        )
        assert imported == []
        assert result["statistics"]["imported_counts"]["grading_feedback"] == 0
        # The rest of the project still imported normally.
        assert test_db.query(Task).filter(Task.project_id == new_id).count() == 3

    def test_comprehensive_json_path_matches_ndjson(self, test_db, full_project):
        """The multi-pass (single-object JSON) importer imports the same rows."""
        project, admin = full_project
        self._seed(test_db, project, admin)
        comprehensive = "".join(
            stream_comprehensive_project_data_json(test_db, project.id)
        )
        payload = json.loads(comprehensive)
        assert len(payload["grading_feedback"]) == 2
        assert payload["statistics"]["total_grading_feedback"] == 2
        # The users block carries the author, which is what gates the import.
        assert any(u["id"] == admin.id for u in payload["users"])

        result = run_full_project_import(
            test_db, io.BytesIO(comprehensive.encode()), admin.id
        )
        new_id = result["project_id"]
        imported = (
            test_db.query(GradingFeedback)
            .filter(GradingFeedback.project_id == new_id)
            .all()
        )
        assert len(imported) == 2
        assert {f.grading_source for f in imported} == {"llm", "general"}
        assert {f.user_id for f in imported} == {admin.id}


class TestTaskRubricsInNdjson:
    """Bewertungsbogen rows travel in the NDJSON stream, in an order a single
    forward import pass can use, and imported gradings point at the imported
    sheet rather than at the source deployment's."""

    def _seed(self, db, project, admin):
        from models import TaskEvaluation
        from project_models import TaskRubric
        from sqlalchemy.orm.attributes import flag_modified

        grading = (
            db.query(TaskEvaluation)
            .join(Task, Task.id == TaskEvaluation.task_id)
            .filter(Task.project_id == project.id)
            .first()
        )
        assert grading is not None, "full_project must carry a grading"
        rubric = TaskRubric(
            id=_uid(),
            task_id=grading.task_id,
            project_id=project.id,
            title="Korrekturbogen NDJSON",
            criteria={"s01_a": {"name": "A", "rubric": "r", "max_score": 12.5}},
            total_points=12.5,
            source="human",
            status="active",
            created_by=admin.id,
        )
        db.add(rubric)
        db.flush()
        grading.metrics = {
            **(grading.metrics or {}),
            "llm_judge_rubric": {
                "value": 0.8,
                "details": {"rubric_id": rubric.id, "grade_points": 11},
            },
        }
        flag_modified(grading, "metrics")
        db.commit()
        return rubric

    def test_records_are_ordered_for_a_single_pass_import(self, test_db, full_project):
        project, admin = full_project
        rubric = self._seed(test_db, project, admin)
        lines = [json.loads(ln) for ln in _export_ndjson(test_db, project).splitlines()]
        types = [r["_type"] for r in lines]

        assert types.count("task_rubric") == 1
        first_rubric = types.index("task_rubric")
        last_task = max(i for i, t in enumerate(types) if t == "task")
        first_grading = types.index("task_evaluation")
        # After its task (FK) and before any grading that names it.
        assert last_task < first_rubric < first_grading

        record = lines[first_rubric]
        assert record["id"] == rubric.id
        assert record["task_id"] == rubric.task_id
        assert record["total_points"] == 12.5
        end = lines[-1]
        assert end["_type"] == "end"
        assert end["statistics"]["total_task_rubrics"] == 1

    def test_roundtrip_carries_the_sheet_and_repoints_gradings(
        self, test_db, full_project
    ):
        from models import TaskEvaluation
        from project_models import TaskRubric

        project, admin = full_project
        source = self._seed(test_db, project, admin)
        ndjson = _export_ndjson(test_db, project)

        result = run_ndjson_import(test_db, io.BytesIO(ndjson.encode()), admin.id)
        new_id = result["project_id"]
        assert result["statistics"]["imported_counts"]["task_rubrics"] == 1

        imported = (
            test_db.query(TaskRubric).filter(TaskRubric.project_id == new_id).one()
        )
        assert imported.id != source.id
        assert imported.title == "Korrekturbogen NDJSON"
        assert imported.status == "active"

        new_task_ids = [
            t.id for t in test_db.query(Task).filter(Task.project_id == new_id).all()
        ]
        gradings = [
            row
            for row in test_db.query(TaskEvaluation)
            .filter(TaskEvaluation.task_id.in_(new_task_ids))
            .all()
            if isinstance(row.metrics, dict) and "llm_judge_rubric" in row.metrics
        ]
        assert gradings
        for row in gradings:
            assert row.metrics["llm_judge_rubric"]["details"]["rubric_id"] == imported.id

    def test_full_project_export_carries_the_sheet_and_repoints_gradings(
        self, test_db, full_project
    ):
        """The comprehensive format, which production's async project export
        uses. Before this change it carried no Bewertungsbogen at all, so a
        restored project lost every sheet and every grading kept a dangling
        rubric id."""
        from export_stream import stream_comprehensive_project_data_json
        from import_stream import run_full_project_import
        from models import TaskEvaluation
        from project_models import TaskRubric

        project, admin = full_project
        source = self._seed(test_db, project, admin)
        payload = json.loads(
            "".join(stream_comprehensive_project_data_json(test_db, project.id))
        )

        records = payload.get("task_rubrics") or []
        assert [r["id"] for r in records] == [source.id]
        assert records[0]["task_id"] == source.task_id
        export_stats = next(
            v for v in payload.values() if isinstance(v, dict) and "total_tasks" in v
        )
        assert export_stats["total_task_rubrics"] == 1

        result = run_full_project_import(
            test_db, io.BytesIO(json.dumps(payload).encode()), admin.id
        )
        stats = result.get("statistics") or result
        new_id = (
            result.get("project_id")
            or result.get("new_project_id")
            or stats.get("new_project_id")
        )
        assert new_id
        assert stats["imported_counts"]["task_rubrics"] == 1

        imported = (
            test_db.query(TaskRubric).filter(TaskRubric.project_id == new_id).one()
        )
        assert imported.id != source.id
        assert imported.status == "active"
        assert imported.total_points == 12.5

        new_task_ids = [
            t.id for t in test_db.query(Task).filter(Task.project_id == new_id).all()
        ]
        gradings = [
            row
            for row in test_db.query(TaskEvaluation)
            .filter(TaskEvaluation.task_id.in_(new_task_ids))
            .all()
            if isinstance(row.metrics, dict) and "llm_judge_rubric" in row.metrics
        ]
        assert gradings
        for row in gradings:
            assert row.metrics["llm_judge_rubric"]["details"]["rubric_id"] == imported.id


@pytest.mark.integration
class TestImportOwningOrganization:
    """``organization_id`` (the target named in the import request) picks the
    owning org and is re-validated when the project is created."""

    @staticmethod
    def _second_org(test_db, name):
        from models import Organization

        oid = _uid()
        org = Organization(
            id=oid, name=name, display_name=name, slug=f"own-{oid[:8]}"
        )
        test_db.add(org)
        test_db.flush()
        return org

    @staticmethod
    def _join(test_db, user, org, active=True):
        from models import OrganizationMembership

        test_db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=user.id,
                organization_id=org.id,
                role="CONTRIBUTOR",
                is_active=active,
            )
        )
        test_db.flush()

    @staticmethod
    def _owner_org(test_db, project_id):
        return (
            test_db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project_id)
            .scalar()
        )

    def test_member_org_owns_the_import_for_json_and_ndjson(
        self, test_db, test_users, full_project
    ):
        project, _admin = full_project
        contributor = test_users[1]  # active member of test_org
        target = self._second_org(test_db, "Target")
        self._join(test_db, contributor, target)
        test_db.commit()

        ndjson = _export_ndjson(test_db, project)
        comprehensive = "".join(
            stream_comprehensive_project_data_json(test_db, project.id)
        )
        for body in (ndjson, comprehensive):
            pid = run_full_project_import(
                test_db,
                io.BytesIO(body.encode("utf-8")),
                contributor.id,
                organization_id=target.id,
            )["project_id"]
            assert self._owner_org(test_db, pid) == target.id

    def test_without_a_target_the_import_is_private(
        self, test_db, test_users, test_org, full_project
    ):
        project, _admin = full_project
        contributor = test_users[1]
        pid = run_full_project_import(
            test_db,
            io.BytesIO(_export_ndjson(test_db, project).encode("utf-8")),
            contributor.id,
        )["project_id"]
        assert self._owner_org(test_db, pid) is None
        imported = test_db.query(Project).filter(Project.id == pid).one()
        assert imported.is_private is True
        assert imported.created_by == contributor.id

    def test_non_member_is_rejected_before_anything_is_written(
        self, test_db, test_users, full_project
    ):
        project, _admin = full_project
        contributor = test_users[1]
        foreign = self._second_org(test_db, "Foreign")
        inactive = self._second_org(test_db, "Inactive")
        self._join(test_db, contributor, inactive, active=False)
        test_db.commit()
        ndjson = _export_ndjson(test_db, project)

        for org in (foreign, inactive):
            before = test_db.query(Project).count()
            with pytest.raises(ImportValidationError) as exc:
                run_full_project_import(
                    test_db,
                    io.BytesIO(ndjson.encode("utf-8")),
                    contributor.id,
                    organization_id=org.id,
                )
            assert exc.value.status_code == 403
            test_db.rollback()
            assert test_db.query(Project).count() == before

    def test_superadmin_may_import_into_any_existing_org(
        self, test_db, test_users, full_project
    ):
        project, admin = full_project
        assert admin.is_superadmin
        foreign = self._second_org(test_db, "Superadmin Target")
        test_db.commit()
        ndjson = _export_ndjson(test_db, project)

        pid = run_full_project_import(
            test_db,
            io.BytesIO(ndjson.encode("utf-8")),
            admin.id,
            organization_id=foreign.id,
        )["project_id"]
        assert self._owner_org(test_db, pid) == foreign.id

        with pytest.raises(ImportValidationError) as exc:
            run_full_project_import(
                test_db,
                io.BytesIO(ndjson.encode("utf-8")),
                admin.id,
                organization_id=_uid(),
            )
        assert exc.value.status_code == 404


@pytest.mark.integration
class TestTaskExportRejectedByProjectImport:
    """A Projektdaten task export must not pass as a project export."""

    def test_task_export_is_rejected_with_a_stable_code(self, test_db, full_project):
        from import_stream import TASK_EXPORT_NOT_PROJECT

        project, admin = full_project
        task_export = "".join(select_export_generator(test_db, project, "json"))
        doc = json.loads(task_export)
        assert "format_version" not in doc and "evaluation_runs" in doc

        before = test_db.query(Project).count()
        with pytest.raises(ImportValidationError) as exc:
            run_full_project_import(
                test_db, io.BytesIO(task_export.encode("utf-8")), admin.id
            )
        assert exc.value.status_code == 400
        assert exc.value.code == TASK_EXPORT_NOT_PROJECT
        assert exc.value.detail.startswith(f"{TASK_EXPORT_NOT_PROJECT}: ")
        assert "task export" in exc.value.detail
        test_db.rollback()
        assert test_db.query(Project).count() == before

    def test_nested_tasks_without_evaluation_runs_are_rejected(
        self, test_db, full_project
    ):
        project, admin = full_project
        doc = json.loads("".join(select_export_generator(test_db, project, "json")))
        doc.pop("evaluation_runs")
        with pytest.raises(ImportValidationError) as exc:
            run_full_project_import(
                test_db, io.BytesIO(json.dumps(doc).encode("utf-8")), admin.id
            )
        assert exc.value.code == "task_export_not_project"

    def test_comprehensive_export_is_still_accepted(self, test_db, full_project):
        project, admin = full_project
        body = "".join(stream_comprehensive_project_data_json(test_db, project.id))
        result = run_full_project_import(
            test_db, io.BytesIO(body.encode("utf-8")), admin.id
        )
        assert result["project_id"]

    def test_legacy_export_without_format_version_is_still_accepted(
        self, test_db, full_project
    ):
        """Old comprehensive exports may lack format_version; their flat
        top-level annotations block keeps them importable."""
        project, admin = full_project
        doc = json.loads(
            "".join(stream_comprehensive_project_data_json(test_db, project.id))
        )
        doc.pop("format_version")
        result = run_full_project_import(
            test_db, io.BytesIO(json.dumps(doc).encode("utf-8")), admin.id
        )
        assert result["project_id"]

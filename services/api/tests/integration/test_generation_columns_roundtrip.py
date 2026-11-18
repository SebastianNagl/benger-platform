"""Every generation column survives export and import.

A generation row carries research data beyond its answer: the run index of
the trial, the prompt structure of its job, the per-call telemetry (seed,
finish reason, refusal, truncation, latency, tokens), the request record of
what the provider client sent, and the format-retry trail. The task-level
("data") export and the nested import used to drop all of that and renumber
the runs by order; these tests pin that both export formats carry every
column and both importers restore it, with each row in the job of its model
and structure and on its own run index.
"""

import io
import json
import uuid
from datetime import datetime, timezone

import pytest

from ai_services.request_capture import request_sha256
from export_stream import stream_export_json
from models import Generation, ResponseGeneration
from project_models import Project, ProjectOrganization, Task
from routers.projects._export_stream import stream_export_ndjson
from routers.projects._import_stream import run_full_project_import, run_nested_import


def _uid() -> str:
    return str(uuid.uuid4())


def _record(user_text: str) -> dict:
    body = {
        "model": "acme/open-model-7b",
        "messages": [
            {"role": "system", "content": "Du bist Schlichterin für Mietsachen."},
            {"role": "user", "content": user_text},
        ],
        "max_tokens": 600,
        "temperature": 0.7,
        "stream": False,
    }
    return {
        "version": 1,
        "provider": "DeepInfra",
        "api": "chat.completions",
        "capture": "http_body",
        "model": body["model"],
        "messages": body["messages"],
        "response_format": None,
        "parameters": {"max_tokens": 600, "temperature": 0.7, "stream": False},
        "requests": [
            {"provider": "DeepInfra", "api": "chat.completions", "capture": "http_body",
             "body": body, "sends": 1},
        ],
    }


# (structure_key, run_index, retried): two trials of one job on runs 0 and 3,
# and one trial of a second structure of the same model.
ROWS = [("s_plain", 0, False), ("s_plain", 3, True), ("s_alt", 0, False)]

COLUMNS = (
    "model_id", "response_content", "reasoning", "case_data", "response_metadata",
    "usage_stats", "status", "error_message", "parse_status", "parse_error",
    "parsed_annotation", "parse_metadata", "label_config_version", "label_config_snapshot",
    "run_index", "seed", "finish_reason", "truncated", "refusal", "error_type",
    "latency_ms", "input_tokens", "output_tokens", "request_record", "request_sha256",
    "first_response_content", "retried",
)


@pytest.fixture
def fidelity_project(test_db, test_users, test_org):
    admin = test_users[0]
    project = Project(
        id=_uid(),
        title=f"Generation columns RT {_uid()[:8]}",
        label_config='<View><Text name="text" value="$text"/>'
        '<Number name="anteil" toName="text"/></View>',
        created_by=admin.id,
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(ProjectOrganization(
        id=_uid(), project_id=project.id, organization_id=test_org.id, assigned_by=admin.id,
    ))
    task = Task(
        id=_uid(), project_id=project.id, inner_id=1,
        data={"text": "Mietminderung wegen Schimmel"}, created_by=admin.id,
    )
    test_db.add(task)
    test_db.flush()
    parents = {}
    for structure_key, run_index, retried in ROWS:
        if structure_key not in parents:
            parents[structure_key] = ResponseGeneration(
                id=_uid(), task_id=task.id, project_id=project.id,
                model_id="acme/open-model-7b", structure_key=structure_key,
                status="completed", responses_generated=1, created_by=admin.id,
            )
            test_db.add(parents[structure_key])
            test_db.flush()
        record = _record(f"Akte {structure_key} Lauf {run_index}")
        test_db.add(Generation(
            id=_uid(), generation_id=parents[structure_key].id, task_id=task.id,
            model_id="acme/open-model-7b", run_index=run_index,
            case_data=json.dumps({"text": "Mietminderung"}),
            response_content=f'{{"anteil": {run_index * 10}}}',
            reasoning=f"Abwägung {run_index}",
            usage_stats={"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
            response_metadata={"provider": "DeepInfra", "format_retry": {"attempts": int(retried)}},
            status="completed",
            parse_status="success",
            parsed_annotation=[{"from_name": "anteil", "type": "number",
                                "value": {"number": run_index * 10}}],
            parse_metadata={"retry_count": 1},
            label_config_version="v1",
            label_config_snapshot=project.label_config,
            seed=1000 + run_index,
            finish_reason="stop" if not retried else "length",
            truncated=retried,
            refusal=retried,
            error_type=None,
            latency_ms=800 + run_index,
            input_tokens=120,
            output_tokens=30,
            request_record=record,
            request_sha256=request_sha256(record),
            first_response_content="Ich halte die Minderung für begründet." if retried else None,
            retried=retried,
            created_at=datetime(2026, 11, 1, 12, run_index, tzinfo=timezone.utc),
        ))
    test_db.commit()
    return project, admin


def _rows(test_db, project_id):
    """{(structure_key, run_index): column tuple} of a project's generations."""
    result = {}
    query = (
        test_db.query(Generation, ResponseGeneration.structure_key)
        .join(ResponseGeneration, Generation.generation_id == ResponseGeneration.id)
        .join(Task, Task.id == Generation.task_id)
        .filter(Task.project_id == project_id)
    )
    for gen, structure_key in query:
        result[(structure_key, gen.run_index)] = (
            tuple(getattr(gen, c) for c in COLUMNS),
            gen.created_at,
        )
    return result


def _target(test_db, project, admin, test_org):
    target = Project(
        id=_uid(), title=f"Generation columns target {_uid()[:8]}",
        label_config=project.label_config, created_by=admin.id,
    )
    test_db.add(target)
    test_db.flush()
    test_db.add(ProjectOrganization(
        id=_uid(), project_id=target.id, organization_id=test_org.id, assigned_by=admin.id,
    ))
    test_db.commit()
    return target


@pytest.mark.integration
class TestGenerationColumnsRoundTrip:
    def test_nested_task_export_import_keeps_every_column(
        self, test_db, test_org, fidelity_project
    ):
        project, admin = fidelity_project
        before = _rows(test_db, project.id)
        body = "".join(stream_export_json(test_db, project.id, None, {"project_id": project.id}))
        doc = json.loads(body)
        exported = [g for t in doc["tasks"] for g in t.get("generations", [])]
        assert {(g["structure_key"], g["run_index"]) for g in exported} == set(before)
        assert all("request_record" in g and "retried" in g and "seed" in g for g in exported)

        target = _target(test_db, project, admin, test_org)
        payload = {k: v for k, v in doc.items() if k != "tasks"}
        payload["data"] = doc["tasks"]
        run_nested_import(
            test_db, target.id, io.BytesIO(json.dumps(payload).encode("utf-8")), admin.id
        )
        after = _rows(test_db, target.id)
        assert after == before

        # One job per model and structure, sized by its imported runs.
        jobs = (
            test_db.query(ResponseGeneration)
            .join(Task, Task.id == ResponseGeneration.task_id)
            .filter(Task.project_id == target.id)
            .all()
        )
        assert {(j.structure_key, j.runs_requested) for j in jobs} == {
            ("s_plain", 2), ("s_alt", 1)
        }

    def test_full_export_import_keeps_request_columns(self, test_db, fidelity_project):
        project, admin = fidelity_project
        before = _rows(test_db, project.id)
        body = "".join(stream_export_ndjson(test_db, project.id))
        new_pid = run_full_project_import(test_db, io.BytesIO(body.encode("utf-8")), admin.id)[
            "project_id"
        ]
        assert _rows(test_db, new_pid) == before

    def test_external_payload_run_index_hash_and_collisions(
        self, test_db, test_org, fidelity_project
    ):
        """A hand-written payload: explicit run indexes are kept (a repeated
        one takes the lowest free index), a request record gets the hash of
        its own content whatever hash the file names, and a malformed hash
        without a record is dropped."""
        project, admin = fidelity_project
        target = _target(test_db, project, admin, test_org)
        record = _record("Akte extern")
        gens = [
            {"model_id": "m", "structure_key": "s", "run_index": 7, "response_content": "a",
             "request_record": record, "request_sha256": "0" * 64, "retried": True,
             "first_response_content": "erste Antwort"},
            {"model_id": "m", "structure_key": "s", "run_index": 7, "response_content": "b"},
            {"model_id": "m", "structure_key": "s", "response_content": "c",
             "request_sha256": "not-a-hash"},
        ]
        payload = {"data": [{"data": {"text": "Fall"}, "generations": gens}]}
        run_nested_import(
            test_db, target.id, io.BytesIO(json.dumps(payload).encode("utf-8")), admin.id
        )
        rows = {
            g.response_content: g
            for g in test_db.query(Generation)
            .join(Task, Task.id == Generation.task_id)
            .filter(Task.project_id == target.id)
        }
        assert rows["a"].run_index == 7
        assert {rows["b"].run_index, rows["c"].run_index} == {0, 1}
        assert rows["a"].request_sha256 == request_sha256(record) != "0" * 64
        assert rows["a"].retried is True
        assert rows["a"].first_response_content == "erste Antwort"
        assert rows["c"].request_sha256 is None
        assert rows["b"].retried is False

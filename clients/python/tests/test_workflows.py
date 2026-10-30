from __future__ import annotations

import json

import httpx
import pytest
from conftest import BASE

from benger_client import BengerError, BengerJobError

STORAGE = "https://storage.test.example/benger"


def _upload_answer(prefix: str) -> dict:
    key = f"imports/2026/10/{prefix}/abc_import.json"
    return {
        "upload_url": STORAGE,
        "method": "POST",
        "file_key": key,
        "fields": {"key": key, "Content-Type": "application/json", "policy": "p", "x-amz-signature": "s"},
        "expires_at": "2026-10-30T12:00:00",
    }


def test_import_upload_flow(client, router, tmp_path):
    router.add("POST", "/api/projects/p1/imports/upload-url", _upload_answer("p1"))
    storage_requests = []

    def storage(request):
        storage_requests.append(request)
        return httpx.Response(204)

    router.add("POST", STORAGE, storage)
    router.add("POST", "/api/projects/p1/imports", lambda r: httpx.Response(
        202, json={"job_id": "j1", "status": "pending"}))
    polls = iter([
        {"job_id": "j1", "status": "running", "progress": 10},
        {"job_id": "j1", "status": "completed", "result": {"created_tasks": 2}},
    ])
    router.add("GET", "/api/projects/p1/imports/j1", lambda r: httpx.Response(200, json=next(polls)))

    tasks = [{"data": {"question": "Q1", "reference_answer": "A1"}}, {"data": {"question": "Q2"}}]
    job = client.imports.upload("p1", tasks)
    assert job["result"] == {"created_tasks": 2}

    upload_call = router.calls[0]
    assert upload_call.url.params["filename"] == "import.json"
    # Storage got a multipart POST with the policy fields, the file last, and no key.
    (req,) = storage_requests
    assert "Authorization" not in req.headers
    assert req.headers["Content-Type"].startswith("multipart/form-data")
    body = req.content.decode()
    assert body.index('name="policy"') < body.index('name="file"')
    assert json.dumps({"data": tasks}, ensure_ascii=False) in body
    assert router.bodies("POST", "/api/projects/p1/imports") == [
        {"object_key": "imports/2026/10/p1/abc_import.json"}
    ]

    # A path works too, and wait=False returns the job right away.
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({"data": tasks}))
    assert client.imports.upload("p1", path, wait=False) == {"job_id": "j1", "status": "pending"}
    assert router.calls[-2].url.params.get("filename") is None  # storage call
    upload_url_calls = [c for c in router.calls if c.url.path.endswith("upload-url")]
    assert upload_url_calls[-1].url.params["filename"] == "tasks.json"


def test_import_failure_raises(client, router):
    router.add("POST", "/api/projects/p1/imports/upload-url", _upload_answer("p1"))
    router.add("POST", STORAGE, lambda r: httpx.Response(204))
    router.add("POST", "/api/projects/p1/imports", lambda r: httpx.Response(
        202, json={"job_id": "j1", "status": "pending"}))
    router.add("GET", "/api/projects/p1/imports/j1", {
        "job_id": "j1", "status": "failed", "error_message": "Field 'data' is required"})
    with pytest.raises(BengerJobError, match="Field 'data'"):
        client.imports.upload("p1", b'{"x": 1}')


def test_create_project_import(client, router):
    router.add("POST", "/api/projects/project-imports/upload-url", _upload_answer("u1"))
    router.add("POST", STORAGE, lambda r: httpx.Response(204))
    router.add("POST", "/api/projects/project-imports", lambda r: httpx.Response(
        202, json={"job_id": "j9", "status": "pending"}))
    router.add("GET", "/api/projects/project-imports/j9", {
        "job_id": "j9", "status": "completed", "project_id": "new-p"})
    job = client.imports.create_project({"project": {"title": "x"}}, organization_id="org1")
    assert job["project_id"] == "new-p"
    assert router.bodies("POST", "/api/projects/project-imports") == [
        {"object_key": "imports/2026/10/u1/abc_import.json", "organization_id": "org1"}
    ]


def test_local_storage_backend_is_reported(client, router):
    router.add("POST", "/api/projects/p1/imports/upload-url", {
        "upload_url": "/api/upload", "method": "POST", "file_key": "imports/x/p1/a.json"})
    with pytest.raises(BengerError, match="local storage"):
        client.imports.upload("p1", b"{}")


def test_register_and_test_custom_model(client, router):
    router.add("POST", "/api/custom-models/", lambda r: httpx.Response(201, json={
        "id": "custom-123", "name": "my-model", "provider": "Custom", "model_type": "chat",
        "base_url": "https://inference.example.org/v1", "endpoint_model_name": "llama",
        "has_credential": True, "is_private": True}))
    router.add("POST", "/api/custom-models/custom-123/test", {
        "status": "success", "message": "ok", "error_type": None})
    model = client.models.register_custom(
        "my-model", "https://inference.example.org/v1", "llama", api_key="sk-endpoint",
        parameter_constraints={"temperature": {"supported": True, "max": 1}},
    )
    assert model["id"] == "custom-123"
    (body,) = router.bodies("POST", "/api/custom-models/")
    assert body == {
        "name": "my-model", "base_url": "https://inference.example.org/v1",
        "endpoint_model_name": "llama", "api_key": "sk-endpoint", "requires_api_key": True,
        "model_type": "chat", "parameter_constraints": {"temperature": {"supported": True, "max": 1}},
    }
    assert client.models.test("custom-123", chat_ping=True)["status"] == "success"
    assert router.bodies("POST", "/api/custom-models/custom-123/test") == [{"chat_ping": True}]


def test_generate_then_evaluate(client, router):
    pid = "p1"
    router.add("PATCH", f"/api/projects/{pid}", {"id": pid})
    router.add("POST", f"/api/generation-tasks/projects/{pid}/generate", {
        "project_id": pid, "mode": "missing", "tasks_queued": 2, "models_count": 1,
        "generation_job_ids": ["g1", "g2"], "estimated_time_seconds": 10, "message": "Queued"})
    gen_polls = iter([
        {"generations": [{"id": "g1", "status": "running"}, {"id": "g2", "status": "pending"},
                         {"id": "old", "status": "running"}], "is_running": True},
        {"generations": [{"id": "g1", "status": "completed"}, {"id": "g2", "status": "failed"},
                         {"id": "old", "status": "running"}], "is_running": True},
    ])
    router.add("GET", f"/api/projects/{pid}/generation-status",
               lambda r: httpx.Response(200, json=next(gen_polls)))
    eval_config = {"id": "bleu", "metric": "bleu", "prediction_fields": ["__all_model__"],
                   "reference_fields": ["reference_answer"], "enabled": True}
    router.add("PUT", f"/api/evaluations/projects/{pid}/evaluation-config",
               {"message": "ok", "config": {"evaluation_configs": [eval_config]}, "warnings": []})
    router.add("GET", f"/api/evaluations/projects/{pid}/evaluation-config",
               {"evaluation_configs": [eval_config, {**eval_config, "id": "off", "enabled": False}]})
    router.add("POST", "/api/evaluations/run", {
        "evaluation_id": "e1", "project_id": pid, "status": "pending", "message": "started",
        "evaluation_configs_count": 1, "started_at": "2026-10-30T10:00:00"})
    eval_polls = iter([{"id": "e1", "status": "running"}, {"id": "e1", "status": "completed"}])
    router.add("GET", "/api/evaluations/evaluation/status/e1",
               lambda r: httpx.Response(200, json=next(eval_polls)))
    router.add("GET", "/api/evaluations/run/results/e1",
               {"evaluation_id": "e1", "status": "completed", "aggregated_metrics": {"bleu": 0.4}})

    client.generation.configure(pid, models=["custom-123"], runs_per_task=1)
    assert router.bodies("PATCH", f"/api/projects/{pid}") == [
        {"generation_config": {"selected_configuration": {"models": ["custom-123"]}, "runs_per_task": 1}}
    ]
    started = client.generation.start(pid, model_ids=["custom-123"], temperature=0.0, seed=7)
    assert router.bodies("POST", f"/api/generation-tasks/projects/{pid}/generate") == [
        {"mode": "missing", "model_ids": ["custom-123"], "parameters": {"temperature": 0.0, "seed": 7}}
    ]
    done = client.generation.wait(pid, started)
    assert done["done"] and done["counts"] == {"completed": 1, "failed": 1}
    assert [g["id"] for g in done["generations"]] == ["g1", "g2"]  # unrelated "old" ignored

    client.evaluations.configure(pid, [eval_config])
    run = client.evaluations.run(pid)  # uses the saved, enabled configs
    (run_body,) = router.bodies("POST", "/api/evaluations/run")
    assert run_body == {"project_id": pid, "evaluation_configs": [eval_config], "force_rerun": False}
    assert client.evaluations.wait(run)["status"] == "completed"
    assert client.evaluations.results("e1")["aggregated_metrics"] == {"bleu": 0.4}


def test_generation_wait_raise_on_failure(client, router):
    router.add("GET", "/api/projects/p/generation-status",
               {"generations": [{"id": "g1", "status": "failed"}]})
    with pytest.raises(BengerJobError):
        client.generation.wait("p", ["g1"], raise_on_failure=True)


def test_evaluation_failure_and_project_scoped_status(client, router):
    router.add("GET", "/api/runs", lambda r: httpx.Response(200, json={
        "items": [{"id": "e2", "type": "evaluation", "status": "failed",
                   "error_message": "no generations matched"}],
        "total": 1, "page": 1, "page_size": 200}))
    with pytest.raises(BengerJobError, match="no generations matched"):
        client.evaluations.wait("e2", project_id="p")
    params = router.calls[0].url.params
    assert (params["type"], params["project_id"]) == ("evaluation", "p")


def test_export_create_wait_download(client, router, tmp_path):
    router.add("POST", "/api/v1/projects/p1/exports", lambda r: httpx.Response(
        202, json={"id": "x1", "status": "pending"}, headers={"Location": "/api/v1/exports/x1"}))
    polls = iter([{"id": "x1", "status": "running"},
                  {"id": "x1", "status": "completed", "download_url": "/api/v1/exports/x1/download"}])
    router.add("GET", "/api/v1/exports/x1", lambda r: httpx.Response(200, json=next(polls)))
    signed = "https://storage.test.example/benger/exports/x1.json?X-Amz-Signature=abc"
    router.add("GET", "/api/v1/exports/x1/download",
               lambda r: httpx.Response(302, headers={"Location": signed}))
    storage_calls = []

    def storage(request):
        storage_calls.append(request)
        return httpx.Response(200, content=b'{"tasks": []}')

    router.add("GET", "https://storage.test.example/benger/exports/x1.json", storage)

    job = client.exports.wait(client.exports.create("p1"))
    target = client.exports.download(job, tmp_path / "export.json")
    assert target.read_bytes() == b'{"tasks": []}'
    assert all("Authorization" not in c.headers for c in storage_calls)
    assert client.exports.download("x1") == b'{"tasks": []}'
    assert router.calls[0].url == httpx.URL(BASE + "/api/v1/projects/p1/exports")

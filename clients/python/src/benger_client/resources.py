"""Thin helpers over the BenGER routes a research pipeline needs.

Each method maps to one documented route (named in its docstring) and
returns the decoded JSON unchanged, so new fields the server adds show up
without a client release. Anything not covered here is one
``client.request(...)`` away; ``docs/full-api-routes.md`` lists every route
an access key may call and the scopes it needs.
"""

from __future__ import annotations

import json as _json
import os
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

from .errors import BengerError, BengerJobError

if TYPE_CHECKING:
    from ._client import BengerClient

__all__ = [
    "Projects",
    "Tasks",
    "Imports",
    "Models",
    "Generation",
    "Evaluations",
    "Exports",
    "GENERATION_FINAL_STATUSES",
    "EVALUATION_FINAL_STATUSES",
]

#: Statuses after which a job no longer changes on its own.
JOB_FINAL_STATUSES = frozenset({"completed", "failed"})
GENERATION_FINAL_STATUSES = frozenset({"completed", "failed", "stopped", "cancelled"})
EVALUATION_FINAL_STATUSES = frozenset({"completed", "failed", "stopped", "cancelled"})

#: What an import accepts: a file path, raw bytes, an open binary file, or a
#: JSON-serialisable object.
ImportSource = str | os.PathLike | bytes | BinaryIO | Mapping[str, Any] | list


def _q(value: str) -> str:
    """Path-segment escape for ids (they are UUIDs or slugs; this is defensive)."""
    from urllib.parse import quote

    return quote(str(value), safe="")


def _drop_none(data: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None}


class _Resource:
    def __init__(self, client: BengerClient):
        self._client = client


# --------------------------------------------------------------------------- #
# Projects and tasks
# --------------------------------------------------------------------------- #


class Projects(_Resource):
    """Projects. Reads use the stable ``/api/v1``; writes use the full API."""

    def list(self, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Every project the key may read (``GET /api/v1/projects``, auto-paginated)."""
        return self._client.paginate("/api/v1/projects", limit=limit)

    def page(self, *, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        """One page: ``{"items": [...], "next_cursor": str | None}``."""
        return self._client.get("/api/v1/projects", params={"limit": limit, "cursor": cursor})

    def get(self, project_id: str, *, full: bool = False) -> dict[str, Any]:
        """One project.

        By default the v1 shape (``GET /api/v1/projects/{id}``: id, title,
        task_count, bound_fields, answer_fields, access). ``full=True``
        returns the full-API ``ProjectResponse`` (``GET /api/projects/{id}``)
        with label_config, generation_config and evaluation_config.
        """
        if full:
            return self._client.get(f"/api/projects/{_q(project_id)}")
        return self._client.get(f"/api/v1/projects/{_q(project_id)}")

    def create(
        self,
        title: str,
        *,
        description: str | None = None,
        label_config: str | None = None,
        organization_id: str | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        """Create a project (``POST /api/projects/``, scope ``projects:write``).

        Without ``organization_id`` the project is the key user's private
        project. A key limited to a project list cannot create projects.
        Further ``ProjectCreate`` fields (``expert_instruction``, ``kind``...)
        pass through ``fields``.
        """
        body = _drop_none(
            {
                "title": title,
                "description": description,
                "label_config": label_config,
                "organization_id": organization_id,
                **fields,
            }
        )
        return self._client.post("/api/projects/", json=body)

    def update(self, project_id: str, **fields: Any) -> dict[str, Any]:
        """Update a project (``PATCH /api/projects/{id}``).

        ``generation_config`` and ``evaluation_config`` are deep-merged on
        the server (nested dicts merge, lists replace, ``None`` deletes a key).
        """
        return self._client.patch(f"/api/projects/{_q(project_id)}", json=fields)

    def delete(self, project_id: str) -> Any:
        """Soft-delete a project (``DELETE /api/projects/{id}``)."""
        return self._client.delete(f"/api/projects/{_q(project_id)}")


class Tasks(_Resource):
    """Tasks through ``/api/v1`` (blinded unless the key may see reference data)."""

    def iter(self, project_id: str, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Every task of a project, ordered by ``inner_id`` (auto-paginated)."""
        return self._client.paginate(f"/api/v1/projects/{_q(project_id)}/tasks", limit=limit)

    def list(self, project_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """All tasks as a list (convenience over :meth:`iter`)."""
        return list(self.iter(project_id, limit=limit))

    def page(
        self, project_id: str, *, limit: int = 50, cursor: str | None = None
    ) -> dict[str, Any]:
        return self._client.get(
            f"/api/v1/projects/{_q(project_id)}/tasks",
            params={"limit": limit, "cursor": cursor},
        )

    def get(self, project_id: str, task_id: str) -> dict[str, Any]:
        """``GET /api/v1/projects/{project_id}/tasks/{task_id}``."""
        return self._client.get(f"/api/v1/projects/{_q(project_id)}/tasks/{_q(task_id)}")


# --------------------------------------------------------------------------- #
# Imports (presigned object-storage upload)
# --------------------------------------------------------------------------- #


def _read_source(source: ImportSource, filename: str | None, *, wrap_list: bool):
    """``(bytes, filename)`` for an import source."""
    if isinstance(source, (bytes, bytearray)):
        return bytes(source), filename or "import.json"
    if isinstance(source, (str, os.PathLike)):
        path = Path(source)
        return path.read_bytes(), filename or path.name
    if hasattr(source, "read"):
        data = source.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        name = filename or Path(getattr(source, "name", "import.json")).name
        return data, name
    if isinstance(source, list) and wrap_list:
        source = {"data": source}
    if isinstance(source, (Mapping, list)):
        return _json.dumps(source, ensure_ascii=False).encode("utf-8"), filename or "import.json"
    raise TypeError(f"Unsupported import source: {type(source).__name__}")


class Imports(_Resource):
    """Task and project imports.

    Both flows upload the file straight to object storage with a presigned
    POST, then start a job and poll it:

    1. ``POST .../upload-url`` returns ``{upload_url, method, file_key, fields}``
    2. the bytes go to ``upload_url`` as multipart form (``fields`` + ``file``),
       without the access key
    3. ``POST .../imports {"object_key": file_key}`` returns ``{job_id, status}``
    4. ``GET .../imports/{job_id}`` until ``status`` is ``completed`` or ``failed``
    """

    def upload(
        self,
        project_id: str,
        source: ImportSource,
        *,
        filename: str | None = None,
        wait: bool = True,
        timeout: float = 1800.0,
        interval: float = 2.0,
    ) -> dict[str, Any]:
        """Add tasks to an existing project (scopes ``projects:write`` + ``tasks:write``).

        ``source`` is a path, bytes, a binary file, or a JSON-serialisable
        object. The payload is BenGER's nested format,
        ``{"data": [{"data": {...task fields...}, "meta": {...}}, ...]}``;
        a plain list of task items is wrapped into ``{"data": [...]}``.

        With ``wait=True`` returns the finished job (``result`` holds the
        counts such as ``created_tasks``) and raises
        :class:`~benger_client.errors.BengerJobError` if it failed. With
        ``wait=False`` returns ``{"job_id", "status"}`` right away.
        """
        content, name = _read_source(source, filename, wrap_list=True)
        base = f"/api/projects/{_q(project_id)}/imports"
        upload = self._client.post(f"{base}/upload-url", params={"filename": name})
        object_key = self._put_to_storage(upload, content, name)
        job = self._client.post(base, json={"object_key": object_key})
        if not wait:
            return job
        return self.wait(job["job_id"], project_id=project_id, timeout=timeout, interval=interval)

    def create_project(
        self,
        source: ImportSource,
        *,
        organization_id: str | None = None,
        organization_group_id: str | None = None,
        filename: str | None = None,
        wait: bool = True,
        timeout: float = 1800.0,
        interval: float = 2.0,
    ) -> dict[str, Any]:
        """Create a NEW project from a full-project export (``comprehensive`` format).

        Uses ``POST /api/projects/project-imports/upload-url`` and
        ``POST /api/projects/project-imports``. Without ``organization_id``
        the project is the importer's private project. The finished job's
        ``project_id`` is the new project.
        """
        content, name = _read_source(source, filename, wrap_list=False)
        base = "/api/projects/project-imports"
        upload = self._client.post(f"{base}/upload-url", params={"filename": name})
        object_key = self._put_to_storage(upload, content, name)
        body = _drop_none(
            {
                "object_key": object_key,
                "organization_id": organization_id,
                "organization_group_id": organization_group_id if organization_id else None,
            }
        )
        job = self._client.post(base, json=body)
        if not wait:
            return job
        return self.wait(job["job_id"], timeout=timeout, interval=interval)

    def status(self, job_id: str, *, project_id: str | None = None) -> dict[str, Any]:
        """One poll: ``GET /api/projects/{id}/imports/{job_id}`` (or the
        create-new ``/api/projects/project-imports/{job_id}`` without ``project_id``)."""
        if project_id:
            return self._client.get(f"/api/projects/{_q(project_id)}/imports/{_q(job_id)}")
        return self._client.get(f"/api/projects/project-imports/{_q(job_id)}")

    def wait(
        self,
        job_id: str,
        *,
        project_id: str | None = None,
        timeout: float = 1800.0,
        interval: float = 2.0,
    ) -> dict[str, Any]:
        """Poll until the import job is final; raise on ``failed``."""

        def poll():
            job = self.status(job_id, project_id=project_id)
            return job if job.get("status") in JOB_FINAL_STATUSES else None

        job = self._client.wait_until(
            poll, timeout=timeout, interval=interval, description=f"import {job_id}"
        )
        if job.get("status") == "failed":
            raise BengerJobError(
                f"Import {job_id} failed: {job.get('error_message') or 'unknown error'}", job
            )
        return job

    def _put_to_storage(self, upload: Mapping[str, Any], content: bytes, name: str) -> str:
        url = upload.get("upload_url") or ""
        key = upload.get("file_key") or (upload.get("fields") or {}).get("key")
        if not key:
            raise BengerError("The upload-url answer carried no file_key")
        if not url.startswith(("http://", "https://")):
            raise BengerError(
                f"This deployment hands out a non-absolute upload URL ({url!r}); its "
                "object storage is not reachable from outside (local storage backend)"
            )
        method = (upload.get("method") or "POST").upper()
        fields = dict(upload.get("fields") or {})
        with self._client._storage_client() as storage:
            if method == "POST":
                content_type = fields.get("Content-Type", "application/json")
                # The policy covers every form field; "file" must come last.
                response = storage.post(
                    url, data=fields, files={"file": (name, content, content_type)}
                )
            else:
                response = storage.request(
                    method,
                    url,
                    content=content,
                    headers=dict(upload.get("headers") or {}),
                )
        if response.status_code >= 300:
            raise BengerError(
                f"Upload to object storage failed ({response.status_code}): {response.text[:300]}"
            )
        return key


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #


class Models(_Resource):
    """The model catalog and your own (BYOM) OpenAI-compatible models."""

    def catalog(self) -> list[dict[str, Any]]:
        """Official catalog models (``GET /api/llm_models/public/models``)."""
        return self._client.get("/api/llm_models/public/models")

    list = catalog

    def list_custom(self) -> list[dict[str, Any]]:
        """Custom models visible to the key's user (``GET /api/custom-models/``)."""
        return self._client.get("/api/custom-models/")

    def get_custom(self, model_id: str) -> dict[str, Any]:
        return self._client.get(f"/api/custom-models/{_q(model_id)}")

    def register_custom(
        self,
        name: str,
        base_url: str,
        endpoint_model_name: str,
        *,
        api_key: str | None = None,
        description: str | None = None,
        requires_api_key: bool = True,
        model_type: str = "chat",
        capabilities: Iterable[str] | None = None,
        input_cost_per_million: float | None = None,
        output_cost_per_million: float | None = None,
        parameter_constraints: Mapping[str, Any] | None = None,
        default_config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register an OpenAI-compatible endpoint as a model (``POST /api/custom-models/``,
        scope ``models:manage``).

        ``base_url`` is the API root that serves ``/chat/completions`` (for
        example ``https://inference.example.org/v1``). ``endpoint_model_name``
        is the ``model`` value the endpoint expects. ``api_key`` (the
        endpoint's key, not your BenGER key) is stored encrypted for the key's
        user; responses only report ``has_credential``. The model starts
        private; use its ``id`` (``custom-<uuid>``) in generation configs.
        ``parameter_constraints`` example:
        ``{"temperature": {"supported": True, "min": 0, "max": 1},
        "max_tokens": {"max": 8192}}``.
        """
        body = _drop_none(
            {
                "name": name,
                "base_url": base_url,
                "endpoint_model_name": endpoint_model_name,
                "api_key": api_key,
                "description": description,
                "requires_api_key": requires_api_key,
                "model_type": model_type,
                "capabilities": list(capabilities) if capabilities is not None else None,
                "input_cost_per_million": input_cost_per_million,
                "output_cost_per_million": output_cost_per_million,
                "parameter_constraints": dict(parameter_constraints)
                if parameter_constraints is not None
                else None,
                "default_config": dict(default_config) if default_config is not None else None,
            }
        )
        return self._client.post("/api/custom-models/", json=body)

    def update_custom(self, model_id: str, **fields: Any) -> dict[str, Any]:
        """``PATCH /api/custom-models/{id}`` (name, base_url, endpoint_model_name, ...)."""
        return self._client.patch(f"/api/custom-models/{_q(model_id)}", json=fields)

    def set_visibility(
        self,
        model_id: str,
        *,
        is_private: bool | None = None,
        is_public: bool | None = None,
        organization_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """``PATCH /api/custom-models/{id}/visibility``: private, org-shared or public."""
        body = _drop_none(
            {
                "is_private": is_private,
                "is_public": is_public,
                "organization_ids": list(organization_ids)
                if organization_ids is not None
                else None,
            }
        )
        return self._client.patch(f"/api/custom-models/{_q(model_id)}/visibility", json=body)

    def set_credential(
        self, model_id: str, api_key: str, *, expected_base_url: str | None = None
    ) -> dict[str, Any]:
        """Store the endpoint key for this user (``PUT /api/custom-models/{id}/credential``).

        With ``expected_base_url`` the server refuses (409) if the model's
        endpoint changed meanwhile.
        """
        body = _drop_none({"api_key": api_key, "expected_base_url": expected_base_url})
        return self._client.put(f"/api/custom-models/{_q(model_id)}/credential", json=body)

    def credential_status(self, model_id: str) -> dict[str, Any]:
        """``{"has_credential": bool, "updated_at": str | None}``."""
        return self._client.get(f"/api/custom-models/{_q(model_id)}/credential")

    def delete_credential(self, model_id: str) -> dict[str, Any]:
        return self._client.delete(f"/api/custom-models/{_q(model_id)}/credential")

    def test(
        self, model_id: str, *, api_key: str | None = None, chat_ping: bool = False
    ) -> dict[str, Any]:
        """Probe a saved model (``POST /api/custom-models/{id}/test``).

        Returns ``{"status": "success" | "error", "message", "error_type"}``,
        plus ``chat_ping`` (latency of a one-message completion) when asked.
        The probe is limited to 10 calls a minute per user.
        """
        body = _drop_none({"api_key": api_key, "chat_ping": chat_ping})
        return self._client.post(f"/api/custom-models/{_q(model_id)}/test", json=body)

    def test_endpoint(self, base_url: str, *, api_key: str | None = None) -> dict[str, Any]:
        """Probe an unsaved endpoint (``POST /api/custom-models/test``)."""
        body = _drop_none({"base_url": base_url, "api_key": api_key})
        return self._client.post("/api/custom-models/test", json=body)

    def delete(self, model_id: str) -> Any:
        """``DELETE /api/custom-models/{id}``; soft-deletes when generations reference it."""
        return self._client.delete(f"/api/custom-models/{_q(model_id)}")


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #


def _job_ids(jobs: Any) -> list[str]:
    if isinstance(jobs, Mapping):
        return [str(j) for j in jobs.get("generation_job_ids") or []]
    if isinstance(jobs, str):
        return [jobs]
    return [str(j) for j in jobs]


class Generation(_Resource):
    """Model response generation for a project (scopes ``runs:read`` / ``runs:write``)."""

    def get_config(self, project_id: str) -> dict[str, Any]:
        """``GET /api/projects/{id}/generation-config`` (``selected_configuration``)."""
        return self._client.get(f"/api/projects/{_q(project_id)}/generation-config")

    def configure(
        self,
        project_id: str,
        *,
        models: Iterable[str] | None = None,
        prompt_structures: Mapping[str, Mapping[str, Any]] | None = None,
        runs_per_task: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Merge settings into the project's ``generation_config``.

        Sends ``PATCH /api/projects/{id}`` with ``generation_config``, which
        the server deep-merges, so keys you do not send survive.
        (``PUT /api/projects/{id}/generation-config`` would replace the whole
        document.) ``models`` becomes ``selected_configuration.models``
        (catalog ids or ``custom-...`` ids); ``prompt_structures`` maps a
        structure key to ``{"name", "system_prompt", "instruction_prompt", ...}``.
        Returns the updated project.
        """
        config: dict[str, Any] = dict(extra)
        if models is not None:
            selected = dict(config.get("selected_configuration") or {})
            selected["models"] = list(models)
            config["selected_configuration"] = selected
        if prompt_structures is not None:
            config["prompt_structures"] = {k: dict(v) for k, v in prompt_structures.items()}
        if runs_per_task is not None:
            config["runs_per_task"] = runs_per_task
        return self._client.patch(
            f"/api/projects/{_q(project_id)}", json={"generation_config": config}
        )

    def set_structure(
        self, project_id: str, key: str, structure: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Create or replace one prompt structure
        (``PUT /api/projects/{id}/generation-config/structures/{key}``)."""
        return self._client.put(
            f"/api/projects/{_q(project_id)}/generation-config/structures/{_q(key)}",
            json=dict(structure),
        )

    def start(
        self,
        project_id: str,
        *,
        mode: str = "missing",
        model_ids: Iterable[str] | None = None,
        task_ids: Iterable[str] | None = None,
        structure_keys: Iterable[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        seed: int | None = None,
        model_configs: Mapping[str, Any] | None = None,
        runs_per_task: int | None = None,
        billing_organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Queue generation (``POST /api/generation-tasks/projects/{id}/generate``).

        ``mode`` is ``"missing"`` (cells without a result), ``"all"``
        (regenerate everything) or ``"single"`` (exactly one task and one
        model). Without ``model_ids`` the project's configured models run.
        ``structure_keys`` is required when the project has prompt
        structures. Returns ``{project_id, mode, tasks_queued, models_count,
        generation_job_ids, estimated_time_seconds, message}``; pass it to
        :meth:`wait`.
        """
        parameters = _drop_none(
            {"temperature": temperature, "max_tokens": max_tokens, "seed": seed}
        )
        body = _drop_none(
            {
                "mode": mode,
                "model_ids": list(model_ids) if model_ids is not None else None,
                "task_ids": list(task_ids) if task_ids is not None else None,
                "structure_keys": list(structure_keys) if structure_keys is not None else None,
                "parameters": parameters or None,
                "model_configs": dict(model_configs) if model_configs is not None else None,
                "runs_per_task": runs_per_task,
                "billing_organization_id": billing_organization_id,
            }
        )
        return self._client.post(
            f"/api/generation-tasks/projects/{_q(project_id)}/generate", json=body
        )

    def status(self, project_id: str, jobs: Any = None) -> dict[str, Any]:
        """Generation progress of a project (``GET /api/projects/{id}/generation-status``).

        ``jobs`` (a :meth:`start` result or a list of job ids) narrows it to
        those jobs. Returns ``{"generations": [...], "counts": {status: n},
        "done": bool, "is_running": bool}``. Job ids the server no longer
        lists count as ``"missing"`` (and as done).
        """
        data = self._client.get(f"/api/projects/{_q(project_id)}/generation-status")
        generations = list(data.get("generations") or [])
        if jobs is not None:
            wanted = _job_ids(jobs)
            by_id = {g.get("id"): g for g in generations}
            generations = [by_id.get(j) or {"id": j, "status": "missing"} for j in wanted]
        counts: dict[str, int] = {}
        for g in generations:
            key = g.get("status") or "unknown"
            counts[key] = counts.get(key, 0) + 1
        done = all(
            g.get("status") in GENERATION_FINAL_STATUSES or g.get("status") == "missing"
            for g in generations
        )
        return {
            "generations": generations,
            "counts": counts,
            "done": done,
            "is_running": not done,
        }

    def job(self, generation_id: str) -> dict[str, Any]:
        """One job (``GET /api/generation/status/{id}``): ``{id, status, message}``.

        Not callable with a key limited to a project list (the route names
        no project); use :meth:`status` there.
        """
        return self._client.get(f"/api/generation/status/{_q(generation_id)}")

    def wait(
        self,
        project_id: str,
        jobs: Any,
        *,
        timeout: float = 6 * 3600.0,
        interval: float = 5.0,
        raise_on_failure: bool = False,
    ) -> dict[str, Any]:
        """Poll :meth:`status` until every job is final and return the last status.

        With ``raise_on_failure=True`` a failed or stopped job raises
        :class:`~benger_client.errors.BengerJobError`.
        """
        ids = _job_ids(jobs)
        if not ids:
            return {"generations": [], "counts": {}, "done": True, "is_running": False}

        def poll():
            result = self.status(project_id, ids)
            return result if result["done"] else None

        result = self._client.wait_until(
            poll,
            timeout=timeout,
            interval=interval,
            max_interval=60.0,
            description=f"{len(ids)} generation job(s)",
        )
        if raise_on_failure:
            bad = [g for g in result["generations"] if g.get("status") != "completed"]
            if bad:
                raise BengerJobError(f"{len(bad)} of {len(ids)} generation job(s) failed", result)
        return result

    def task_status(
        self,
        project_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        status_filter: str | None = None,
        structure_key: str | None = None,
    ) -> dict[str, Any]:
        """Task x model matrix (``GET /api/generation-tasks/projects/{id}/task-status``)."""
        return self._client.get(
            f"/api/generation-tasks/projects/{_q(project_id)}/task-status",
            params={
                "page": page,
                "page_size": page_size,
                "status_filter": status_filter,
                "structure_key": structure_key,
            },
        )

    def result(self, task_id: str, model_id: str, **params: Any) -> dict[str, Any]:
        """Generated responses for one task and model
        (``GET /api/generation-tasks/generation-result``, needs ``tasks:read_reference``)."""
        return self._client.get(
            "/api/generation-tasks/generation-result",
            params={"task_id": task_id, "model_id": model_id, **params},
        )


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #


class Evaluations(_Resource):
    """Automatic evaluation (scopes ``evaluations:read`` / ``evaluations:run`` /
    ``results:read``)."""

    def supported_metrics(self) -> Any:
        """``GET /api/evaluations/supported-metrics``."""
        return self._client.get("/api/evaluations/supported-metrics")

    def get_config(self, project_id: str) -> dict[str, Any]:
        """``GET /api/evaluations/projects/{id}/evaluation-config``."""
        return self._client.get(f"/api/evaluations/projects/{_q(project_id)}/evaluation-config")

    def configure(
        self,
        project_id: str,
        evaluation_configs: Iterable[Mapping[str, Any]] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Save evaluation settings (``PUT /api/evaluations/projects/{id}/evaluation-config``).

        The server deep-merges the body into the stored config; the
        ``evaluation_configs`` list is replaced as a whole. Each entry::

            {"id": "bleu-answer", "metric": "bleu",
             "prediction_fields": ["__all_model__"],   # or "model:<field>", "human:<field>"
             "reference_fields": ["reference_answer"], # task data field(s)
             "metric_parameters": {...}, "enabled": True}

        Returns ``{"message", "config", "warnings"}``; ``warnings`` names
        configs that will grade nothing as written.
        """
        body: dict[str, Any] = dict(extra)
        if evaluation_configs is not None:
            body["evaluation_configs"] = [dict(c) for c in evaluation_configs]
        return self._client.put(
            f"/api/evaluations/projects/{_q(project_id)}/evaluation-config", json=body
        )

    def run(
        self,
        project_id: str,
        evaluation_configs: Iterable[Mapping[str, Any]] | None = None,
        *,
        force_rerun: bool = False,
        task_ids: Iterable[str] | None = None,
        model_ids: Iterable[str] | None = None,
        structure_keys: Iterable[str] | None = None,
        batch_size: int | None = None,
        seed: int | None = None,
        label_config_version: str | None = None,
        billing_organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Start an evaluation run (``POST /api/evaluations/run``).

        Without ``evaluation_configs`` the project's saved, enabled configs
        are used. ``force_rerun=False`` only evaluates cells without a
        result. Returns ``{evaluation_id, project_id, status, message,
        evaluation_configs_count, started_at, ...}``; an identical run still
        in flight is returned instead of a new one.
        """
        if evaluation_configs is None:
            saved = self.get_config(project_id).get("evaluation_configs") or []
            configs = [c for c in saved if c.get("enabled", True)]
            if not configs:
                raise BengerError(
                    f"Project {project_id} has no enabled evaluation_configs; "
                    "pass evaluation_configs or call evaluations.configure() first"
                )
        else:
            configs = [dict(c) for c in evaluation_configs]
        body = _drop_none(
            {
                "project_id": project_id,
                "evaluation_configs": configs,
                "force_rerun": force_rerun,
                "task_ids": list(task_ids) if task_ids is not None else None,
                "model_ids": list(model_ids) if model_ids is not None else None,
                "structure_keys": list(structure_keys) if structure_keys is not None else None,
                "batch_size": batch_size,
                "seed": seed,
                "label_config_version": label_config_version,
                "billing_organization_id": billing_organization_id,
            }
        )
        return self._client.post("/api/evaluations/run", json=body)

    def status(self, evaluation_id: str, *, project_id: str | None = None) -> dict[str, Any]:
        """``{id, status, message}`` of a run.

        Uses ``GET /api/evaluations/evaluation/status/{id}``. A key limited to
        a project list cannot call that route (it names no project); pass
        ``project_id`` and the run is looked up in
        ``GET /api/runs?type=evaluation&project_id=...`` instead.
        """
        if project_id is None:
            return self._client.get(f"/api/evaluations/evaluation/status/{_q(evaluation_id)}")
        listing = self._client.get(
            "/api/runs",
            params={"type": "evaluation", "project_id": project_id, "page_size": 200},
        )
        for run in listing.get("items") or []:
            if run.get("id") == evaluation_id:
                return {
                    "id": run["id"],
                    "status": run.get("status"),
                    "message": run.get("error_message"),
                }
        return {"id": evaluation_id, "status": "missing", "message": "Run not listed"}

    def wait(
        self,
        evaluation_id: str | Mapping[str, Any],
        *,
        project_id: str | None = None,
        timeout: float = 6 * 3600.0,
        interval: float = 5.0,
        raise_on_failure: bool = True,
    ) -> dict[str, Any]:
        """Poll :meth:`status` until the run is final and return the last status.

        Accepts the :meth:`run` result too. Raises
        :class:`~benger_client.errors.BengerJobError` when the run ends
        ``failed``/``cancelled``/``stopped`` unless ``raise_on_failure=False``.
        """
        if isinstance(evaluation_id, Mapping):
            evaluation_id = str(evaluation_id["evaluation_id"])

        def poll():
            state = self.status(evaluation_id, project_id=project_id)
            final = state.get("status") in EVALUATION_FINAL_STATUSES
            return state if final or state.get("status") == "missing" else None

        state = self._client.wait_until(
            poll,
            timeout=timeout,
            interval=interval,
            max_interval=60.0,
            description=f"evaluation {evaluation_id}",
        )
        if raise_on_failure and state.get("status") != "completed":
            raise BengerJobError(
                f"Evaluation {evaluation_id} ended {state.get('status')}: "
                f"{state.get('message') or ''}".rstrip(": "),
                state,
            )
        return state

    def results(self, evaluation_id: str) -> dict[str, Any]:
        """Detailed results of one run (``GET /api/evaluations/run/results/{id}``):
        ``results_by_config``, ``aggregated_metrics``, ``error_message``..."""
        return self._client.get(f"/api/evaluations/run/results/{_q(evaluation_id)}")

    def project_results(self, project_id: str, *, latest_only: bool = True) -> dict[str, Any]:
        """``GET /api/evaluations/run/results/project/{id}``:
        ``{"project_id", "evaluations": [...], "total_count"}``."""
        return self._client.get(
            f"/api/evaluations/run/results/project/{_q(project_id)}",
            params={"latest_only": str(latest_only).lower()},
        )

    def by_task_model(self, project_id: str, **params: Any) -> Any:
        """Score matrix (``GET /api/evaluations/projects/{id}/results/by-task-model``)."""
        return self._client.get(
            f"/api/evaluations/projects/{_q(project_id)}/results/by-task-model", params=params
        )

    def cancel(self, evaluation_id: str) -> dict[str, Any]:
        """``POST /api/evaluations/run/{id}/cancel``."""
        return self._client.post(f"/api/evaluations/run/{_q(evaluation_id)}/cancel")


# --------------------------------------------------------------------------- #
# Exports (v1)
# --------------------------------------------------------------------------- #


class Exports(_Resource):
    """Project exports through ``/api/v1`` (scopes ``exports:read`` +
    ``tasks:read_reference``, role ORG_ADMIN or CONTRIBUTOR)."""

    def create(
        self,
        project_id: str,
        *,
        format: str = "json",
        task_ids: Iterable[str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Start an export (``POST /api/v1/projects/{id}/exports``, 202).

        ``format``: json, ndjson, ndjson_gz, csv, tsv, comprehensive or
        label_studio. ``task_ids`` restricts a json export. An
        ``Idempotency-Key`` is sent automatically; pass your own (e.g.
        ``"nightly-2026-10-30"``) to make reruns return the same job.
        """
        body = _drop_none(
            {"format": format, "task_ids": list(task_ids) if task_ids is not None else None}
        )
        return self._client.post(
            f"/api/v1/projects/{_q(project_id)}/exports",
            json=body,
            idempotency_key=idempotency_key,
        )

    def get(self, job_id: str) -> dict[str, Any]:
        """``GET /api/v1/exports/{id}``."""
        return self._client.get(f"/api/v1/exports/{_q(job_id)}")

    def wait(
        self, job_id: str | Mapping[str, Any], *, timeout: float = 1800.0, interval: float = 2.0
    ) -> dict[str, Any]:
        """Poll until the export is final; raise on ``failed``."""
        if isinstance(job_id, Mapping):
            job_id = str(job_id["id"])

        def poll():
            job = self.get(job_id)
            return job if job.get("status") in JOB_FINAL_STATUSES else None

        job = self._client.wait_until(
            poll, timeout=timeout, interval=interval, description=f"export {job_id}"
        )
        if job.get("status") == "failed":
            raise BengerJobError(
                f"Export {job_id} failed: {job.get('error_message') or 'unknown error'}", job
            )
        return job

    def download_url(self, job_id: str) -> str:
        """The presigned object-storage URL (valid 5 minutes) behind
        ``GET /api/v1/exports/{id}/download``."""
        response = self._client.raw_request("GET", f"/api/v1/exports/{_q(job_id)}/download")
        location = response.headers.get("Location")
        if not location:
            raise BengerError(f"Export {job_id} download answered without a Location header")
        return location

    def download(self, job_id: str | Mapping[str, Any], path: str | os.PathLike | None = None):
        """Download a finished export.

        Writes to ``path`` and returns it as a ``Path``; without ``path``
        returns the bytes. The storage request never carries the access key.
        """
        if isinstance(job_id, Mapping):
            job_id = str(job_id["id"])
        url = self.download_url(job_id)
        with self._client._storage_client() as storage:
            if path is None:
                response = storage.get(url)
                if response.status_code >= 300:
                    raise BengerError(f"Export download failed ({response.status_code})")
                return response.content
            target = Path(path)
            with storage.stream("GET", url) as response:
                if response.status_code >= 300:
                    raise BengerError(f"Export download failed ({response.status_code})")
                with target.open("wb") as fh:
                    for chunk in response.iter_bytes():
                        fh.write(chunk)
            return target

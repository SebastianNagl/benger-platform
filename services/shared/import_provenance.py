"""Import provenance and idempotent re-import of import jobs (migration 147).

Every import job records what it imported: the SHA-256 of the payload bytes
the worker downloaded (``import_jobs.payload_sha256``) and a source manifest
(``import_jobs.source_manifest``) naming the payload, where it came from, the
target and the import options, plus an optional manifest the caller declared
when creating the job (for example the source files a converter built the
payload from, with their hashes).

From the manifest follows the job's ``idempotency_key``: a SHA-256 over the
payload hash, the target and the options that shape what the import writes.
A new import whose key equals that of an import that already completed is a
no-op: the job completes without writing anything, points at the earlier job
through ``duplicate_of_job_id`` and returns that job's project. A changed
payload has another hash and so another key, and imports as usual.

Same target means: the same existing project for the project-scoped imports
(nested, tabular, merge); for an import that creates a project, the same
requester, organization and group, as long as the project the earlier import
created still exists and is not deleted. A merge preview (``dry_run``) writes
nothing and gets no key, so it never matches and is never matched.

An import records the tasks it wrote (``import_job_tasks``): the tasks it
created and the existing tasks it added rows to, as a merge does. A repeat
is a no-op only while every one of those tasks still exists; once any of
them was deleted, the repeat imports again as a new import with the same
payload hash and no ``duplicate_of_job_id``. ``reimport`` (API only) imports
the same payload again in any case; that job still records hash, manifest,
key and its tasks.

Two identical imports running at once are serialized by a transaction-level
advisory lock on the key, taken before the lookup and held until the import
commits, so the second one sees the first one's completed row and becomes
the no-op. The wait is bounded by the worker's ``lock_timeout``: when the
first import takes longer, the second fails with the retryable 409
``import_conflict``, and starting it again after the first finished is the
no-op.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any, BinaryIO, Dict, Iterable, Mapping, Optional, Set, Tuple

MANIFEST_VERSION = 1

# Upper bound of a declared manifest, serialized as JSON.
DECLARED_MANIFEST_MAX_BYTES = 64 * 1024

# Class id of the two-key advisory locks taken on an import key; the two-key
# form has its own key space, apart from the one-key locks used elsewhere.
_LOCK_CLASS = 0x1D9

_HASH_CHUNK = 1024 * 1024

# Task ids per statement when an import's task links are written.
_LINK_BATCH = 10_000

# Import modes whose result depends on model_id_map; the others ignore it.
_MODES_WITH_MODEL_MAP = frozenset({"merge", "comprehensive"})


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_fileobj(fileobj: BinaryIO) -> Tuple[str, int]:
    """``(sha256 hex, byte count)`` of a seekable file from its start; leaves
    the file at its start again."""
    fileobj.seek(0)
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = fileobj.read(_HASH_CHUNK)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    fileobj.seek(0)
    return digest.hexdigest(), size


def validate_declared_manifest(value: Any) -> Optional[Dict[str, Any]]:
    """The caller's declared manifest, or None. Raises ``ValueError`` for
    anything but a JSON object of at most ``DECLARED_MANIFEST_MAX_BYTES``."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("source_manifest must be a JSON object")
    try:
        size = len(canonical_json(value).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ValueError("source_manifest must be plain JSON") from exc
    if size > DECLARED_MANIFEST_MAX_BYTES:
        raise ValueError(
            f"source_manifest is too large ({size} bytes; "
            f"limit {DECLARED_MANIFEST_MAX_BYTES})"
        )
    return value


def project_target(project_id: str) -> Dict[str, Any]:
    """Target of an import into an existing project."""
    return {"kind": "project", "project_id": project_id}


def new_project_target(
    requested_by: str,
    organization_id: Optional[str],
    organization_group_id: Optional[str],
) -> Dict[str, Any]:
    """Target of an import that creates a project."""
    return {
        "kind": "new_project",
        "requested_by": requested_by,
        "organization_id": organization_id,
        "organization_group_id": organization_group_id,
    }


def build_manifest(
    *,
    payload_sha256: str,
    byte_size: int,
    object_key: str,
    source_connection_id: Optional[str],
    target: Dict[str, Any],
    mode: str,
    model_id_map: Optional[Mapping[str, str]] = None,
    reimport: bool = False,
    declared: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """The source manifest of an import job.

    ``mode`` is what the payload is imported as: ``nested``, ``merge``,
    ``merge_preview``, ``comprehensive`` or a tabular format (``csv``,
    ``tsv``, ``txt``).
    """
    source: Dict[str, Any] = {
        "kind": "storage_connection" if source_connection_id else "upload",
        "object_key": object_key,
        "filename": os.path.basename(object_key),
    }
    if source_connection_id:
        source["connection_id"] = source_connection_id
    manifest: Dict[str, Any] = {
        "version": MANIFEST_VERSION,
        "payload": {"sha256": payload_sha256, "byte_size": byte_size},
        "source": source,
        "target": target,
        "import": {
            "mode": mode,
            "model_id_map": (
                dict(sorted((model_id_map or {}).items()))
                if mode in _MODES_WITH_MODEL_MAP
                else {}
            ),
            "reimport": bool(reimport),
        },
    }
    if declared is not None:
        manifest["declared"] = declared
    return manifest


def idempotency_key(manifest: Mapping[str, Any]) -> Optional[str]:
    """SHA-256 over the parts of the manifest that decide what the import
    writes: payload hash, target, mode and (where it applies) the model map.
    None for a merge preview, which writes nothing. Where the payload came
    from, its file name, ``reimport`` and the declared manifest do not count."""
    options = manifest["import"]
    if options["mode"] == "merge_preview":
        return None
    return hashlib.sha256(
        canonical_json(
            {
                "payload_sha256": manifest["payload"]["sha256"],
                "target": manifest["target"],
                "mode": options["mode"],
                "model_id_map": options["model_id_map"],
            }
        ).encode("utf-8")
    ).hexdigest()


def lock_import_key(db, key: str) -> None:
    """Hold a transaction-level advisory lock on ``key`` until ``db``'s
    transaction ends, so identical imports run one after the other."""
    from sqlalchemy import text

    # Lower 31 bits of the key: an int4 for the two-key lock form.
    low = int(key[:8], 16) & 0x7FFFFFFF
    db.execute(
        text("SELECT pg_advisory_xact_lock(:cls, :key)"),
        {"cls": _LOCK_CLASS, "key": low},
    )


def track_written_tasks(db) -> Set[str]:
    """The ids of the tasks ``db`` writes from now on, filled at each flush:
    every task it creates and every task a row it creates points at through
    ``task_id``. Includes ids of other kinds of ``task_id``;
    :func:`record_written_tasks` keeps only real tasks of the project."""
    from sqlalchemy import event

    from project_models import Task

    written: Set[str] = set()

    def _collect(session, _flush_context, _instances) -> None:
        for obj in session.new:
            task_id = obj.id if isinstance(obj, Task) else getattr(obj, "task_id", None)
            if isinstance(task_id, str) and task_id:
                written.add(task_id)

    event.listen(db, "before_flush", _collect)
    return written


def record_written_tasks(
    db, job_id: str, project_id: Optional[str], task_ids: Iterable[str]
) -> None:
    """Link ``job_id`` to those of ``task_ids`` that are tasks of
    ``project_id``, in ``db``'s transaction. Flush first, so the import's
    pending tasks are collected and visible."""
    from sqlalchemy import text

    if not project_id:
        return
    ids = sorted(task_ids)
    for start in range(0, len(ids), _LINK_BATCH):
        db.execute(
            text(
                "INSERT INTO import_job_tasks (import_job_id, task_id) "
                "SELECT :job_id, id FROM tasks "
                "WHERE project_id = :project_id AND id = ANY(:ids)"
            ),
            {
                "job_id": job_id,
                "project_id": project_id,
                "ids": ids[start : start + _LINK_BATCH],
            },
        )


def find_completed_import(db, key: str, job_id: str, target: Mapping[str, Any]):
    """The latest completed, non-no-op import job with ``key`` other than
    ``job_id`` whose written tasks all still exist, or None. For a
    new-project target the project that import created must also still exist
    and not be deleted."""
    from sqlalchemy import exists

    from models import ImportJob, ImportJobTask, JobStatus
    from project_models import Project, Task

    lost_task = exists().where(
        ImportJobTask.import_job_id == ImportJob.id,
        ~exists().where(Task.id == ImportJobTask.task_id),
    )
    query = (
        db.query(ImportJob)
        .filter(
            ImportJob.idempotency_key == key,
            ImportJob.status == JobStatus.COMPLETED.value,
            ImportJob.duplicate_of_job_id.is_(None),
            ImportJob.id != job_id,
            ~lost_task,
        )
        .order_by(ImportJob.updated_at.desc())
    )
    if target.get("kind") == "new_project":
        query = query.join(Project, Project.id == ImportJob.project_id).filter(
            Project.deleted_at.is_(None)
        )
    return query.first()


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def no_op_result(prior, payload_sha256: str) -> Dict[str, Any]:
    """Result of a job that repeated ``prior``: nothing was written. It keeps
    the earlier import's project fields, so a client lands where that
    import did, and carries no counts of its own."""
    earlier = prior.result or {}
    result: Dict[str, Any] = {
        "project_id": prior.project_id,
        "no_op": True,
        "duplicate_of": {
            "job_id": prior.id,
            "completed_at": _iso(prior.updated_at),
            "payload_sha256": payload_sha256,
        },
    }
    for field in ("project_title", "project_url"):
        if earlier.get(field):
            result[field] = earlier[field]
    return result

"""Async project export/import Celery-task implementations (worker).

Extracted from ``services/workers/tasks.py`` as part of the structural
decomposition of that module. Behavior-preserving move: the function bodies
are byte-identical to the originals, except that references to ``tasks``-module
globals (``SessionLocal``, ``logger``, monkeypatched helpers, etc.) are
resolved through the ``tasks`` module at call time so that test monkeypatches
like ``patch("tasks.SessionLocal")`` continue to apply.

The public, decorated Celery task wrappers (with their original names, task
names, and decorator args) remain in ``tasks.py`` and delegate here.
"""

import tasks
from typing import Any, Dict, List

# S3/MinIO require every multipart part EXCEPT the last to be >= 5MB. We buffer
# to 8MB before flushing a part; 8MB x 10_000 parts (the S3 part-count ceiling)
# = 80GB, far beyond any realistic export.
_EXPORT_PART_SIZE = 8 * 1024 * 1024

# Spool the downloaded import artifact in RAM up to this size, then spill to
# disk — mirrors the API endpoint's _IMPORT_SPOOL_THRESHOLD so the worker's peak
# heap during download stays bounded the same way.
_IMPORT_SPOOL_THRESHOLD = 4 * 1024 * 1024

def export_project_impl(self, job_id: str) -> Dict[str, Any]:
    """Stream a project export into object storage as a multipart upload.

    Reads the ExportJob row, picks the streaming generator for its format, and
    pushes the bytes to storage in ~8MB parts. On success the row is marked
    completed with the object_key, byte_size, and a 7-day expiry; on failure
    the in-flight multipart upload is aborted and the row marked failed.

    Idempotent: a job already past `running` (completed/failed) is skipped, so
    an acks_late redelivery of a finished job is a no-op. A job left `running`
    by a crashed worker IS re-run — that's the crash-recovery path.
    """
    from datetime import datetime, timedelta, timezone

    from export_stream import (
        EXPORT_FORMAT_MEDIA_TYPES,
        export_format_is_gzipped,
        select_export_generator,
    )
    from models import ExportJob, JobStatus
    from project_models import Project
    from storage.object_storage import object_storage

    db = tasks.SessionLocal()
    upload_id = None
    file_key = None
    try:
        job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
        if job is None:
            tasks.logger.error("export_project: job %s not found", job_id)
            return {"status": "error", "error": "job_not_found", "job_id": job_id}

        if job.status not in (JobStatus.PENDING.value, JobStatus.RUNNING.value):
            tasks.logger.info(
                "export_project: job %s already in status %s; skipping",
                job_id,
                job.status,
            )
            return {"status": "skipped", "job_id": job_id, "job_status": job.status}

        project = (
            db.query(Project).filter(Project.id == job.project_id).first()
        )
        if project is None:
            job.status = JobStatus.FAILED.value
            job.error_message = "project_not_found"
            db.commit()
            return {"status": "error", "error": "project_not_found", "job_id": job_id}

        fmt = job.format or "json"
        channel = f"export:progress:{job.project_id}"

        job.status = JobStatus.RUNNING.value
        db.commit()
        tasks._publish_progress(
            channel,
            {"job_id": job_id, "status": "running", "progress": 0, "bytes": 0},
        )

        media_type, ext = EXPORT_FORMAT_MEDIA_TYPES.get(
            fmt, ("application/octet-stream", "dat")
        )
        safe_title = (project.title or "project").replace(" ", "_")
        filename = f"{safe_title}_export.{ext}"

        upload = object_storage.create_multipart_upload(
            filename=filename,
            file_type="exports",
            user_id=job.requested_by,
            content_type=media_type,
        )
        upload_id = upload["upload_id"]
        file_key = upload["file_key"]

        buffer = bytearray()
        parts: List[Dict[str, Any]] = []
        part_number = 1
        total_bytes = 0

        # gzip-compress on the fly for gzipped formats. zlib with wbits
        # 16+MAX_WBITS emits a standard gzip member; .compress() may buffer and
        # return b"", with the remainder flushed once the generator is drained.
        # total_bytes tracks the *stored* (compressed) byte count so the job's
        # byte_size is accurate even before complete_multipart_upload reports it.
        compressor = None
        if export_format_is_gzipped(fmt):
            import zlib
            compressor = zlib.compressobj(6, zlib.DEFLATED, zlib.MAX_WBITS | 16)

        def _flush_part() -> None:
            nonlocal buffer, part_number
            if not buffer:
                return
            etag = object_storage.upload_part(
                file_key, upload_id, part_number, bytes(buffer)
            )
            parts.append({"PartNumber": part_number, "ETag": etag})
            part_number += 1
            buffer = bytearray()

        def _consume(data: bytes) -> None:
            nonlocal total_bytes
            if compressor is not None:
                data = compressor.compress(data)
            if not data:
                return
            buffer.extend(data)
            total_bytes += len(data)

        # Throttled, cursor-safe progress persistence. The json generator streams
        # over a server-side cursor on `db`; committing `db` mid-stream would
        # invalidate that cursor and sever the export, so the progress UPDATE runs
        # on its own short-lived session. Capped at 99 (the completion path sets
        # 100) and written only when the integer percent advances, so a whole
        # export costs <= 100 small UPDATEs regardless of size.
        progress_state = {"last": 0}

        def _on_progress(streamed: int, total: int) -> None:
            if total <= 0:
                return
            pct = min(99, round(streamed * 100 / total))
            if pct <= progress_state["last"]:
                return
            progress_state["last"] = pct
            pdb = tasks.SessionLocal()
            try:
                pdb.query(ExportJob).filter(ExportJob.id == job_id).update(
                    {"progress": pct}, synchronize_session=False
                )
                pdb.commit()
            except Exception:
                pdb.rollback()
            finally:
                pdb.close()
            tasks._publish_progress(
                channel,
                {
                    "job_id": job_id,
                    "status": "running",
                    "progress": pct,
                    "bytes": total_bytes,
                },
            )

        # task_ids restricts a json export to a selected/filtered subset; NULL is
        # a whole-project export. select_export_generator rejects a subset for any
        # non-json format, but create_export_job already guards that at 422. Only
        # the json generator consumes progress_cb; other formats ignore it and the
        # bar stays at 0 until completion flips it to 100.
        generator = select_export_generator(
            db, project, fmt, task_ids=job.task_ids, progress_cb=_on_progress
        )

        for chunk in generator:
            if not chunk:
                continue
            raw = chunk.encode("utf-8") if isinstance(chunk, str) else chunk
            _consume(raw)
            if len(buffer) >= _EXPORT_PART_SIZE:
                _flush_part()
                tasks._publish_progress(
                    channel,
                    {
                        "job_id": job_id,
                        "status": "running",
                        "progress": progress_state["last"],
                        "bytes": total_bytes,
                    },
                )

        # Drain the compressor's internal buffer into the final part(s).
        if compressor is not None:
            tail = compressor.flush()
            if tail:
                buffer.extend(tail)
                total_bytes += len(tail)

        # Final flush — the last part may be < 5MB (S3 only constrains
        # non-final parts), so a small export ends up as a single short part.
        _flush_part()

        result_info = object_storage.complete_multipart_upload(
            file_key, upload_id, parts
        )
        byte_size = result_info.get("size", total_bytes)

        job.status = JobStatus.COMPLETED.value
        job.object_key = file_key
        job.byte_size = byte_size
        job.progress = 100
        job.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        job.error_message = None
        db.commit()

        tasks._publish_progress(
            channel,
            {
                "job_id": job_id,
                "status": "completed",
                "progress": 100,
                "bytes": byte_size,
            },
        )
        tasks.logger.info(
            "export_project: job %s completed (%s bytes, key=%s)",
            job_id,
            byte_size,
            file_key,
        )
        return {
            "status": "completed",
            "job_id": job_id,
            "object_key": file_key,
            "byte_size": byte_size,
        }

    except Exception as exc:
        tasks.logger.error(
            "export_project: job %s failed: %s", job_id, exc, exc_info=True
        )
        # Abort the in-flight upload so no orphaned parts accrue storage cost.
        if upload_id and file_key:
            object_storage.abort_multipart_upload(file_key, upload_id)
        try:
            db.rollback()
            from models import ExportJob, JobStatus

            job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
            if job is not None:
                job.status = JobStatus.FAILED.value
                job.error_message = str(exc)[:2000]
                db.commit()
                tasks._publish_progress(
                    f"export:progress:{job.project_id}",
                    {
                        "job_id": job_id,
                        "status": "failed",
                        "progress": job.progress or 0,
                    },
                )
        except Exception as inner:
            tasks.logger.error(
                "export_project: failed to mark job %s failed: %s", job_id, inner
            )
        return {"status": "error", "job_id": job_id, "error": str(exc)}
    finally:
        db.close()

def import_project_impl(self, job_id: str) -> Dict[str, Any]:
    """Download an uploaded import artifact and stream-import it into the DB.

    The inverse of ``export_project``: reads the ImportJob row, downloads its
    object_key from storage into a seekable spool, then runs the same shared
    streaming driver the synchronous endpoints use. ``project_id`` set ⇒ nested
    (label-studio, into the existing project); ``project_id`` None ⇒ flat
    comprehensive (creates a new project). The driver parses with ijson and
    inserts in flush-batched passes, so import memory stays O(batch).

    Idempotent: a job already past `running` is skipped (acks_late redelivery of
    a finished job is a no-op); a job left `running` by a crashed worker IS
    re-run — its single end-of-import commit means a crashed run left nothing
    partial behind.
    """
    import tempfile
    from datetime import datetime, timedelta, timezone

    from import_stream import (
        ImportValidationError,
        run_full_project_import,
        run_nested_import,
    )
    from models import ImportJob, JobStatus
    from storage.object_storage import object_storage

    db = tasks.SessionLocal()
    try:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if job is None:
            tasks.logger.error("import_project: job %s not found", job_id)
            return {"status": "error", "error": "job_not_found", "job_id": job_id}

        if job.status not in (JobStatus.PENDING.value, JobStatus.RUNNING.value):
            tasks.logger.info(
                "import_project: job %s already in status %s; skipping",
                job_id,
                job.status,
            )
            return {"status": "skipped", "job_id": job_id, "job_status": job.status}

        # project_id is set for the nested (into-existing-project) format and
        # None for the comprehensive (creates-project) format. The progress
        # channel for a project-less import is keyed by job id instead.
        channel = f"import:progress:{job.project_id or job_id}"
        requested_by = job.requested_by
        object_key = job.object_key
        project_id = job.project_id

        job.status = JobStatus.RUNNING.value
        db.commit()
        tasks._publish_progress(
            channel,
            {"job_id": job_id, "status": "running", "progress": 0},
        )

        spooled = tempfile.SpooledTemporaryFile(max_size=_IMPORT_SPOOL_THRESHOLD)
        try:
            object_storage.download_to_fileobj(object_key, spooled)
            byte_size = spooled.tell()
            spooled.seek(0)

            if project_id:
                result = run_nested_import(db, project_id, spooled, requested_by)
                detected_format = "nested"
            else:
                result = run_full_project_import(db, spooled, requested_by)
                detected_format = "comprehensive"
        finally:
            spooled.close()

        # run_full_project_import creates the project; capture its id so the
        # status row and download/poll URLs resolve to the created project.
        result_project_id = (result or {}).get("project_id")

        job.status = JobStatus.COMPLETED.value
        job.format = detected_format
        job.byte_size = byte_size
        job.progress = 100
        job.result = result
        if result_project_id and not job.project_id:
            job.project_id = result_project_id
        job.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        job.error_message = None
        db.commit()

        tasks._publish_progress(
            f"import:progress:{job.project_id or job_id}",
            {"job_id": job_id, "status": "completed", "progress": 100},
        )
        tasks.logger.info(
            "import_project: job %s completed (%s bytes, format=%s, project=%s)",
            job_id,
            byte_size,
            detected_format,
            job.project_id,
        )
        return {
            "status": "completed",
            "job_id": job_id,
            "project_id": job.project_id,
            "byte_size": byte_size,
        }

    except ImportValidationError as exc:
        # Malformed / mistyped payload — a client error, not a worker fault. The
        # driver already rolled back nothing was committed; record the 4xx detail.
        tasks.logger.warning(
            "import_project: job %s validation failed (%s): %s",
            job_id,
            exc.status_code,
            exc.detail,
        )
        tasks._fail_import_job(db, job_id, f"{exc.status_code}: {exc.detail}")
        return {"status": "error", "job_id": job_id, "error": exc.detail}
    except Exception as exc:
        tasks.logger.error(
            "import_project: job %s failed: %s", job_id, exc, exc_info=True
        )
        tasks._fail_import_job(db, job_id, str(exc))
        return {"status": "error", "job_id": job_id, "error": str(exc)}
    finally:
        db.close()

def _fail_import_job_impl(db, job_id: str, message: str) -> None:
    """Roll back and mark an ImportJob failed, publishing a final progress event."""
    from models import ImportJob, JobStatus

    try:
        db.rollback()
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if job is not None:
            job.status = JobStatus.FAILED.value
            job.error_message = message[:2000]
            db.commit()
            tasks._publish_progress(
                f"import:progress:{job.project_id or job_id}",
                {
                    "job_id": job_id,
                    "status": "failed",
                    "progress": job.progress or 0,
                },
            )
    except Exception as inner:
        tasks.logger.error(
            "import_project: failed to mark job %s failed: %s", job_id, inner
        )

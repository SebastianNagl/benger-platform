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
from typing import Any, Dict, List, Optional

from storage.upload_policy import IMPORT_UPLOAD_MAX_BYTES

# S3/MinIO require every multipart part EXCEPT the last to be >= 5MB. We buffer
# to 8MB before flushing a part; 8MB x 10_000 parts (the S3 part-count ceiling)
# = 80GB, far beyond any realistic export.
_EXPORT_PART_SIZE = 8 * 1024 * 1024

# Spool the downloaded import artifact in RAM up to this size, then spill to
# disk — mirrors the API endpoint's _IMPORT_SPOOL_THRESHOLD so the worker's peak
# heap during download stays bounded the same way.
_IMPORT_SPOOL_THRESHOLD = 4 * 1024 * 1024

# Cap for a cloud-import source object (customer bucket): the same import cap
# as the presigned upload (upload_policy.IMPORT_UPLOAD_MAX_BYTES), so both
# import surfaces bound the artifact alike; checked via head_object BEFORE
# downloading.
_CLOUD_IMPORT_MAX_BYTES = IMPORT_UPLOAD_MAX_BYTES

# Cloud-import extensions dispatched to the tabular driver; everything else
# runs through the regular nested JSON driver.
_TABULAR_EXTENSIONS = {".csv": "csv", ".tsv": "tsv", ".txt": "txt"}

# Postgres error codes of a write that collided with a concurrent transaction:
# lock_not_available (lock_timeout), deadlock_detected, serialization_failure.
_CONCURRENT_WRITE_PGCODES = frozenset({"55P03", "40P01", "40001"})


def public_job_error(exc: BaseException, job_id: str, action: str) -> str:
    """The reason a failed export or import job reports to its API client.

    ``error_message`` is returned verbatim by the job status endpoints, so it
    must not carry the exception text: a database error embeds the whole SQL
    statement with its column list (Kolibri-1 benchmark, K5: an import job
    showed ``INSERT INTO users (... encrypted_openai_api_key ...)``), and
    storage or broker errors embed hosts and paths. The caller logs the full
    exception; the job keeps a short reason a person can act on.

    A write that collided with a concurrent one gets the
    ``"409: <action>_conflict: ..."`` shape (see ``split_job_error`` in the
    API), so a client can tell it apart and simply start the job again. Every
    other fault is reported without a status, as worker faults always were.
    """
    pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
    if pgcode in _CONCURRENT_WRITE_PGCODES:
        return (
            f"409: {action}_conflict: Another job was writing the same data at "
            f"the same time. Start the {action} again."
        )
    return (
        f"The {action} failed because of an internal error. The server log "
        f"has the details under job {job_id}."
    )


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
    from models import ExportJob, JobStatus, User
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
        # The requester decides which LMS users' real names the user block of
        # the comprehensive formats may carry (owner decision D8).
        requester = db.query(User).filter(User.id == job.requested_by).first()
        generator = select_export_generator(
            db,
            project,
            fmt,
            task_ids=job.task_ids,
            progress_cb=_on_progress,
            viewer=requester,
        )

        # Lossless export (variant_experiments, core 2.69) is decided for the
        # requester; the generator reads the answer from this scope while it
        # is drained (serializers.serialize_generation).
        from feature_flags import VARIANT_EXPERIMENTS
        from feature_flags.scope import flag_scope
        from feature_flags.worker import flag_enabled_sync

        with flag_scope(
            {VARIANT_EXPERIMENTS: flag_enabled_sync(db, job.requested_by, VARIANT_EXPERIMENTS)}
        ):
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
                job.error_message = public_job_error(exc, job_id, "export")
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

def import_project_impl(
    self,
    job_id: str,
    model_id_map: Optional[Dict[str, str]] = None,
    mode: Optional[str] = None,
    dry_run: bool = False,
    reimport: bool = False,
) -> Dict[str, Any]:
    """Download an uploaded import artifact and stream-import it into the DB.

    The inverse of ``export_project``: reads the ImportJob row, downloads its
    object_key from storage into a seekable spool, then runs the same shared
    streaming driver the synchronous endpoints use. ``project_id`` set ⇒ nested
    (label-studio, into the existing project); ``project_id`` None ⇒ flat
    comprehensive (creates a new project). The driver parses with ijson and
    inserts in flush-batched passes, so import memory stays O(batch).

    ``mode="merge"`` (with ``project_id`` set) merges a full project export's
    new results into that project (``run_merge_import``) instead of the
    nested import. ``model_id_map`` (source model id -> model id here) is the
    model translation of the create-new and the merge import; the nested and
    tabular imports ignore it. ``dry_run`` (merge only) is the merge preview:
    the merge runs and is rolled back, and only the job row is committed,
    completed with format ``merge_preview`` and the preview as its result.

    Provenance and re-import (``import_provenance``): the job records the
    payload's SHA-256 and its source manifest before importing. When an
    import with the same idempotency key (payload hash, target, options)
    already completed and every task it wrote still exists, the job
    completes as a no-op that writes nothing and names that job in
    ``duplicate_of_job_id``; ``reimport`` imports anyway. The job links the
    tasks it writes (``import_job_tasks``) in the import's commit.

    Idempotent: a job already past `running` is skipped (acks_late redelivery of
    a finished job is a no-op); a job left `running` by a crashed worker IS
    re-run — its single end-of-import commit means a crashed run left nothing
    partial behind.

    All or nothing: the job's completed state (status, format, size, result,
    created project) is written by the driver's ``before_commit`` hook, so it
    commits in the same transaction as the imported rows. A job that fails
    before that commit is marked failed with nothing imported; once it has
    committed it stays completed.
    """
    import tempfile
    from datetime import datetime, timedelta, timezone

    from import_stream import (
        ImportValidationError,
        run_full_project_import,
        run_merge_import,
        run_nested_import,
        run_tabular_import,
    )
    from models import ImportJob, JobStatus, OrgStorageConnection
    from storage.object_storage import object_storage

    import import_provenance as provenance

    # Filled by the driver's before_commit hook (_mark_completed below).
    completed: Dict[str, Any] = {}
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
        source_connection_id = job.source_connection_id
        # Owning org for a create-new import (request org context); None keeps
        # the first-active-membership fallback. Re-validated by the importer.
        organization_id = job.organization_id
        organization_group_id = getattr(job, "organization_group_id", None)
        # The manifest the caller declared when creating the job, if any.
        declared_manifest = (job.source_manifest or {}).get("declared")

        # Cloud import: the artifact lives in a customer bucket reached through
        # an org storage connection, not in our own object storage. Resolve the
        # connection BEFORE flipping to running so a deleted connection (FK SET
        # NULL races included) fails cleanly.
        source_connection = None
        if source_connection_id:
            import org_storage_connection_service

            source_connection = (
                db.query(OrgStorageConnection)
                .filter(OrgStorageConnection.id == source_connection_id)
                .first()
            )
            if source_connection is None:
                tasks._fail_import_job(db, job_id, "storage connection removed")
                return {
                    "status": "error",
                    "job_id": job_id,
                    "error": "storage connection removed",
                }

        job.status = JobStatus.RUNNING.value
        db.commit()
        tasks._publish_progress(
            channel,
            {"job_id": job_id, "status": "running", "progress": 0},
        )

        spooled = tempfile.SpooledTemporaryFile(max_size=_IMPORT_SPOOL_THRESHOLD)
        try:
            if source_connection is not None:
                # Size cap BEFORE downloading — a customer bucket is not bounded
                # by our presigned-upload cap, so enforce the equivalent here.
                size = org_storage_connection_service.head_object_size(
                    source_connection, object_key
                )
                if size > _CLOUD_IMPORT_MAX_BYTES:
                    raise ImportValidationError(
                        413,
                        f"Source file is too large ({size} bytes; "
                        f"limit {_CLOUD_IMPORT_MAX_BYTES})",
                    )
                org_storage_connection_service.download_to_fileobj(
                    source_connection, object_key, spooled
                )
            else:
                object_storage.download_to_fileobj(object_key, spooled)
            # Import provenance belongs to variant_experiments (core 2.69):
            # off for the requester, nothing is recorded and every import
            # imports, as before.
            from feature_flags import VARIANT_EXPERIMENTS
            from feature_flags.worker import flag_enabled_sync

            provenance_on = flag_enabled_sync(db, requested_by, VARIANT_EXPERIMENTS)
            if provenance_on:
                payload_sha256, byte_size = provenance.hash_fileobj(spooled)
            else:
                payload_sha256 = None
                byte_size = spooled.tell()
                spooled.seek(0)

            lowered_key = object_key.lower()
            tabular_fmt = next(
                (
                    fmt
                    for ext, fmt in _TABULAR_EXTENSIONS.items()
                    if lowered_key.endswith(ext)
                ),
                None,
            )
            if source_connection is not None and tabular_fmt is not None:
                detected_format = tabular_fmt
            elif project_id and mode == "merge":
                detected_format = "merge_preview" if dry_run else "merge"
            elif project_id:
                detected_format = "nested"
            else:
                detected_format = "comprehensive"

            manifest = None if not provenance_on else provenance.build_manifest(
                payload_sha256=payload_sha256,
                byte_size=byte_size,
                object_key=object_key,
                source_connection_id=source_connection_id,
                target=(
                    provenance.project_target(project_id)
                    if project_id
                    else provenance.new_project_target(
                        requested_by, organization_id, organization_group_id
                    )
                ),
                mode=detected_format,
                model_id_map=model_id_map,
                reimport=reimport,
                declared=declared_manifest,
            )
            import_key = provenance.idempotency_key(manifest) if provenance_on else None
            if provenance_on:
                # Committed on its own, so a failed import keeps its provenance too.
                recorded = db.query(ImportJob).filter(ImportJob.id == job_id).one()
                recorded.payload_sha256 = payload_sha256
                recorded.source_manifest = manifest
                recorded.idempotency_key = import_key
                db.commit()

            if import_key is not None:
                # Held until the import commits: an identical import running
                # at the same time waits here and then finds this one.
                provenance.lock_import_key(db, import_key)
                prior = (
                    None
                    if reimport
                    else provenance.find_completed_import(
                        db, import_key, job_id, manifest["target"]
                    )
                )
                if prior is not None:
                    done = db.query(ImportJob).filter(ImportJob.id == job_id).one()
                    done.status = JobStatus.COMPLETED.value
                    done.format = prior.format
                    done.byte_size = byte_size
                    done.progress = 100
                    done.duplicate_of_job_id = prior.id
                    done.result = provenance.no_op_result(prior, payload_sha256)
                    if not done.project_id:
                        done.project_id = prior.project_id
                    done.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
                    done.error_message = None
                    result_project_id = done.project_id
                    db.commit()
                    tasks._publish_progress(
                        f"import:progress:{result_project_id or job_id}",
                        {"job_id": job_id, "status": "completed", "progress": 100},
                    )
                    tasks.logger.info(
                        "import_project: job %s is a no-op, payload %s already "
                        "imported by job %s",
                        job_id,
                        payload_sha256,
                        prior.id,
                    )
                    return {
                        "status": "completed",
                        "job_id": job_id,
                        "project_id": result_project_id,
                        "byte_size": byte_size,
                        "no_op": True,
                        "duplicate_of_job_id": prior.id,
                    }

            # The tasks this import writes, linked to the job at its commit
            # so a later repeat can tell whether they all still exist.
            written_tasks = (
                provenance.track_written_tasks(db) if import_key is not None else None
            )

            def _mark_completed(result: Dict[str, Any]) -> None:
                # The drivers flush + expunge_all the session every batch,
                # which detaches the `job` loaded above, so load the row again
                # here. The driver commits it together with the imported rows.
                if written_tasks is not None:
                    db.flush()
                done = db.query(ImportJob).filter(ImportJob.id == job_id).one()
                done.status = JobStatus.COMPLETED.value
                done.format = detected_format
                done.byte_size = byte_size
                done.progress = 100
                done.result = result
                # A create-new import made the project; point the status row
                # and the download/poll URLs at it.
                if not done.project_id and (result or {}).get("project_id"):
                    done.project_id = result["project_id"]
                done.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
                done.error_message = None
                if written_tasks is not None:
                    provenance.record_written_tasks(
                        db, job_id, done.project_id, written_tasks
                    )
                completed["project_id"] = done.project_id
                completed["byte_size"] = byte_size

            # The drivers read the requester's variant_experiments answer
            # (import_stream._experiments_on) from this scope.
            from feature_flags.scope import flag_scope

            with flag_scope({VARIANT_EXPERIMENTS: provenance_on}):
                if detected_format in _TABULAR_EXTENSIONS.values():
                    run_tabular_import(
                        db, project_id, spooled, requested_by, tabular_fmt,
                        before_commit=_mark_completed,
                    )
                elif detected_format == "merge_preview":
                    _mark_completed(
                        run_merge_import(
                            db, project_id, spooled, requested_by,
                            model_id_map=model_id_map, dry_run=True,
                        )
                    )
                    db.commit()
                elif detected_format == "merge":
                    run_merge_import(
                        db, project_id, spooled, requested_by,
                        model_id_map=model_id_map, before_commit=_mark_completed,
                    )
                elif detected_format == "nested":
                    run_nested_import(
                        db, project_id, spooled, requested_by,
                        before_commit=_mark_completed,
                    )
                else:
                    import_kwargs = {"organization_id": organization_id}
                    if organization_group_id:
                        import_kwargs["organization_group_id"] = organization_group_id
                    if model_id_map:
                        import_kwargs["model_id_map"] = model_id_map
                    run_full_project_import(
                        db, spooled, requested_by,
                        before_commit=_mark_completed, **import_kwargs,
                    )
        finally:
            spooled.close()

        if "project_id" not in completed:
            # Every driver calls the hook right before its commit; a driver
            # that returned without it committed without marking the job.
            raise RuntimeError("import driver returned without marking the job completed")
        result_project_id = completed["project_id"]

        tasks._publish_progress(
            f"import:progress:{result_project_id or job_id}",
            {"job_id": job_id, "status": "completed", "progress": 100},
        )
        tasks.logger.info(
            "import_project: job %s completed (%s bytes, format=%s, project=%s)",
            job_id,
            byte_size,
            detected_format,
            result_project_id,
        )
        return {
            "status": "completed",
            "job_id": job_id,
            "project_id": result_project_id,
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
        if tasks._fail_import_job(
            db, job_id, public_job_error(exc, job_id, "import")
        ) is False:
            # The error came after the import committed: the job is completed
            # and so is what the caller is told.
            return {
                "status": "completed",
                "job_id": job_id,
                "project_id": completed.get("project_id"),
                "byte_size": completed.get("byte_size"),
            }
        return {"status": "error", "job_id": job_id, "error": str(exc)}
    finally:
        db.close()

def _fail_escaped_job_impl(action: str, job_id: str, exc: BaseException) -> Dict[str, Any]:
    """Mark an export or import job failed after its task body raised.

    ``export_project_impl`` and ``import_project_impl`` mark their job failed
    for anything raised inside their try, but not for what raises before it:
    their lazy imports (a worker still running code older than the shared
    models raised ``ImportError`` on ``import_stream`` in the rubric e2e, D01)
    or opening the session. Such a job stayed ``pending`` for good, and every
    client polling it waited forever. The Celery task wrappers call this for
    any exception the body lets escape. ``action`` is ``"export"`` or
    ``"import"``. A job already past ``running`` is left alone, so this can
    never turn a committed import into a failed one.
    """
    tasks.logger.error(
        "%s_project: job %s raised outside its handler: %s",
        action, job_id, exc, exc_info=True,
    )
    try:
        from models import ExportJob, ImportJob, JobStatus

        job_model = ExportJob if action == "export" else ImportJob
        db = tasks.SessionLocal()
        try:
            job = db.query(job_model).filter(job_model.id == job_id).first()
            if job is not None and job.status in (
                JobStatus.PENDING.value,
                JobStatus.RUNNING.value,
            ):
                job.status = JobStatus.FAILED.value
                job.error_message = public_job_error(exc, job_id, action)
                db.commit()
                channel_id = job.project_id or job_id
                tasks._publish_progress(
                    f"{action}:progress:{channel_id}",
                    {
                        "job_id": job_id,
                        "status": "failed",
                        "progress": job.progress or 0,
                    },
                )
        finally:
            db.close()
    except Exception as inner:
        tasks.logger.error(
            "%s_project: failed to mark job %s failed: %s", action, job_id, inner
        )
    return {"status": "error", "job_id": job_id, "error": str(exc)}


def _fail_import_job_impl(db, job_id: str, message: str) -> Optional[bool]:
    """Roll back and mark an ImportJob failed, publishing a final progress event.

    A job whose completed state already committed (with its imported rows, see
    ``import_project_impl``) is left completed and ``False`` is returned: the
    import has landed, and a failed status would only invite a retry that
    imports it twice.
    """
    from models import ImportJob, JobStatus

    try:
        db.rollback()
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if job is not None and job.status == JobStatus.COMPLETED.value:
            tasks.logger.error(
                "import_project: job %s already committed as completed; "
                "not marking it failed after: %s",
                job_id,
                message,
            )
            return False
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

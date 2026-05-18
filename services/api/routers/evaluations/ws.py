"""WebSocket endpoint for live evaluation progress.

Primary path: subscribe to the Redis channel `evaluation:progress:{project_id}`
that workers publish on after each per-cell commit (see workers/tasks.py's
`_publish_progress`). Each Redis message is forwarded to the connected
browser as a `tick`; the frontend then re-fetches the by-task-model view.

Fallback path: if Redis is unavailable, fall back to a per-iteration DB
snapshot loop (5-second cadence, less aggressive than the prior 2 s
polling — fallback is the unhappy path now). The fallback uses the same
`_snapshot_project_progress` helper to count rows + active runs.

Auto-closes when no in-flight runs remain for the project for 30 s,
freeing the connection for the client's reconnect-with-fallback path.

Session lifecycle (important — see 2026-05-18 incident postmortem):
the polling loop opens and closes a fresh DB session per iteration
instead of holding one across ``await``. The Depends(get_db) session is
also closed right after the up-front access check so it doesn't linger
for the WS lifetime.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth_module import WebSocketAuthError, verify_token_for_websocket
from auth_module.user_service import get_user_by_id
from database import get_db
from models import EvaluationRun as DBEvaluationRun
from models import TaskEvaluation
from project_models import Task
from redis_cache import get_redis_client
from routers.projects.helpers import check_project_accessible

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/api/ws", tags=["websocket"])

# Idle timeout: when no in-flight runs are seen for this many seconds the
# WS auto-closes. Same UX as the prior polling behavior (15 ticks × 2 s).
_IDLE_CLOSE_SECONDS = 30
# Fallback polling cadence when Redis is unavailable. Looser than the
# original 2 s because the primary path covers the live-update case; the
# fallback is just a backstop.
_FALLBACK_POLL_SECONDS = 5


def _snapshot_project_progress(project_id: str) -> tuple[int, int]:
    """Open a short-lived DB session, return (row_count, active_runs).

    Used by both the idle-close check (primary path) and the polling
    fallback. The session never spans an `await` — opens, reads, closes.
    """
    db = next(get_db())
    try:
        row_count = (
            db.query(func.count(TaskEvaluation.id))
            .join(Task, TaskEvaluation.task_id == Task.id)
            .filter(Task.project_id == project_id)
            .scalar()
        ) or 0
        active_runs = (
            db.query(func.count(DBEvaluationRun.id))
            .filter(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.status.in_(("pending", "running")),
            )
            .scalar()
        ) or 0
        return int(row_count), int(active_runs)
    finally:
        db.close()


async def _run_pubsub_primary(
    websocket: WebSocket, project_id: str, sync_redis_client
) -> bool:
    """Subscribe to evaluation:progress:{project_id} and forward each
    message to the client. Returns True on clean completion (idle close),
    False if the caller should fall back to polling.

    Idle-close logic: after `_IDLE_CLOSE_SECONDS` of no messages AND zero
    active runs (verified by a one-shot DB snapshot, not a poll loop), we
    send `idle` and exit. The DB snapshot is cheap (two counts) and only
    runs on the idle path, not in the hot loop.
    """
    import redis.asyncio as redis_async

    try:
        kwargs = sync_redis_client.connection_pool.connection_kwargs
        async_redis = redis_async.Redis(
            host=kwargs.get("host", "localhost"),
            port=kwargs.get("port", 6379),
            db=kwargs.get("db", 0),
            password=kwargs.get("password"),
            decode_responses=True,
        )
        pubsub = async_redis.pubsub()
        channel = f"evaluation:progress:{project_id}"
        await pubsub.subscribe(channel)
    except Exception as e:
        logger.warning(
            f"evaluation-progress: pubsub subscribe failed ({e}); falling back to polling"
        )
        return False

    try:
        while True:
            try:
                # `get_message` with a timeout: avoids an unbounded `listen()`
                # so we get a regular tick to check the idle-close condition.
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=_IDLE_CLOSE_SECONDS,
                )
            except Exception as e:
                logger.warning(
                    f"evaluation-progress: pubsub get_message failed for {project_id}: {e}"
                )
                return False

            if msg is None:
                # Timeout fired with no message. Check the idle-close gate.
                _, active_runs = _snapshot_project_progress(project_id)
                if active_runs == 0:
                    await websocket.send_json({
                        "type": "idle",
                        "message": (
                            f"No in-flight runs for {_IDLE_CLOSE_SECONDS}s; closing."
                        ),
                    })
                    return True
                # In-flight runs but no recent commits — keep waiting.
                continue

            try:
                payload = json.loads(msg["data"])
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

            # Forward as `tick` — the frontend's existing handler treats
            # `tick` and `idle` as the trigger to re-fetch. Carries the
            # publisher's payload for any consumers that want richer
            # information (e.g. samples_added for analytics).
            await websocket.send_json({"type": "tick", **payload})
    except WebSocketDisconnect:
        return True
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            pass


async def _run_polling_fallback(websocket: WebSocket, project_id: str) -> None:
    """DB-polling fallback used when Redis isn't speaking pub/sub. Same
    semantics as the legacy loop but at a slower cadence."""
    last_row_count = -1
    last_active_runs = -1
    idle_iterations = 0
    max_idle = _IDLE_CLOSE_SECONDS // _FALLBACK_POLL_SECONDS

    while True:
        row_count, active_runs = _snapshot_project_progress(project_id)
        if row_count != last_row_count or active_runs != last_active_runs:
            await websocket.send_json({
                "type": "tick",
                "row_count": row_count,
                "active_runs": active_runs,
            })
            last_row_count = row_count
            last_active_runs = active_runs

        if active_runs == 0:
            idle_iterations += 1
            if idle_iterations >= max_idle:
                await websocket.send_json({
                    "type": "idle",
                    "message": (
                        f"No in-flight runs for {_IDLE_CLOSE_SECONDS}s; closing."
                    ),
                })
                return
        else:
            idle_iterations = 0

        await asyncio.sleep(_FALLBACK_POLL_SECONDS)


@ws_router.websocket("/projects/{project_id}/evaluation-progress")
async def evaluation_progress_websocket(
    websocket: WebSocket,
    project_id: str,
    db: Session = Depends(get_db),
):
    """Push a `tick` event whenever a cell commits (Redis pub/sub primary)
    or the project's in-flight state changes (DB-poll fallback).

    Message shapes::

        {"type": "tick", "evaluation_id": str, "task_id": str, ...}
        {"type": "tick", "row_count": int, "active_runs": int}      # fallback
        {"type": "idle", "message": "..."}                          # close
        {"type": "connection", "status": "connected"}               # one-shot
    """
    # Authenticate and authorize BEFORE accepting the upgrade.
    try:
        payload = verify_token_for_websocket(websocket)
    except WebSocketAuthError as e:
        logger.info(f"WS auth rejected for project {project_id}: {e}")
        await websocket.close(code=4401)
        return

    user_id = payload.get("user_id")
    try:
        user = get_user_by_id(db, user_id) if user_id else None
        if not user or not check_project_accessible(db, user, project_id):
            await websocket.close(code=4403)
            return
    finally:
        db.close()

    await websocket.accept()
    await websocket.send_json({
        "type": "connection",
        "status": "connected",
        "project_id": project_id,
        "message": "Subscribed to evaluation progress",
    })

    try:
        sync_redis_client = get_redis_client()
        used_pubsub = False
        if sync_redis_client is not None and hasattr(sync_redis_client, "pubsub"):
            used_pubsub = await _run_pubsub_primary(
                websocket, project_id, sync_redis_client
            )
        if not used_pubsub:
            await _run_polling_fallback(websocket, project_id)
    except WebSocketDisconnect:
        return
    except Exception as e:
        logger.error(f"evaluation-progress ws error for project {project_id}: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

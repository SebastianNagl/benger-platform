"""WebSocket endpoint for live evaluation progress.

Mirrors the pattern at ``services/api/routers/generation.py:671`` but
specialised for evaluation cell-by-cell streaming. The worker commits
each TaskEvaluation row to Postgres immediately after the evaluator
returns; this endpoint polls the DB every 2 seconds and pushes a
"tick" event to the connected client whenever the per-project row
count or active-run summary changes. The client is expected to
re-fetch ``/results/by-task-model`` on each tick.

Why polling-internally instead of Redis pub/sub: the worker doesn't
currently publish per-row events (and adding a publish hook to the
hot path risks breaking in-flight runs). DB polling at 2s captures
the same "live update" UX with one extra query per second per
connected client — cheap given typical project usage.

Auto-closes when no in-flight runs remain for the project for 30s,
freeing the connection for the client's reconnect-with-fallback path.

Session lifecycle (important — see 2026-05-18 incident postmortem):
the polling loop opens and closes a fresh DB session per iteration
instead of holding one across ``await asyncio.sleep(2)``. Holding a
``Depends(get_db)`` session for the WS lifetime was leaving the
underlying connection IDLE IN TRANSACTION between polls and draining
the per-process pool with a handful of open browser tabs.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func

from auth_module import WebSocketAuthError, verify_token_for_websocket
from auth_module.user_service import get_user_by_id
from database import get_db
from models import EvaluationRun as DBEvaluationRun
from models import TaskEvaluation
from project_models import Task
from routers.projects.helpers import check_project_accessible

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/api/ws", tags=["websocket"])


def _snapshot_project_progress(project_id: str) -> tuple[int, int]:
    """Open a short-lived DB session, return (row_count, active_runs).

    The session is opened and closed inside this call so the WS handler
    never holds a connection across ``await``.
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


@ws_router.websocket("/projects/{project_id}/evaluation-progress")
async def evaluation_progress_websocket(
    websocket: WebSocket,
    project_id: str,
):
    """Push a "tick" event whenever the project's in-flight evaluation
    state changes (row count delta or run-status flip). Frontend
    re-fetches the cell scores on each tick.

    Message shape::

        {"type": "tick", "row_count": int, "active_runs": int}
        {"type": "idle", "message": "..."}                # no in-flight runs
        {"type": "connection", "status": "connected"}     # one-shot on accept
    """
    # Authenticate and authorize BEFORE accepting the upgrade. An
    # unauthenticated client must never consume server resources past the
    # handshake (frontend reconnect storms would otherwise drain the pool).
    try:
        payload = verify_token_for_websocket(websocket)
    except WebSocketAuthError as e:
        logger.info(f"WS auth rejected for project {project_id}: {e}")
        await websocket.close(code=4401)
        return

    user_id = payload.get("user_id")
    db = next(get_db())
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

    last_row_count = -1
    last_active_runs = -1
    idle_ticks = 0  # consecutive ticks with 0 in-flight runs

    try:
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
                idle_ticks += 1
                # 15 idle ticks × 2s = 30s of no in-flight runs → close.
                if idle_ticks >= 15:
                    await websocket.send_json({
                        "type": "idle",
                        "message": "No in-flight runs for 30s; closing.",
                    })
                    break
            else:
                idle_ticks = 0

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        # Client closed the connection; nothing to do.
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

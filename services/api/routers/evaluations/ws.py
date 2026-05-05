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
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import EvaluationRun as DBEvaluationRun
from models import TaskEvaluation
from project_models import Task

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/api/ws", tags=["websocket"])


@ws_router.websocket("/projects/{project_id}/evaluation-progress")
async def evaluation_progress_websocket(
    websocket: WebSocket,
    project_id: str,
    db: Session = Depends(get_db),
):
    """Push a "tick" event whenever the project's in-flight evaluation
    state changes (row count delta or run-status flip). Frontend
    re-fetches the cell scores on each tick.

    Message shape::

        {"type": "tick", "row_count": int, "active_runs": int}
        {"type": "idle", "message": "..."}                # no in-flight runs
        {"type": "connection", "status": "connected"}     # one-shot on accept
    """
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
            # Snapshot: total row count + in-flight run count for this project.
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

            if row_count != last_row_count or active_runs != last_active_runs:
                await websocket.send_json({
                    "type": "tick",
                    "row_count": int(row_count),
                    "active_runs": int(active_runs),
                })
                last_row_count = int(row_count)
                last_active_runs = int(active_runs)

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

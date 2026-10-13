"""Batched writer for ``api_key_usage_events``.

The usage middleware calls :func:`enqueue` once per ``/api/v1`` request
made with an access key. A single consumer task (started and stopped in
``main.py``'s lifespan) drains the queue and writes batches of up to
``BATCH_SIZE`` rows, or whatever arrived within ``FLUSH_INTERVAL`` seconds,
through ``AsyncSessionLocal``; each batch also refreshes ``last_used_at`` of
the keys involved (throttled in the database to once a minute per key).

Usage logging is best effort: :func:`enqueue` never raises, a full queue
drops the event (with a warning), and a failed batch is logged and
dropped, never retried into the request path.

Tests replace the queue with a synchronous sink (:func:`set_sink`).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
FLUSH_INTERVAL = 1.0
MAX_QUEUE = 10000

_queue: Optional[asyncio.Queue] = None
_task: Optional[asyncio.Task] = None
_sink: Optional[Callable[[Dict[str, Any]], Any]] = None
_dropped = 0


def set_sink(sink: Optional[Callable[[Dict[str, Any]], Any]]) -> None:
    """Route events to ``sink`` synchronously instead of the queue (tests)."""
    global _sink
    _sink = sink


def enqueue(event: Dict[str, Any]) -> bool:
    """Hand one usage event to the writer. Never raises."""
    global _dropped
    try:
        if _sink is not None:
            _sink(event)
            return True
        if _queue is None:
            return False
        _queue.put_nowait(event)
        return True
    except asyncio.QueueFull:
        _dropped += 1
        if _dropped % 1000 == 1:
            logger.warning("API usage queue full; %d event(s) dropped so far", _dropped)
        return False
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("API usage event not recorded: %s", e)
        return False


async def write_batch(events: Sequence[Dict[str, Any]]) -> int:
    """Insert one batch in its own session. Never raises."""
    if not events:
        return 0
    try:
        import database
        from services.api_key_service import record_usage

        if database.AsyncSessionLocal is None:
            return 0
        async with database.AsyncSessionLocal() as session:
            try:
                written = await record_usage(session, events)
                await session.commit()
                return written
            except Exception:
                await session.rollback()
                raise
    except Exception as e:
        logger.warning("API usage batch of %d event(s) dropped: %s", len(events), e)
        return 0


async def _collect(queue: asyncio.Queue) -> List[Dict[str, Any]]:
    """Wait for one event, then gather more until BATCH_SIZE or the flush
    interval elapses."""
    batch = [await queue.get()]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + FLUSH_INTERVAL
    while len(batch) < BATCH_SIZE:
        timeout = deadline - loop.time()
        if timeout <= 0:
            break
        try:
            batch.append(await asyncio.wait_for(queue.get(), timeout))
        except asyncio.TimeoutError:
            break
    return batch


async def _run(queue: asyncio.Queue) -> None:
    while True:
        try:
            batch = await _collect(queue)
        except asyncio.CancelledError:
            raise
        await write_batch(batch)


def _drain(queue: asyncio.Queue) -> List[Dict[str, Any]]:
    out = []
    while True:
        try:
            out.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            return out


async def start() -> None:
    global _queue, _task
    if _task is not None and not _task.done():
        return
    _queue = asyncio.Queue(maxsize=MAX_QUEUE)
    _task = asyncio.create_task(_run(_queue), name="api-usage-writer")


async def stop() -> None:
    """Stop the consumer and flush what is still queued."""
    global _queue, _task
    task, queue = _task, _queue
    _task, _queue = None, None
    if task is not None:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    if queue is not None:
        pending = _drain(queue)
        for i in range(0, len(pending), BATCH_SIZE):
            await write_batch(pending[i : i + BATCH_SIZE])

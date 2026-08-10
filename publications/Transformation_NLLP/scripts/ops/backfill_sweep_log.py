#!/usr/bin/env python3
"""Backfill sweep-log rows for dispatch series the driver did not poll.

One-shot repair (2026-08-03): a driver bug dispatched the 15 gpt-5.4-mini
series without logging them (the old --dry-run still hit the bulk
endpoint). Failures never create DB rows, so without this backfill the
per-model failure table would silently miss those series.

Mechanism: celery task ids are scraped from the worker containers'
"Task tasks.generate_bewertungsbogen[<id>] received" lines, each id is
polled through the status endpoint (celery result backend retains results
long enough), and rows are appended to ``rubric_sweep_log.jsonl`` in the
driver's exact schema — deduped on celery_task_id against existing rows.

Usage: uv run python scripts/ops/backfill_sweep_log.py --since 60m \
           [--generator gpt-5.4-mini]
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
LOG = HERE / "data" / "interim" / "rubric_sweep_log.jsonl"

BASE_URL = "http://benger.localhost"
PROJECT_ID = "e529779b-300f-48c0-89cb-90f3f4b72a51"
WORKERS = ["benger-worker-1", "benger-worker-fast-1"]
RECEIVED = re.compile(r"Task tasks\.generate_bewertungsbogen\[([0-9a-f-]{36})\] received")


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _request(opener, method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="60m", help="docker logs --since window")
    parser.add_argument("--generator", help="only backfill rows for this generator id")
    args = parser.parse_args()

    task_ids: list[str] = []
    for worker in WORKERS:
        out = subprocess.run(
            ["docker", "logs", worker, "--since", args.since],
            capture_output=True,
            text=True,
        )
        task_ids.extend(RECEIVED.findall(out.stdout + out.stderr))
    task_ids = list(dict.fromkeys(task_ids))
    print(f"found {len(task_ids)} generate_bewertungsbogen task id(s) in worker logs")

    # Dedupe against the live log AND every archived log variant — celery
    # results outlive harness resets, so a wide --since window must never
    # re-import series from a retired contract era.
    already = set()
    for log_file in LOG.parent.glob("rubric_sweep_log*.jsonl"):
        for line in log_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                already.add(json.loads(line).get("celery_task_id"))

    opener = _opener()
    _request(
        opener,
        "POST",
        "/api/auth/login",
        {"username": "admin@example.com", "password": "admin"},
    )

    added = skipped = pending = 0
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        for celery_id in task_ids:
            if celery_id in already:
                skipped += 1
                continue
            status = _request(
                opener,
                "GET",
                f"/api/projects/{PROJECT_ID}/bewertungsbogen/status/{celery_id}",
            )
            state = status.get("status")
            if state == "running":
                pending += 1
                continue
            result = status.get("result") or {}
            generator = result.get("generator_model_id")
            if args.generator and generator != args.generator:
                skipped += 1
                continue
            row = {
                "generator_model_id": generator,
                "task_id": result.get("task_id"),
                "celery_task_id": celery_id,
                "outcome": "completed" if state == "completed" else "failed",
                "attempts": result.get("attempts"),
                "ts": datetime.now(timezone.utc).isoformat(),
                "backfilled": True,
            }
            if state == "completed":
                row["rubric_id"] = result.get("rubric_id")
                row["steps"] = result.get("steps")
            else:
                row["error"] = status.get("error") or result.get("error")
                row["error_stage"] = result.get("error_stage")
                row["error_categories"] = result.get("error_categories")
                row["attempt_errors"] = result.get("attempt_errors")
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            added += 1
    print(f"backfilled {added} row(s); {skipped} already logged/filtered; {pending} still running")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

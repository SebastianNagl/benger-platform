#!/usr/bin/env python3
"""12-generator × 15-task Bewertungsbogen sweep against the LOCAL dev stack.

Reads the generator roster from the dataset paper's ``systems.json`` (never
hardcode — DESIGN.md D3), then per generator calls the extended bulk
endpoint (``POST .../bewertungsbogen/generate`` without ``task_id``), which
targets every task not yet covered by a non-archived rubric from that
generator — so re-running this script resumes an interrupted sweep instead
of duplicating work.

Every dispatched job is polled to a terminal state and appended to
``data/interim/rubric_sweep_log.jsonl`` — one JSON line per
(generator, task, dispatch series). FAILED series are first-class data:
per Studiendesign the sweep measures how often each model fails to produce
a contract-valid rubric (strict validation, no repair; 3 attempts per
series inside the worker), and the log carries the per-attempt stage +
category telemetry the analysis aggregates.

Usage (from the publication root):
    uv run python scripts/ops/sweep_rubrics.py [--generators id1,id2] [--dry-run]

Stdlib-only on purpose (urllib + cookiejar) — no new project deps.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
SYSTEMS = HERE.parent / "Benchmark_EMNLP" / "data" / "processed" / "systems.json"
LOG = HERE / "data" / "interim" / "rubric_sweep_log.jsonl"

BASE_URL = os.environ.get("BENGER_BASE_URL", "http://benger.localhost")
PROJECT_ID = os.environ.get(
    "BENGER_PROJECT_ID", "e529779b-300f-48c0-89cb-90f3f4b72a51"
)
PROMPT_KEY = "bewertungsbogen"
LOGIN_USER = os.environ.get("BENGER_USER", "admin@example.com")
LOGIN_PASSWORD = os.environ.get("BENGER_PASSWORD", "admin")

POLL_INTERVAL_S = 10
# Thinking-class generators (Qwen3 Thinking, DeepSeek) can take several
# minutes PER ATTEMPT, and provider SDKs retry timeouts internally (the
# Anthropic client ran ~14 min on one attempt in the smoke) — 3 attempts
# per series need real headroom. A series exceeding this is logged as
# timeout.
JOB_TIMEOUT_S = 45 * 60


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _login(opener):
    data = json.dumps({"username": LOGIN_USER, "password": LOGIN_PASSWORD}).encode()
    req = urllib.request.Request(
        BASE_URL + "/api/auth/login",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _request(opener, method: str, path: str, payload=None, retries: int = 5):
    """HTTP with bounded retries — a transient timeout between generators
    must not kill a multi-hour sweep (it did once), and the session cookie
    expires mid-run (it did too): 401/403 triggers a re-login before the
    retry."""
    data = json.dumps(payload).encode() if payload is not None else None
    last_exc: Exception = RuntimeError("no attempt")
    for attempt in range(retries):
        req = urllib.request.Request(
            BASE_URL + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with opener.open(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in (401, 403):
                try:
                    _login(opener)
                except Exception:
                    pass
            time.sleep(5 * (attempt + 1))
        except Exception as exc:  # timeouts, 5xx, transient proxy errors
            last_exc = exc
            time.sleep(5 * (attempt + 1))
    raise last_exc


def _log_row(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    row["ts"] = datetime.now(timezone.utc).isoformat()
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_generator(opener, generator: str) -> dict:
    dispatch = _request(
        opener,
        "POST",
        f"/api/projects/{PROJECT_ID}/bewertungsbogen/generate",
        {"generator_model_id": generator, "prompt_key": PROMPT_KEY},
    )
    jobs = dispatch.get("jobs") or []
    print(f"[{generator}] dispatched {len(jobs)} uncovered task(s)", flush=True)
    if not jobs:
        return {"dispatched": 0, "completed": 0, "failed": 0, "timeout": 0}

    pending = {j["celery_task_id"]: j["task_id"] for j in jobs if j.get("celery_task_id")}
    started = time.monotonic()
    tally = {"dispatched": len(jobs), "completed": 0, "failed": 0, "timeout": 0}

    while pending:
        time.sleep(POLL_INTERVAL_S)
        for celery_id in list(pending):
            task_id = pending[celery_id]
            try:
                status = _request(
                    opener,
                    "GET",
                    f"/api/projects/{PROJECT_ID}/bewertungsbogen/status/{celery_id}",
                )
            except Exception as exc:  # transient poll failure: retry next tick
                print(f"[{generator}] poll error ({task_id}): {exc}", flush=True)
                continue
            state = status.get("status")
            if state == "running":
                if time.monotonic() - started > JOB_TIMEOUT_S:
                    tally["timeout"] += 1
                    _log_row(
                        {
                            "generator_model_id": generator,
                            "task_id": task_id,
                            "celery_task_id": celery_id,
                            "outcome": "timeout",
                            "timeout_s": JOB_TIMEOUT_S,
                        }
                    )
                    print(f"[{generator}] TIMEOUT {task_id}", flush=True)
                    del pending[celery_id]
                continue

            result = status.get("result") or {}
            row = {
                "generator_model_id": generator,
                "task_id": task_id,
                "celery_task_id": celery_id,
                "outcome": "completed" if state == "completed" else "failed",
                "attempts": result.get("attempts"),
            }
            if state == "completed":
                tally["completed"] += 1
                row["rubric_id"] = result.get("rubric_id")
                row["steps"] = result.get("steps")
            else:
                tally["failed"] += 1
                row["error"] = status.get("error") or result.get("error")
                row["error_stage"] = result.get("error_stage")
                row["error_categories"] = result.get("error_categories")
                row["attempt_errors"] = result.get("attempt_errors")
                print(
                    f"[{generator}] FAILED {task_id}: "
                    f"{row.get('error_stage')}: {str(row.get('error'))[:160]}",
                    flush=True,
                )
            _log_row(row)
            del pending[celery_id]
        done = tally["completed"] + tally["failed"] + tally["timeout"]
        if done and done % 5 == 0:
            print(
                f"[{generator}] {done}/{tally['dispatched']} done "
                f"({tally['failed']} failed)",
                flush=True,
            )

    print(
        f"[{generator}] finished: {tally['completed']} ok, "
        f"{tally['failed']} failed, {tally['timeout']} timeout",
        flush=True,
    )
    return tally


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--generators",
        help="Comma-separated model ids (default: all systems.json model_ids)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generator roster and exit — dispatches NOTHING "
        "(the bulk endpoint has no preview mode, so a dry run must never "
        "reach it).",
    )
    args = parser.parse_args()

    if args.generators:
        generators = [g.strip() for g in args.generators.split(",") if g.strip()]
    else:
        systems = json.loads(SYSTEMS.read_text(encoding="utf-8"))
        generators = [s["model_id"] for s in systems]
    print(f"sweep over {len(generators)} generator(s): {', '.join(generators)}")
    if args.dry_run:
        print("dry run: nothing dispatched")
        return 0

    opener = _opener()
    login = _request(
        opener,
        "POST",
        "/api/auth/login",
        {"username": LOGIN_USER, "password": LOGIN_PASSWORD},
    )
    if not (login.get("user") or login.get("access_token") or login.get("success", True)):
        print("login failed", file=sys.stderr)
        return 1

    totals = {"dispatched": 0, "completed": 0, "failed": 0, "timeout": 0}
    for generator in generators:
        # Sequential per generator: keeps provider rate limits happy and the
        # failure log ordered; tasks within a generator run in parallel on
        # the worker pool.
        tally = run_generator(opener, generator)
        for key in totals:
            totals[key] += tally.get(key, 0)

    print(
        f"SWEEP DONE: {totals['completed']} ok, {totals['failed']} failed, "
        f"{totals['timeout']} timeout of {totals['dispatched']} dispatched",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

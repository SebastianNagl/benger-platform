#!/usr/bin/env python3
"""Few-shot Bewertungsbogen sweep — 5 generators × 15 clone tasks (WP A3).

Unlike the zero-shot sweep, this cannot use the bulk endpoint: bulk coverage
keys on (project, generator, non-archived) and ignores prompt_key, so every
(generator, task) already looks covered. Instead this dispatches per
(generator, task) in SINGLE mode ("always generates a fresh candidate")
with prompt_key="bewertungsbogen_fewshot" — the few-shot structure whose
distinct prompt_version separates this cohort in SQL.

Resume-safe: skips any (generator, task) already present in the log with a
terminal outcome. Same row schema as rubric_sweep_log.jsonl so
backfill_sweep_log.py's dedupe glob picks it up. Logs to
data/interim/rubric_sweep_log.fewshot.jsonl.

Env: BENGER_BASE_URL (default the direct host http://localhost:8001 — the
Traefik host 504'd on config PUTs), BENGER_PROJECT_ID (the clone),
BENGER_ADMIN_EMAIL/PASSWORD.

Usage: uv run python scripts/ops/sweep_fewshot.py [--generators a,b] [--tasks id1,id2] [--dry-run]
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
INTERIM = HERE / "data" / "interim"
LOG = INTERIM / "rubric_sweep_log.fewshot.jsonl"

BASE_URL = os.environ.get("BENGER_BASE_URL", "http://localhost:8001")
PROJECT_ID = os.environ.get("BENGER_PROJECT_ID", "81e474b8-d226-4bf8-bc2e-fb744d25cba5")
PROMPT_KEY = "bewertungsbogen_fewshot"
LOGIN_USER = os.environ.get("BENGER_ADMIN_EMAIL", "admin@example.com")
LOGIN_PASSWORD = os.environ.get("BENGER_ADMIN_PASSWORD", "admin")

DEFAULT_GENERATORS = [
    "gemini-3.1-flash-lite-preview",
    "Qwen/Qwen3-235B-A22B-Thinking-2507",
    "gpt-5.4",
    "gpt-5.4-mini",
    "claude-sonnet-4-6",
]
POLL_INTERVAL_S = 10
JOB_TIMEOUT_S = 45 * 60


def _opener():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _request(opener, method, path, payload=None, retries=5):
    data = json.dumps(payload).encode() if payload is not None else None
    last = RuntimeError("no attempt")
    for attempt in range(retries):
        req = urllib.request.Request(BASE_URL + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with opener.open(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (401, 403):
                try:
                    _login(opener)
                except Exception:
                    pass
            time.sleep(5 * (attempt + 1))
        except Exception as exc:
            last = exc
            time.sleep(5 * (attempt + 1))
    raise last


def _login(opener):
    return _request(opener, "POST", "/api/auth/login",
                    {"username": LOGIN_USER, "password": LOGIN_PASSWORD})


def _log_row(row):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    row["ts"] = datetime.now(timezone.utc).isoformat()
    row["prompt_key"] = PROMPT_KEY
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _done_pairs():
    done = set()
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("outcome") in ("completed", "failed", "timeout"):
                done.add((r["generator_model_id"], r["task_id"]))
    return done


def _dispatch_and_poll(opener, generator, task_id):
    disp = _request(opener, "POST", f"/api/projects/{PROJECT_ID}/bewertungsbogen/generate",
                    {"task_id": task_id, "generator_model_id": generator, "prompt_key": PROMPT_KEY})
    jobs = disp.get("jobs") or []
    if not jobs or not jobs[0].get("celery_task_id"):
        _log_row({"generator_model_id": generator, "task_id": task_id,
                  "celery_task_id": None, "outcome": "failed", "error": "no job dispatched"})
        return "failed"
    celery_id = jobs[0]["celery_task_id"]
    started = time.monotonic()
    while True:
        time.sleep(POLL_INTERVAL_S)
        try:
            status = _request(opener, "GET",
                              f"/api/projects/{PROJECT_ID}/bewertungsbogen/status/{celery_id}")
        except Exception as exc:
            print(f"  poll error {task_id[:8]}: {exc}", flush=True)
            continue
        state = status.get("status")
        if state == "running":
            if time.monotonic() - started > JOB_TIMEOUT_S:
                _log_row({"generator_model_id": generator, "task_id": task_id,
                          "celery_task_id": celery_id, "outcome": "timeout",
                          "timeout_s": JOB_TIMEOUT_S})
                return "timeout"
            continue
        result = status.get("result") or {}
        row = {"generator_model_id": generator, "task_id": task_id,
               "celery_task_id": celery_id,
               "outcome": "completed" if state == "completed" else "failed",
               "attempts": result.get("attempts")}
        if state == "completed":
            row["rubric_id"] = result.get("rubric_id")
            row["steps"] = result.get("steps")
        else:
            row["error"] = status.get("error") or result.get("error")
            row["error_stage"] = result.get("error_stage")
            row["error_categories"] = result.get("error_categories")
            row["attempt_errors"] = result.get("attempt_errors")
        _log_row(row)
        return row["outcome"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generators")
    parser.add_argument("--tasks", help="Comma-separated clone task ids (default: all 15 exemplar tasks)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    generators = ([g.strip() for g in args.generators.split(",") if g.strip()]
                  if args.generators else DEFAULT_GENERATORS)
    if args.tasks:
        tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    else:
        exemplars = json.loads((INTERIM / "fewshot" / "exemplars.json").read_text())
        tasks = [a["target_clone_task"] for a in exemplars.values()]
    done = _done_pairs()
    todo = [(g, t) for g in generators for t in tasks if (g, t) not in done]
    print(f"few-shot sweep: {len(generators)} generators × {len(tasks)} tasks "
          f"= {len(generators) * len(tasks)} series; {len(done)} already done, "
          f"{len(todo)} to run")
    if args.dry_run:
        for g in generators:
            print(f"  {g}: {sum(1 for gg, tt in todo if gg == g)} tasks pending")
        return 0

    opener = _opener()
    _login(opener)
    tally = {"completed": 0, "failed": 0, "timeout": 0}
    for i, (g, t) in enumerate(todo, 1):
        outcome = _dispatch_and_poll(opener, g, t)
        tally[outcome] += 1
        print(f"[{i}/{len(todo)}] {g.split('/')[-1]} × {t[:8]} -> {outcome}", flush=True)
    print(f"FEW-SHOT SWEEP DONE: {tally}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

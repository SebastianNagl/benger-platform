"""Build a Benchathon-shaped export JSON with mock korrektur_falloesung entries.

Produces `publications/Dataset_ARR/data/raw/mock/benchathon_mock.json` for manuscript
work while the human correctors finish grading. As real korrektur_falloesung
rows land in prod, they replace mocks on the next re-run; mocks only fill the
4-grader-per-pick slots that are still unfinished.

Workflow:
  1. SSH into the K3s server and `kubectl exec` a small fetcher into the api
     pod (read-only — pulls project + tasks + annotations + generations +
     evaluation_runs + task_evaluations + task_assignments via DATABASE_URI).
  2. Locally, identify the 45 pick × 4 grader slots from task_assignments and
     for each slot lacking a real korrektur_falloesung entry, mint a mock
     grounded in the existing llm_judge_falloesung score for the same target.
  3. Assemble the output in the production export shape (mirrors
     `GET /api/projects/{id}/export` in import_export.py:715) and write it to
     the data/raw/mock/ folder.

Re-running with new real grades is idempotent: the mock generator is deterministic
per (target_id, pass) and real rows always supersede mocks.

Usage (from anywhere on host):
    python publications/Dataset_ARR/scripts/build_benchathon_mock.py
    python publications/Dataset_ARR/scripts/build_benchathon_mock.py --out /tmp/test.json
    python publications/Dataset_ARR/scripts/build_benchathon_mock.py --from-snapshot fetched.json --no-pull
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import textwrap
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Resolve repo paths and import the canonical Falllösung constants from
# benger-extended so the dimensions + grade table are single-sourced.
SCRIPT_PATH = Path(__file__).resolve()
PLATFORM_ROOT = SCRIPT_PATH.parents[3]                          # benger-platform/
WORKSPACE_ROOT = PLATFORM_ROOT.parent                           # benger-workspace parent
EXTENDED_ROOT = WORKSPACE_ROOT / "benger-extended"
sys.path.insert(0, str(EXTENDED_ROOT))
from benger_extended.workers.falloesung_constants import (      # noqa: E402
    FALLOESUNG_DIMENSIONS,
    raw_score_to_grade_points,
)

PROJECT_ID = "e529779b-300f-48c0-89cb-90f3f4b72a51"             # Benchathon
SSH_HOST = "root@178.105.26.90"
K8S_NS = "benger"
API_DEPLOYMENT = "deployment/benger-api"

MOCK_EVAL_RUN_ID = "00000000-0000-0000-0000-000000feb001"       # synthetic
MOCK_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-00000000feb1")
MOCK_CREATED_AT = "2026-05-13T12:00:00+00:00"

DEFAULT_OUT = (
    PLATFORM_ROOT / "publications" / "Dataset_ARR" / "data" / "raw" / "mock" / "benchathon_mock.json"
)

EXPECTED_PASSES = ("A", "B", "C", "D")                          # 4 graders/pick


# =============================================================================
# Fetcher — runs inside the api pod via kubectl exec, table by table
# =============================================================================
#
# Pulling all ~130 MB of project data through a single kubectl exec stdout pipe
# truncates around 116 MB. Splitting by table keeps each transfer well under
# any buffer limit and makes failures easy to retry.
#

_FETCHER_TEMPLATE = r"""
import os, json, sys
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import create_engine, text

PID = "e529779b-300f-48c0-89cb-90f3f4b72a51"

QUERIES = {
    "project":            "SELECT id, title, description, created_at, label_config FROM projects WHERE id=:p",
    "tasks":              "SELECT id, inner_id, data, meta, is_labeled, created_at, updated_at FROM tasks WHERE project_id=:p ORDER BY inner_id NULLS LAST, id",
    "annotations":        "SELECT id, task_id, result, completed_by, created_at, updated_at, was_cancelled, ground_truth, lead_time FROM annotations WHERE project_id=:p",
    "generations":        "SELECT g.id, g.task_id, g.model_id, g.response_content, g.case_data, g.created_at, g.response_metadata FROM generations g JOIN tasks t ON g.task_id=t.id WHERE t.project_id=:p",
    "evaluation_runs":    "SELECT id, model_id, evaluation_type_ids, metrics, status, samples_evaluated, created_at, completed_at, eval_metadata, error_message, created_by, has_sample_results FROM evaluation_runs WHERE project_id=:p",
    "task_evaluations":   "SELECT te.id, te.evaluation_id, te.task_id, te.annotation_id, te.generation_id, te.field_name, te.answer_type, te.ground_truth, te.prediction, te.metrics, te.passed, te.confidence_score, te.error_message, te.processing_time_ms, te.judge_prompts_used, te.created_at, te.created_by FROM task_evaluations te JOIN evaluation_runs er ON te.evaluation_id=er.id WHERE er.project_id=:p",
    "task_assignments":   "SELECT ta.id, ta.task_id, ta.user_id, ta.target_type, ta.target_id, ta.notes, ta.status, ta.assigned_at, ta.completed_at FROM task_assignments ta JOIN tasks t ON ta.task_id=t.id WHERE t.project_id=:p",
}


def _default(o):
    if isinstance(o, (datetime, date)): return o.isoformat()
    if isinstance(o, UUID): return str(o)
    if isinstance(o, Decimal): return float(o)
    if isinstance(o, bytes): return o.decode("utf-8", errors="replace")
    raise TypeError(f"Unserializable type {type(o).__name__}")


table = "__TABLE__"
db_url = os.environ.get("DATABASE_URI")
if not db_url:
    print("✗ DATABASE_URI not set", file=sys.stderr); sys.exit(2)
engine = create_engine(db_url)
with engine.connect() as c:
    if table == "project":
        row = c.execute(text(QUERIES[table]), {"p": PID}).first()
        out = dict(row._mapping) if row else None
    else:
        out = [dict(r._mapping) for r in c.execute(text(QUERIES[table]), {"p": PID}).all()]
json.dump(out, sys.stdout, default=_default, ensure_ascii=False)
"""


def _ssh_kubectl_exec(stdin_payload: str) -> str:
    cmd = [
        "ssh", "-o", "ConnectTimeout=15", SSH_HOST,
        f"kubectl exec -i {API_DEPLOYMENT} -n {K8S_NS} -- python3 -",
    ]
    res = subprocess.run(cmd, input=stdin_payload, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        print("✗ fetch failed", file=sys.stderr)
        print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)
    return res.stdout


def fetch_from_prod() -> dict[str, Any]:
    """Pull each table separately, then assemble into a single dict."""
    print(f"  fetching live data via {SSH_HOST}:{API_DEPLOYMENT} ...", file=sys.stderr, flush=True)
    raw: dict[str, Any] = {}
    for table in ["project", "tasks", "annotations", "generations",
                  "evaluation_runs", "task_evaluations", "task_assignments"]:
        prog = _FETCHER_TEMPLATE.replace("__TABLE__", table)
        out = _ssh_kubectl_exec(prog)
        try:
            raw[table] = json.loads(out)
        except json.JSONDecodeError as e:
            debug_path = Path(f"/tmp/build_benchathon_mock_raw_{table}.json")
            debug_path.write_text(out)
            print(f"✗ JSON decode failed for {table} at char {e.pos}; raw saved to {debug_path}", file=sys.stderr)
            print(f"  total chars received: {len(out):,}", file=sys.stderr)
            ctx_start = max(0, e.pos - 120)
            ctx_end = min(len(out), e.pos + 120)
            print(f"  context: ...{out[ctx_start:ctx_end]!r}...", file=sys.stderr)
            raise
        n = 1 if table == "project" else len(raw[table])
        print(f"    ✓ {table}: {n:>4} rows ({len(out):>11,} chars)", file=sys.stderr, flush=True)
    return raw


# =============================================================================
# Roster parsing — extract (pick_id, pass) and assigned user_id per assignment
# =============================================================================

def _parse_notes(notes: str) -> dict[str, str]:
    """Notes look like 'evaluator_type=blind;pick_id=P01;pass=A;source=...'."""
    out = {}
    for part in (notes or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def build_roster(assignments: list[dict]) -> list[dict]:
    """Return one dict per assignment with pick_id, pass, target_type, target_id, user_id, task_id."""
    rows = []
    for a in assignments:
        meta = _parse_notes(a.get("notes", ""))
        if not meta.get("pick_id") or not meta.get("pass"):
            continue
        rows.append({
            "pick_id": meta["pick_id"],
            "pass": meta["pass"],
            "evaluator_type": meta.get("evaluator_type"),
            "task_id": a["task_id"],
            "target_type": a["target_type"],
            "target_id": a["target_id"],
            "user_id": a["user_id"],
        })
    return rows


# =============================================================================
# Mock generation — grounded in existing llm_judge_falloesung scores
# =============================================================================

def _grader_bias(user_id: str) -> float:
    """Per-grader leniency bias drawn deterministically. Humans tend ~3pt below LLM judge."""
    rng = random.Random(int(uuid.uuid5(MOCK_NAMESPACE, f"grader:{user_id}").int) & 0xFFFFFFFF)
    return rng.gauss(-3.0, 2.0)


def _llm_judge_raw_score(target_id: str, task_evaluations: list[dict]) -> float | None:
    """Find the llm_judge_falloesung raw_score for this annotation/generation, if any."""
    for te in task_evaluations:
        if te.get("annotation_id") != target_id and te.get("generation_id") != target_id:
            continue
        m = te.get("metrics") or {}
        if not isinstance(m, dict):
            continue
        if "llm_judge_falloesung" in m:
            v = m["llm_judge_falloesung"]
            if isinstance(v, dict):
                # Recent shape: {value, method, details: {raw_score, ...}}
                if "details" in v and isinstance(v["details"], dict):
                    rs = v["details"].get("raw_score")
                    if isinstance(rs, (int, float)):
                        return float(rs)
                if isinstance(v.get("value"), (int, float)):
                    # value may be 0-100 (human/llm same scale) or 0-1; if <=1 scale up
                    val = float(v["value"])
                    return val * 100 if val <= 1.0 else val
            elif isinstance(v, (int, float)):
                val = float(v)
                return val * 100 if val <= 1.0 else val
        if isinstance(m.get("raw_score"), (int, float)):
            return float(m["raw_score"])
    return None


def _half_point_round(x: float) -> float:
    return round(x * 2) / 2


def _band(raw: float) -> str:
    if raw >= 70: return "high"
    if raw >= 50: return "mid"
    return "low"


_JUSTIFICATIONS = {
    "high": [
        "Klare und überwiegend zutreffende Bearbeitung mit nachvollziehbarer Begründung.",
        "Schlüssige Argumentation auf solidem dogmatischen Niveau; einzelne Feinheiten ausbaufähig.",
        "Saubere Subsumtion mit korrektem Fallbezug und stimmiger Methodik.",
    ],
    "mid": [
        "Tragfähige Grundstruktur, an einzelnen Stellen aber lückenhaft oder ungenau.",
        "Argumentation überwiegend nachvollziehbar; Definitionen teilweise nur schlagwortartig.",
        "Korrekter Ansatz, jedoch fehlt es an Tiefe in mehreren Prüfungspunkten.",
    ],
    "low": [
        "Erhebliche dogmatische und methodische Defizite; Subsumtion bleibt oft an der Oberfläche.",
        "Wesentliche Probleme verfehlt oder unzureichend behandelt; Aufbau wirkt brüchig.",
        "Definitionen und Normenarbeit teils fehlerhaft; Begründungen nicht hinreichend tragfähig.",
    ],
}

_OVERALLS = {
    "high": "Insgesamt gute Leistung mit erkennbarer dogmatischer Sicherheit und nachvollziehbarem Aufbau.",
    "mid":  "Insgesamt durchschnittliche Leistung mit erkennbarem Grundverständnis, aber spürbaren Schwächen in Tiefe und Stringenz.",
    "low":  "Insgesamt schwache Leistung mit gravierenden methodischen und inhaltlichen Mängeln.",
}

_TIPS = {
    "high": [
        "Definitionen vor Subsumtion noch konsequenter explizit machen.",
        "Schwerpunktsetzung an die Signale des Sachverhalts weiter feinjustieren.",
        "Streitstände prägnanter referieren, Entscheidung knapp begründen.",
    ],
    "mid": [
        "Obersatz–Definition–Subsumtion–Ergebnis-Schema durchgängiger anwenden.",
        "Konkreten Fallbezug bei jeder Subsumtion herstellen.",
        "Schwerpunkte deutlicher setzen, Nebensächliches kürzer halten.",
    ],
    "low": [
        "Prüfungsaufbau und Anspruchsgrundlagen systematisch wiederholen.",
        "Definitionen sicher beherrschen und im Fallbezug anwenden.",
        "Sachverhalt sorgfältiger auswerten und konsequent subsumieren.",
    ],
}


def _mock_dimensions(target_raw: float, rng: random.Random) -> tuple[dict[str, dict], float]:
    """Sample per-dimension scores so the sum lands close to target_raw."""
    dims: dict[str, dict] = {}
    target_frac = max(0.05, min(0.95, target_raw / 100.0))
    raw_sum = 0.0
    for key, cfg in FALLOESUNG_DIMENSIONS.items():
        max_score = cfg["max_score"]
        # Beta with concentration ~12 around target_frac, scaled to max_score.
        a = 2 + target_frac * 10
        b = 2 + (1 - target_frac) * 10
        score = rng.betavariate(a, b) * max_score
        score = _half_point_round(max(0.0, min(float(max_score), score)))
        dims[key] = {"score": score, "max": max_score, "justification": ""}
        raw_sum += score

    # Renormalise to hit target_raw within 1pt: scale uniformly, re-round.
    if raw_sum > 0:
        scale = target_raw / raw_sum
        raw_sum = 0.0
        for key, cfg in FALLOESUNG_DIMENSIONS.items():
            scaled = dims[key]["score"] * scale
            scaled = _half_point_round(max(0.0, min(float(cfg["max_score"]), scaled)))
            dims[key]["score"] = scaled
            raw_sum += scaled

    # Final drift fix: nudge ergebnisrichtigkeit in half-point steps to land within 0.5 of target.
    drift = target_raw - raw_sum
    if abs(drift) >= 0.5:
        cur = dims["ergebnisrichtigkeit"]["score"]
        max_e = FALLOESUNG_DIMENSIONS["ergebnisrichtigkeit"]["max_score"]
        new = _half_point_round(max(0.0, min(float(max_e), cur + drift)))
        raw_sum += (new - cur)
        dims["ergebnisrichtigkeit"]["score"] = new

    band = _band(raw_sum)
    for key in dims:
        dims[key]["justification"] = rng.choice(_JUSTIFICATIONS[band])
    return dims, raw_sum


def _extract_annotation_prediction(ann_result: Any, field: str) -> str:
    """Mirror _extract_answer_from_annotation in korrektur.py: read value.text
    (or value.value) from the result entry whose from_name == field.

    Note: benchathon `loesung` entries actually store the answer under
    `value.markdown` (Milkdown editor format), not `value.text`/`value.value`.
    Production code does not look at `markdown`, so real korrektur submissions
    on benchathon annotations store `prediction=""`. We mirror that strictly
    rather than diverge from what real entries will look like.
    """
    if not ann_result:
        return ""
    for r in ann_result:
        if isinstance(r, dict) and r.get("from_name") == field:
            v = (r.get("value") or {}).get("text") or (r.get("value") or {}).get("value")
            if isinstance(v, list):
                return v[0] if v else ""
            return v or ""
    return ""


def _resolve_ground_truth(task_data: dict) -> str:
    """Mirror submit_falloesung_grade's fallback chain (korrektur.py:936-945)."""
    if not task_data:
        return ""
    return (
        task_data.get("musterlösung")
        or task_data.get("musterloesung")
        or task_data.get("reference")
        or ""
    )


def build_mock_evaluation(
    pick_id: str,
    pass_letter: str,
    target_type: str,
    target_id: str,
    user_id: str,
    task_id: str,
    task_data: dict,
    annotation_result: Any,
    eval_run_id: str,
    llm_judge_raw: float | None,
    model_tier_prior_val: float,
) -> dict[str, Any]:
    """Return a TaskEvaluation-shaped dict matching serialize_task_evaluation(mode='data')
    for a human-submitted korrektur_falloesung row.

    Honest match to what `submit_falloesung_grade` writes:
      - judge_prompts_used = {"source": "human"}
      - evaluated_model    = "human" (the eval_run.model_id for the korrektur run)
      - ground_truth       = musterlösung/musterloesung/reference || ""
      - prediction (ann)   = extracted value.text from the result entry
      - prediction (gen)   = "" (production code looks for a `parsed_data` attr
                                  that does not exist on the Generation model,
                                  so the fallback empty string is what actually
                                  lands in the DB today)
    """
    rng = random.Random(int(uuid.uuid5(MOCK_NAMESPACE, f"{target_id}:{pass_letter}").int) & 0xFFFFFFFF)
    q = llm_judge_raw if llm_judge_raw is not None else model_tier_prior_val
    bias = _grader_bias(user_id)
    noise = rng.gauss(0, 4.0)
    raw = max(25.0, min(95.0, q + bias + noise))
    raw = _half_point_round(raw)

    dimensions, raw = _mock_dimensions(raw, rng)
    grade_points = raw_score_to_grade_points(raw)
    passed = grade_points >= 4
    band = _band(raw)

    metric_body = {
        "korrektur_falloesung": {
            "value": raw,
            "method": "korrektur_falloesung",
            "details": {
                "raw_score": raw,
                "grade_points": grade_points,
                "passed": passed,
                "dimensions": dimensions,
                "overall_assessment": _OVERALLS[band],
                "improvement_tips": list(_TIPS[band]),
            },
            "error": None,
        }
    }

    if target_type == "annotation":
        prediction = _extract_annotation_prediction(annotation_result, "loesung")
    else:
        prediction = ""

    return {
        "id": str(uuid.uuid5(MOCK_NAMESPACE, f"te:{target_id}:{pass_letter}")),
        "annotation_id": target_id if target_type == "annotation" else None,
        "field_name": "loesung",
        "answer_type": "long_text",
        "ground_truth": _resolve_ground_truth(task_data),
        "prediction": prediction,
        "metrics": metric_body,
        "passed": passed,
        "confidence_score": None,
        "error_message": None,
        "processing_time_ms": None,
        "judge_prompts_used": {"source": "human"},
        "created_at": MOCK_CREATED_AT,
        "evaluation_run_id": eval_run_id,
        "evaluated_model": "human",
        "judge_model": None,
    }


# =============================================================================
# Per-model tier prior — used only if no llm_judge_falloesung sibling exists
# =============================================================================

def model_tier_prior(model_id: str | None) -> float:
    if not model_id: return 60.0
    m = model_id.lower()
    if any(k in m for k in ("opus", "gpt-5.4", "gpt-5-4")): return 72.0
    if "mini" in m or "flash" in m or "haiku" in m: return 52.0
    return 62.0


# =============================================================================
# Serializers that match the production export shape
# =============================================================================

def serialize_evaluation_run(er: dict) -> dict:
    return {
        "id": er["id"],
        "model_id": er["model_id"],
        "evaluation_type_ids": er["evaluation_type_ids"],
        "metrics": er["metrics"],
        "status": er["status"],
        "samples_evaluated": er["samples_evaluated"],
        "created_at": er["created_at"],
        "completed_at": er["completed_at"],
        "eval_metadata": er["eval_metadata"],
        "error_message": er["error_message"],
        "has_sample_results": er["has_sample_results"],
        "created_by": er["created_by"],
    }


def serialize_task(t: dict) -> dict:
    return {
        "id": t["id"],
        "inner_id": t["inner_id"],
        "data": t["data"],
        "meta": t["meta"],
        "is_labeled": t["is_labeled"],
        "created_at": t["created_at"],
        "updated_at": t["updated_at"],
    }


def serialize_annotation(a: dict) -> dict:
    return {
        "id": a["id"],
        "result": a["result"],
        "completed_by": a["completed_by"],
        "created_at": a["created_at"],
        "updated_at": a["updated_at"],
        "was_cancelled": a["was_cancelled"],
        "ground_truth": a["ground_truth"],
        "lead_time": a["lead_time"],
    }


def serialize_generation(g: dict, evaluations: list[dict]) -> dict:
    return {
        "id": g["id"],
        "model_id": g["model_id"],
        "response_content": g["response_content"],
        "case_data": g["case_data"],
        "created_at": g["created_at"],
        "response_metadata": g["response_metadata"],
        "evaluations": evaluations,
    }


def serialize_real_te(te: dict) -> dict:
    """Mirror serialize_task_evaluation(mode='data'): drop created_by, task_id, generation_id."""
    return {
        "id": te["id"],
        "annotation_id": te["annotation_id"],
        "field_name": te["field_name"],
        "answer_type": te["answer_type"],
        "ground_truth": te["ground_truth"],
        "prediction": te["prediction"],
        "metrics": te["metrics"],
        "passed": te["passed"],
        "confidence_score": te["confidence_score"],
        "error_message": te["error_message"],
        "processing_time_ms": te["processing_time_ms"],
        "judge_prompts_used": te["judge_prompts_used"],
        "created_at": te["created_at"],
        "evaluation_run_id": te["evaluation_id"],
        "evaluated_model": None,
        "judge_model": None,
    }


# =============================================================================
# Main assembly
# =============================================================================

def has_korrektur(te: dict) -> bool:
    m = te.get("metrics") or {}
    return isinstance(m, dict) and "korrektur_falloesung" in m


def build_export(raw: dict) -> tuple[dict, dict]:
    """Return (export_json, summary_stats)."""
    proj = raw["project"]
    tasks = raw["tasks"]
    annotations = raw["annotations"]
    generations = raw["generations"]
    evaluation_runs = raw["evaluation_runs"]
    task_evaluations = raw["task_evaluations"]
    assignments = raw["task_assignments"]

    ann_by_id = {a["id"]: a for a in annotations}
    gen_by_id = {g["id"]: g for g in generations}
    task_by_id = {t["id"]: t for t in tasks}

    te_by_generation: dict[str, list[dict]] = defaultdict(list)
    te_by_annotation: dict[str, list[dict]] = defaultdict(list)
    for te in task_evaluations:
        if te["generation_id"]:
            te_by_generation[te["generation_id"]].append(te)
        elif te["annotation_id"]:
            te_by_annotation[te["annotation_id"]].append(te)

    roster = build_roster(assignments)

    # Find an existing korrektur_falloesung EvaluationRun if one exists in prod
    # (real human grading has started). Otherwise we'll synthesize a placeholder
    # that exactly matches what `get_or_create_human_eval_run` would create.
    existing_korrektur_run = next(
        (er for er in evaluation_runs
         if "korrektur_falloesung" in (er.get("evaluation_type_ids") or [])
         and er.get("model_id") == "human"),
        None,
    )
    if existing_korrektur_run is not None:
        eval_run_id = existing_korrektur_run["id"]
        synthetic_run = None
    else:
        eval_run_id = MOCK_EVAL_RUN_ID
        synthetic_run = {
            "id": MOCK_EVAL_RUN_ID,
            "model_id": "human",
            "evaluation_type_ids": ["korrektur_falloesung"],
            "metrics": {},
            "status": "completed",
            "samples_evaluated": 0,
            "created_at": MOCK_CREATED_AT,
            "completed_at": MOCK_CREATED_AT,
            "eval_metadata": {
                "evaluation_type": "korrektur_falloesung",
                "evaluation_configs": [
                    {
                        "id": "korrektur_falloesung",
                        "metric": "korrektur_falloesung",
                        "enabled": True,
                        "display_name": "Korrektur Falloesung",
                    }
                ],
            },
            "error_message": None,
            "has_sample_results": True,
            "created_by": None,
        }

    # Build (target_id, pass) -> assignment row
    roster_by_slot: dict[tuple[str, str], dict] = {}
    picks: dict[str, dict] = {}  # pick_id -> a representative roster row (target info)
    for r in roster:
        roster_by_slot[(r["target_id"], r["pass"])] = r
        picks.setdefault(r["pick_id"], r)

    # Generate mocks per slot, preserving any real korrektur_falloesung entries
    annotation_mocks: dict[str, list[dict]] = defaultdict(list)
    generation_mocks: dict[str, list[dict]] = defaultdict(list)

    real_kept = 0
    mocks_generated = 0
    per_model_scores: dict[str, list[float]] = defaultdict(list)
    per_grader_scores: dict[str, list[float]] = defaultdict(list)

    # Group roster rows by target_id, sorted by pass letter
    by_target: dict[str, list[dict]] = defaultdict(list)
    for r in roster:
        by_target[r["target_id"]].append(r)
    for target_id in by_target:
        by_target[target_id].sort(key=lambda x: x["pass"])

    for target_id, slots in by_target.items():
        target_type = slots[0]["target_type"]
        task_id = slots[0]["task_id"]
        task = task_by_id.get(task_id, {})
        task_data = task.get("data") or {}

        if target_type == "annotation":
            annotation_result = (ann_by_id.get(target_id) or {}).get("result")
            target_model_id = None
            existing_real = [te for te in te_by_annotation.get(target_id, []) if has_korrektur(te)]
        else:
            gen = gen_by_id.get(target_id) or {}
            annotation_result = None
            target_model_id = gen.get("model_id")
            existing_real = [te for te in te_by_generation.get(target_id, []) if has_korrektur(te)]

        # Match real entries to slots by created_by where possible.
        real_by_user: dict[str, dict] = {}
        for r_te in existing_real:
            uid = r_te.get("created_by")
            if uid and uid not in real_by_user:
                real_by_user[uid] = r_te

        llm_raw = _llm_judge_raw_score(target_id, task_evaluations)
        prior = model_tier_prior(target_model_id)

        for slot in slots:
            real = real_by_user.pop(slot["user_id"], None)
            if real is not None:
                serialized = serialize_real_te(real)
                real_kept += 1
                # Extract score for per-model summary
                m = real.get("metrics") or {}
                kb = m.get("korrektur_falloesung", {})
                if isinstance(kb, dict):
                    det = kb.get("details", {}) if isinstance(kb.get("details"), dict) else {}
                    rs = det.get("raw_score", kb.get("value"))
                    if isinstance(rs, (int, float)):
                        per_model_scores[target_model_id or "annotation"].append(float(rs))
                        per_grader_scores[slot["user_id"]].append(float(rs))
            else:
                serialized = build_mock_evaluation(
                    pick_id=slot["pick_id"],
                    pass_letter=slot["pass"],
                    target_type=target_type,
                    target_id=target_id,
                    user_id=slot["user_id"],
                    task_id=task_id,
                    task_data=task_data,
                    annotation_result=annotation_result,
                    eval_run_id=eval_run_id,
                    llm_judge_raw=llm_raw,
                    model_tier_prior_val=prior,
                )
                mocks_generated += 1
                raw_score = serialized["metrics"]["korrektur_falloesung"]["details"]["raw_score"]
                per_model_scores[target_model_id or "annotation"].append(raw_score)
                per_grader_scores[slot["user_id"]].append(raw_score)

            if target_type == "annotation":
                annotation_mocks[target_id].append(serialized)
            else:
                generation_mocks[target_id].append(serialized)

        # Any leftover real entries that didn't match a slot still get included
        for leftover in real_by_user.values():
            serialized = serialize_real_te(leftover)
            real_kept += 1
            if target_type == "annotation":
                annotation_mocks[target_id].append(serialized)
            else:
                generation_mocks[target_id].append(serialized)

    # Assemble final export. Only inject the synthetic korrektur EvaluationRun
    # if a real one doesn't already exist in prod (it's a placeholder for the
    # singleton row that get_or_create_human_eval_run materialises on first grade).
    eval_runs_serialized = [serialize_evaluation_run(er) for er in evaluation_runs]
    if synthetic_run is not None:
        eval_runs_serialized.append(synthetic_run)

    export = {
        "project": {
            "id": proj["id"],
            "title": proj["title"],
            "description": proj["description"],
            "created_at": proj["created_at"],
            "task_count": len(tasks),
            "annotation_count": len(annotations),
            "generation_count": len(generations),
            "evaluation_run_count": len(eval_runs_serialized),
            "task_evaluation_count": len(task_evaluations) + mocks_generated,
            "label_config": proj["label_config"],
        },
        "evaluation_runs": eval_runs_serialized,
        "tasks": [],
    }

    for t in tasks:
        task_obj = serialize_task(t)
        task_obj["annotations"] = [serialize_annotation(a) for a in annotations if a["task_id"] == t["id"]]
        task_obj["generations"] = []
        task_obj["evaluations"] = []
        # Annotation-targeted evals: nest under tasks[i].evaluations (with annotation_id set)
        for a in annotations:
            if a["task_id"] != t["id"]: continue
            # Real non-korrektur task-level evals for this annotation
            for te in te_by_annotation.get(a["id"], []):
                if has_korrektur(te): continue  # korrektur handled separately
                task_obj["evaluations"].append(serialize_real_te(te))
            # Mock + real korrektur entries for this annotation (if any)
            for me in annotation_mocks.get(a["id"], []):
                task_obj["evaluations"].append(me)
        # Generation-targeted evals: nest under each generation
        for g in generations:
            if g["task_id"] != t["id"]: continue
            gen_evals: list[dict] = []
            for te in te_by_generation.get(g["id"], []):
                if has_korrektur(te): continue
                gen_evals.append(serialize_real_te(te))
            for me in generation_mocks.get(g["id"], []):
                gen_evals.append(me)
            task_obj["generations"].append(serialize_generation(g, gen_evals))
        export["tasks"].append(task_obj)

    # Top-level human-evaluation + Korrektur blocks (left empty — production
    # export populates these but they're not load-bearing for the manuscript).
    export["human_evaluation_configs"] = []
    export["human_evaluation_sessions"] = []
    export["human_evaluation_results"] = []
    export["preference_rankings"] = []
    export["likert_scale_evaluations"] = []
    export["korrektur_comments"] = []

    summary = {
        "picks": len(by_target),
        "slots_expected": len(roster),
        "real_kept": real_kept,
        "mocks_generated": mocks_generated,
        "per_model_means": {
            k: round(sum(v) / len(v), 2) for k, v in per_model_scores.items() if v
        },
        "per_grader_means": {
            k[:8] + "…": round(sum(v) / len(v), 2) for k, v in per_grader_scores.items() if v
        },
    }
    return export, summary


def print_summary(summary: dict) -> None:
    print(f"  picks:           {summary['picks']}", file=sys.stderr)
    print(f"  slots expected:  {summary['slots_expected']}", file=sys.stderr)
    print(f"  real kept:       {summary['real_kept']}", file=sys.stderr)
    print(f"  mocks generated: {summary['mocks_generated']}", file=sys.stderr)
    print("  per-model raw_score means:", file=sys.stderr)
    for model, mean in sorted(summary["per_model_means"].items(), key=lambda x: -x[1]):
        print(f"    {mean:5.1f}  {model}", file=sys.stderr)
    print("  per-grader raw_score means:", file=sys.stderr)
    for grader, mean in sorted(summary["per_grader_means"].items()):
        print(f"    {mean:5.1f}  {grader}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--from-snapshot", type=Path, default=None,
                    help="Read fetched data from this JSON file instead of querying prod.")
    ap.add_argument("--save-snapshot", type=Path, default=None,
                    help="After fetching, also write the raw fetched data here for offline re-runs.")
    args = ap.parse_args()

    if args.from_snapshot:
        print(f"  loading snapshot {args.from_snapshot}", file=sys.stderr)
        raw = json.loads(args.from_snapshot.read_text())
    else:
        raw = fetch_from_prod()
        if args.save_snapshot:
            args.save_snapshot.write_text(json.dumps(raw))
            print(f"  saved snapshot to {args.save_snapshot}", file=sys.stderr)

    export, summary = build_export(raw)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(export, indent=2, ensure_ascii=False))
    print(f"  wrote {args.out}  ({args.out.stat().st_size:,} bytes)", file=sys.stderr)
    print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())

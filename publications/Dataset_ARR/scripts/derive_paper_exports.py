"""Derive per-figure JSON exports for manuscript.qmd.

Sources (read-only):
  - data/raw/benchathon/Benchathon-tasks-2026-05-23.json
      Authoritative for tasks, annotations, generations, automatic metrics,
      LLM-judge evaluations.
  - data/raw/benchathon/korrektur_grades_sidecar.json
      Real human (korrektur_falloesung) grades dumped from prod DB and
      strict-filtered to the 180 ARR pick assignments (`source=arr_dataset_2026-05-11`)
      by scripts/pull_korrektur_sidecar.py. Carries grader email + role per row
      (`role_from_assignment`, `pick_id`, `pass`) so the join here doesn't have
      to re-derive the assignment metadata.

Outputs (data/processed/):
  - systems.json
  - benchathon_model_evaluations.json
  - benchathon_automatic_metrics.json
  - benchathon_human_automatic_metrics.json
  - benchathon_human_grades.json
  - benchathon_human_judge_repeats.json
  - benchathon_generations_stats.json

Idempotent: rerunning overwrites outputs deterministically.
Stdlib only.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("o200k_base")

    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text or ""))
except Exception:
    def count_tokens(text: str) -> int:  # type: ignore[misc]
        return len((text or "").split())

HERE = Path(__file__).resolve().parent.parent
RAW = HERE / "data" / "raw"
OUT = HERE / "data" / "processed"

REAL_EXPORT = RAW / "benchathon" / "Benchathon-tasks-2026-05-23.json"
HUMAN_AUTO_EXPORT = RAW / "benchathon" / "human_automatic_metrics_export.json"
KORREKTUR_SIDECAR = RAW / "benchathon" / "korrektur_grades_sidecar.json"
ZJS_SUMMARY = OUT / "zjs_model_summary.json"
VARIANTS_PATH = OUT / "benchathon_instruction_variants.json"

# Three LLM-judge configurations coexist on each generation in the
# 2026-05-21 export. Each derivation picks the relevant one by field_name:
#   - LEGACY  (mmpfzsar-7wb3): single-pass, canonical judge for RQ1/2/3 system
#     leaderboards. Matches what manuscript.qmd was written against.
#   - CONFIG_A (mpe7mkzx-2zp6): gpt-5-mini × 3 passes per generation, for
#     intra-judge stability (derive_judge_repeats).
#   - CONFIG_B (mpe7o02k-yrio): gpt-5-mini + opus + gemini per generation, for
#     inter-judge agreement (separate script).
LEGACY_JUDGE_FIELD_PREFIX  = "llm_judge_falloesung-mmpfzsar-7wb3"
CONFIG_A_FIELD_PREFIX      = "llm_judge_falloesung-mpe7mkzx-2zp6"
CONFIG_B_FIELD_PREFIX      = "llm_judge_falloesung-mpe7o02k-yrio"


def _zjs_model_whitelist() -> set[str]:
    """The canonical model set is the one used in the ZJS Fälle generation run.

    Benchathon contains a few additional models that we drop from the paper to
    keep the system list consistent across corpora. If zjs_model_summary.json
    is not yet built, this returns None and no filtering is applied.
    """
    if not ZJS_SUMMARY.exists():
        return None
    with ZJS_SUMMARY.open(encoding="utf-8") as f:
        return {r["system"] for r in json.load(f)}


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def dump(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=False)


# ---------- provider / openness mapping (derived from model_id prefix) ----------

CLOSED_PROVIDERS = {
    "claude": ("Anthropic", "closed"),
    "gpt": ("OpenAI", "closed"),
    "o1": ("OpenAI", "closed"),
    "o3": ("OpenAI", "closed"),
    "gemini": ("Google", "closed"),
}
OPEN_PROVIDERS = {
    "Qwen": ("Alibaba", "open"),
    "deepseek": ("DeepSeek", "open"),
    "MiniMaxAI": ("MiniMax", "open"),
    "meta-llama": ("Meta", "open"),
    "mistralai": ("Mistral", "open"),
}

# Hand-curated tier classification per model_id. Closed flagships and open-weight
# systems get distinguished from efficiency-oriented variants. Update this when
# adding new models — keep it small and explicit rather than heuristic.
TIER_BY_MODEL_ID = {
    # Closed flagship
    "claude-opus-4-7": "flagship",
    "claude-sonnet-4-6": "flagship",
    "gpt-5.4": "flagship",
    "gemini-3.1-pro-preview": "flagship",
    # Closed efficiency-oriented
    "gpt-5.4-mini": "efficiency",
    "gemini-3.1-flash-lite-preview": "efficiency",
    "gemini-3-flash-preview": "efficiency",
    # Open-weight reference systems (regardless of size)
    "Qwen/Qwen3-235B-A22B-Thinking-2507": "open_reference",
    "Qwen/Qwen3.5-122B-A10B": "open_reference",
    "Qwen/Qwen3.6-35B-A3B": "open_reference",
    "deepseek-ai/DeepSeek-V4-Pro": "open_reference",
    "deepseek-ai/DeepSeek-V4-Flash": "open_reference",
    "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8": "open_reference",
}

# Raw-data → canonical paper-id mapping for slots where the same conceptual
# system was generated under different model ids across corpora. The Google
# efficiency-tier slot was generated with gemini-3-flash-preview on Benchathon
# (collected before the model set was locked in) and with the successor
# gemini-3.1-flash-lite-preview on ZJS and Grundprinzipien. We fold both raw
# ids into a single row keyed by the canonical (ZJS/GP) id. See manuscript
# §Limitations on model-version drift.
MODEL_ID_ALIASES: dict[str, str] = {
    "gemini-3-flash-preview": "gemini-3.1-flash-lite-preview",
}


def canonical_model_id(model_id: str) -> str:
    return MODEL_ID_ALIASES.get(model_id, model_id)


def provider_openness(model_id: str) -> tuple[str, str]:
    lower = model_id.lower()
    for prefix, (provider, openness) in CLOSED_PROVIDERS.items():
        if lower.startswith(prefix):
            return provider, openness
    for prefix, (provider, openness) in OPEN_PROVIDERS.items():
        if model_id.startswith(prefix) or lower.startswith(prefix.lower()):
            return provider, openness
    return "Unknown", "unknown"


def tier_for(model_id: str, weights: str) -> str:
    if model_id in TIER_BY_MODEL_ID:
        return TIER_BY_MODEL_ID[model_id]
    return "open_reference" if weights == "open" else "flagship"


def access_for(weights: str) -> str:
    # Closed weights are served via the provider's own API; open weights in
    # this study are served via a managed inference provider (DeepInfra).
    return "provider_api" if weights == "closed" else "managed_inference"


def short_name(model_id: str) -> str:
    return model_id.split("/", 1)[-1]


# ---------- derivations ----------

AUTOMATIC_METRIC_KEYS = (
    "bleu", "rouge", "meteor",
    "bertscore", "moverscore", "semantic_similarity",
    "coherence",
)


def iter_gen_evals(export):
    for task in export["tasks"]:
        task_id = task["id"]
        for gen in task.get("generations") or []:
            for ev in gen.get("evaluations") or []:
                yield task_id, gen, ev


def _parse_metadata(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _gen_metadata(gen) -> dict:
    return _parse_metadata(gen.get("response_metadata"))


def _response_text(gen) -> str:
    rc = gen.get("response_content")
    if isinstance(rc, str):
        return rc
    if isinstance(rc, dict):
        return " ".join(str(v) for v in rc.values())
    return ""


def derive_systems(real, whitelist=None) -> list[dict]:
    """One row per model_id in the canonical model set.

    The canonical set is `whitelist` if provided (defaults to the ZJS Fälle
    generation set), otherwise every distinct `model_id` observed in real
    Benchathon generations. ZJS-only models get a row with no Benchathon
    generation count; Benchathon-only models are dropped.
    """
    per_model: dict[str, dict] = {}
    for task in real["tasks"]:
        for gen in task.get("generations") or []:
            raw_mid = gen["model_id"]
            mid = canonical_model_id(raw_mid)
            md = _gen_metadata(gen)
            slot = per_model.setdefault(mid, {
                "gen_count": 0,
                "providers": defaultdict(int),
                "temperatures": [],
                "max_tokens": [],
                "truncated": 0,
                "short_words": 0,
                "cost_usd": [],
                "response_time_ms": [],
                "output_words": [],
                "raw_model_ids": set(),
            })
            slot["raw_model_ids"].add(raw_mid)
            slot["gen_count"] += 1
            prov = md.get("provider_name") or md.get("provider")
            if prov:
                slot["providers"][prov] += 1
            for k in ("actual_temperature", "temperature", "requested_temperature"):
                if k in md and md[k] is not None:
                    slot["temperatures"].append(md[k])
                    break
            if md.get("max_tokens") is not None:
                slot["max_tokens"].append(md["max_tokens"])
            # Truncation signal: explicit truncated flag OR a "hit the token
            # budget" finish reason. response_metadata.output_tokens is not
            # populated in this export, so we also count word-count <200 as a
            # "very short answer" proxy.
            if md.get("truncated") or (md.get("finish_reason") or "").lower() in ("length", "max_tokens"):
                slot["truncated"] += 1
            text = _response_text(gen)
            words = len(text.split())
            slot["output_words"].append(words)
            if words < 200:
                slot["short_words"] += 1
            if md.get("cost_usd") is not None:
                slot["cost_usd"].append(float(md["cost_usd"]))
            if md.get("response_time_ms") is not None:
                slot["response_time_ms"].append(float(md["response_time_ms"]))

    model_ids = set(per_model)
    if whitelist is not None:
        model_ids = (model_ids | set(whitelist)) & set(whitelist)

    rows = []
    for mid in model_ids:
        s = per_model.get(mid)
        canonical_provider, openness = provider_openness(mid)
        if s and canonical_provider == "Unknown" and s["providers"]:
            canonical_provider = max(s["providers"].items(), key=lambda kv: kv[1])[0]
        temps = s["temperatures"] if s else []
        max_t = s["max_tokens"] if s else []
        gen_count = s["gen_count"] if s else 0
        raw_ids = sorted(s["raw_model_ids"]) if s else []
        rows.append({
            "model_id": mid,
            "raw_model_ids": raw_ids,
            "name": short_name(mid),
            "provider": canonical_provider,
            "weights": openness,
            "openness": openness,  # back-compat alias for older chunks
            "access": access_for(openness),
            "tier": tier_for(mid, openness),
            "size": None,
            "access_date": "2026-05",
            "temperature": statistics.median(temps) if temps else None,
            "max_output_tokens": statistics.median(max_t) if max_t else None,
            "repetitions": gen_count,
            "n_truncated": s["truncated"] if s else 0,
            "n_short_words": s["short_words"] if s else 0,
            "truncation_rate": (s["truncated"] / gen_count) if (s and gen_count) else None,
            "mean_cost_usd": statistics.mean(s["cost_usd"]) if (s and s["cost_usd"]) else None,
            "mean_response_time_s": (statistics.mean(s["response_time_ms"]) / 1000.0) if (s and s["response_time_ms"]) else None,
            "mean_output_words": statistics.mean(s["output_words"]) if (s and s["output_words"]) else None,
        })
    order = {"closed": 0, "open": 1, "unknown": 2}
    rows.sort(key=lambda r: (order[r["openness"]], r["provider"], r["name"]))
    return rows


def _legacy_judge_score(metrics: dict):
    """Pull (raw_score, grade_points, passed) from a legacy judge eval row.

    The legacy `mmpfzsar-7wb3` run carries two coexisting metric shapes:

      Shape B (original, 180/208 rows): top-level `raw_score`, `llm_judge_falloesung`
        as a 0–1 ratio, and `llm_judge_falloesung_response` carrying the rubric.

      Shape A (re-run + backfilled, 28/208 rows): nested
        `llm_judge_falloesung.details.raw_score`, matching the Config A/B
        shape. Backfilled rows used to carry only `{backfilled_legacy: true}`
        in `details`, but platform issue #113's cleanup populated
        `details.{raw_score, grade_points, passed, judge_response}` from the
        top-level companions, so the Shape A branch returns unconditionally
        when the envelope is a dict.
    """
    m = metrics or {}
    kf = m.get("llm_judge_falloesung")
    if isinstance(kf, dict):
        details = kf.get("details") or {}
        return (details.get("raw_score"),
                details.get("grade_points"),
                details.get("passed"))
    response = m.get("llm_judge_falloesung_response") or {}
    raw = m.get("raw_score")
    if raw is None and isinstance(response, dict):
        raw = response.get("score")
    grade_points = m.get("llm_judge_falloesung_grade_points")
    passed_v = m.get("llm_judge_falloesung_passed")
    passed = bool(passed_v) if passed_v is not None else (
        response.get("passed") if isinstance(response, dict) else None)
    return raw, grade_points, passed


def derive_model_evaluations(real, whitelist=None) -> list[dict]:
    """One row per generation, scored by the legacy single-pass judge.

    Restricted to the legacy `mmpfzsar-7wb3` field so RQ1/2/3 system rankings
    stay on the canonical judge the manuscript was written against.
    Config A/B passes flow through their own derive scripts.
    """
    rows = []
    for task_id, gen, ev in iter_gen_evals(real):
        mid = canonical_model_id(gen["model_id"])
        if whitelist is not None and mid not in whitelist:
            continue
        if not str(ev.get("field_name") or "").startswith(LEGACY_JUDGE_FIELD_PREFIX):
            continue
        raw, grade_points, passed = _legacy_judge_score(ev.get("metrics"))
        if raw is None:
            continue
        rows.append({
            "system": mid,
            "task_id": task_id,
            "generation_id": gen["id"],
            "raw_score": raw,
            "grade_points": grade_points,
            "passed": passed,
            "output_tokens": count_tokens(_response_text(gen)),
        })
    return rows


def derive_automatic_metrics(real, whitelist=None) -> list[dict]:
    """One row per (generation, metric) for the standard automatic metric set."""
    rows = []
    for task_id, gen, ev in iter_gen_evals(real):
        mid = canonical_model_id(gen["model_id"])
        if whitelist is not None and mid not in whitelist:
            continue
        m = ev.get("metrics") or {}
        for k in AUTOMATIC_METRIC_KEYS:
            if k in m:
                val = m[k]
                if isinstance(val, dict):
                    val = val.get("value", val.get("score"))
                if val is None:
                    continue
                rows.append({
                    "system": mid,
                    "task_id": task_id,
                    "generation_id": gen["id"],
                    "metric": k,
                    "value": val,
                })
    return rows


def derive_human_automatic_metrics(human_auto_export_path, variants) -> list[dict]:
    """One row per (annotation_id, metric) joining the prod-sidecar dump with
    the per-annotation working-condition variant. Used by compute_agreement.py
    to split metric-vs-judge correlations by classic / co-creation condition.

    The sidecar export (data/raw/benchathon/human_automatic_metrics_export.json)
    is produced by scripts/export_human_automatic_metrics.py because the
    standard Benchathon export carries only the LLM-judge runs on humans.
    """
    if not human_auto_export_path.exists():
        return []
    with human_auto_export_path.open(encoding="utf-8") as f:
        raw = json.load(f)
    rows = []
    for r in raw:
        metric = r.get("metric")
        if metric not in AUTOMATIC_METRIC_KEYS:
            continue
        ann_id = r.get("annotation_id")
        if not ann_id or r.get("value") is None:
            continue
        rows.append({
            "annotation_id": ann_id,
            "metric": metric,
            "value": r["value"],
            "variant": variants.get(ann_id),
        })
    return rows


def derive_human_grades(sidecar, real=None, variants=None) -> list[dict]:
    """Canonical one-row-per-(solution, grader) human-grade table.

    Consumes the korrektur sidecar (`korrektur_grades_sidecar.json`) — a flat
    list of rows pulled directly from prod `task_evaluations` with grader
    email and role joined from `task_assignments.notes`. `real` is the
    regular Benchathon export, used here only for bereich/variant/model_id
    metadata lookups, not as the grade source.

    Per-row fields:
      solution_id     annotation_id (human solutions) or generation_id (LLM)
      solution_type   "human_traditional" | "human_co_creation" | "llm_system"
      system_or_user  model_id for LLM solutions, annotator id for humans
      task_id         task uuid
      bereich         Zivilrecht | Strafrecht | Öffentliches Recht
      grader_id       grader email (stable across exports)
      role            "blind" | "creator", from task_assignments.notes
      role_inferred   True when role was inferred (no matching assignment row)
      raw_score       0–100 rubric raw points
      grade_points    0–18 German grade-point scale
      passed          bool
      dimensions      {dimension_name: score}
    """
    ann_meta: dict[str, dict] = {}
    gen_meta: dict[str, dict] = {}
    if real is not None:
        for task in real["tasks"]:
            bereich = (task.get("data") or {}).get("bereich")
            for ann in task.get("annotations") or []:
                ann_meta[ann["id"]] = {
                    "task_id": task["id"],
                    "bereich": bereich,
                    "user_id": ann.get("completed_by"),
                }
            for gen in task.get("generations") or []:
                gen_meta[gen["id"]] = {
                    "task_id": task["id"],
                    "bereich": bereich,
                    "model_id": canonical_model_id(gen.get("model_id") or ""),
                }

    def _classify(annotation_id, generation_id):
        if generation_id and generation_id in gen_meta:
            m = gen_meta[generation_id]
            return generation_id, "llm_system", m["model_id"], m["task_id"], m["bereich"]
        if annotation_id and annotation_id in ann_meta:
            m = ann_meta[annotation_id]
            v = (variants or {}).get(annotation_id)
            stype = ("human_co_creation" if v == "ai"
                     else "human_traditional" if v == "no_ai"
                     else "human_unknown_variant")
            return annotation_id, stype, m["user_id"], m["task_id"], m["bereich"]
        return annotation_id or generation_id, "unknown", None, None, None

    rows = []
    for r in sidecar.get("rows") or []:
        kf = (r.get("metrics") or {}).get("korrektur_falloesung")
        if not isinstance(kf, dict):
            continue
        details = kf.get("details") or {}
        annotation_id = r.get("annotation_id")
        generation_id = r.get("generation_id")
        solution_id, solution_type, system_or_user, task_id, bereich = \
            _classify(annotation_id, generation_id)
        task_id = task_id or r.get("task_id")
        rows.append({
            "solution_id": solution_id,
            "solution_type": solution_type,
            "system_or_user": system_or_user,
            "task_id": task_id,
            "bereich": bereich,
            "grader_id": r.get("created_by_email"),
            "role": r.get("role_from_assignment") or "blind",
            "role_inferred": bool(r.get("role_inferred")),
            # `value` and `details.raw_score` are both on 0-100 for korrektur
            # (unlike the llm_judge backfill trap), but we still gate on
            # `details.raw_score` only and let downstream skip on None rather
            # than silently fall back to a sibling field.
            "raw_score": details.get("raw_score"),
            "grade_points": details.get("grade_points"),
            "passed": details.get("passed"),
            "dimensions": {
                name: dim.get("score")
                for name, dim in (details.get("dimensions") or {}).items()
            },
            "annotation_id": annotation_id,
        })
    return rows


def derive_judge_repeats(real, whitelist=None) -> list[dict]:
    """Per-generation stdev of the Config A intra-run (gpt-5-mini × 3 passes).

    Filters by `field_name.startswith(CONFIG_A_FIELD_PREFIX)` so the result
    measures within-cell stability of a single judge model rather than mixing
    in Config B's three different judges or the legacy single-pass run.
    """
    by_gen: dict[str, list[float]] = defaultdict(list)
    for _task_id, gen, ev in iter_gen_evals(real):
        mid = canonical_model_id(gen["model_id"])
        if whitelist is not None and mid not in whitelist:
            continue
        if not str(ev.get("field_name") or "").startswith(CONFIG_A_FIELD_PREFIX):
            continue
        kf = (ev.get("metrics") or {}).get("llm_judge_falloesung")
        if not isinstance(kf, dict):
            continue
        raw = (kf.get("details") or {}).get("raw_score", kf.get("value"))
        if raw is None:
            continue
        by_gen[gen["id"]].append(raw)
    rows = []
    for gid, raws in by_gen.items():
        if len(raws) < 2:
            continue
        rows.append({
            "generation_id": gid,
            "raw_scores": raws,
            "mean": statistics.mean(raws),
            "stdev": statistics.pstdev(raws) if len(raws) > 1 else 0.0,
        })
    return rows


def derive_generations_stats(real, whitelist=None) -> list[dict]:
    """One row per generation with model + task + response word count."""
    rows = []
    for task in real["tasks"]:
        for gen in task.get("generations") or []:
            mid = canonical_model_id(gen["model_id"])
            if whitelist is not None and mid not in whitelist:
                continue
            text = _response_text(gen)
            rows.append({
                "model": mid,
                "task": task["id"],
                "words": len(text.split()),
            })
    return rows


# ---------- entry point ----------

def main() -> None:
    real = load(REAL_EXPORT)
    sidecar = load(KORREKTUR_SIDECAR)
    whitelist = _zjs_model_whitelist()
    variants = load(VARIANTS_PATH) if VARIANTS_PATH.exists() else {}

    OUT.mkdir(parents=True, exist_ok=True)

    if whitelist:
        print(f"Filtering to {len(whitelist)} models from zjs_model_summary.json.")
        # Surface raw Benchathon model_ids that are neither in the whitelist
        # directly nor reachable via MODEL_ID_ALIASES, so future model-version
        # drift becomes loud instead of silent.
        observed = {gen.get("model_id") for task in real["tasks"]
                    for gen in (task.get("generations") or []) if gen.get("model_id")}
        unmapped = sorted(m for m in observed
                          if canonical_model_id(m) not in whitelist)
        if unmapped:
            print(f"  note: {len(unmapped)} Benchathon model_id(s) not in the "
                  f"canonical set (dropped from paper exports): {unmapped}")
    else:
        print("zjs_model_summary.json not found — no model filtering applied.")

    pipeline = [
        ("systems.json",                       derive_systems(real, whitelist)),
        ("benchathon_model_evaluations.json",  derive_model_evaluations(real, whitelist)),
        ("benchathon_automatic_metrics.json",  derive_automatic_metrics(real, whitelist)),
        ("benchathon_human_automatic_metrics.json",
                                               derive_human_automatic_metrics(
                                                    HUMAN_AUTO_EXPORT, variants)),
        ("benchathon_human_grades.json",       derive_human_grades(
                                                    sidecar, real=real, variants=variants)),
        ("benchathon_human_judge_repeats.json", derive_judge_repeats(real, whitelist)),
        ("benchathon_generations_stats.json",  derive_generations_stats(real, whitelist)),
    ]
    for name, payload in pipeline:
        dump(OUT / name, payload)
        print(f"  wrote {name:<42} ({len(payload)} rows)")

    # Sanity report: list every system observed so a human can verify the catalog.
    print()
    print("Systems observed in real export (sorted by gen count desc):")
    sys_rows = pipeline[0][1]
    for s in sorted(sys_rows, key=lambda r: -r["repetitions"]):
        print(
            f"  {s['repetitions']:>4d}  {s['provider']:<10} {s['openness']:<6} "
            f"T={s['temperature']!s:<6} max_t={s['max_output_tokens']!s:<6} {s['model_id']}"
        )


if __name__ == "__main__":
    main()

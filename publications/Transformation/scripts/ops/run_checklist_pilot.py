#!/usr/bin/env python3
"""Pilot runner for the checklist instrument (P1 probes, P2 human study D2).

Runs INSIDE the local dev worker container, so every call goes through the
product's own judge and generator code. Always start it through the host
wrapper, which seeds and saves the ledger, copies inputs and outputs, records
the git SHAs, stops the run on Ctrl-C and deletes the copied data afterwards:

    scripts/ops/pilot.sh <phase> [options]

Phases
  selftest     pure checks without database or provider: spec adapter on the
               expert sheet (every sheet state), probe builders, canary
               phrases, leakage guard, ledger and metering, script selection.
  probes       the probe battery on the D1 exams, product lane (--lane
               product) or checklist lane (--lane checklist --unit ...),
               against one rubric per exam (--rubric).
  generate     checklist Bewertungsbögen for one D1 task (--task), stored as
               candidate rubrics on the D1 research clone.
  checklist    checklist judgments of D1 picks against a generated rubric.
  d2-setup     the research project "Transformation D2 research" and its task
               for the D2 exam (case text only, no sheet, no hints, no
               exemplars). Moves a D2 task left on the D1 clone and removes
               the checklist prompt from the clone's config. Idempotent.
  d2-generate  checklist rubrics for the D2 task (--generators, --samples).
  d2-judge     judges x arms x scripts x passes on the D2 scripts. Arms:
               martin:<step|rating>[:<alt>], rubric:<id>:<unit>[:<alt>].
               Scripts: --scripts ids and/or cohorts (D2a, D2b); default D2a.
               Excluded scripts are never judged.
  d2-probes    the probe battery on the D2 exam per judge and arm.
  ledger       print the ledger.

Integrity
  - Every provider call is metered: catalog price required, spend cap
    checked before dispatch (--cap is the cumulative ceiling), a call that
    raises is charged the model's reserve, a failure without usage is
    charged the reserve, and the provider's internal retries are charged
    (their usage, else the reserve each). PILOT_DRY_RUN=1 stops each call
    before the provider with a dry-run failure and spends nothing.
  - Dry runs never write the database: d2-setup and the prompt install
    print their plan instead. The generator reads the mounted checklist
    prompt through an in-memory overlay on the project row, in dry and live
    runs, so the D1 clone's config is never changed.
  - Leakage guard: every generator prompt and every judge prompt of a
    non-expert arm is checked for the D2 canary terms before it is sent
    (pilot_lib.CanaryGuard). A hit raises LeakageDetected. PILOT_CANARY=warn
    downgrades that to a warning, and only in a dry run. Messages name the
    term's index, never the term.
  - Pass k uses seed 42 + k. Every judge row stores the full finalized
    result, the raw model output, usage, latency, arm and provenance (git
    SHAs, content hashes of every instrument module, the validator hash,
    prompt hashes).
  - SIGINT and SIGTERM stop the run cleanly: the current row is written as
    aborted and the ledger records the run as interrupted.

Outputs: one JSON line per judgment or generation in <work>/out/<phase>.jsonl
(probe coverage in <work>/out/<phase>-coverage.jsonl). The wrapper appends
them to data/interim/pilot/ (D1) or data/interim/human/pilot/ (D2). Local dev
stack only.
"""

from __future__ import annotations

import argparse
import contextlib
import inspect
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# The D1 research clone of the Benchathon project (local dev database).
CLONE_PROJECT = "81e474b8-d226-4bf8-bc2e-fb744d25cba5"
D2_PROJECT_TITLE = "Transformation D2 research"
RESEARCH_USER_EMAIL = "research-ops@example.com"
CHECKLIST_PROMPT_KEY = "bewertungsbogen_checklist"
CHECKLIST_PROMPT_REL = "benger_extended/workers/rubric_prompt_checklist.json"
# The instrument: judge rules, evidence verifier, rubric structure, generator
# contract, validator, generator prompts, the pilot helpers (probe builders,
# spec adapter). Their content hashes make up the code version the gate
# filters on. Paths are relative to the import roots (/app, /shared, work/in).
INSTRUMENT_FILES = (
    "ml_evaluation/checklist_scoring.py",
    "ml_evaluation/llm_judge_evaluator.py",
    "rubric_structure.py",
    "benger_extended/workers/bewertungsbogen_checklist.py",
    "benger_extended/workers/bewertungsbogen_constants.py",
    "benger_extended/workers/bewertungsbogen_tasks.py",
    "pilot_lib.py",
)
INSTRUMENT_GLOBS = ("benger_extended/workers/rubric_prompt*.py", "benger_extended/workers/rubric_prompt*.json")
VALIDATOR_FILE = "benger_extended/workers/bewertungsbogen_checklist.py"
D2_MARKER = "heidebach_polr_2026"
# Same values as the D1 tasks on the clone, so the generator prompt is built
# the same way for both corpora.
D2_TASK_FIELDS = {"rechtsordnung": "Deutschland", "rechtsstand": "nicht angegeben",
                  "pruefungsniveau": "Universitäre juristische Klausur"}
D2_AREA = "Öffentliches Recht"
D2_OFFTOPIC_EXAM = 1  # a civil-law D1 exam: its Musterlösung is off topic for the police-law case
PROBE_TYPES = ("empty", "repetition", "offtopic", "musterloesung", "negation_flip", "keyword_salad",
               "injection", "same_area_offtopic", "section_ablation", "misplacement", "result_swap")
INVALID_PROBES = {"result_swap": "invalid (review round 2): the builder broke on escaped Markdown and "
                                 "swapped non-results; kept for the record only"}
DEFAULT_PROBES = tuple(t for t in PROBE_TYPES if t not in INVALID_PROBES)
MIN_NEGATION_FLIPS = 3
MIN_RESULT_SWAPS = 8
SEED_BASE = 42
ROW_SCHEMA = 3
SPENDING_PHASES = ("probes", "generate", "checklist", "d2-generate", "d2-judge", "d2-probes")
PHASES = ("selftest", "ledger", "d2-setup") + SPENDING_PHASES

L: Any = None  # pilot_lib, imported in main() once the work dir is known


class Ctx:
    """Everything a phase needs: args, paths, ledger, guard, provenance."""

    def __init__(self, args, ledger, guard, provenance):
        self.args = args
        self.work = Path(args.work)
        self.inp = self.work / "in"
        self.out = self.work / "out"
        self.ledger = ledger
        self.guard = guard
        self.provenance = provenance
        self.run_id = args.run_id
        self.dry_run = os.environ.get("PILOT_DRY_RUN") == "1"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write(ctx: Ctx, phase: str, row: dict[str, Any]) -> None:
    ctx.out.mkdir(parents=True, exist_ok=True)
    with (ctx.out / f"{phase}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def load_input(ctx: Ctx, name: str) -> Any:
    path = ctx.inp / name
    if not path.exists():
        legacy = ctx.work / name  # direct runs with inputs in the work dir
        path = legacy if legacy.exists() else path
    if not path.exists():
        raise SystemExit(f"input {name} missing in {ctx.inp} (start the run through scripts/ops/pilot.sh)")
    return json.loads(path.read_text(encoding="utf-8"))


def find_file(rel: str, kind: str = "file") -> Path | None:
    """The first import root (sys.path entry) that holds ``rel``."""
    for root in sys.path:
        path = Path(root) / rel if root else None
        if path is not None and (path.is_file() if kind == "file" else path.is_dir()):
            return path
    return None


def instrument_hashes() -> dict[str, str | None]:
    files: dict[str, str | None] = {}
    for rel in INSTRUMENT_FILES:
        path = find_file(rel)
        files[rel] = L.sha256_file(path) if path else None
    for pattern in INSTRUMENT_GLOBS:
        folder, glob = pattern.rsplit("/", 1)
        base = find_file(folder, kind="dir")
        for path in sorted(base.glob(glob)) if base else []:
            files[f"{folder}/{path.name}"] = L.sha256_file(path)
    return files


# ---------------------------------------------------------------------------
# Database and judge plumbing
# ---------------------------------------------------------------------------


def open_db():
    import models  # noqa: F401  (registers User etc. before project_models)
    import project_models  # noqa: F401
    from database import SessionLocal

    return SessionLocal()


def research_user_id(db) -> str:
    from models import User

    return db.query(User).filter(User.email == RESEARCH_USER_EMAIL).one().id


def require_org(ctx: Ctx) -> str:
    if not ctx.args.org:
        raise SystemExit("no organisation for the API keys: pass --org (pilot.sh reads org_id from "
                         "PILOT_ORG or .pilot.local.json)")
    return ctx.args.org


def make_judge(ctx: Ctx, db, user_id: str, judge_model: str, calls: list):
    import tasks
    from ai_services.provider_capabilities import get_provider_from_model
    from benger_extended.workers.rubric_prompt import DEFAULT_GRADING_PROMPT_TEMPLATE
    from ml_evaluation.llm_judge_evaluator import create_llm_judge_for_user
    from models import LLMModel

    ctx.ledger.price(judge_model)  # an unpriced model stops the run before any call
    row = db.query(LLMModel).filter(LLMModel.id == judge_model).first()
    requested = 0.0 if "DeepSeek" in judge_model else 1.0
    temperature, _ = tasks._clamp_temperature_to_constraint(requested, getattr(row, "parameter_constraints", None) or None)
    # The product template for the product lane. On the checklist lane the
    # judge's configure_checklist owns the user template (stream B) and
    # replaces this one; the row's prompt hashes record what was sent.
    ev = create_llm_judge_for_user(
        db, user_id, get_provider_from_model(judge_model), judge_model,
        temperature=temperature, max_tokens=32000,
        custom_prompt_template=DEFAULT_GRADING_PROMPT_TEMPLATE,
        organization_id=require_org(ctx),
    )
    if ev.ai_service is None:
        raise SystemExit(f"{judge_model}: no usable API key for the research user")
    L.meter(ev.ai_service, "generate_structured", judge_model, ctx.ledger, calls, ctx.guard)
    return ev


def prepare_judge(ev, *, rubric=None, spec=None, unit=None, alternatives="branch",
                  total_mode="declared", grade_scale=None) -> dict[str, Any]:
    """Reset the evaluator to one arm: product lane (spec None) or checklist lane."""
    ev.custom_criteria = {}
    ev.checklist = None
    if rubric is not None:
        ev.bind_task_rubric(rubric)
    info: dict[str, Any] = {"grade_scale_applied": None}
    if spec is not None:
        kwargs: dict[str, Any] = {}
        if grade_scale is not None:
            if "grade_scale" in inspect.signature(ev.configure_checklist).parameters:
                kwargs["grade_scale"] = grade_scale
                info["grade_scale_applied"] = True
            else:
                info["grade_scale_applied"] = False
        ev.configure_checklist(spec, unit, alternatives, total_mode, **kwargs)
    return info


def judge_inputs(task_data: dict[str, Any], rendered: str, sachverhalt: str | None = None
                 ) -> tuple[str, str, dict[str, Any]]:
    """(context, Musterlösung, task data) for one judgment.

    Sheet, grading hints and exemplar rubrics are stripped from the task data
    for every arm; the rubric under test is bound as ``bewertungsbogen``.
    ``sachverhalt`` replaces the task's case text (the script's own year).
    """
    import tasks
    from evaluation.cell_evaluator import _build_judge_context

    data = L.strip_task_data(task_data)
    if sachverhalt is not None:
        key = next((k for k in data if isinstance(k, str) and k.casefold() == "sachverhalt"), "sachverhalt")
        data[key] = sachverhalt
    data["bewertungsbogen"] = rendered
    context = _build_judge_context(data, include_korrekturhinweise=False)
    ground_truth = tasks._get_insensitive(data, "musterlösung") or tasks._get_insensitive(data, "musterloesung") or ""
    return context, str(ground_truth), data


def rendered_text(rubric, alternatives: str) -> tuple[str, str]:
    """(judge-facing rubric text, where it came from)."""
    from rubric_structure import rubric_prompt_text

    meta = rubric.generation_metadata or {}
    if alternatives == "replace":
        text = meta.get("rendered_text_replace")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"rubric {rubric.id}: replace mode needs generation_metadata.rendered_text_replace")
        return text, "rendered_text_replace"
    source = "rendered_text" if isinstance(meta.get("rendered_text"), str) and meta["rendered_text"].strip() else "structure_or_criteria"
    return rubric_prompt_text(rubric), source


def spec_for(rubric, unit: str) -> tuple[dict[str, Any], str]:
    """The rubric's own checklist spec, else the adapter (step and rating only)."""
    meta = rubric.generation_metadata or {}
    if isinstance(meta.get("checklist_spec"), dict):
        return meta["checklist_spec"], "checklist_spec"
    if unit not in L.ADAPTER_UNITS:
        raise ValueError(f"rubric {rubric.id} has no checklist_spec; the {unit} unit needs one")
    return L.spec_from_rubric(rubric.criteria, rubric.structure, rubric.total_points), "adapter"


def closing_text(ev) -> str:
    if ev.checklist:
        if ev.checklist.get("closing_rules"):  # the judge stores the exact text it sends
            return ev.checklist["closing_rules"]
        from ml_evaluation import checklist_scoring

        return checklist_scoring.closing_rules(ev.checklist["score_unit"], ev.checklist["alternatives"])
    from ml_evaluation.llm_judge_evaluator import RUBRIC_JUDGE_CLOSING_RULES

    return RUBRIC_JUDGE_CLOSING_RULES


def judged(ctx: Ctx, phase: str, base: dict[str, Any], ev, calls: list, *, spec, unit, guard_on: bool,
           rubric_texts: list[str], context: str, ground_truth: str, prediction: str,
           data: dict[str, Any]) -> dict[str, Any] | None:
    """One judgment. The row is written in ``finally``, also when the call aborts."""
    calls.clear()
    checks_before = ctx.guard.checked
    if guard_on:
        ctx.guard.arm(f"{phase} {base.get('judge')} {base.get('arm') or base.get('probe') or ''}".strip(),
                      case_texts=[context, ground_truth, prediction], rubric_texts=rubric_texts)
    else:
        ctx.guard.disarm()
    started = time.monotonic()
    result, exc = None, None
    try:
        result = ev._evaluate_multidim_single_call(
            context=context, ground_truth=ground_truth, prediction=prediction, task_data=data,
        )
        return result
    except BaseException as e:
        exc = e
        raise
    finally:
        ctx.guard.disarm()
        row = judge_row(ctx, phase, base, ev, calls, result, exc, spec, unit, guard_on,
                        round(time.monotonic() - started, 1))
        row["guard_checks"] = ctx.guard.checked - checks_before
        write(ctx, phase, row)


def usage_check(calls: list, meta: dict[str, Any]) -> dict[str, Any] | None:
    """Metered tokens against the judge's own call metadata.

    The wrapper meters every provider call the judge makes, retries
    included. The judge sums the usage of all its attempts in
    ``usage_all_attempts``; both sides agree unless a call went unmetered.
    """
    live = [c for c in calls if not c.get("dry_run")]
    if not live:
        return None
    metered_in = sum(int(c.get("in") or 0) for c in live)
    metered_out = sum(int(c.get("out") or 0) for c in live)
    summed = meta.get("usage_all_attempts") if isinstance(meta.get("usage_all_attempts"), dict) else {}
    judge_in = summed.get("input_tokens", meta.get("input_tokens"))
    judge_out = summed.get("output_tokens", meta.get("output_tokens"))
    return {"metered_calls": len(live), "metered_in": metered_in, "metered_out": metered_out,
            "judge_in": judge_in, "judge_out": judge_out,
            "match": judge_in == metered_in and judge_out == metered_out}


def judge_row(ctx: Ctx, phase: str, base: dict[str, Any], ev, calls: list, result, exc, spec, unit,
              guard_on: bool, seconds: float) -> dict[str, Any]:
    row: dict[str, Any] = {"schema": ROW_SCHEMA, "run_id": ctx.run_id, "ts": now(), "phase": phase, **base,
                           "seed": ev.seed, "guard": "on" if guard_on else "off"}
    closing = closing_text(ev)
    if result is None:
        row.update(total=None, error=f"aborted: {type(exc).__name__}: {str(exc)[:400]}", error_type="aborted")
        system_sent = next((c.get("system_sha256") for c in calls), None)
        row["prompt"] = {"system_sha256": system_sent, "closing_rules_sha256": L.sha256_text(closing)}
    else:
        failed = bool(result.get("error"))
        meta = result.get("_call_metadata") or {}
        prompts = result.get("_judge_prompts_used") or {}
        user_prompt = prompts.get("evaluation_prompt") or ""
        row.update(
            total=None if failed else result.get("total_score"),
            error=result.get("error_message") if failed else None,
            error_type=meta.get("error_type") if failed else None,
            result={k: v for k, v in result.items() if not str(k).startswith("_")},
            raw_output=result.get("_raw_output"),
            call_metadata=meta,
            usage_check=usage_check(calls, meta),
            prompt={
                "system_sha256": L.sha256_text(prompts.get("system_prompt")),
                "user_sha256": L.sha256_text(user_prompt),
                "closing_rules_sha256": L.sha256_text(closing),
                "closing_rules_in_prompt": closing in user_prompt,
                "reasoning_effort": prompts.get("reasoning_effort"),
                "temperature": ev.temperature,
                "max_tokens": ev.max_tokens,
                "mode": prompts.get("mode"),
            },
        )
        if not failed:
            ck = result.get("checklist") or {}
            row["zeroed"] = ck.get("zeroed_items") if ck else sum(
                1 for s in (result.get("scores") or {}).values()
                if isinstance(s, dict) and (s.get("model_score") or 0) > (s.get("score") or 0))
            grade_scale = (ev.checklist or {}).get("grade_scale")
            row["model_total"] = L.model_total(result, spec, unit, grade_scale=grade_scale)
            if unit == "rating":
                row["model_total_mapping"] = L.rating_table(grade_scale, (spec or {}).get("total_points") or 100)[1]
    row.update(calls=list(calls), usage=L.usage_summary(calls), latency_s=seconds, provenance=ctx.provenance)
    return row


def print_row(ctx: Ctx, label: str, result) -> None:
    if result is None:
        status = "ABORTED"
    elif result.get("error"):
        status = "ERROR " + str(result.get("error_message"))[:100]
    else:
        status = f"total {result.get('total_score')}"
    print(f"{label}: {status}  (ledger ${ctx.ledger.state['spent']:.3f}, +${ctx.ledger.added():.3f} this run)", flush=True)


def skipped_row(ctx: Ctx, phase: str, base: dict[str, Any], seed: int) -> dict[str, Any]:
    return {"schema": ROW_SCHEMA, "run_id": ctx.run_id, "ts": now(), "phase": phase, **base, "seed": seed,
            "skipped": True, "total": None, "error": None, "provenance": ctx.provenance}


def coverage_row(ctx: Ctx, phase: str, base: dict[str, Any], texts: dict[str, tuple], types) -> dict[str, Any]:
    """Which probe types could be built for one exam and instrument."""
    probes = {}
    for ptype in types:
        text, meta = texts[ptype]
        probes[ptype] = {"built": text is not None, "skipped": meta.get("skipped"),
                         "valid": ptype not in INVALID_PROBES,
                         **{k: v for k, v in meta.items() if k in ("expected_drop", "section", "from", "to", "source",
                                                                   "flipped_sentences", "items", "similarity")}}
    return {"schema": ROW_SCHEMA, "run_id": ctx.run_id, "ts": now(), "phase": phase, "kind": "coverage", **base,
            "probes": probes, "provenance": ctx.provenance}


# ---------------------------------------------------------------------------
# probes (D1)
# ---------------------------------------------------------------------------


def select_rubric(db, task, exam_id: int, ctx: Ctx, actives: dict[str, str]):
    from project_models import TaskRubric

    args = ctx.args
    override = args.rubric_map.get(exam_id)
    if override:
        rubric = db.query(TaskRubric).filter(TaskRubric.id == override).one()
        if rubric.task_id != task.id:
            raise SystemExit(f"rubric {override} does not belong to exam {exam_id}")
        return rubric
    policy = args.rubric_policy
    if policy == "active":
        return db.query(TaskRubric).filter(TaskRubric.id == actives[task.id]).one()
    if policy.startswith("checklist-latest"):
        generator = policy.split(":", 1)[1] if ":" in policy else None
        rows = (db.query(TaskRubric).filter(TaskRubric.task_id == task.id)
                .order_by(TaskRubric.created_at.desc()).all())
        for rubric in rows:
            meta = rubric.generation_metadata or {}
            if isinstance(meta.get("checklist_spec"), dict) and (generator is None or rubric.generator_model_id == generator):
                return rubric
        return None
    raise SystemExit(f"--rubric: unknown policy {policy!r}")


def result_swap_probe(musterloesung: str) -> tuple[str | None, dict[str, Any]]:
    """INVALID probe (kept for the record): every result statement swapped."""
    swapped, n, _pairs = L.result_swap(musterloesung)
    meta = {"swapped_sentences": n, "sha256": L.sha256_text(swapped), "invalid": INVALID_PROBES["result_swap"]}
    if n < MIN_RESULT_SWAPS:
        return None, {**meta, "skipped": f"only {n} result sentences swapped (< {MIN_RESULT_SWAPS})"}
    return swapped, meta


def negation_flip_probe(musterloesung: str) -> tuple[str | None, dict[str, Any]]:
    """Descriptive only: result polarity flipped on the cleaned Musterlösung."""
    flipped, sentences, flips = L.negation_flip(musterloesung)
    meta = {"flipped_sentences": sentences, "flips": flips, "descriptive": True}
    if sentences < MIN_NEGATION_FLIPS:
        return None, {**meta, "skipped": f"only {sentences} sentences flipped (< {MIN_NEGATION_FLIPS})"}
    return flipped, meta


def common_probes(musterloesung: str, offtopic: str | None, same_area: tuple[str | None, dict[str, Any]],
                  rubric_text: str, steps: list[tuple[str, float]], salad_key: str,
                  types) -> dict[str, tuple[str | None, dict[str, Any]]]:
    """The probe texts shared by the D1 and D2 batteries (only the requested types)."""
    out: dict[str, tuple[str | None, dict[str, Any]]] = {}
    if "negation_flip" in types:
        out["negation_flip"] = negation_flip_probe(musterloesung)
    if "keyword_salad" in types:
        salad, meta = L.keyword_salad(rubric_text, [n for n, _ in steps], seed_key=salad_key)
        out["keyword_salad"] = (salad, meta) if salad else (None, {**meta, "skipped": "no norms or key terms"})
    if "injection" in types:
        out["injection"] = L.injection(offtopic) if offtopic else (None, {"skipped": "no off-topic text"})
    if "same_area_offtopic" in types:
        out["same_area_offtopic"] = same_area
    if "section_ablation" in types:
        out["section_ablation"] = L.section_ablation(musterloesung, steps)
    if "misplacement" in types:
        out["misplacement"] = L.misplacement(musterloesung)
    if "result_swap" in types:
        out["result_swap"] = result_swap_probe(musterloesung)
    return out


def primary_steps(spec: dict[str, Any] | None, criteria: dict[str, Any] | None) -> list[tuple[str, float]]:
    """(name, max BE) of the instrument's primary-path steps in outline order."""
    if spec:
        return [(str(spec["steps"][k].get("name") or k), float(spec["steps"][k]["max_score"])) for k in spec["order"]]
    from rubric_structure import order_criteria_keys

    crit = criteria or {}
    return [(str(crit[k].get("name") or k), float(crit[k].get("max_score") or 0))
            for k in order_criteria_keys(crit) if isinstance(crit.get(k), dict)]


def d1_same_area(exam: dict[str, Any], probes: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any]]:
    """The Musterlösung of another D1 exam of the same area, not the one the
    offtopic probe already uses: the next such exam in id order (cyclic)."""
    same = sorted(e["exam_inner_id"] for e in probes if e.get("bereich") == exam.get("bereich"))
    used = {exam["exam_inner_id"], exam.get("offtopic_source_inner_id")}
    if not same:
        return None, {"skipped": "area unknown"}
    start = same.index(exam["exam_inner_id"]) if exam["exam_inner_id"] in same else 0
    for step in range(1, len(same) + 1):
        pick = same[(start + step) % len(same)]
        if pick not in used:
            text = next(e for e in probes if e["exam_inner_id"] == pick)["probes"].get("musterloesung")
            return (text, {"source": f"D1 exam {pick} musterloesung", "area": exam.get("bereich")}) if text else \
                (None, {"skipped": f"D1 exam {pick} has no Musterlösung"})
    return None, {"skipped": f"no third exam in {exam.get('bereich')}"}


def probe_texts(exam: dict[str, Any], probes: list[dict[str, Any]], rubric_text: str,
                steps: list[tuple[str, float]], rubric_id: str, types):
    """{type: (text or None, meta)}; None means the probe is skipped for this exam."""
    out: dict[str, tuple[str | None, dict[str, Any]]] = {}
    given = exam.get("probes") or {}
    for ptype in ("empty", "repetition", "offtopic", "musterloesung"):
        out[ptype] = (given[ptype], {}) if isinstance(given.get(ptype), str) else (None, {"skipped": "not in probe_texts.json"})
    out.update(common_probes(given.get("musterloesung") or "", given.get("offtopic"), d1_same_area(exam, probes),
                             rubric_text, steps, f"{exam['exam_inner_id']}:{rubric_id}", types))
    return out


def phase_probes(ctx: Ctx) -> None:
    from project_models import Task

    args = ctx.args
    probes = load_input(ctx, "probe_texts.json")
    actives = load_input(ctx, "clone_d6_actives.json")
    lane, unit = args.lane, (args.unit if args.lane == "checklist" else None)
    all_types = sorted(set(args.types) | {t for ts in args.types_by_judge.values() for t in ts}, key=PROBE_TYPES.index)
    db = open_db()
    try:
        user_id = research_user_id(db)
        plans = []
        for exam in probes[: args.limit_exams]:
            exam_id = exam["exam_inner_id"]
            if args.exams and exam_id not in args.exams:
                continue
            task = db.query(Task).filter(Task.id == exam["clone_task_id"]).one()
            rubric = select_rubric(db, task, exam_id, ctx, actives)
            if rubric is None:
                print(f"exam {exam_id:>3}: no rubric for --rubric {args.rubric_policy}, skipped", flush=True)
                continue
            spec, spec_source = spec_for(rubric, unit) if lane == "checklist" else (None, None)
            text, text_source = rendered_text(rubric, args.alternatives if lane == "checklist" else "branch")
            context, ground_truth, data = judge_inputs(task.data or {}, text)
            steps = primary_steps(spec, rubric.criteria)
            plan = {
                "exam": exam, "task": task, "rubric": rubric, "spec": spec, "context": context,
                "ground_truth": ground_truth, "data": data,
                "rubric_texts": L.guard_rubric_texts(text, spec, rubric.criteria),
                "texts": probe_texts(exam, probes, text, steps, rubric.id, all_types),
                "arm": {"lane": lane, "unit": unit, "alternatives": args.alternatives if lane == "checklist" else None,
                        "total_mode": args.total_mode if lane == "checklist" else None,
                        "rubric_policy": args.rubric_policy, "spec_source": spec_source, "rendered": text_source,
                        "spec_sha256": L.sha256_text(json.dumps(spec, sort_keys=True)) if spec else None},
            }
            write(ctx, "probes-coverage", coverage_row(ctx, "probes", {"exam": exam_id, "rubric_id": rubric.id,
                                                                       "lane": lane, "unit": unit},
                                                       plan["texts"], all_types))
            plans.append(plan)
        judges: dict[str, tuple[Any, list]] = {}
        for k in range(args.pass_start, args.pass_start + args.passes):
            for judge_model in args.judges:
                if judge_model not in judges:
                    calls: list = []
                    judges[judge_model] = (make_judge(ctx, db, user_id, judge_model, calls), calls)
                ev, calls = judges[judge_model]
                ev.seed = SEED_BASE + k
                types = args.types_by_judge.get(judge_model, args.types)
                for plan in plans:
                    exam_id = plan["exam"]["exam_inner_id"]
                    prepare_judge(ev, rubric=plan["rubric"], spec=plan["spec"], unit=unit,
                                  alternatives=args.alternatives, total_mode=args.total_mode)
                    for ptype in types:
                        text, meta = plan["texts"][ptype]
                        base = {"judge": judge_model, "exam": exam_id, "task_id": plan["task"].id,
                                "rubric_id": plan["rubric"].id, "probe": ptype, "probe_valid": ptype not in INVALID_PROBES,
                                "lane": lane, "unit": unit, "pass": k, "arm_config": plan["arm"], "probe_meta": meta}
                        if text is None:
                            write(ctx, "probes", skipped_row(ctx, "probes", base, ev.seed))
                            print(f"{judge_model} pass {k} exam {exam_id:>3} {ptype:18s}: skipped ({meta.get('skipped')})", flush=True)
                            continue
                        result = judged(ctx, "probes", base, ev, calls, spec=plan["spec"], unit=unit, guard_on=True,
                                        rubric_texts=plan["rubric_texts"], context=plan["context"],
                                        ground_truth=plan["ground_truth"], prediction=text, data=plan["data"])
                        print_row(ctx, f"{judge_model} pass {k} exam {exam_id:>3} {ptype:18s}", result)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# generation (D1 and D2)
# ---------------------------------------------------------------------------


def checklist_prompt() -> tuple[dict[str, Any], str]:
    """(the mounted generator prompt structure, sha256 of the file)."""
    path = find_file(CHECKLIST_PROMPT_REL)
    if path is None:
        raise SystemExit(f"{CHECKLIST_PROMPT_REL} not found on the import path (is benger_extended mounted?)")
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw), L.sha256_text(raw)


@contextlib.contextmanager
def prompt_overlay(project_id: str, structure: dict[str, Any]):
    """Let the generator read ``structure`` as the project's checklist prompt
    without writing it: every Project row loaded or refreshed for
    ``project_id`` gets the prompt in its generation_config as a committed
    (clean) value, so no flush ever writes it back."""
    from project_models import Project
    from sqlalchemy import event
    from sqlalchemy.orm.attributes import set_committed_value

    def apply(target, *_args):
        if getattr(target, "id", None) != project_id:
            return
        config = dict(target.generation_config or {})
        structures = dict(config.get("prompt_structures") or {})
        structures[CHECKLIST_PROMPT_KEY] = structure
        config["prompt_structures"] = structures
        set_committed_value(target, "generation_config", config)

    event.listen(Project, "load", apply)
    event.listen(Project, "refresh", apply)
    try:
        yield
    finally:
        event.remove(Project, "load", apply)
        event.remove(Project, "refresh", apply)


def install_checklist_prompt(ctx: Ctx, db, project_id: str) -> dict[str, Any]:
    """Store the mounted generator prompt in the project's config.

    Only for the D2 research project and only in a live run; a dry run
    prints the plan. The D1 clone never gets it (the overlay serves it)."""
    from project_models import Project
    from sqlalchemy.orm.attributes import flag_modified

    if project_id == CLONE_PROJECT:
        raise SystemExit("install_checklist_prompt: the D1 clone's config stays as it is (the overlay serves the prompt)")
    structure, digest = checklist_prompt()
    project = db.query(Project).filter(Project.id == project_id).one()
    config = dict(project.generation_config or {})
    structures = dict(config.get("prompt_structures") or {})
    current = structures.get(CHECKLIST_PROMPT_KEY)
    current_digest = L.sha256_text(json.dumps(current, sort_keys=True)) if current is not None else None
    wanted_digest = L.sha256_text(json.dumps(structure, sort_keys=True))
    if current_digest == wanted_digest:
        print(f"checklist prompt on project {project_id}: up to date", flush=True)
        return {"prompt_sha256": digest, "installed": False}
    if ctx.dry_run:
        print(f"DRY RUN: would install the checklist prompt (file sha256 {digest[:12]}) on project {project_id} "
              f"({'replacing a different one' if current is not None else 'new'}); nothing written", flush=True)
        return {"prompt_sha256": digest, "installed": False, "plan": "install"}
    structures[CHECKLIST_PROMPT_KEY] = structure
    config["prompt_structures"] = structures
    project.generation_config = config
    flag_modified(project, "generation_config")
    db.commit()
    print(f"checklist prompt installed on project {project_id} (file sha256 {digest[:12]})", flush=True)
    return {"prompt_sha256": digest, "installed": True}


def case_texts_of(data: dict[str, Any]) -> list[str]:
    import tasks

    return [str(tasks._get_insensitive(data or {}, key) or "")
            for key in ("sachverhalt", "musterlösung", "musterloesung")]


def run_generation(ctx: Ctx, phase: str, user_id: str, project_id: str, task, generator: str, sample: int,
                   prompt: tuple[dict[str, Any], str]) -> dict[str, Any] | None:
    """One generator call chain; the row is written in ``finally``."""
    import benger_extended.workers.judge_resolution as jr
    from benger_extended.workers.bewertungsbogen_tasks import (
        generate_bewertungsbogen_impl,
    )

    args = ctx.args
    ctx.ledger.price(generator)
    calls: list = []
    original_resolve = jr.resolve_judge_ai_service

    def resolve(*a, **k):
        service = original_resolve(*a, **k)
        if service is not None:
            L.meter(service, "generate", generator, ctx.ledger, calls, ctx.guard)
        return service

    jr.resolve_judge_ai_service = resolve
    checks_before = ctx.guard.checked
    ctx.guard.arm(f"{phase} {generator} sample {sample}", case_texts=case_texts_of(task.data or {}))
    started = time.monotonic()
    out, exc, extra = None, None, {}
    try:
        with prompt_overlay(project_id, prompt[0]):
            out = generate_bewertungsbogen_impl(
                None, project_id, task.id, user_id, organization_id=require_org(ctx), generator_model_id=generator,
                prompt_key=CHECKLIST_PROMPT_KEY, activate_if_first=False,
                rubric_contract="checklist", allocation_mode=args.allocation_mode,
            )
        if out.get("status") == "completed" and out.get("rubric_id"):
            extra = rubric_generation_facts(out["rubric_id"], ctx.provenance.get("validator_sha256"))
        return out
    except BaseException as e:
        exc = e
        raise
    finally:
        jr.resolve_judge_ai_service = original_resolve
        ctx.guard.disarm()
        first = calls[0] if calls else {}
        write(ctx, phase, {
            "schema": ROW_SCHEMA, "run_id": ctx.run_id, "ts": now(), "phase": phase,
            "generator": generator, "project_id": project_id, "task_id": task.id, "sample": sample,
            "allocation_mode": args.allocation_mode, "prompt_file_sha256": prompt[1], "prompt_source": "overlay",
            "status": (out or {}).get("status") or "aborted", "rubric_id": (out or {}).get("rubric_id"),
            "result": out, "attempt_errors": (out or {}).get("attempt_errors") or extra.get("attempt_errors") or [],
            "rubric": extra or None,
            "error": None if exc is None else f"aborted: {type(exc).__name__}: {str(exc)[:400]}",
            "prompt": {"system_sha256": first.get("system_sha256"), "prompt_sha256": first.get("prompt_sha256")},
            "guard_checks": ctx.guard.checked - checks_before,
            "calls": calls, "usage": L.usage_summary(calls), "latency_s": round(time.monotonic() - started, 1),
            "provenance": ctx.provenance,
        })
        print(f"{generator} sample {sample}: {(out or {}).get('status') or 'ABORTED'} rubric {(out or {}).get('rubric_id')} "
              f"steps {(out or {}).get('steps')} attempts {(out or {}).get('attempts')} "
              f"(ledger ${ctx.ledger.state['spent']:.3f}, +${ctx.ledger.added():.3f} this run)", flush=True)


def rubric_generation_facts(rubric_id: str, validator_sha256: str | None) -> dict[str, Any]:
    from project_models import TaskRubric

    db = open_db()
    try:
        rubric = db.query(TaskRubric).filter(TaskRubric.id == rubric_id).one()
        meta = rubric.generation_metadata or {}
        stored_validator = meta.get("validator_sha256")  # stream A, contract checklist-3
        return {"prompt_version": rubric.prompt_version, "contract_version": meta.get("contract_version"),
                "validator_sha256": stored_validator, "prompt_sha256": meta.get("prompt_sha256"),
                "validator_matches_mounted": (stored_validator == validator_sha256) if stored_validator else None,
                "attempts": meta.get("attempts"), "attempt_errors": meta.get("attempt_errors") or [],
                "hinweise": meta.get("hinweise"), "steps": len(rubric.criteria or {}),
                "spec_sha256": L.sha256_text(json.dumps(meta.get("checklist_spec"), sort_keys=True))}
    finally:
        db.close()


def phase_generate(ctx: Ctx) -> None:
    from project_models import Task

    if not ctx.args.task:
        raise SystemExit("generate needs --task")
    prompt = checklist_prompt()
    db = open_db()
    try:
        user_id = research_user_id(db)
        task = db.query(Task).filter(Task.id == ctx.args.task).one()
    finally:
        db.close()
    for generator in ctx.args.generators:
        for sample in range(ctx.args.samples):
            run_generation(ctx, "generate", user_id, task.project_id, task, generator, sample, prompt)


# ---------------------------------------------------------------------------
# checklist (D1 picks)
# ---------------------------------------------------------------------------


def answer_text(db, pick) -> str:
    from project_models import Annotation

    if pick["target_type"] == "annotation":
        ann = db.query(Annotation).filter(Annotation.id == pick["target_id"]).one()
        for entry in ann.result or []:
            value = entry.get("value") if isinstance(entry, dict) else None
            if isinstance(value, dict):
                for key in ("markdown", "text"):
                    if isinstance(value.get(key), str) and value[key].strip():
                        return value[key]
                    if isinstance(value.get(key), list):
                        return "\n".join(map(str, value[key]))
        return ""
    import models

    gen = db.query(models.Generation).filter(models.Generation.id == pick["target_id"]).one()
    for attr in ("response_content", "content", "output", "response"):
        value = getattr(gen, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def phase_checklist(ctx: Ctx) -> None:
    from project_models import Task, TaskRubric

    args = ctx.args
    picks = {p["pick_id"]: p for p in load_input(ctx, "picks_temp0.json")["resolved"]}
    db = open_db()
    try:
        user_id = research_user_id(db)
        rubric = db.query(TaskRubric).filter(TaskRubric.id == args.rubric_id).one()
        task = db.query(Task).filter(Task.id == rubric.task_id).one()
        text, text_source = rendered_text(rubric, args.alternatives)
        context, ground_truth, data = judge_inputs(task.data or {}, text)
        for k in range(args.pass_start, args.pass_start + args.passes):
            for judge_model in args.judges:
                calls: list = []
                ev = make_judge(ctx, db, user_id, judge_model, calls)
                ev.seed = SEED_BASE + k
                for unit in args.units:
                    spec, spec_source = spec_for(rubric, unit)
                    prepare_judge(ev, rubric=rubric, spec=spec, unit=unit, alternatives=args.alternatives,
                                  total_mode=args.total_mode)
                    for pick_id in args.picks:
                        base = {"judge": judge_model, "unit": unit, "pick": pick_id, "rubric_id": rubric.id,
                                "task_id": task.id, "pass": k,
                                "arm_config": {"lane": "checklist", "unit": unit, "alternatives": args.alternatives,
                                               "total_mode": args.total_mode, "spec_source": spec_source,
                                               "rendered": text_source}}
                        result = judged(ctx, "checklist", base, ev, calls, spec=spec, unit=unit, guard_on=True,
                                        rubric_texts=L.guard_rubric_texts(text, spec, rubric.criteria),
                                        context=context, ground_truth=ground_truth,
                                        prediction=answer_text(db, picks[pick_id]), data=data)
                        print_row(ctx, f"{judge_model} pass {k} {unit:6s} {pick_id}", result)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# D2: the expert's exam
# ---------------------------------------------------------------------------


def find_d2_project(db):
    from project_models import Project

    rows = (db.query(Project).filter(Project.title == D2_PROJECT_TITLE, Project.deleted_at.is_(None))
            .order_by(Project.created_at).all())
    if len(rows) > 1:
        raise SystemExit(f"{len(rows)} projects titled {D2_PROJECT_TITLE!r}: keep one")
    return rows[0] if rows else None


def find_d2_task(db, project_ids: list[str]):
    from project_models import Task

    found = []
    for task in db.query(Task).filter(Task.project_id.in_(project_ids)).all():
        research = (task.meta or {}).get("research") if isinstance(task.meta, dict) else None
        if isinstance(research, dict) and research.get("d2_exam") == D2_MARKER:
            found.append(task)
    if len(found) > 1:
        raise SystemExit(f"{len(found)} D2 research tasks in {project_ids}: keep one")
    return found[0] if found else None


def d2_task_data(exam: dict[str, Any]) -> dict[str, Any]:
    return {"sachverhalt": exam["sachverhalt"], "musterloesung": exam["musterloesung"], **D2_TASK_FIELDS}


def require_d2(db, exam: dict[str, Any]):
    project = find_d2_project(db)
    task = find_d2_task(db, [project.id]) if project is not None else None
    if project is None or task is None:
        raise SystemExit(f"no D2 research task in project {D2_PROJECT_TITLE!r}: run the d2-setup phase first "
                         "(a live run; a dry run only prints its plan)")
    if dict(task.data or {}) != d2_task_data(exam):
        raise SystemExit(f"D2 task {task.id} differs from heidebach_exam.json: rerun d2-setup --force-update")
    return project, task


def phase_d2_setup(ctx: Ctx) -> None:
    """Research project + D2 task; moves a legacy D2 task off the D1 clone.

    A dry run prints the plan and writes nothing to the database."""
    from project_models import Project, Task, TaskRubric
    from sqlalchemy import func
    from sqlalchemy.orm.attributes import flag_modified

    exam = load_input(ctx, "heidebach_exam.json")
    data = d2_task_data(exam)
    db = open_db()
    try:
        user_id = research_user_id(db)
        project = find_d2_project(db)
        task = find_d2_task(db, [p for p in (project.id if project else None, CLONE_PROJECT) if p])
        clone = db.query(Project).filter(Project.id == CLONE_PROJECT).first()
        clone_structures = ((clone.generation_config or {}).get("prompt_structures") or {}) if clone else {}
        plan: list[str] = []
        if project is None:
            plan.append(f"create project {D2_PROJECT_TITLE!r}")
        if task is None:
            plan.append("create the D2 task (case text only)")
        else:
            if project is None or task.project_id != project.id:
                n = db.query(TaskRubric).filter(TaskRubric.task_id == task.id).count()
                plan.append(f"move task {task.id} and its {n} rubrics from project {task.project_id} to the D2 project")
            if dict(task.data or {}) != data:
                plan.append("update the task data to the current pack"
                            + ("" if ctx.args.force_update else " (needs --force-update)"))
            leaked = [k for k in (task.data or {}) if isinstance(k, str) and k.casefold() in L.SENSITIVE_TASK_KEYS]
            if leaked:
                raise SystemExit(f"D2 task {task.id} carries {leaked}: remove them before any generation")
        if CHECKLIST_PROMPT_KEY in clone_structures:
            plan.append("remove the checklist prompt from the D1 clone's generation_config "
                        "(its state before install_checklist_prompt)")
        row = {"schema": ROW_SCHEMA, "run_id": ctx.run_id, "ts": now(), "phase": "d2-setup",
               "dry_run": ctx.dry_run, "plan": plan, "sachverhalt_sha256": L.sha256_text(data["sachverhalt"]),
               "musterloesung_sha256": L.sha256_text(data["musterloesung"]), "provenance": ctx.provenance}
        if ctx.dry_run:
            print("DRY RUN: d2-setup plan (nothing written):" + ("".join(f"\n  - {p}" for p in plan) or " nothing to do"),
                  flush=True)
            write(ctx, "d2-setup", {**row, "project_id": project.id if project else None,
                                    "task_id": task.id if task else None})
            return
        if task is not None and dict(task.data or {}) != data and not ctx.args.force_update:
            raise SystemExit(f"D2 task {task.id} exists with different data (the exam pack changed). Pass "
                             "--force-update to overwrite it; rubrics generated from the old text stay.")
        stamp = now()
        if project is None:
            project = Project(id=str(uuid.uuid4()), title=D2_PROJECT_TITLE, created_by=user_id, is_private=True,
                              description="Research project for the D2 exam of the Transformation study "
                                          "(local dev only). Case text only: no Bewertungsbogen, "
                                          "Korrekturhinweise or exemplar rubrics.")
            db.add(project)
            db.flush()
            print(f"D2 project {project.id}: created", flush=True)
        created = moved = updated = False
        if task is None:
            inner = (db.query(func.max(Task.inner_id)).filter(Task.project_id == project.id).scalar() or 0) + 1
            task = Task(id=str(uuid.uuid4()), project_id=project.id, data=data, inner_id=inner, created_by=user_id,
                        meta={"research": {"d2_exam": D2_MARKER, "created_by": "run_checklist_pilot d2-setup",
                                           "created_at": stamp,
                                           "note": "Case text only: no Bewertungsbogen, Korrekturhinweise or exemplar rubrics."}})
            db.add(task)
            created = True
        meta = dict(task.meta or {})
        research = dict(meta.get("research") or {})
        history = list(research.get("history") or [])
        if not created and task.project_id != project.id:
            old = task.project_id
            task.project_id = project.id
            task.inner_id = (db.query(func.max(Task.inner_id)).filter(Task.project_id == project.id).scalar() or 0) + 1
            db.query(TaskRubric).filter(TaskRubric.task_id == task.id).update({"project_id": project.id},
                                                                              synchronize_session=False)
            history.append({"at": stamp, "event": "moved", "from_project": old, "to_project": project.id})
            moved = True
        if not created and dict(task.data or {}) != data:
            task.data = data
            history.append({"at": stamp, "event": "data_updated",
                            "sachverhalt_sha256": row["sachverhalt_sha256"],
                            "musterloesung_sha256": row["musterloesung_sha256"],
                            "note": "rubrics generated before this date saw the previous text"})
            updated = True
        if history:
            research["history"] = history
            meta["research"] = research
            task.meta = meta
            flag_modified(task, "meta")
        clone_restored = False
        if clone is not None and CHECKLIST_PROMPT_KEY in clone_structures:
            config = dict(clone.generation_config or {})
            structures = dict(config.get("prompt_structures") or {})
            structures.pop(CHECKLIST_PROMPT_KEY, None)
            config["prompt_structures"] = structures
            clone.generation_config = config
            flag_modified(clone, "generation_config")
            clone_restored = True
        db.commit()
        print(f"D2 task {task.id} in project {project.id}: "
              + ", ".join(w for w, flag in (("created", created), ("moved", moved), ("data updated", updated)) if flag)
              + (" (unchanged)" if not (created or moved or updated) else "")
              + ("; clone prompt removed" if clone_restored else ""), flush=True)
        write(ctx, "d2-setup", {**row, "project_id": project.id, "task_id": task.id, "created": created,
                                "moved": moved, "data_updated": updated, "clone_prompt_removed": clone_restored,
                                "data_keys": sorted(task.data or {})})
    finally:
        db.close()


def phase_d2_generate(ctx: Ctx) -> None:
    exam = load_input(ctx, "heidebach_exam.json")
    prompt = checklist_prompt()
    db = open_db()
    try:
        user_id = research_user_id(db)
        project, task = require_d2(db, exam)
        install_checklist_prompt(ctx, db, project.id)
    finally:
        db.close()
    for generator in ctx.args.generators:
        for sample in range(ctx.args.samples):
            run_generation(ctx, "d2-generate", user_id, project.id, task, generator, sample, prompt)


def prepare_arm(ctx: Ctx, db, arm: dict[str, Any], exam: dict[str, Any], task, state: str | None = None
                ) -> dict[str, Any]:
    """One arm, for the expert sheet in one sheet state (the scripts' maxima)."""
    from project_models import TaskRubric

    unit, alternatives = arm["unit"], arm["alternatives"]
    if arm["source"] == "martin":
        if unit == "bullet":
            raise SystemExit("martin arm: the bullet unit waits for the expert's own bullets (decisions, section 5)")
        spec = L.spec_from_sheet(exam["sheet"], state)
        text, text_source, spec_source = L.render_sheet_text(exam, state), "sheet_structure", "adapter"
        rubric, guard_on = None, False
    else:
        state = None
        rubric = db.query(TaskRubric).filter(TaskRubric.id == arm["rubric_id"]).one()
        if rubric.task_id != task.id:
            raise SystemExit(f"arm {arm['id']}: rubric belongs to task {rubric.task_id}, not to the D2 task {task.id}")
        spec, spec_source = spec_for(rubric, unit)
        text, text_source = rendered_text(rubric, alternatives)
        guard_on = True
    grade_scale = L.exam_grade_scale(exam["grade_scale"], spec.get("total_points")) if unit == "rating" else None
    return {
        "arm": arm, "rubric": rubric, "spec": spec, "guard_on": guard_on, "text": text, "state": state,
        "grade_scale": grade_scale, "contexts": {},
        "rubric_texts": L.guard_rubric_texts(text, spec, getattr(rubric, "criteria", None)),
        "config": {"source": arm["source"], "rubric_id": arm["rubric_id"],
                   "sheet_id": exam["sheet"].get("prod_rubric_id") if arm["source"] == "martin" else None,
                   "sheet_state": state, "score_unit": unit, "alternatives": alternatives,
                   "total_mode": ctx.args.total_mode, "grade_scale": grade_scale, "spec_source": spec_source,
                   "rendered": text_source, "spec_sha256": L.sha256_text(json.dumps(spec, sort_keys=True)),
                   "rendered_sha256": L.sha256_text(text)},
    }


def plan_context(plan: dict[str, Any], task, sachverhalt: str | None = None) -> tuple[str, str, dict[str, Any]]:
    key = L.sha256_text(sachverhalt) if sachverhalt is not None else None
    if key not in plan["contexts"]:
        plan["contexts"][key] = judge_inputs(task.data or {}, plan["text"], sachverhalt)
    return plan["contexts"][key]


def phase_d2_judge(ctx: Ctx) -> None:
    args = ctx.args
    exam = load_input(ctx, "heidebach_exam.json")
    scripts = load_input(ctx, "heidebach_scripts.json")
    try:
        chosen = L.select_scripts(scripts, args.scripts)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    arms = [L.parse_arm(a) for a in args.arms]
    if not arms:
        raise SystemExit("d2-judge needs --arms")
    db = open_db()
    try:
        user_id = research_user_id(db)
        _project, task = require_d2(db, exam)
        prepared = []
        for arm in arms:  # the expert sheet: one plan per sheet state among the chosen scripts
            states = sorted({s.get("sheet_state") for s in chosen}, key=str) if arm["source"] == "martin" else [None]
            for state in states:
                plan = prepare_arm(ctx, db, arm, exam, task, state)
                plan["scripts"] = [s for s in chosen if arm["source"] != "martin" or s.get("sheet_state") == state]
                prepared.append(plan)
        print(f"d2-judge: {len(args.judges)} judges x {len(arms)} arms x {len(chosen)} scripts x {args.passes} passes "
              f"({len(prepared)} arm/sheet-state plans)", flush=True)
        judges: dict[str, tuple[Any, list]] = {}
        for k in range(args.pass_start, args.pass_start + args.passes):
            for judge_model in args.judges:
                if judge_model not in judges:
                    calls: list = []
                    judges[judge_model] = (make_judge(ctx, db, user_id, judge_model, calls), calls)
                ev, calls = judges[judge_model]
                ev.seed = SEED_BASE + k
                for plan in prepared:
                    arm = plan["arm"]
                    info = prepare_judge(ev, rubric=plan["rubric"], spec=plan["spec"], unit=arm["unit"],
                                         alternatives=arm["alternatives"], total_mode=args.total_mode,
                                         grade_scale=plan["grade_scale"])
                    config = {**plan["config"], "grade_scale_applied": info["grade_scale_applied"]}
                    for script in plan["scripts"]:
                        sachverhalt, case_text_year, mismatch = L.case_text_for(exam, script)
                        context, ground_truth, data = plan_context(plan, task, sachverhalt)
                        base = {"judge": judge_model, "arm": arm["id"], "arm_config": config,
                                "script_id": script["script_id"], "cohort": script.get("cohort"),
                                "case_year": script.get("case_year"), "case_text_year": case_text_year,
                                "case_text_year_mismatch": mismatch, "case_text_sha256": L.sha256_text(sachverhalt),
                                "sheet_state": script.get("sheet_state"),
                                "task_id": task.id, "rubric_id": arm["rubric_id"], "pass": k}
                        result = judged(ctx, "d2-judge", base, ev, calls, spec=plan["spec"], unit=arm["unit"],
                                        guard_on=plan["guard_on"], rubric_texts=plan["rubric_texts"],
                                        context=context, ground_truth=ground_truth,
                                        prediction=script.get("text") or "", data=data)
                        print_row(ctx, f"{judge_model} pass {k} {arm['id']} {script['script_id']}", result)
    finally:
        db.close()


def d2_same_area(exam: dict[str, Any], probes: list[dict[str, Any]], override: int | None
                 ) -> tuple[str | None, dict[str, Any]]:
    """A public-law D1 Musterlösung for the police-law exam: the one closest to
    the D2 Musterlösung (the hardest case), unless --same-area-exam names one."""
    pool = {e["exam_inner_id"]: e["probes"].get("musterloesung") for e in probes
            if e.get("bereich") == D2_AREA and e["probes"].get("musterloesung")}
    if not pool:
        return None, {"skipped": f"no D1 exam in {D2_AREA}"}
    if override is not None:
        if override not in pool:
            raise SystemExit(f"--same-area-exam {override} is not a D1 exam in {D2_AREA}")
        pick, score = override, None
    else:
        pick, score = L.closest_text(exam["musterloesung"], pool)
    return pool[pick], {"source": f"D1 exam {pick} musterloesung", "area": D2_AREA, "similarity": score,
                        "chosen_by": "override" if override is not None else "closest"}


def d2_probe_texts(exam: dict[str, Any], offtopic: str, same_area: tuple[str | None, dict[str, Any]],
                   rubric_text: str, steps: list[tuple[str, float]], arm_id: str,
                   types) -> dict[str, tuple[str | None, dict[str, Any]]]:
    """The probe battery on the D2 exam (only the requested types)."""
    musterloesung = exam["musterloesung"]
    out: dict[str, tuple[str | None, dict[str, Any]]] = {
        "empty": (" ", {}),
        "repetition": (exam["sachverhalt"], {"source": "sachverhalt"}),
        "offtopic": (offtopic, {"source": f"D1 exam {D2_OFFTOPIC_EXAM} musterloesung"}),
        "musterloesung": (musterloesung, {}),
    }
    out.update(common_probes(musterloesung, offtopic, same_area, rubric_text, steps, f"D2:{arm_id}", types))
    return out


def phase_d2_probes(ctx: Ctx) -> None:
    """The probe battery on the D2 exam, per judge and instrument (arm), on the checklist lane."""
    args = ctx.args
    exam = load_input(ctx, "heidebach_exam.json")
    probes = load_input(ctx, "probe_texts.json")
    offtopic = next(e for e in probes if e["exam_inner_id"] == D2_OFFTOPIC_EXAM)["probes"]["musterloesung"]
    same_area = d2_same_area(exam, probes, args.same_area_exam)
    all_types = sorted(set(args.types) | {t for ts in args.types_by_judge.values() for t in ts}, key=PROBE_TYPES.index)
    arms = [L.parse_arm(a) for a in args.arms]
    if not arms:
        raise SystemExit("d2-probes needs --arms")
    db = open_db()
    try:
        user_id = research_user_id(db)
        _project, task = require_d2(db, exam)
        prepared = []
        for arm in arms:
            plan = prepare_arm(ctx, db, arm, exam, task)
            steps = primary_steps(plan["spec"], None)
            plan["texts"] = d2_probe_texts(exam, offtopic, same_area, plan["text"], steps, arm["id"], all_types)
            write(ctx, "d2-probes-coverage", coverage_row(ctx, "d2-probes", {"exam": "D2", "arm": arm["id"],
                                                                             "rubric_id": arm["rubric_id"]},
                                                          plan["texts"], all_types))
            prepared.append(plan)
        print(f"d2-probes: {len(args.judges)} judges x {len(prepared)} arms x {len(args.types)} probes x "
              f"{args.passes} passes", flush=True)
        judges: dict[str, tuple[Any, list]] = {}
        for k in range(args.pass_start, args.pass_start + args.passes):
            for judge_model in args.judges:
                if judge_model not in judges:
                    calls: list = []
                    judges[judge_model] = (make_judge(ctx, db, user_id, judge_model, calls), calls)
                ev, calls = judges[judge_model]
                ev.seed = SEED_BASE + k
                types = args.types_by_judge.get(judge_model, args.types)
                for plan in prepared:
                    arm = plan["arm"]
                    info = prepare_judge(ev, rubric=plan["rubric"], spec=plan["spec"], unit=arm["unit"],
                                         alternatives=arm["alternatives"], total_mode=args.total_mode,
                                         grade_scale=plan["grade_scale"])
                    config = {**plan["config"], "grade_scale_applied": info["grade_scale_applied"]}
                    context, ground_truth, data = plan_context(plan, task)
                    for ptype in types:
                        text, meta = plan["texts"][ptype]
                        base = {"judge": judge_model, "exam": "D2", "arm": arm["id"], "arm_config": config,
                                "task_id": task.id, "rubric_id": arm["rubric_id"], "probe": ptype,
                                "probe_valid": ptype not in INVALID_PROBES, "lane": "checklist",
                                "unit": arm["unit"], "pass": k, "probe_meta": meta}
                        if text is None:
                            write(ctx, "d2-probes", skipped_row(ctx, "d2-probes", base, ev.seed))
                            print(f"{judge_model} pass {k} {arm['id']} {ptype:18s}: skipped ({meta.get('skipped')})",
                                  flush=True)
                            continue
                        result = judged(ctx, "d2-probes", base, ev, calls, spec=plan["spec"], unit=arm["unit"],
                                        guard_on=plan["guard_on"], rubric_texts=plan["rubric_texts"],
                                        context=context, ground_truth=ground_truth, prediction=text, data=data)
                        print_row(ctx, f"{judge_model} pass {k} {arm['id']} {ptype}", result)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------

# Synthetic rubric and Gutachten for the selftest. Nothing here comes from
# the expert's sheet; his sheet is read from the git-ignored pack only.
SYNTHETIC_RUBRIC_TEXT = ("I. Anspruch aus § 433 II BGB (3 BE)\n"
                         "a) Art. 12 Abs. 1 S. 2 Nr. 3 lit. b GG (2 BE). Wirksamkeit, § 142 I BGB analog.\n"
                         "Rücktritt, §§ 323 ff. BGB")
SYNTHETIC_STEP_NAMES = ["Wirksamer Kaufvertrag", "Anfechtungserklärung des Verkäufers", "Rücktrittsrecht"]
SYNTHETIC_GUTACHTEN = (
    "Titel\n\n# A. Zulässigkeit\n\n## I. Rechtsweg\n\n" + "Der Rechtsweg ist eröffnet, weil die Norm "
    "öffentlich-rechtlich ist. " * 6 + "\n\n## II. Klageart\n\nDie Anfechtungsklage ist statthaft.\n\n"
    "# B. Begründetheit\n\n## I. Rechtsgrundlage\n\n" + "Die Rechtsgrundlage ist die Generalklausel; "
    "sie deckt die Maßnahme. " * 10 + "\n\nEin zweiter Absatz zur Rechtsgrundlage mit Subsumtion. " * 3
    + "\n\n## II. Formelle Rechtmäßigkeit\n\nDie Behörde war zuständig.\n\n## III. Materielle "
    "Rechtmäßigkeit\n\n" + "Die Maßnahme ist verhältnismäßig und ermessensfehlerfrei. " * 8
    + "\n\n# C. Ergebnis\n\nDie Klage ist zulässig und begründet.\n\nFußnoten\n\n[1] Beleg.")
SYNTHETIC_STEPS = [("Rechtsweg", 2.0), ("Statthafte Klageart", 3.0), ("Rechtsgrundlage Generalklausel", 5.0),
                   ("Formelle Rechtmäßigkeit Zuständigkeit", 4.0), ("Materielle Rechtmäßigkeit", 6.0)]


def phase_selftest(ctx: Ctx) -> int:
    import tempfile

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)
        if not ok:
            failures.append(name)

    exam = load_input(ctx, "heidebach_exam.json")
    phrases = L.load_canary_phrases(ctx.inp / "canary_phrases.json")
    sheet = exam["sheet"]

    # --- spec adapter on the expert sheet (counts and totals from the pack) ----
    spec = L.spec_from_sheet(sheet)
    total = sum(s["max_score"] for s in spec["steps"].values())
    check("adapter: one spec step per sheet step", len(spec["order"]) == len(sheet["step_keys"]), str(len(spec["order"])))
    check("adapter: the spec sums to the sheet total",
          abs(total - float(sheet["total_points"])) < 1e-9 and spec["total_points"] == float(sheet["total_points"]),
          str(total))
    check("adapter: order follows the outline", spec["order"] == list(sheet["step_keys"]))
    check("adapter: requirement lists are empty", all(s["anforderungen"] == [] for s in spec["steps"].values()))
    for state, info in (sheet.get("states") or {}).items():
        state_spec = L.spec_from_sheet(sheet, state)
        maxima_ok = all(abs(state_spec["steps"][k]["max_score"] - float(v)) < 1e-9 for k, v in info["step_maxima"].items())
        state_total = sum(s["max_score"] for s in state_spec["steps"].values())
        check(f"adapter: sheet state {state} uses its maxima and sums to its total",
              maxima_ok and abs(state_total - float(info["total_points"])) < 1e-9, str(state_total))
    check("sheet text: the current state renders like the sheet itself",
          "current" not in (sheet.get("states") or {}) or L.render_sheet_text(exam, "current") == L.render_sheet_text(exam))
    expected_top = {"version", "allocation_mode", "total_points", "order", "steps", "loesungsweg_steps",
                    "weichenstellungen", "arbeitsergebnisse", "hilfsgutachten"}
    expected_step = {"step_id", "name", "max_score", "anforderungen", "keine_punkte", "weichenstellung",
                     "arbeitsergebnis_id", "hilfsgutachten"}
    check("adapter: spec key layout (arbeitsergebnisse)", set(spec) == expected_top, str(sorted(set(spec) ^ expected_top)))
    check("adapter: step key layout (arbeitsergebnis_id)",
          all(set(s) == expected_step for s in spec["steps"].values()))
    try:  # the mounted extended module, with the arbeitsprodukt -> arbeitsergebnis rename normalised
        from benger_extended.workers import bewertungsbogen_checklist as ext

        rename = {"arbeitsprodukte": "arbeitsergebnisse", "arbeitsprodukt_id": "arbeitsergebnis_id"}
        doc = {"abschnitte": [{"id": "A1", "bezeichnung": "A", "schritte": [
            {"id": "S1", "bezeichnung": "Schritt", "max_punkte": 100, "anforderungen": [], "keine_punkte": "x"}]}]}
        ext_spec = ext.checklist_spec(doc, {"S1": "s01_schritt"})
        ext_top = {rename.get(k, k) for k in ext_spec}
        ext_step = {rename.get(k, k) for k in ext_spec["steps"]["s01_schritt"]}
        check("adapter: mirrors the mounted extended checklist_spec() keys",
              ext_top == expected_top and ext_step == expected_step,
              f"top {sorted(ext_top ^ expected_top)}, step {sorted(ext_step ^ expected_step)}")
    except ImportError as exc:
        print(f"SKIP  extended checklist_spec() comparison ({exc})")

    # rubric row with scrambled JSONB key order and a structure
    from rubric_structure import (
        criteria_from_structure,
        structure_from_flat_criteria,
        validate_grade_scale,
    )

    crit = {"s02_b": {"name": "B", "max_score": 40}, "s10_c": {"name": "C", "max_score": 10},
            "s01_a": {"name": "A", "max_score": 50}}
    scrambled = L.spec_from_rubric(crit, None, 100)
    check("adapter: flat criteria ordered by sNN ordinal", scrambled["order"] == ["s01_a", "s02_b", "s10_c"],
          str(scrambled["order"]))
    structure = structure_from_flat_criteria({"s01_a": crit["s01_a"], "s02_b": crit["s02_b"], "s10_c": crit["s10_c"]})
    structure["nodes"] = [structure["nodes"][2], structure["nodes"][0], structure["nodes"][1]]
    with_structure = L.spec_from_rubric(criteria_from_structure(structure), structure, 100)
    check("adapter: structure order wins", with_structure["order"] == ["s10_c", "s01_a", "s02_b"],
          str(with_structure["order"]))
    try:
        L.spec_from_rubric(crit, None, 90)
        check("adapter: total mismatch raises", False)
    except ValueError:
        check("adapter: total mismatch raises", True)

    # the judge accepts the spec: schema, and full marks give the sheet total
    try:
        from ml_evaluation import checklist_scoring as cs

        for unit in ("step", "rating"):
            schema = cs.build_schema(spec, unit, "branch")
            check(f"judge: schema for the {unit} unit covers every step",
                  set(schema["properties"]["scores"]["properties"]) == set(spec["order"]))
        parsed = {"scores": {k: {"score": s["max_score"], "evidence": "x", "abweichender_weg": False,
                                 "fehlplatziert": False, "reason": ""} for k, s in spec["steps"].items()},
                  "assessment_status": "scored", "supplementary_reviews": [], "work_products": [],
                  "error_chains": [], "review_reasons": [], "improvements": []}
        done = cs.finalize(parsed, spec, "step", "branch", "declared", lambda quote: True)
        check("judge: full marks on the adapted sheet give the sheet total",
              done.get("total_score") == float(sheet["total_points"]), str(done.get("total_score")))
        key = L.exam_grade_scale(exam["grade_scale"], sheet["total_points"])
        table, source = L.rating_table(key, sheet["total_points"])
        rating = {"scores": {k: {"model_note": 18} for k in spec["order"]}, "checklist": {}}
        mapped = L.model_total(rating, spec, "rating", grade_scale=key)
        check("model total: the rating unit maps notes through the grade key",
              source == "grade_key" and abs(mapped - sum(spec["steps"][k]["max_score"] for k in spec["order"])
                                            * table[18] / 100) < 1e-6, f"{mapped} via {source}")
        four = {"scores": {k: {"model_note": 4} for k in spec["order"]}, "checklist": {}}
        check("model total: 4 NP maps to the key's band, not to 4/18",
              abs(L.model_total(four, spec, "rating", grade_scale=key) - float(sheet["total_points"]) * 4 / 18) > 1)
    except ImportError as exc:
        print(f"SKIP  judge integration ({exc})")

    # rendered sheet: the mirror text minus its Notenschlüssel block
    rendered = L.render_sheet_text(exam)
    mirror = exam.get("bewertungsbogen_text") or ""
    check("sheet text: rendered from the structure equals the mirror without its grade block",
          mirror.startswith(rendered) and "NOTENSCHLÜSSEL" in mirror[len(rendered):] and "NOTENSCHLÜSSEL" not in rendered)
    import re as _re

    check("sheet text: keys match the spec", _re.findall(r"\[Schlüssel: ([^\]]+)\]", rendered) == spec["order"])
    scale = L.exam_grade_scale(exam["grade_scale"], sheet["total_points"])
    check("grade key: the exam's key is a valid platform scale", not validate_grade_scale(scale), json.dumps(scale))

    # --- cleaned pack texts ------------------------------------------------------
    for name in ("sachverhalt", "musterloesung"):
        meta = (exam.get("texts") or {}).get(name) or {}
        check(f"pack: the {name} matches its stored sha256 and has no Markdown escapes",
              meta.get("sha256") == L.sha256_text(exam[name]) and not _re.search(r"\\[.()\-\[\]]", exam[name]))

    # --- negation flip -------------------------------------------------------
    para = ("Die Klage ist zulässig. Sie ist jedoch nicht begründet. Ein Mangel liegt vor. "
            "Ein Anspruch besteht nicht. Fraglich ist, ob der Vertrag wirksam war. "
            "Es besteht kein Rücktrittsrecht. Somit ist festzuhalten, dass keine Pflichtverletzung vorliegt. "
            "Anspruch (+). Verzug (-). "
            "Der Käufer ist in seinem Eigentum aus § 903 BGB verletzt.")
    want = ("Die Klage ist nicht zulässig. Sie ist jedoch begründet. Ein Mangel liegt nicht vor. "
            "Ein Anspruch besteht. Fraglich ist, ob der Vertrag wirksam war. "
            "Es besteht ein Rücktrittsrecht. Somit ist festzuhalten, dass eine Pflichtverletzung vorliegt. "
            "Anspruch (-). Verzug (+). "
            "Der Käufer ist in seinem Eigentum aus § 903 BGB nicht verletzt.")
    flipped, sentences, flips = L.negation_flip(para)
    check("negation flip: synthetic paragraph", flipped == want, flipped if flipped != want else "")
    check("negation flip: 9 of 10 sentences flipped, the question stays", sentences == 9 and flips == 9,
          f"{sentences} sentences, {flips} flips")
    simple = "Die Klage ist zulässig. Ein Mangel liegt nicht vor. Ein Anspruch besteht. Verzug (+)."
    check("negation flip: twice gives the original back", L.negation_flip(L.negation_flip(simple)[0])[0] == simple)
    check("negation flip: deterministic", L.negation_flip(para) == (flipped, sentences, flips))
    ml_flips = L.negation_flip(exam["musterloesung"])[1]
    check("negation flip: the cleaned Musterlösung has enough flips", ml_flips >= MIN_NEGATION_FLIPS, str(ml_flips))
    check("result swap: marked invalid and out of the default battery",
          "result_swap" in INVALID_PROBES and "result_swap" not in DEFAULT_PROBES)

    # --- section ablation, misplacement, injection, same area ---------------
    ablated, meta = L.section_ablation(SYNTHETIC_GUTACHTEN, SYNTHETIC_STEPS)
    check("section ablation: removes the Zulässigkeit section, expects the BE of its steps",
          ablated is not None and meta["section"] == "A. Zulässigkeit" and meta["expected_drop"] == 5.0
          and "Rechtsweg ist eröffnet" not in ablated and "Rechtsgrundlage" in ablated and "Fußnoten" in ablated,
          json.dumps({k: v for k, v in meta.items() if k != "sha256"}, ensure_ascii=False))
    moved, meta = L.misplacement(SYNTHETIC_GUTACHTEN)
    check("misplacement: moves the longest paragraph under the sibling heading, text unchanged otherwise",
          moved is not None and meta["from"] == "I. Rechtsgrundlage" and meta["to"] == "II. Formelle Rechtmäßigkeit"
          and sorted(moved.split()) == sorted(SYNTHETIC_GUTACHTEN.split())
          and moved.index("Die Rechtsgrundlage ist die Generalklausel") > moved.index("## II. Formelle"),
          json.dumps({k: v for k, v in meta.items() if k != "sha256"}, ensure_ascii=False))
    flat_ml, flat_meta = L.section_ablation("ein Text ohne Überschriften " * 50, SYNTHETIC_STEPS)
    check("section ablation: skipped without Markdown sections", flat_ml is None and "skipped" in flat_meta)
    injected, _ = L.injection("Off-topic Lösung.")
    check("injection: the instruction is appended", injected.endswith(L.INJECTION_TEXT))
    pick, _ = L.closest_text("Rechtsweg Klageart Generalklausel", {1: "Kaufvertrag Rücktritt", 2: "Rechtsweg Klageart"})
    check("same area: the closest Musterlösung is chosen", pick == 2)
    ml_sections = L.md_sections(exam["musterloesung"])
    real, real_meta = L.section_ablation(exam["musterloesung"], primary_steps(spec, None))
    check("section ablation: the cleaned Musterlösung has labelled sections and an ablation target",
          len(ml_sections) >= 5 and real is not None and 0 < real_meta["expected_drop"] < float(sheet["total_points"]),
          f"{len(ml_sections)} sections, expected drop {real_meta.get('expected_drop')}")

    # --- keyword salad (synthetic rubric) ------------------------------------------
    salad, _ = L.keyword_salad(SYNTHETIC_RUBRIC_TEXT, SYNTHETIC_STEP_NAMES, "exam-1")
    items = salad.splitlines()
    check("keyword salad: norms extracted",
          {"§ 433 II BGB", "Art. 12 Abs. 1 S. 2 Nr. 3 lit. b GG", "§ 142 I BGB", "§§ 323 ff. BGB"} <= set(items),
          str(items))
    check("keyword salad: key terms of 8+ characters",
          {"Kaufvertrag", "Anfechtungserklärung", "Verkäufers", "Rücktrittsrecht"} <= set(items) and "Wirksamer" in items)
    check("keyword salad: no sentences, only norms and single terms",
          all(L.NORM_RE.fullmatch(i) or L.KEY_TERM_RE.fullmatch(i) for i in items), str(items))
    check("keyword salad: deterministic, seed-dependent order",
          L.keyword_salad(SYNTHETIC_RUBRIC_TEXT, SYNTHETIC_STEP_NAMES, "exam-1")[0] == salad
          and sorted(L.keyword_salad(SYNTHETIC_RUBRIC_TEXT, SYNTHETIC_STEP_NAMES, "exam-2")[0].splitlines()) == sorted(items))
    _, sheet_meta = L.keyword_salad(rendered, [spec["steps"][k]["name"] for k in spec["order"]], "expert")
    check("keyword salad: the expert sheet yields norms and terms", sheet_meta["norms"] >= 5 and sheet_meta["terms"] >= 10,
          json.dumps(sheet_meta))

    # --- canaries (reported by index, never by text) ------------------------------
    case = L.norm_text(exam["sachverhalt"]) + "\n" + L.norm_text(exam["musterloesung"])
    present = [i for i, p in enumerate(phrases) if L.norm_text(p) in case]
    check(f"canaries: {len(phrases)} sheet phrases, none in the Sachverhalt or the Musterlösung",
          len(phrases) >= 10 and not present, f"present: phrase indices {present}" if present else "")
    missing = [i for i, p in enumerate(phrases) if L.norm_text(p) not in L.norm_text(mirror)]
    check("canaries: every phrase occurs in the expert sheet", not missing,
          f"missing: phrase indices {missing}" if missing else "")
    in_case = [i for i, t in enumerate(L.FIXED_CANARIES) if L.norm_text(t) in case]
    print(f"INFO  fixed canary terms (by index) that occur in the case text, hence removed before the check: {in_case}")

    guard = L.CanaryGuard(phrases)
    ml, sv, answer = exam["musterloesung"], exam["sachverhalt"], "Die Klage ist zulässig und begründet. " * 3
    rubric_lines = [f"Schritt 3: {L.FIXED_CANARIES[1]} (2 BE)", f"Schritt 4: {phrases[1]} (1 BE)"]
    guard.arm("selftest", case_texts=[sv, ml, answer], rubric_texts=rubric_lines)
    clean_prompt = f"SACHVERHALT:\n<sachverhalt>\n{sv}\n</sachverhalt>\nMUSTERLÖSUNG:\n{ml}\nBEARBEITUNG:\n{answer}"

    def raises(system: str, prompt: str) -> str | None:
        try:
            guard.check(system, prompt)
            return None
        except L.LeakageDetected as exc:
            return str(exc)

    check("guard: case text, answer and rubric terms pass",
          raises("Bewerte fair.", clean_prompt + "\n" + rubric_lines[0]) is None)
    message = raises(f"Etwa ein Argument zur {L.FIXED_CANARIES[1]}.", clean_prompt)
    check("guard: a fixed term in the system prompt raises, naming its index only",
          message is not None and "fixed term #" in message and L.FIXED_CANARIES[1] not in message)
    check("guard: ss spelling is caught too", raises(f"Zur {L.FIXED_CANARIES[2]}.", clean_prompt) is not None)
    message = raises("Bewerte fair.", clean_prompt + "\n" + phrases[0])
    check("guard: a sheet phrase in the user prompt raises, naming its index only",
          message is not None and "sheet phrase #0" in message and phrases[0] not in message)
    check("guard: a sheet phrase inside the rubric under test raises",
          raises("Bewerte fair.", clean_prompt + "\n" + rubric_lines[1]) is not None)
    check("guard: the generator's correction block is not scanned",
          raises("Bewerte fair.", clean_prompt + L.CORRECTION_MARKER + "\nVORHERIGES DOKUMENT: " + L.FIXED_CANARIES[0]) is None)
    guard.disarm()
    check("guard: disarmed guard never raises", raises(L.FIXED_CANARIES[1], phrases[0]) is None)
    check("guard: LeakageDetected escapes except Exception", not issubclass(L.LeakageDetected, Exception))
    stripped = L.strip_task_data({"Sachverhalt": 1, "Bewertungsbogen": 2, "korrekturhinweise": 3, "exemplar_rubrics": 4})
    check("strip: sheet, hints and exemplars removed case-insensitively", stripped == {"Sachverhalt": 1})

    # --- script selection and per-year case texts (synthetic scripts) ------------
    fake = [{"script_id": "H01", "cohort": "D2a", "case_year": "2025"},
            {"script_id": "H02", "cohort": "D2a", "case_year": "2024", "exclude_reason": "duplicate"},
            {"script_id": "B01", "cohort": "D2b", "case_year": "2026"}]
    check("scripts: default is D2a minus exclusions", [s["script_id"] for s in L.select_scripts(fake, None)] == ["H01"])
    check("scripts: cohort tokens expand", [s["script_id"] for s in L.select_scripts(fake, ["D2b", "H01"])] == ["B01", "H01"])
    try:
        L.select_scripts(fake, ["H02"])
        check("scripts: an excluded script is refused", False)
    except ValueError:
        check("scripts: an excluded script is refused", True)
    years = {"case_texts": {"2026": {"sachverhalt": "S26"}}, "sachverhalt": "S26"}
    check("case text: the script's year when present, else the platform text flagged",
          L.case_text_for(years, fake[2]) == ("S26", "2026", False)
          and L.case_text_for(years, fake[0]) == ("S26", "2026", True))

    # --- ledger and metering -------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        ledger = L.Ledger(Path(tmp) / "ledger.json", cap=1.0, prices={"m": (1.0, 2.0), "free": (None, None)})
        try:
            ledger.price("unknown-model")
            check("ledger: unpriced model raises", False)
        except L.PriceMissing:
            check("ledger: unpriced model raises", True)

        class Service:
            def generate(self, **kwargs):
                raise RuntimeError("socket closed")

            def ok(self, **kwargs):
                return {"success": True, "usage": {"prompt_tokens": 1000, "completion_tokens": 500}}

            def retried(self, **kwargs):
                return {"success": True, "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
                        "metadata": {"retry_count": 2, "retry_attempts": [{"attempt": 1}, {"attempt": 2}]}}

            def failed(self, **kwargs):
                return {"success": False, "error": "HTTP 500", "usage": {}, "metadata": {"error_type": "server"}}

        calls: list = []
        service = Service()
        saved = os.environ.pop("PILOT_DRY_RUN", None)
        try:
            L.meter(service, "generate", "m", ledger, calls)
            try:
                service.generate(prompt="p", system_prompt="s")
                check("ledger: a raising call re-raises", False)
            except RuntimeError:
                check("ledger: a raising call re-raises", True)
            check("ledger: a raising call is charged the reserve",
                  abs(ledger.state["spent"] - ledger.reserve("m")) < 1e-9 and calls[-1].get("reserve_charged"))
            L.meter(service, "ok", "m", ledger, calls)
            L.meter(service, "ok", "m", ledger, calls)  # re-wrapping must not meter twice
            before = ledger.state["spent"]
            service.ok(prompt="p")
            check("ledger: usage priced once", abs(ledger.state["spent"] - before - 0.002) < 1e-9,
                  f"{ledger.state['spent'] - before:.6f}")
            L.meter(service, "retried", "m", ledger, calls)
            before = ledger.state["spent"]
            service.retried(prompt="p")
            check("ledger: provider-internal retries are charged the reserve each",
                  abs(ledger.state["spent"] - before - 0.002 - 2 * ledger.reserve("m")) < 1e-9,
                  f"{ledger.state['spent'] - before:.4f}")
            L.meter(service, "failed", "m", ledger, calls)
            before = ledger.state["spent"]
            service.failed(prompt="p")
            check("ledger: a failure without usage is charged the reserve",
                  abs(ledger.state["spent"] - before - ledger.reserve("m")) < 1e-9)
            usage_attempts = {"success": True, "usage": {"prompt_tokens": 10, "completion_tokens": 0},
                              "metadata": {"retry_attempts": [{"usage": {"prompt_tokens": 1000, "completion_tokens": 0}}]}}
            before = ledger.state["spent"]
            booked = L.charge_response(ledger, "m", usage_attempts)
            check("ledger: a retry attempt with usage is priced by its usage",
                  booked["reserves_charged"] == 0 and abs(ledger.state["spent"] - before - 0.00101) < 1e-9)
            os.environ["PILOT_DRY_RUN"] = "1"
            before = ledger.state["spent"]
            response = service.ok(prompt="p")
            check("ledger: dry run spends nothing", ledger.state["spent"] == before and response.get("error") == "dry run")
            unpriced: list = []
            L.meter(service, "ok", "free", ledger, unpriced)
            try:
                service.ok(prompt="p")
                check("ledger: unpriced model raises before the call, also in a dry run", False)
            except L.PriceMissing:
                check("ledger: unpriced model raises before the call, also in a dry run", not unpriced)
            os.environ.pop("PILOT_DRY_RUN", None)
            ledger.cap = ledger.state["spent"] + 0.01
            try:
                L.meter(service, "ok", "m", ledger, calls)
                service.ok(prompt="p")
                check("ledger: cap stops the call", False)
            except L.BudgetExceeded:
                check("ledger: cap stops the call", True)
        finally:
            os.environ.pop("PILOT_DRY_RUN", None)
            if saved is not None:
                os.environ["PILOT_DRY_RUN"] = saved

    # --- arms ---------------------------------------------------------------
    arm = L.parse_arm("rubric:abc:step:replace")
    check("arms: rubric arm with replace", arm["rubric_id"] == "abc" and arm["alternatives"] == "replace")
    try:
        L.parse_arm("rubric:abc:bullet:replace")
        check("arms: bullet with replace is rejected", False)
    except ValueError:
        check("arms: bullet with replace is rejected", True)

    print(f"\nselftest: {'FAILED ' + str(len(failures)) if failures else 'all passed'}", flush=True)
    return 1 if failures else 0


# ---------------------------------------------------------------------------


def parse_args(argv: list[str]):
    parser = argparse.ArgumentParser(description="Checklist pilot runner (see the module docstring).")
    parser.add_argument("phase", choices=PHASES)
    parser.add_argument("--work", default="/tmp/pilot", help="container work dir (in/, out/, ledger.json)")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--cap", type=float, default=None, help="cumulative spend ceiling in USD (required for paid runs)")
    parser.add_argument("--org", default=os.environ.get("PILOT_ORG") or None,
                        help="organisation whose API keys pay (pilot.sh passes org_id from the local config)")
    # provenance passed in by pilot.sh
    parser.add_argument("--platform-sha", default=None)
    parser.add_argument("--platform-mounted-sha", default=None)
    parser.add_argument("--extended-sha", default=None)
    parser.add_argument("--runner-sha256", default=None)
    # judges and passes
    parser.add_argument("--judges", nargs="*", default=["gpt-5.6-luna", "deepseek-ai/DeepSeek-V4-Pro"])
    parser.add_argument("--passes", type=int, default=1)
    parser.add_argument("--pass-start", type=int, default=0, help="first pass index (seed = 42 + index)")
    parser.add_argument("--total-mode", default="declared", choices=("declared", "best"))
    parser.add_argument("--alternatives", default="branch", choices=("branch", "replace"))
    # probes
    parser.add_argument("--lane", default="product", choices=("product", "checklist"))
    parser.add_argument("--unit", default="bullet", choices=("bullet", "step", "rating"))
    parser.add_argument("--rubric", nargs="*", default=None,
                        help="policy (active | checklist-latest[:<generator>]) and/or EXAM=RUBRIC_ID overrides")
    parser.add_argument("--types", nargs="*", default=list(DEFAULT_PROBES),
                        help=f"probe types (default: {' '.join(DEFAULT_PROBES)}; result_swap is invalid)")
    parser.add_argument("--ds-types", nargs="*", default=None, help="probe types for DeepSeek (default: --types)")
    parser.add_argument("--exams", nargs="*", type=int, default=None)
    parser.add_argument("--limit-exams", type=int, default=None)
    parser.add_argument("--same-area-exam", type=int, default=None,
                        help="d2-probes: the D1 exam for same_area_offtopic (default: the closest public-law one)")
    # generation
    parser.add_argument("--generators", nargs="*", default=["gpt-5.4-mini", "gpt-5.4"])
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--task")
    parser.add_argument("--allocation-mode", default="flat")
    # checklist (D1 picks)
    parser.add_argument("--rubric-id", help="checklist phase: the generated rubric to judge against")
    parser.add_argument("--units", nargs="*", default=["bullet"])
    parser.add_argument("--picks", nargs="*", default=["P02", "P03"])
    # D2
    parser.add_argument("--arms", nargs="*", default=[])
    parser.add_argument("--scripts", nargs="*", default=None,
                        help="script ids and/or cohorts D2a, D2b (default: D2a minus exclusions)")
    parser.add_argument("--force-update", action="store_true", help="d2-setup: overwrite a changed D2 task")
    args = parser.parse_args(argv)
    args.run_id = args.run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    args.types_by_judge = {"deepseek-ai/DeepSeek-V4-Pro": args.ds_types} if args.ds_types else {}
    unknown = [t for t in args.types + (args.ds_types or []) if t not in PROBE_TYPES]
    if unknown:
        parser.error(f"unknown probe types {unknown}")
    for t in sorted({t for t in args.types + (args.ds_types or []) if t in INVALID_PROBES}):
        print(f"WARNING probe type {t} is {INVALID_PROBES[t]}; its rows carry probe_valid false", flush=True)
    policies = [r for r in (args.rubric or []) if "=" not in r]
    if len(policies) > 1:
        parser.error("--rubric takes at most one policy")
    default_policy = "checklist-latest" if args.lane == "checklist" and args.unit == "bullet" else "active"
    args.rubric_policy = policies[0] if policies else default_policy
    args.rubric_map = {int(r.split("=", 1)[0]): r.split("=", 1)[1] for r in (args.rubric or []) if "=" in r}
    if args.passes < 1:
        parser.error("--passes must be at least 1")
    return args


def setup_paths(work: Path) -> None:
    paths = [p for p in ("/shared", "/app") if Path(p).is_dir()]
    here = Path(__file__).resolve().parent if __file__ and Path(__file__).is_file() else None
    if here is not None:  # host runs (selftest): the repo's own service dirs
        repo = here.parents[3]
        paths += [str(repo / "services" / "shared"), str(repo / "services" / "workers")]
    lib_dirs = [str(work / "in")] + ([str(here)] if here is not None else [])
    sys.path[:0] = lib_dirs + paths


def interrupt_on_term(signum, _frame):
    raise KeyboardInterrupt(f"signal {signum}")


def main() -> int:
    global L
    args = parse_args(sys.argv[1:])
    work = Path(args.work)
    setup_paths(work)
    import pilot_lib

    L = pilot_lib
    dry_run = os.environ.get("PILOT_DRY_RUN") == "1"
    canary_mode = os.environ.get("PILOT_CANARY", "raise") or "raise"
    if canary_mode == "warn" and not dry_run:
        print("PILOT_CANARY=warn is only allowed together with PILOT_DRY_RUN=1", flush=True)
        return 2
    if args.phase in SPENDING_PHASES and not dry_run and args.cap is None:
        print(f"{args.phase} spends money: pass --cap (cumulative USD ceiling)", flush=True)
        return 2
    work.mkdir(parents=True, exist_ok=True)
    # pilot.sh stops the run by this pid; SIGTERM ends it like Ctrl-C does.
    (work / "pid").write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, interrupt_on_term)

    files = instrument_hashes()
    missing = sorted(k for k, v in files.items() if v is None)
    if missing:
        print(f"WARNING instrument files not found on the import path: {missing}", flush=True)
    provenance = {
        "code_version": L.code_version(files),
        "files": files,
        "validator_sha256": files.get(VALIDATOR_FILE),
        "runner_sha256": args.runner_sha256,
        "lib_sha256": L.sha256_file(pilot_lib.__file__),
        "git": {"platform": args.platform_sha, "platform_mounted": args.platform_mounted_sha,
                "extended": args.extended_sha},
        "run_id": args.run_id,
        "dry_run": dry_run,
    }
    print(f"run {args.run_id} phase {args.phase}  code_version {provenance['code_version']}"
          f"{'  DRY RUN' if dry_run else ''}", flush=True)

    if args.phase == "selftest":
        ctx = Ctx(args, None, None, provenance)
        return phase_selftest(ctx)

    ledger = L.Ledger(work / "ledger.json", cap=args.cap)
    guard = None
    if args.phase in SPENDING_PHASES:
        canaries = work / "in" / "canary_phrases.json"
        if not canaries.exists():
            print(f"{canaries} missing: the leakage guard fails closed", flush=True)
            return 2
        guard = L.CanaryGuard(L.load_canary_phrases(canaries), mode=canary_mode)
    ctx = Ctx(args, ledger, guard, provenance)
    started = now()
    status, rc = "ok", 0
    try:
        if args.phase == "ledger":
            print(json.dumps(ledger.state, indent=1))
        elif args.phase == "probes":
            phase_probes(ctx)
        elif args.phase == "generate":
            phase_generate(ctx)
        elif args.phase == "checklist":
            if not args.rubric_id:
                raise SystemExit("checklist needs --rubric-id")
            phase_checklist(ctx)
        elif args.phase == "d2-setup":
            phase_d2_setup(ctx)
        elif args.phase == "d2-generate":
            phase_d2_generate(ctx)
        elif args.phase == "d2-judge":
            phase_d2_judge(ctx)
        elif args.phase == "d2-probes":
            phase_d2_probes(ctx)
    except L.BudgetExceeded as exc:
        status, rc = f"budget stop: {exc}", 3
    except L.ProviderBlocked as exc:
        status, rc = f"provider stop: {exc}", 4
    except L.PriceMissing as exc:
        status, rc = f"price missing: {exc}", 5
    except L.LeakageDetected as exc:
        status, rc = f"LEAKAGE: {exc}", 6
    except KeyboardInterrupt as exc:
        status, rc = f"interrupted ({str(exc) or 'SIGINT'})", 130
    except SystemExit as exc:
        status, rc = f"stopped: {exc}", 2
    except BaseException as exc:
        status, rc = f"error: {type(exc).__name__}: {str(exc)[:300]}", 1
        raise
    finally:
        print(f"STOP ({rc}): {status}" if rc else "done", flush=True)
        if args.phase != "ledger":
            ledger.record_run({
                "run_id": args.run_id, "phase": args.phase, "started": started, "ended": now(), "status": status[:500],
                "cap": args.cap, "dry_run": dry_run, "spent_before": ledger.start_spent,
                "spent_after": ledger.state["spent"], "added": ledger.added(),
                "code_version": provenance["code_version"], "git": provenance["git"],
                "canary_warnings": len(guard.warnings) if guard else 0,
            })
        print("LEDGER " + json.dumps({"spent": round(ledger.state["spent"], 5), "added": round(ledger.added(), 5),
                                      "calls": ledger.state["calls"]}), flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

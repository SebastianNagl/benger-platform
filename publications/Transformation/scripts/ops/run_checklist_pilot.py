#!/usr/bin/env python3
"""Pilot runner for the checklist instrument (P1 probes, P2 human study D2).

Runs INSIDE the local dev worker container, so every call goes through the
product's own judge and generator code. Always start it through the host
wrapper, which seeds and saves the ledger, copies inputs and outputs, records
the git SHAs and deletes the copied data afterwards:

    scripts/ops/pilot.sh <phase> [options]

Phases
  selftest     pure checks without database or provider: spec adapter on
               Martin's sheet, negation flip, keyword salad, canary phrases,
               leakage guard, ledger.
  probes       the probe battery (empty, repetition, offtopic, musterloesung,
               negation_flip, keyword_salad) on the product lane (--lane
               product) or the checklist lane (--lane checklist --unit ...),
               against one rubric per exam (--rubric).
  generate     checklist Bewertungsbögen for one D1 task (--task), stored as
               candidate rubrics on the research clone.
  checklist    checklist judgments of D1 picks against a generated rubric.
  d2-setup     the research Task for Martin's exam on the research clone
               (idempotent; case text only, no sheet, no hints, no exemplars).
  d2-generate  checklist rubrics for the D2 task (--generators, --samples).
  d2-judge     judges x arms x scripts x passes on the D2 scripts. Arms:
               martin:<step|rating>[:<alt>], rubric:<id>:<unit>[:<alt>].
  ledger       print the ledger.

Integrity
  - Every provider call is metered: catalog price required, spend cap
    checked before dispatch (--cap is the cumulative ceiling), a call that
    raises is charged the model's reserve. PILOT_DRY_RUN=1 stops each call
    before the provider with a dry-run failure and spends nothing.
  - Leakage guard: every generator prompt and every judge prompt of a
    non-Martin arm is checked for the D2 canary terms before it is sent
    (pilot_lib.CanaryGuard). A hit raises LeakageDetected. PILOT_CANARY=warn
    downgrades that to a warning, and only in a dry run.
  - Pass k uses seed 42 + k. Every judge row stores the full finalized
    result, the raw model output, usage, latency, arm and provenance (git
    SHAs, content hashes of the instrument files, prompt hashes).

Outputs: one JSON line per judgment or generation in <work>/out/<phase>.jsonl.
The wrapper appends them to data/interim/pilot/ (D1) or
data/interim/human/pilot/ (D2). Local dev stack only.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

CLONE_PROJECT = "81e474b8-d226-4bf8-bc2e-fb744d25cba5"
RESEARCH_USER_EMAIL = "research-ops@example.com"
# Spend goes to this organisation's keys (org-pays; the research user is a
# superadmin, which the org-key gate accepts). Local dev stack only.
DEFAULT_ORG = "<org-id>"  # TUM
CHECKLIST_PROMPT_KEY = "bewertungsbogen_checklist"
CHECKLIST_PROMPT_FILE = "/app/benger_extended/workers/rubric_prompt_checklist.json"
# The instrument: judge rules, evidence verifier, generator contract, generator
# prompt. Their content hashes make up the code version the gate filters on.
INSTRUMENT_FILES = (
    "/app/ml_evaluation/checklist_scoring.py",
    "/app/ml_evaluation/llm_judge_evaluator.py",
    "/app/benger_extended/workers/bewertungsbogen_checklist.py",
    "/app/benger_extended/workers/rubric_prompt_checklist.json",
)
D2_MARKER = "heidebach_polr_2026"
# Same values as the D1 tasks on the clone, so the generator prompt is built
# the same way for both corpora.
D2_TASK_FIELDS = {"rechtsordnung": "Deutschland", "rechtsstand": "nicht angegeben",
                  "pruefungsniveau": "Universitäre juristische Klausur"}
PROBE_TYPES = ("empty", "repetition", "offtopic", "musterloesung", "negation_flip", "keyword_salad", "result_swap")
MIN_NEGATION_FLIPS = 3
MIN_RESULT_SWAPS = 8  # G0' amendment: fewer swapped results make the probe invalid
SEED_BASE = 42
ROW_SCHEMA = 2
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
    ev = create_llm_judge_for_user(
        db, user_id, get_provider_from_model(judge_model), judge_model,
        temperature=temperature, max_tokens=32000,
        custom_prompt_template=DEFAULT_GRADING_PROMPT_TEMPLATE,
        organization_id=ctx.args.org,
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
                # TODO(clfix-judge): configure_checklist(grade_scale=...) lands with
                # the review-round judge work. Until then the rating unit's
                # BE-equivalent uses the judge's default key; the row says so.
                info["grade_scale_applied"] = False
        ev.configure_checklist(spec, unit, alternatives, total_mode, **kwargs)
    return info


def judge_inputs(task_data: dict[str, Any], rendered: str) -> tuple[str, str, dict[str, Any]]:
    """(context, Musterlösung, task data) for one judgment.

    Sheet, grading hints and exemplar rubrics are stripped from the task data
    for every arm; the rubric under test is bound as ``bewertungsbogen``.
    """
    import tasks
    from evaluation.cell_evaluator import _build_judge_context

    data = L.strip_task_data(task_data)
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
            row["model_total"] = L.model_total(result, spec, unit)
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


# ---------------------------------------------------------------------------
# probes
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
    """The G0' amendment probe: every result statement of the Musterlösung swapped."""
    swapped, n, pairs = L.result_swap(musterloesung)
    meta = {"swapped_sentences": n, "sha256": L.sha256_text(swapped)}
    if n < MIN_RESULT_SWAPS:
        return None, {**meta, "skipped": f"only {n} result sentences swapped (< {MIN_RESULT_SWAPS})"}
    return swapped, meta

def probe_texts(exam: dict[str, Any], rubric_text: str, step_names: list[str], rubric_id: str):
    """{type: (text or None, meta)}; None means the probe is skipped for this exam."""
    out: dict[str, tuple[str | None, dict[str, Any]]] = {}
    given = exam.get("probes") or {}
    for ptype in ("empty", "repetition", "offtopic", "musterloesung"):
        out[ptype] = (given[ptype], {}) if isinstance(given.get(ptype), str) else (None, {"skipped": "not in probe_texts.json"})
    musterloesung = given.get("musterloesung") or ""
    flipped, sentences, flips = L.negation_flip(musterloesung)
    meta = {"flipped_sentences": sentences, "flips": flips}
    if sentences < MIN_NEGATION_FLIPS:
        meta["skipped"] = f"only {sentences} sentences flipped (< {MIN_NEGATION_FLIPS})"
        out["negation_flip"] = (None, meta)
    else:
        out["negation_flip"] = (flipped, meta)
    salad, salad_meta = L.keyword_salad(rubric_text, step_names, seed_key=f"{exam['exam_inner_id']}:{rubric_id}")
    out["keyword_salad"] = (salad, salad_meta) if salad else (None, {**salad_meta, "skipped": "no norms or key terms"})
    out["result_swap"] = result_swap_probe(musterloesung)
    return out


def phase_probes(ctx: Ctx) -> None:
    from project_models import Task

    args = ctx.args
    probes = load_input(ctx, "probe_texts.json")
    actives = load_input(ctx, "clone_d6_actives.json")
    lane, unit = args.lane, (args.unit if args.lane == "checklist" else None)
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
            names = ([spec["steps"][k].get("name") for k in spec["order"]] if spec
                     else [c.get("name") for c in (rubric.criteria or {}).values() if isinstance(c, dict)])
            plans.append({
                "exam": exam, "task": task, "rubric": rubric, "spec": spec, "context": context,
                "ground_truth": ground_truth, "data": data,
                "rubric_texts": L.guard_rubric_texts(text, spec, rubric.criteria),
                "texts": probe_texts(exam, text, names, rubric.id),
                "arm": {"lane": lane, "unit": unit, "alternatives": args.alternatives if lane == "checklist" else None,
                        "total_mode": args.total_mode if lane == "checklist" else None,
                        "rubric_policy": args.rubric_policy, "spec_source": spec_source, "rendered": text_source,
                        "spec_sha256": L.sha256_text(json.dumps(spec, sort_keys=True)) if spec else None},
            })
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
                                "rubric_id": plan["rubric"].id, "probe": ptype, "lane": lane, "unit": unit,
                                "pass": k, "arm_config": plan["arm"], "probe_meta": meta}
                        if text is None:
                            write(ctx, "probes", {"schema": ROW_SCHEMA, "run_id": ctx.run_id, "ts": now(),
                                                  "phase": "probes", **base, "seed": ev.seed, "skipped": True,
                                                  "total": None, "error": None, "provenance": ctx.provenance})
                            print(f"{judge_model} pass {k} exam {exam_id:>3} {ptype:13s}: skipped ({meta.get('skipped')})", flush=True)
                            continue
                        result = judged(ctx, "probes", base, ev, calls, spec=plan["spec"], unit=unit, guard_on=True,
                                        rubric_texts=plan["rubric_texts"], context=plan["context"],
                                        ground_truth=plan["ground_truth"], prediction=text, data=plan["data"])
                        print_row(ctx, f"{judge_model} pass {k} exam {exam_id:>3} {ptype:13s}", result)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# generation (D1 and D2)
# ---------------------------------------------------------------------------


def install_checklist_prompt(db) -> str:
    """Install the mounted generator prompt on the clone; returns its hash."""
    from project_models import Project
    from sqlalchemy.orm.attributes import flag_modified

    raw = Path(CHECKLIST_PROMPT_FILE).read_text(encoding="utf-8")
    project = db.query(Project).filter(Project.id == CLONE_PROJECT).one()
    config = dict(project.generation_config or {})
    structures = dict(config.get("prompt_structures") or {})
    structures[CHECKLIST_PROMPT_KEY] = json.loads(raw)
    config["prompt_structures"] = structures
    project.generation_config = config
    flag_modified(project, "generation_config")
    db.commit()
    return L.sha256_text(raw)


def case_texts_of(data: dict[str, Any]) -> list[str]:
    import tasks

    return [str(tasks._get_insensitive(data or {}, key) or "")
            for key in ("sachverhalt", "musterlösung", "musterloesung")]


def run_generation(ctx: Ctx, phase: str, user_id: str, task, generator: str, sample: int) -> dict[str, Any] | None:
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
        out = generate_bewertungsbogen_impl(
            None, CLONE_PROJECT, task.id, user_id, organization_id=args.org, generator_model_id=generator,
            prompt_key=CHECKLIST_PROMPT_KEY, activate_if_first=False,
            rubric_contract="checklist", allocation_mode=args.allocation_mode,
        )
        if out.get("status") == "completed" and out.get("rubric_id"):
            extra = rubric_generation_facts(out["rubric_id"])
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
            "generator": generator, "task_id": task.id, "sample": sample, "allocation_mode": args.allocation_mode,
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


def rubric_generation_facts(rubric_id: str) -> dict[str, Any]:
    from project_models import TaskRubric

    db = open_db()
    try:
        rubric = db.query(TaskRubric).filter(TaskRubric.id == rubric_id).one()
        meta = rubric.generation_metadata or {}
        return {"prompt_version": rubric.prompt_version, "contract_version": meta.get("contract_version"),
                "attempts": meta.get("attempts"), "attempt_errors": meta.get("attempt_errors") or [],
                "hinweise": meta.get("hinweise"), "steps": len(rubric.criteria or {}),
                "spec_sha256": L.sha256_text(json.dumps(meta.get("checklist_spec"), sort_keys=True))}
    finally:
        db.close()


def phase_generate(ctx: Ctx) -> None:
    from project_models import Task

    if not ctx.args.task:
        raise SystemExit("generate needs --task")
    db = open_db()
    try:
        user_id = research_user_id(db)
        install_checklist_prompt(db)
        task = db.query(Task).filter(Task.id == ctx.args.task).one()
    finally:
        db.close()
    for generator in ctx.args.generators:
        for sample in range(ctx.args.samples):
            run_generation(ctx, "generate", user_id, task, generator, sample)


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
# D2: Martin's exam
# ---------------------------------------------------------------------------


def find_d2_task(db):
    from project_models import Task

    for task in db.query(Task).filter(Task.project_id == CLONE_PROJECT).all():
        research = (task.meta or {}).get("research") if isinstance(task.meta, dict) else None
        if isinstance(research, dict) and research.get("d2_exam") == D2_MARKER:
            return task
    return None


def d2_task_data(exam: dict[str, Any]) -> dict[str, Any]:
    return {"sachverhalt": exam["sachverhalt"], "musterloesung": exam["musterloesung"], **D2_TASK_FIELDS}


def require_d2_task(db):
    task = find_d2_task(db)
    if task is None:
        raise SystemExit("no D2 research task on the clone: run the d2-setup phase first")
    return task


def phase_d2_setup(ctx: Ctx) -> None:
    from project_models import Task
    from sqlalchemy import func

    exam = load_input(ctx, "heidebach_exam.json")
    data = d2_task_data(exam)
    db = open_db()
    try:
        user_id = research_user_id(db)
        task = find_d2_task(db)
        created = False
        if task is not None:
            if dict(task.data or {}) != data:
                if not ctx.args.force_update:
                    raise SystemExit(f"D2 task {task.id} exists with different data (the exam pack changed?). "
                                     "Pass --force-update to overwrite it; rubrics generated from the old text stay.")
                task.data = data
                db.commit()
                print(f"D2 task {task.id}: data updated", flush=True)
            else:
                print(f"D2 task {task.id}: exists, reused", flush=True)
        else:
            inner = (db.query(func.max(Task.inner_id)).filter(Task.project_id == CLONE_PROJECT).scalar() or 0) + 1
            task = Task(id=str(uuid.uuid4()), project_id=CLONE_PROJECT, data=data, inner_id=inner, created_by=user_id,
                        meta={"research": {"d2_exam": D2_MARKER, "created_by": "run_checklist_pilot d2-setup",
                                           "created_at": now(),
                                           "note": "Case text only: no Bewertungsbogen, Korrekturhinweise or exemplar rubrics."}})
            db.add(task)
            db.commit()
            created = True
            print(f"D2 task {task.id}: created (inner id {inner})", flush=True)
        leaked = [k for k in (task.data or {}) if k.casefold() in L.SENSITIVE_TASK_KEYS]
        if leaked:
            raise SystemExit(f"D2 task {task.id} carries {leaked}: remove them before any generation")
        write(ctx, "d2-setup", {
            "schema": ROW_SCHEMA, "run_id": ctx.run_id, "ts": now(), "phase": "d2-setup", "task_id": task.id,
            "created": created, "data_keys": sorted(task.data or {}),
            "sachverhalt_sha256": L.sha256_text(data["sachverhalt"]),
            "musterloesung_sha256": L.sha256_text(data["musterloesung"]),
            "provenance": ctx.provenance,
        })
    finally:
        db.close()


def phase_d2_generate(ctx: Ctx) -> None:
    db = open_db()
    try:
        user_id = research_user_id(db)
        install_checklist_prompt(db)
        task = require_d2_task(db)
    finally:
        db.close()
    for generator in ctx.args.generators:
        for sample in range(ctx.args.samples):
            run_generation(ctx, "d2-generate", user_id, task, generator, sample)


def prepare_arm(ctx: Ctx, db, arm: dict[str, Any], exam: dict[str, Any], task) -> dict[str, Any]:
    from project_models import TaskRubric

    unit, alternatives = arm["unit"], arm["alternatives"]
    if arm["source"] == "martin":
        if unit == "bullet":
            raise SystemExit("martin arm: the bullet unit waits for Martin's own bullets (decisions, section 5)")
        spec = L.spec_from_sheet(exam["sheet"])
        text, text_source, spec_source = L.render_sheet_text(exam), "sheet_structure", "adapter"
        rubric, guard_on = None, False
    else:
        rubric = db.query(TaskRubric).filter(TaskRubric.id == arm["rubric_id"]).one()
        if rubric.task_id != task.id:
            raise SystemExit(f"arm {arm['id']}: rubric belongs to task {rubric.task_id}, not to the D2 task {task.id}")
        spec, spec_source = spec_for(rubric, unit)
        text, text_source = rendered_text(rubric, alternatives)
        guard_on = True
    grade_scale = L.exam_grade_scale(exam["grade_scale"], exam["sheet"].get("total_points")) if unit == "rating" else None
    context, ground_truth, data = judge_inputs(task.data or {}, text)
    return {
        "arm": arm, "rubric": rubric, "spec": spec, "guard_on": guard_on, "context": context,
        "ground_truth": ground_truth, "data": data, "grade_scale": grade_scale,
        "rubric_texts": L.guard_rubric_texts(text, spec, getattr(rubric, "criteria", None)),
        "config": {"source": arm["source"], "rubric_id": arm["rubric_id"],
                   "sheet_id": exam["sheet"].get("prod_rubric_id") if arm["source"] == "martin" else None,
                   "score_unit": unit, "alternatives": alternatives, "total_mode": ctx.args.total_mode,
                   "grade_scale": grade_scale, "spec_source": spec_source, "rendered": text_source,
                   "spec_sha256": L.sha256_text(json.dumps(spec, sort_keys=True)),
                   "rendered_sha256": L.sha256_text(text)},
    }


def phase_d2_judge(ctx: Ctx) -> None:
    args = ctx.args
    exam = load_input(ctx, "heidebach_exam.json")
    scripts = load_input(ctx, "heidebach_scripts.json")
    by_id = {s["script_id"]: s for s in scripts}
    if args.scripts:
        unknown = [s for s in args.scripts if s not in by_id]
        if unknown:
            raise SystemExit(f"unknown scripts: {unknown}")
        chosen = [by_id[s] for s in args.scripts]
    else:
        chosen = [s for s in scripts if s.get("human")]
    arms = [L.parse_arm(a) for a in args.arms]
    if not arms:
        raise SystemExit("d2-judge needs --arms")
    db = open_db()
    try:
        user_id = research_user_id(db)
        task = require_d2_task(db)
        if dict(task.data or {}) != d2_task_data(exam):
            raise SystemExit(f"D2 task {task.id} differs from heidebach_exam.json: rerun d2-setup (--force-update)")
        prepared = [prepare_arm(ctx, db, arm, exam, task) for arm in arms]
        print(f"d2-judge: {len(args.judges)} judges x {len(prepared)} arms x {len(chosen)} scripts x {args.passes} passes",
              flush=True)
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
                    for script in chosen:
                        base = {"judge": judge_model, "arm": arm["id"], "arm_config": config,
                                "script_id": script["script_id"], "cohort": script.get("cohort"),
                                "task_id": task.id, "rubric_id": arm["rubric_id"], "pass": k}
                        result = judged(ctx, "d2-judge", base, ev, calls, spec=plan["spec"], unit=arm["unit"],
                                        guard_on=plan["guard_on"], rubric_texts=plan["rubric_texts"],
                                        context=plan["context"], ground_truth=plan["ground_truth"],
                                        prediction=script.get("text") or "", data=plan["data"])
                        print_row(ctx, f"{judge_model} pass {k} {arm['id']} {script['script_id']}", result)
    finally:
        db.close()


D2_OFFTOPIC_EXAM = 1  # a civil-law D1 exam: its Musterlösung is off topic for the police-law case


def d2_probe_texts(exam: dict[str, Any], offtopic: str, rubric_text: str, step_names: list[str],
                   arm_id: str) -> dict[str, tuple[str | None, dict[str, Any]]]:
    """The six probes of the G0' gate on the D2 exam (DESIGN.md, pre-registration G0')."""
    musterloesung = exam["musterloesung"]
    out: dict[str, tuple[str | None, dict[str, Any]]] = {
        "empty": (" ", {}),
        "repetition": (exam["sachverhalt"], {"source": "sachverhalt"}),
        "offtopic": (offtopic, {"source": f"D1 exam {D2_OFFTOPIC_EXAM} musterloesung"}),
        "musterloesung": (musterloesung, {}),
    }
    flipped, sentences, flips = L.negation_flip(musterloesung)
    meta = {"flipped_sentences": sentences, "flips": flips}
    if sentences < MIN_NEGATION_FLIPS:
        meta["skipped"] = f"only {sentences} sentences flipped (< {MIN_NEGATION_FLIPS})"
        out["negation_flip"] = (None, meta)
    else:
        out["negation_flip"] = (flipped, meta)
    salad, salad_meta = L.keyword_salad(rubric_text, step_names, seed_key=f"D2:{arm_id}")
    out["keyword_salad"] = (salad, salad_meta) if salad else (None, {**salad_meta, "skipped": "no norms or key terms"})
    out["result_swap"] = result_swap_probe(musterloesung)
    return out


def phase_d2_probes(ctx: Ctx) -> None:
    """G0': the probe battery on the D2 exam, per judge and instrument (arm), on the checklist lane."""
    args = ctx.args
    exam = load_input(ctx, "heidebach_exam.json")
    offtopic = next(e for e in load_input(ctx, "probe_texts.json") if e["exam_inner_id"] == D2_OFFTOPIC_EXAM)
    offtopic_text = offtopic["probes"]["musterloesung"]
    arms = [L.parse_arm(a) for a in args.arms]
    if not arms:
        raise SystemExit("d2-probes needs --arms")
    db = open_db()
    try:
        user_id = research_user_id(db)
        task = require_d2_task(db)
        if dict(task.data or {}) != d2_task_data(exam):
            raise SystemExit(f"D2 task {task.id} differs from heidebach_exam.json: rerun d2-setup (--force-update)")
        prepared = []
        for arm in arms:
            plan = prepare_arm(ctx, db, arm, exam, task)
            rubric_text = L.render_sheet_text(exam) if arm["source"] == "martin" else rendered_text(
                plan["rubric"], arm["alternatives"])[0]
            names = [plan["spec"]["steps"][k].get("name") for k in plan["spec"]["order"]]
            plan["texts"] = d2_probe_texts(exam, offtopic_text, rubric_text, names, arm["id"])
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
                    for ptype in types:
                        text, meta = plan["texts"][ptype]
                        base = {"judge": judge_model, "exam": "D2", "arm": arm["id"], "arm_config": config,
                                "task_id": task.id, "rubric_id": arm["rubric_id"], "probe": ptype,
                                "lane": "checklist", "unit": arm["unit"], "pass": k, "probe_meta": meta}
                        if text is None:
                            write(ctx, "d2-probes", {"schema": ROW_SCHEMA, "run_id": ctx.run_id, "ts": now(),
                                                     "phase": "d2-probes", **base, "seed": ev.seed, "skipped": True,
                                                     "total": None, "error": None, "provenance": ctx.provenance})
                            print(f"{judge_model} pass {k} {arm['id']} {ptype:13s}: skipped ({meta.get('skipped')})",
                                  flush=True)
                            continue
                        result = judged(ctx, "d2-probes", base, ev, calls, spec=plan["spec"], unit=arm["unit"],
                                        guard_on=plan["guard_on"], rubric_texts=plan["rubric_texts"],
                                        context=plan["context"], ground_truth=plan["ground_truth"],
                                        prediction=text, data=plan["data"])
                        print_row(ctx, f"{judge_model} pass {k} {arm['id']} {ptype}", result)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------


def phase_selftest(ctx: Ctx) -> int:
    import tempfile

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)
        if not ok:
            failures.append(name)

    exam = load_input(ctx, "heidebach_exam.json")
    phrases = L.load_canary_phrases(ctx.inp / "canary_phrases.json")

    # --- spec adapter on Martin's sheet ------------------------------------
    spec = L.spec_from_sheet(exam["sheet"])
    total = sum(s["max_score"] for s in spec["steps"].values())
    check("adapter: Martin's sheet has 46 steps", len(spec["order"]) == 46, str(len(spec["order"])))
    check("adapter: Martin's sheet sums to 100", abs(total - 100) < 1e-9 and spec["total_points"] == 100.0, str(total))
    check("adapter: order follows the outline", spec["order"] == list(exam["sheet"]["step_keys"]))
    check("adapter: requirement lists are empty", all(s["anforderungen"] == [] for s in spec["steps"].values()))
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

    # the judge accepts the spec: schema, and full marks give 100
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
        check("judge: full marks on the adapted sheet give 100", done.get("total_score") == 100.0,
              str(done.get("total_score")))
    except ImportError as exc:
        print(f"SKIP  judge integration ({exc})")

    # rendered sheet: the mirror text minus its Notenschlüssel block
    rendered = L.render_sheet_text(exam)
    mirror = exam.get("bewertungsbogen_text") or ""
    check("sheet text: rendered from the structure equals the mirror without its grade block",
          mirror.startswith(rendered) and "NOTENSCHLÜSSEL" in mirror[len(rendered):] and "NOTENSCHLÜSSEL" not in rendered)
    import re as _re

    check("sheet text: keys match the spec", _re.findall(r"\[Schlüssel: ([^\]]+)\]", rendered) == spec["order"])
    scale = L.exam_grade_scale(exam["grade_scale"], exam["sheet"]["total_points"])
    check("grade key: Martin's key is a valid platform scale", not validate_grade_scale(scale), json.dumps(scale))

    # --- negation flip -------------------------------------------------------
    para = ("Die Klage ist zulässig. Sie ist jedoch nicht begründet. Eine konkrete Gefahr liegt vor. "
            "Ein Anspruch besteht nicht. Fraglich ist, ob die Maßnahme rechtmäßig war. "
            "Es besteht kein Feststellungsinteresse. Somit ist festzuhalten, dass keine Gefahr vorliegt. "
            "Zuständigkeit (+). Wiederholungsgefahr (-). "
            "Der Kläger ist in seinem Grundrecht aus Art. 8 Abs. 1 GG verletzt.")
    want = ("Die Klage ist nicht zulässig. Sie ist jedoch begründet. Eine konkrete Gefahr liegt nicht vor. "
            "Ein Anspruch besteht. Fraglich ist, ob die Maßnahme rechtmäßig war. "
            "Es besteht ein Feststellungsinteresse. Somit ist festzuhalten, dass eine Gefahr vorliegt. "
            "Zuständigkeit (-). Wiederholungsgefahr (+). "
            "Der Kläger ist in seinem Grundrecht aus Art. 8 Abs. 1 GG nicht verletzt.")
    flipped, sentences, flips = L.negation_flip(para)
    check("negation flip: synthetic paragraph", flipped == want, flipped if flipped != want else "")
    check("negation flip: 9 of 10 sentences flipped, the question stays", sentences == 9 and flips == 9,
          f"{sentences} sentences, {flips} flips")
    simple = "Die Klage ist zulässig. Eine Gefahr liegt nicht vor. Ein Anspruch besteht. Zuständigkeit (+)."
    check("negation flip: twice gives the original back", L.negation_flip(L.negation_flip(simple)[0])[0] == simple)
    check("negation flip: deterministic", L.negation_flip(para) == (flipped, sentences, flips))
    ml_flips = L.negation_flip(exam["musterloesung"])[1]
    check("negation flip: Martin's Musterlösung has enough flips", ml_flips >= MIN_NEGATION_FLIPS, str(ml_flips))
    gutachten = ("# A. Zulässigkeit\nDie Klage ist zulässig, wenn die Sachentscheidungsvoraussetzungen vorliegen. "
                 "Die Klagefrist ist gewahrt. Die Klage ist zulässig.\n# B. Begründetheit\nDie Maßnahme könnte "
                 "rechtswidrig sein. Sie ist nicht verhältnismäßig.\n# Ergebnis\nDie Klage ist zulässig und begründet; "
                 "sie hat daher Erfolg.")
    swapped, n_swaps, _pairs = L.result_swap(gutachten)
    check("result swap: section results and the Ergebnis swap, Obersatz and hypothesis stay",
          "Die Klage ist unzulässig.\n# B." in swapped and "Sie ist verhältnismäßig." in swapped
          and "unzulässig und unbegründet; sie hat daher keinen Erfolg." in swapped
          and "zulässig, wenn die Sachentscheidungsvoraussetzungen" in swapped and "könnte rechtswidrig" in swapped,
          swapped)
    check("result swap: deterministic", L.result_swap(gutachten)[0] == swapped)
    ml_swaps = L.result_swap(exam["musterloesung"])[1]
    check("result swap: Martin's Musterlösung has enough swapped results", ml_swaps >= MIN_RESULT_SWAPS, str(ml_swaps))

    # --- keyword salad -------------------------------------------------------
    rubric_text = ("I. Eröffnung des Verwaltungsrechtswegs nach § 40 I 1 VwGO (1 BE)\n"
                   "a) Art. 16 Abs. 2 S. 1 Nr. 2 lit. a PAG (2 BE). Klagebefugnis, § 42 II VwGO analog.\n"
                   "Vorverfahren, §§ 68 ff. VwGO")
    names = ["Eröffnung des Verwaltungsrechtswegs", "Sperrwirkung der Standardbefugnisse", "Klagebefugnis"]
    salad, _ = L.keyword_salad(rubric_text, names, "exam-1")
    items = salad.splitlines()
    check("keyword salad: norms extracted",
          {"§ 40 I 1 VwGO", "Art. 16 Abs. 2 S. 1 Nr. 2 lit. a PAG", "§ 42 II VwGO", "§§ 68 ff. VwGO"} <= set(items),
          str(items))
    check("keyword salad: key terms of 8+ characters", {"Verwaltungsrechtswegs", "Standardbefugnisse", "Klagebefugnis",
                                                         "Sperrwirkung"} <= set(items) and "Eröffnung" in items)
    check("keyword salad: no sentences, only norms and single terms",
          all(L.NORM_RE.fullmatch(i) or L.KEY_TERM_RE.fullmatch(i) for i in items), str(items))
    check("keyword salad: deterministic, seed-dependent order",
          L.keyword_salad(rubric_text, names, "exam-1")[0] == salad
          and sorted(L.keyword_salad(rubric_text, names, "exam-2")[0].splitlines()) == sorted(items))
    _, martin_meta = L.keyword_salad(rendered, [spec["steps"][k]["name"] for k in spec["order"]], "martin")
    check("keyword salad: Martin's sheet yields norms and terms", martin_meta["norms"] >= 5 and martin_meta["terms"] >= 10,
          json.dumps(martin_meta))

    # --- canaries ----------------------------------------------------------
    case = L.norm_text(exam["sachverhalt"]) + "\n" + L.norm_text(exam["musterloesung"])
    present = [p for p in phrases if L.norm_text(p) in case]
    check(f"canaries: {len(phrases)} sheet phrases, none in the Sachverhalt or the Musterlösung",
          len(phrases) >= 10 and not present, f"present: {present}" if present else "")
    missing = [p for p in phrases if L.norm_text(p) not in L.norm_text(mirror)]
    check("canaries: every phrase occurs in Martin's sheet", not missing, f"missing: {missing}" if missing else "")
    in_ml = [t for t in L.FIXED_CANARIES if L.norm_text(t) in case]
    print(f"INFO  fixed canary terms that occur in the case text (hence the case text is removed before the check): {in_ml}")

    guard = L.CanaryGuard(phrases)
    ml, sv, answer = exam["musterloesung"], exam["sachverhalt"], "Die Klage ist zulässig und begründet. " * 3
    rubric_lines = ["Schritt 3: Maßnahmerichtung (4 BE)", f"Schritt 4: {phrases[1]} (2 BE)"]
    guard.arm("selftest", case_texts=[sv, ml, answer], rubric_texts=rubric_lines)
    clean_prompt = f"SACHVERHALT:\n<sachverhalt>\n{sv}\n</sachverhalt>\nMUSTERLÖSUNG:\n{ml}\nBEARBEITUNG:\n{answer}"

    def raises(system: str, prompt: str) -> bool:
        try:
            guard.check(system, prompt)
            return False
        except L.LeakageDetected:
            return True

    check("guard: case text, answer and rubric terms pass", not raises("Bewerte fair.", clean_prompt
                                                                         + "\nSchritt 3: Maßnahmerichtung (4 BE)"))
    check("guard: a fixed term in the system prompt raises", raises("Etwa ein Argument zur Maßnahmerichtung.", clean_prompt))
    check("guard: ss spelling is caught too", raises("Zur Massnahmerichtung.", clean_prompt))
    check("guard: a sheet phrase in the user prompt raises", raises("Bewerte fair.", clean_prompt + "\n" + phrases[0]))
    check("guard: a sheet phrase inside the rubric under test raises",
          raises("Bewerte fair.", clean_prompt + "\n" + rubric_lines[1]))
    check("guard: the generator's correction block is not scanned",
          not raises("Bewerte fair.", clean_prompt + L.CORRECTION_MARKER + "\nVORHERIGES DOKUMENT: Zweckveranlasser"))
    guard.disarm()
    check("guard: disarmed guard never raises", not raises("Maßnahmerichtung", phrases[0]))
    check("guard: LeakageDetected escapes except Exception", not issubclass(L.LeakageDetected, Exception))
    stripped = L.strip_task_data({"Sachverhalt": 1, "Bewertungsbogen": 2, "korrekturhinweise": 3, "exemplar_rubrics": 4})
    check("strip: sheet, hints and exemplars removed case-insensitively", stripped == {"Sachverhalt": 1})

    # --- ledger --------------------------------------------------------------
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
    parser.add_argument("--org", default=DEFAULT_ORG)
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
    parser.add_argument("--types", nargs="*", default=list(PROBE_TYPES))
    parser.add_argument("--ds-types", nargs="*", default=None, help="probe types for DeepSeek (default: --types)")
    parser.add_argument("--exams", nargs="*", type=int, default=None)
    parser.add_argument("--limit-exams", type=int, default=None)
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
    parser.add_argument("--scripts", nargs="*", default=None, help="script ids (default: every human-graded one)")
    parser.add_argument("--force-update", action="store_true", help="d2-setup: overwrite a changed D2 task")
    args = parser.parse_args(argv)
    args.run_id = args.run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    args.types_by_judge = {"deepseek-ai/DeepSeek-V4-Pro": args.ds_types} if args.ds_types else {}
    unknown = [t for t in args.types + (args.ds_types or []) if t not in PROBE_TYPES]
    if unknown:
        parser.error(f"unknown probe types {unknown}")
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

    files = {path: L.sha256_file(path) for path in INSTRUMENT_FILES}
    provenance = {
        "code_version": L.code_version(files),
        "files": files,
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

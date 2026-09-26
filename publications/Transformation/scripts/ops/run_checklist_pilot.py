#!/usr/bin/env python3
"""P1 pilot for the checklist instrument (extended version), with a spend cap.

Runs INSIDE the local dev worker container, so every call goes through the
product's own judge and generator code:

    docker cp <inputs> benger-worker-1:/tmp/pilot/
    docker exec -i benger-worker-1 python - <phase> [options] < run_checklist_pilot.py

Phases
  probes     the probe battery (empty / repetition / offtopic / musterloesung)
             against each exam's D6-drawn rubric on the CURRENT rubric lane
             (fixed system prompt, tagged inputs, evidence rule): the gate a
             judge must pass before its results count.
  generate   one checklist Bewertungsbogen per generator for one exam, stored
             as a candidate rubric (never activated) on the research clone.
  checklist  checklist judgments of real picks against a generated rubric,
             to measure output tokens, latency and parse success per judge.

Spend control: every provider call (retries and failed attempts included)
is metered from its token usage and the catalog prices in
/shared/seeds/llm_models.yaml. Before each call the ledger checks that the
spend so far plus a per-model reserve stays under --cap; otherwise the run
stops. The ledger file persists across phases (/tmp/pilot/ledger.json).

Outputs one JSON line per call to /tmp/pilot/<phase>.jsonl. Local dev only;
no production access.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path[:0] = ["/shared", "/app"]

WORK = Path("/tmp/pilot")
LEDGER = WORK / "ledger.json"
CLONE_PROJECT = "81e474b8-d226-4bf8-bc2e-fb744d25cba5"
RESEARCH_USER_EMAIL = "research-ops@example.com"
# Spend goes to this organisation's keys (org-pays; the research user is a
# superadmin, which the org-key gate accepts). Local dev stack only.
DEFAULT_ORG = "<org-id>"  # TUM
CHECKLIST_PROMPT_KEY = "bewertungsbogen_checklist"
RESERVE_USD = {  # worst plausible single call, checked before dispatch
    "gpt-5.6-luna": 0.06,
    "deepseek-ai/DeepSeek-V4-Pro": 0.15,
    "gpt-5.4-mini": 0.25,
    "gpt-5.4": 0.80,
}


# Both stop signals derive from BaseException on purpose: the judge and the
# generator wrap provider calls in ``except Exception`` and retry, which would
# swallow them and let the run continue.
class BudgetExceeded(BaseException):
    pass


class ProviderBlocked(BaseException):
    """A provider refuses on billing grounds (no credits, spending limit)."""


_BLOCKED_MARKERS = ("credit_balance_exhausted", "insufficient_quota", "no credits remaining",
                    "user-set limit", "HTTP 402", "billing")


def check_blocked(model: str, response: dict) -> None:
    text = f"{(response or {}).get('error')} {(response or {}).get('content') or ''}"
    if not (response or {}).get("success") and any(m in text for m in _BLOCKED_MARKERS):
        raise ProviderBlocked(f"{model}: provider refuses on billing grounds: {str(response.get('error'))[:200]}")


class Ledger:
    def __init__(self, cap: float):
        import yaml

        self.cap = cap
        catalog = yaml.safe_load(open("/shared/seeds/llm_models.yaml"))
        rows = catalog["models"] if isinstance(catalog, dict) and "models" in catalog else catalog
        self.prices = {r["id"]: (float(r.get("input_cost_per_million") or 0), float(r.get("output_cost_per_million") or 0))
                       for r in rows if isinstance(r, dict) and r.get("id")}
        self.state = json.loads(LEDGER.read_text()) if LEDGER.exists() else {"spent": 0.0, "calls": 0, "by_model": {}}

    def check(self, model: str) -> None:
        reserve = RESERVE_USD.get(model, 0.5)
        if self.state["spent"] + reserve > self.cap:
            raise BudgetExceeded(
                f"stop: spent ${self.state['spent']:.3f} + reserve ${reserve:.2f} for {model} exceeds cap ${self.cap:.2f}"
            )

    def add(self, model: str, usage: dict) -> float:
        pin, pout = self.prices.get(model, (0.0, 0.0))
        cost = (usage.get("prompt_tokens") or 0) * pin / 1e6 + (usage.get("completion_tokens") or 0) * pout / 1e6
        self.state["spent"] += cost
        self.state["calls"] += 1
        m = self.state["by_model"].setdefault(model, {"calls": 0, "usd": 0.0, "in": 0, "out": 0})
        m["calls"] += 1
        m["usd"] += cost
        m["in"] += usage.get("prompt_tokens") or 0
        m["out"] += usage.get("completion_tokens") or 0
        LEDGER.write_text(json.dumps(self.state, indent=1))
        return cost


def meter(service, method: str, model: str, ledger: Ledger, calls: list) -> None:
    """Wrap one provider method on ``service`` with the ledger."""
    original = getattr(service, method)

    def metered(*args, **kwargs):
        ledger.check(model)
        started = time.monotonic()
        if os.environ.get("PILOT_DRY_RUN") == "1":
            prompt = kwargs.get("prompt") or ""
            calls.append({"model": model, "dry_run": True, "prompt_chars": len(prompt),
                          "system_chars": len(kwargs.get("system_prompt") or ""),
                          "schema_bytes": len(json.dumps(kwargs.get("json_schema") or {}))})
            return {"success": False, "error": "dry run", "usage": {}, "metadata": {"error_type": "dry_run"}}
        if os.environ.get("PILOT_DRY_RUN") == "billing":  # exercises the fail-fast without a provider call
            response = {"success": False, "error": "Error code: 429 credit_balance_exhausted", "usage": {}}
            ledger.add(model, {})
            check_blocked(model, response)
        response = original(*args, **kwargs)
        usage = (response or {}).get("usage") or {}
        cost = ledger.add(model, usage)
        check_blocked(model, response)
        calls.append({"model": model, "in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens"),
                      "usd": round(cost, 5), "s": round(time.monotonic() - started, 1),
                      "success": bool((response or {}).get("success"))})
        return response

    setattr(service, method, metered)


def open_db():
    from database import SessionLocal
    import models  # noqa: F401  (registers User etc. before project_models)
    import project_models  # noqa: F401

    return SessionLocal()


def research_user_id(db) -> str:
    from models import User

    return db.query(User).filter(User.email == RESEARCH_USER_EMAIL).one().id


def make_judge(db, user_id: str, judge_model: str, ledger: Ledger, calls: list, org_id: str = None):
    import tasks
    from ai_services.provider_capabilities import get_provider_from_model
    from benger_extended.workers.rubric_prompt import DEFAULT_GRADING_PROMPT_TEMPLATE
    from ml_evaluation.llm_judge_evaluator import create_llm_judge_for_user
    from models import LLMModel

    row = db.query(LLMModel).filter(LLMModel.id == judge_model).first()
    requested = 0.0 if "DeepSeek" in judge_model else 1.0
    temperature, _ = tasks._clamp_temperature_to_constraint(requested, getattr(row, "parameter_constraints", None) or None)
    ev = create_llm_judge_for_user(
        db, user_id, get_provider_from_model(judge_model), judge_model,
        temperature=temperature, max_tokens=32000,
        custom_prompt_template=DEFAULT_GRADING_PROMPT_TEMPLATE,
        organization_id=org_id,
    )
    meter(ev.ai_service, "generate_structured", judge_model, ledger, calls)
    return ev


def task_inputs(task, rubric):
    from evaluation.cell_evaluator import _build_judge_context, _render_rubric_text
    import tasks

    data = dict(task.data or {})
    context = _build_judge_context(data, include_korrekturhinweise=False)
    ground_truth = tasks._get_insensitive(data, "musterlösung") or tasks._get_insensitive(data, "musterloesung") or ""
    data["bewertungsbogen"] = _render_rubric_text(rubric)
    return context, str(ground_truth), data


def write(phase: str, row: dict) -> None:
    with (WORK / f"{phase}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------


def phase_probes(args, ledger):
    from project_models import Task, TaskRubric

    probes = json.loads((WORK / "probe_texts.json").read_text())
    actives = json.loads((WORK / "clone_d6_actives.json").read_text())
    db = open_db()
    try:
        user_id = research_user_id(db)
        for judge_model in args.judges:
            types = args.types_by_judge.get(judge_model, args.types)
            calls: list = []
            ev = make_judge(db, user_id, judge_model, ledger, calls, args.org)
            for exam in probes[: args.limit_exams]:
                if args.exams and exam["exam_inner_id"] not in args.exams:
                    continue
                task = db.query(Task).filter(Task.id == exam["clone_task_id"]).one()
                rubric = db.query(TaskRubric).filter(TaskRubric.id == actives[task.id]).one()
                context, ground_truth, data = task_inputs(task, rubric)
                ev.bind_task_rubric(rubric)
                for ptype in types:
                    calls.clear()
                    started = time.monotonic()
                    result = ev._evaluate_multidim_single_call(
                        context=context, ground_truth=ground_truth,
                        prediction=exam["probes"][ptype], task_data=data,
                    )
                    write("probes", {
                        "judge": judge_model, "exam": exam["exam_inner_id"], "task_id": task.id,
                        "rubric_id": rubric.id, "probe": ptype,
                        "total": None if result.get("error") else result.get("total_score"),
                        "error": result.get("error_message") if result.get("error") else None,
                        "zeroed": sum(1 for s in (result.get("scores") or {}).values()
                                      if isinstance(s, dict) and s.get("model_score", 0) > s.get("score", 0)),
                        "model_total": sum(float(s.get("model_score", s.get("score", 0)) or 0)
                                           for s in (result.get("scores") or {}).values() if isinstance(s, dict)),
                        "seconds": round(time.monotonic() - started, 1), "calls": list(calls),
                        "steps": {k: {f: v.get(f) for f in ("score", "max", "model_score", "evidence",
                                                            "evidence_verified", "reason")}
                                  for k, v in (result.get("scores") or {}).items() if isinstance(v, dict)}
                        if args.store_steps else None,
                    })
                    print(f"{judge_model} exam {exam['exam_inner_id']:>3} {ptype:13s} -> "
                          f"{result.get('total_score') if not result.get('error') else 'ERROR'}  "
                          f"(ledger ${ledger.state['spent']:.3f})", flush=True)
    finally:
        db.close()


def install_checklist_prompt(db) -> None:
    from sqlalchemy.orm.attributes import flag_modified
    from project_models import Project

    project = db.query(Project).filter(Project.id == CLONE_PROJECT).one()
    structure = json.loads((WORK / "rubric_prompt_checklist.json").read_text())
    config = dict(project.generation_config or {})
    structures = dict(config.get("prompt_structures") or {})
    structures[CHECKLIST_PROMPT_KEY] = structure
    config["prompt_structures"] = structures
    project.generation_config = config
    flag_modified(project, "generation_config")
    db.commit()


def phase_generate(args, ledger):
    import benger_extended.workers.judge_resolution as jr
    from benger_extended.workers.bewertungsbogen_tasks import generate_bewertungsbogen_impl

    db = open_db()
    try:
        user_id = research_user_id(db)
        install_checklist_prompt(db)
    finally:
        db.close()
    original_resolve = jr.resolve_judge_ai_service
    for generator in args.generators:
        calls: list = []

        def resolve(*a, _gen=generator, _calls=calls, **k):
            service = original_resolve(*a, **k)
            if service is not None:
                meter(service, "generate", _gen, ledger, _calls)
            return service

        jr.resolve_judge_ai_service = resolve
        started = time.monotonic()
        try:
            out = generate_bewertungsbogen_impl(
                None, CLONE_PROJECT, args.task, user_id, organization_id=args.org, generator_model_id=generator,
                prompt_key=CHECKLIST_PROMPT_KEY, activate_if_first=False,
                rubric_contract="checklist", allocation_mode=args.allocation_mode,
            )
        finally:
            jr.resolve_judge_ai_service = original_resolve
        write("generate", {"generator": generator, "task_id": args.task, "allocation_mode": args.allocation_mode,
                           "result": out, "seconds": round(time.monotonic() - started, 1), "calls": calls})
        print(f"{generator}: {out.get('status')} rubric {out.get('rubric_id')} steps {out.get('steps')} "
              f"attempts {out.get('attempts')} (ledger ${ledger.state['spent']:.3f})", flush=True)


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


def phase_checklist(args, ledger):
    from project_models import Task, TaskRubric

    picks = {p["pick_id"]: p for p in json.loads((WORK / "picks_temp0.json").read_text())["resolved"]}
    db = open_db()
    try:
        user_id = research_user_id(db)
        rubric = db.query(TaskRubric).filter(TaskRubric.id == args.rubric).one()
        spec = (rubric.generation_metadata or {}).get("checklist_spec")
        task = db.query(Task).filter(Task.id == rubric.task_id).one()
        for judge_model in args.judges:
            calls: list = []
            ev = make_judge(db, user_id, judge_model, ledger, calls, args.org)
            ev.bind_task_rubric(rubric)
            for unit in args.units:
                ev.configure_checklist(spec, unit, "branch", "declared")
                context, ground_truth, data = task_inputs(task, rubric)
                for pick_id in args.picks:
                    calls.clear()
                    started = time.monotonic()
                    result = ev._evaluate_multidim_single_call(
                        context=context, ground_truth=ground_truth,
                        prediction=answer_text(db, picks[pick_id]), task_data=data,
                    )
                    ck = result.get("checklist") or {}
                    write("checklist", {
                        "judge": judge_model, "unit": unit, "pick": pick_id, "rubric_id": rubric.id,
                        "total": None if result.get("error") else result.get("total_score"),
                        "totals": ck.get("totals"), "zeroed": ck.get("zeroed_items"),
                        "fehlplatziert": ck.get("fehlplatziert_steps"),
                        "abweichend": ck.get("abweichender_weg_steps"),
                        "assessment": (result.get("assessment") or {}).get("assessment_status"),
                        "error": result.get("error_message") if result.get("error") else None,
                        "seconds": round(time.monotonic() - started, 1), "calls": list(calls),
                    })
                    out_tokens = sum(c.get("out") or 0 for c in calls)
                    print(f"{judge_model} {unit:6s} {pick_id}: total {result.get('total_score')} "
                          f"out_tokens {out_tokens} {'ERROR ' + str(result.get('error_message'))[:120] if result.get('error') else ''}"
                          f"(ledger ${ledger.state['spent']:.3f})", flush=True)
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("probes", "generate", "checklist", "ledger"))
    parser.add_argument("--cap", type=float, default=8.0)
    parser.add_argument("--org", default=DEFAULT_ORG)
    parser.add_argument("--limit-exams", type=int, default=None)
    parser.add_argument("--exams", nargs="*", type=int, default=None)
    parser.add_argument("--store-steps", action="store_true")
    parser.add_argument("--judges", nargs="*", default=["gpt-5.6-luna", "deepseek-ai/DeepSeek-V4-Pro"])
    parser.add_argument("--types", nargs="*", default=["empty", "repetition", "offtopic", "musterloesung"])
    parser.add_argument("--ds-types", nargs="*", default=["empty", "musterloesung"])
    parser.add_argument("--generators", nargs="*", default=["gpt-5.4-mini", "gpt-5.4"])
    parser.add_argument("--task")
    parser.add_argument("--allocation-mode", default="flat")
    parser.add_argument("--rubric")
    parser.add_argument("--units", nargs="*", default=["bullet"])
    parser.add_argument("--picks", nargs="*", default=["P02", "P03"])
    args = parser.parse_args(sys.argv[1:])
    args.types_by_judge = {"deepseek-ai/DeepSeek-V4-Pro": args.ds_types}
    WORK.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(args.cap)
    try:
        if args.phase == "probes":
            phase_probes(args, ledger)
        elif args.phase == "generate":
            phase_generate(args, ledger)
        elif args.phase == "checklist":
            phase_checklist(args, ledger)
    except BudgetExceeded as exc:
        print(f"BUDGET STOP: {exc}", flush=True)
        return 3
    except ProviderBlocked as exc:
        print(f"PROVIDER STOP: {exc}", flush=True)
        return 4
    finally:
        print("LEDGER " + json.dumps(ledger.state), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

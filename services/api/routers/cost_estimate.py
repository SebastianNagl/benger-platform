"""
Cost estimate endpoint for the multi-run feature.

Returns a per-call / per-run / total cost estimate for a generation or
evaluation trigger. Pricing is read from the `llm_models` DB table (seeded
from `services/shared/seeds/llm_models.yaml`); token counts come from
`services/api/services/token_estimation.py` (tiktoken with cl100k_base proxy).

Estimate accuracy is best-effort — UI surfaces a "± ~20%" caveat.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from auth_module import require_user
from database import get_db
from models import LLMModel, User
from project_models import Project
from routers.projects.helpers import check_project_accessible, get_org_context_from_request
from services.token_estimation import (
    estimate_tokens_for_calls,
    sample_prediction_inputs,
    sample_task_texts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm-models", tags=["cost-estimate"])


class EvalConfigForCost(BaseModel):
    """Subset of an evaluation config the cost endpoint needs to size the
    judge fan-out per prediction-field. Carries the metric name so we can
    mirror the worker's `llm_judge_falloesung` backward-compat rule
    (unprefixed prediction fields go to the annotation side for that
    metric only — see `services/workers/tasks.py` ~line 3291)."""
    metric: Optional[str] = None
    prediction_fields: List[str] = Field(default_factory=list)


class CostEstimateRequest(BaseModel):
    project_id: str
    mode: Literal["generation", "evaluation"]
    model_ids: List[str] = Field(default_factory=list)
    judge_models: List[str] = Field(default_factory=list)  # eval ensemble
    runs_per_call: int = Field(default=1, ge=1, le=25)
    samples_per_task: int = Field(default=1, ge=1, le=10)
    task_sample_size: int = Field(default=10, ge=1, le=50)
    # Evaluation scope filters (issue #69). When evaluation_configs is set
    # the eval cost is sized by (subject × prediction_field) pairs instead
    # of the legacy flat tasks-count formula. model_ids/annotator_user_ids
    # then narrow the generation/annotation subject pools respectively.
    annotator_user_ids: Optional[List[str]] = None
    evaluation_configs: List[EvalConfigForCost] = Field(default_factory=list)
    # Without these the estimator counts every (task, structure) combo for
    # every model, even when the user picked "Generate missing" — which
    # only fires the cells whose latest gen failed or is absent. Mirror
    # the trigger endpoint's `mode` and `structure_keys` so the cost
    # number matches what the worker will actually queue.
    generation_mode: Optional[Literal["all", "missing", "single"]] = None
    structure_keys: Optional[List[str]] = None

    @model_validator(mode="after")
    def _reject_cross_mode_keys(self) -> "CostEstimateRequest":
        """Eval-only keys silently passed in generation mode used to be
        ignored. Now reject so client bugs surface immediately instead of
        producing a cost number that doesn't reflect what the user
        intended."""
        if self.mode == "generation":
            offending = []
            if self.evaluation_configs:
                offending.append("evaluation_configs")
            if self.annotator_user_ids:
                offending.append("annotator_user_ids")
            if self.judge_models:
                offending.append("judge_models")
            if offending:
                raise ValueError(
                    f"{', '.join(offending)} are eval-only and must not be set "
                    "when mode == 'generation'"
                )
        return self


class PerModelCost(BaseModel):
    model_id: str
    per_call_usd: float
    per_run_usd: float
    total_usd: float
    pricing_known: bool
    cells_to_generate: int = 0


class TokenBreakdown(BaseModel):
    input_mean: float
    input_p95: float
    output_estimate: float
    encoding: str


class CostEstimateResponse(BaseModel):
    mode: Literal["generation", "evaluation"]
    runs_per_call: int
    sample_size: int
    tasks_total: int
    # Number of (subject × prediction_field) cells that will be (re-)scored
    # when mode == "evaluation" and evaluation_configs were provided. Zero
    # for generation mode and for the legacy eval path that did not pass
    # configs (in which case the cost falls back to tasks_total × samples).
    subject_count: int
    # ISO timestamp of when subject_count was computed (issue #69 follow-up
    # E4). Fresh on every endpoint call. Surfaced so the modal can render
    # an "as of HH:MM:SS" tooltip — the count depends on live DB state
    # (a generation completing changes it) and a user who waits seconds
    # between preview and Run-click otherwise has no way to tell their
    # estimate is stale.
    estimated_at: str
    per_model: List[PerModelCost]
    total_usd: float
    token_estimate: TokenBreakdown
    note: str


def _count_eval_subjects(
    db: Session,
    project_id: str,
    evaluation_configs: List[EvalConfigForCost],
    model_ids: Optional[List[str]],
    annotator_user_ids: Optional[List[str]],
) -> int:
    """Count (subject × prediction_field) cells that the configured eval
    will (re-)score, scoped by the model + annotator filters. Generation
    rows are the subject for non-human fields; Annotation rows for human
    fields. Returns 0 when no configs are provided — the caller then falls
    back to the legacy tasks-count formula for backward-compat.

    Field classification (which fields are human vs LLM) is delegated to
    `services/shared/eval_field_classification.py` so the worker and the
    cost endpoint stay in lockstep, including extension-registered metrics
    that ship from `benger_extended`."""
    if not evaluation_configs:
        return 0

    from eval_field_classification import classify_pred_fields
    from models import Generation
    from project_models import Annotation, Task

    classified = [
        (cfg, classify_pred_fields(cfg.metric, cfg.prediction_fields))
        for cfg in evaluation_configs
    ]
    has_any_human_field = any(human for _, (human, _llm) in classified)
    has_any_llm_field = any(llm for _, (_human, llm) in classified)

    gen_count = 0
    if has_any_llm_field:
        # Generation has no `project_id` column — it scopes through Task.
        gen_q = (
            db.query(Generation)
            .join(Task, Generation.task_id == Task.id)
            .filter(Task.project_id == project_id)
        )
        if model_ids:
            gen_q = gen_q.filter(Generation.model_id.in_(model_ids))
        gen_count = gen_q.count()

    ann_count = 0
    if has_any_human_field:
        ann_q = (
            db.query(Annotation)
            .join(Task, Annotation.task_id == Task.id)
            .filter(Task.project_id == project_id, Annotation.was_cancelled is False)  # noqa: E712
        )
        if annotator_user_ids:
            ann_q = ann_q.filter(Annotation.completed_by.in_(annotator_user_ids))
        ann_count = ann_q.count()

    total = 0
    for _cfg, (human_fields, llm_fields) in classified:
        total += len(llm_fields) * gen_count + len(human_fields) * ann_count
    return total


def _resolve_pricing(db: Session, model_id: str) -> Optional[Dict[str, float]]:
    """Look up per-token cost from `llm_models` (Float columns quoted /1M tokens).
    Normalizes to USD per 1k tokens for downstream multiplication."""
    row = db.query(LLMModel).filter(LLMModel.id == model_id).first()
    if not row:
        return None
    in_per_m = row.input_cost_per_million
    out_per_m = row.output_cost_per_million
    if in_per_m is None and out_per_m is None:
        return None
    return {
        "input_per_1k": (float(in_per_m) / 1000.0) if in_per_m is not None else 0.0,
        "output_per_1k": (float(out_per_m) / 1000.0) if out_per_m is not None else 0.0,
    }


def _resolve_max_tokens_for_model(
    project_gen_config: Dict[str, Any],
    model_id: str,
    project_default: int,
) -> int:
    """Per-model `max_tokens` lookup.

    The cost estimate must mirror the worker's parameter-resolution chain
    (services/workers/tasks.py::_resolve_param) — otherwise an estimate
    computed against the project's 4 000 default while the actual call
    runs at the per-model 32 000 override (e.g. gpt-5.5-pro after the
    Pro-tier max_tokens bump) understates cost by ~8x.

    Priority (highest → lowest):
      1. selected_configuration.model_configs[model_id].max_tokens
      2. selected_configuration.parameters.max_tokens (passed in as project_default)
    """
    sel = (project_gen_config or {}).get("selected_configuration") or {}
    model_overrides = (sel.get("model_configs") or {}).get(model_id) or {}
    if "max_tokens" in model_overrides and model_overrides["max_tokens"]:
        return int(model_overrides["max_tokens"])
    return int(project_default)


def _is_reasoning_model(llm_model_row: LLMModel) -> bool:
    """A model is reasoning-tier if its catalog entry declares a
    reasoning-effort selector (default_config.reasoning_config) or a
    recommended reasoning_effort value. These are the cohorts whose
    output reliably approaches the configured max_tokens budget
    because hidden reasoning tokens are billed as output tokens.
    """
    dc = getattr(llm_model_row, "default_config", None) or {}
    if isinstance(dc, dict) and dc.get("reasoning_config"):
        return True
    rp = getattr(llm_model_row, "recommended_parameters", None) or {}
    if isinstance(rp, dict):
        rec_default = rp.get("default") or {}
        if isinstance(rec_default, dict) and rec_default.get("reasoning_effort"):
            return True
    return False


# Non-reasoning models rarely use more than ~60 % of the configured
# max_tokens budget on real prompts. Reasoning-tier models (Pro/o-series)
# routinely fill 80–95 % because hidden reasoning tokens count toward
# output. Picking 0.9 keeps the estimate slightly conservative without
# pretending every call hits the cap exactly.
_REASONING_OUTPUT_UTILIZATION = 0.9
_DEFAULT_OUTPUT_UTILIZATION = 0.6

# LLM judges output a structured score + short reasoning — typically
# 500-2000 tokens regardless of how high max_tokens is configured. Using
# the generation utilization (0.6 × 16K = 9.6K) over-counts the output
# bill by ~5× for a judge call. We pick 0.15 because typical judge
# `max_tokens` is 8K-16K and 0.15 × that = 1.2K-2.4K, the realistic band
# for a GPT-5-family judge producing JSON-shaped scoring + rationale.
_EVAL_OUTPUT_UTILIZATION = 0.15


def _count_evaluation_judge_calls(
    db: Session,
    project_id: str,
    judge_model_id: str,
    runs_per_call: int,
    generation_mode: Optional[str],
) -> int:
    """Count LLM-judge API calls that would actually fire for
    ``judge_model_id`` across all the project's enabled LLM-judge configs.

    The project's `evaluation_config.evaluation_configs` lists every
    metric configured. Only configs whose `metric` starts with
    `llm_judge_` cost API tokens — deterministic metrics (BERTScore,
    BLEU, ROUGE, semsim, METEOR, MoverScore, coherence, exact_match)
    are compute-only.

    For each LLM-judge config that names this judge in its
    `metric_parameters.judges[].judge_model_id`:

    - Resolve subjects per `prediction_fields` entry:
        * `__all_model__`         → every completed generation
        * `__all_human__`         → every annotation
        * starts with `human:`    → every annotation (the suffix is the
                                    field inside the annotation, not a
                                    subject filter)
        * any other plain string  → the worker auto-evaluates the field
                                    on BOTH models AND humans (services/
                                    workers/tasks.py around lines 234,
                                    3289-3291) — so the cost has to as
                                    well, otherwise the human-side bill
                                    is invisible. Returns generations
                                    AND annotations.
    - Multiply by `runs` from the judge spec.
    - For mode='missing', subtract subjects whose `task_evaluations`
      row is already scored under the matching field_name pattern
      `<metric>-<config_id>|<pred_field_normalized>|...`.

    Returns the total API-call count across all judge configs that
    target ``judge_model_id``.
    """
    cfgs = _load_llm_judge_configs(db, project_id, judge_model_id)
    if not cfgs:
        return 0

    # Resolve the project's universe of subjects once.
    gen_ids_by_field = _completed_generation_ids(db, project_id)
    annotation_ids = _annotation_ids(db, project_id)

    total = 0
    for cfg in cfgs:
        runs = cfg["runs"] * max(runs_per_call, 1)
        # `runs_per_call` is the modal-level "runs across this trigger";
        # `cfg["runs"]` is per-judge in this config. Multiply because
        # each judge invocation is its own API call.
        for pf in cfg["prediction_fields"]:
            subj_keys = _subjects_for_pred_field(
                pf, gen_ids_by_field=gen_ids_by_field,
                annotation_ids=annotation_ids,
            )
            if generation_mode == "missing":
                done = _already_scored_subjects(
                    db, project_id, metric_id=cfg["metric"], pred_field=pf
                )
                missing = [s for s in subj_keys if s not in done]
                total += len(missing) * runs
            else:
                total += len(subj_keys) * runs
    return total


def _load_llm_judge_configs(db: Session, project_id: str, judge_model_id: str) -> List[Dict[str, Any]]:
    """Pull the project's enabled LLM-judge configs that name this
    `judge_model_id` in their judges ensemble. Returns dicts with
    `metric` (id), `prediction_fields`, and `runs` (for this judge)."""
    from project_models import Project
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        return []
    eval_cfg = proj.evaluation_config or {}
    if not isinstance(eval_cfg, dict):
        try:
            import json as _json
            eval_cfg = _json.loads(eval_cfg)
        except Exception:
            return []
    out: List[Dict[str, Any]] = []
    for c in eval_cfg.get("evaluation_configs") or []:
        if c.get("enabled") is False:
            continue
        metric = c.get("metric") or ""
        if not metric.startswith("llm_judge_"):
            continue
        params = c.get("metric_parameters") or {}
        # Two ensemble shapes the codebase uses:
        # 1. judges: [{judge_model_id, runs}]            (preferred)
        # 2. judge_model + runs_per_judge                (legacy single-judge)
        runs_for_this_judge = 0
        if isinstance(params.get("judges"), list):
            for j in params["judges"]:
                if (j or {}).get("judge_model_id") == judge_model_id:
                    runs_for_this_judge = max(int(j.get("runs") or 1), 1)
                    break
        elif params.get("judge_model") == judge_model_id:
            runs_for_this_judge = max(int(params.get("runs_per_judge") or 1), 1)
        if runs_for_this_judge == 0:
            continue
        out.append(
            {
                "metric": metric,
                "prediction_fields": list(c.get("prediction_fields") or []),
                "runs": runs_for_this_judge,
            }
        )
    return out


def _completed_generation_ids(db: Session, project_id: str) -> List[str]:
    """All completed generation ids for the project. Cached scope —
    helper resolves fields against this list rather than re-querying."""
    from project_models import Task
    from models import Generation
    rows = (
        db.query(Generation.id)
        .join(Task, Task.id == Generation.task_id)
        .filter(Task.project_id == project_id, Generation.status == "completed")
        .all()
    )
    return [r[0] for r in rows]


def _annotation_ids(db: Session, project_id: str) -> List[str]:
    from project_models import Annotation, Task
    rows = (
        db.query(Annotation.id)
        .join(Task, Task.id == Annotation.task_id)
        .filter(Task.project_id == project_id)
        .all()
    )
    return [r[0] for r in rows]


def _subjects_for_pred_field(
    pred_field: str,
    *,
    gen_ids_by_field: List[str],
    annotation_ids: List[str],
) -> List[tuple]:
    """Return a list of subject keys for one `prediction_fields` entry.

    Each key is `(kind, id)` where kind ∈ {'generation','annotation'}.

    Mirrors the worker's resolution at services/workers/tasks.py:234
    and the human-eval block around line 3289-3291: a plain field name
    (no `model:`/`human:`/`__all_*__` prefix) gets auto-prefixed to
    `human:<field>` for annotation context AND used as a model field —
    so the cost includes both subject sets, matching what the worker
    will actually run.
    """
    if pred_field == "__all_model__":
        return [("generation", gid) for gid in gen_ids_by_field]
    if pred_field == "__all_human__" or pred_field.startswith("human:"):
        return [("annotation", aid) for aid in annotation_ids]
    if pred_field.startswith("model:"):
        return [("generation", gid) for gid in gen_ids_by_field]
    # Plain field name — both sides.
    return [("generation", gid) for gid in gen_ids_by_field] + [
        ("annotation", aid) for aid in annotation_ids
    ]


def _already_scored_subjects(
    db: Session, project_id: str, *, metric_id: str, pred_field: str
) -> set:
    """Return subject keys (`(kind, id)`) already scored for this
    metric+pred_field combination — i.e. what the worker would skip
    under `evaluate_missing_only`.

    field_name in `task_evaluations` follows the convention
    `<metric>-<config_id>|<pred_field_normalized>|<reference>`.
    The `<config_id>` suffix is unique per metric instance, so we
    match on prefix `<metric>-`. Per worker logic, plain field names
    are recorded with the `human:` prefix in annotation context — so a
    plain pred_field maps to two field_name patterns, one for each
    subject kind.
    """
    from models import TaskEvaluation

    if pred_field.startswith("human:") or pred_field == "__all_human__":
        # Annotation-side field. Match the prefixed form on the
        # annotation_id side only.
        norm = pred_field
        subject_col = TaskEvaluation.annotation_id
    elif pred_field == "__all_model__" or pred_field.startswith("model:"):
        norm = pred_field
        subject_col = TaskEvaluation.generation_id
    else:
        # Plain — recorded both as `<pf>` (model side) and `human:<pf>`
        # (annotation side). Run two queries and union.
        model_done = _scored_for(
            db, project_id, metric_id=metric_id, pred_field_norm=pred_field,
            subject_col=TaskEvaluation.generation_id, kind="generation",
        )
        human_done = _scored_for(
            db, project_id, metric_id=metric_id,
            pred_field_norm=f"human:{pred_field}",
            subject_col=TaskEvaluation.annotation_id, kind="annotation",
        )
        return model_done | human_done
    return _scored_for(
        db, project_id, metric_id=metric_id, pred_field_norm=norm,
        subject_col=subject_col,
        kind="annotation" if subject_col is TaskEvaluation.annotation_id else "generation",
    )


def _scored_for(
    db: Session, project_id: str, *, metric_id: str, pred_field_norm: str,
    subject_col, kind: str,
) -> set:
    from models import TaskEvaluation, EvaluationRun
    rows = (
        db.query(subject_col)
        .join(EvaluationRun, EvaluationRun.id == TaskEvaluation.evaluation_id)
        .filter(
            EvaluationRun.project_id == project_id,
            TaskEvaluation.field_name.like(f"{metric_id}-%|{pred_field_norm}|%"),
            TaskEvaluation.metrics.isnot(None),
            TaskEvaluation.error_message.is_(None),
            subject_col.isnot(None),
        )
        .all()
    )
    return {(kind, r[0]) for r in rows if r[0] is not None}


def _count_cells_to_generate(
    db: Session,
    project_id: str,
    model_id: str,
    structure_keys: Optional[List[str]],
    generation_mode: Optional[str],
) -> int:
    """Count (task, structure) cells that would actually fire for `model_id`.

    Mirrors the should_generate() decision in
    services/api/routers/generation_task_list.py around lines 555-585:

    - mode in ('all', 'single', None): every (task, structure) cell counts,
      regardless of existing generations.
    - mode == 'missing': a cell counts only when the latest matching
      `response_generations` row has status='failed' or no row exists
      at all. Cells whose latest is `completed`/`pending`/`running` are
      skipped — they wouldn't be re-queued.

    The cell count, not raw task count, is what drives cost: with one
    structure active and 14/15 tasks already succeeded, "Generate missing"
    fires 1 cell, not 15.
    """
    from project_models import Task
    from models import ResponseGeneration as DBResponseGeneration

    task_ids = [r[0] for r in db.query(Task.id).filter(Task.project_id == project_id).all()]
    if not task_ids:
        return 0
    structures: List[Optional[str]] = list(structure_keys) if structure_keys else [None]

    if generation_mode != "missing":
        return len(task_ids) * len(structures)

    # Issue #83: mode == "missing" — bulk-fetch latest status per cell in two
    # round-trips (exact structure_key matches + NULL fallback rows) instead
    # of one query per (task, structure). The Python merge below preserves
    # the exact-match-preferred-over-NULL precedence the worker uses.
    sk_values: List[str] = [s for s in structures if s is not None]
    has_none = None in structures

    exact_map: Dict[tuple, str] = {}
    if sk_values:
        rows_exact = (
            db.query(
                DBResponseGeneration.task_id,
                DBResponseGeneration.structure_key,
                DBResponseGeneration.status,
            )
            .filter(
                DBResponseGeneration.project_id == project_id,
                DBResponseGeneration.task_id.in_(task_ids),
                DBResponseGeneration.model_id == model_id,
                DBResponseGeneration.structure_key.in_(sk_values),
            )
            .distinct(
                DBResponseGeneration.task_id,
                DBResponseGeneration.structure_key,
            )
            .order_by(
                DBResponseGeneration.task_id,
                DBResponseGeneration.structure_key,
                DBResponseGeneration.created_at.desc(),
            )
            .all()
        )
        exact_map = {(r.task_id, r.structure_key): r.status for r in rows_exact}

    null_map: Dict[str, str] = {}
    if sk_values or has_none:
        rows_null = (
            db.query(
                DBResponseGeneration.task_id,
                DBResponseGeneration.status,
            )
            .filter(
                DBResponseGeneration.project_id == project_id,
                DBResponseGeneration.task_id.in_(task_ids),
                DBResponseGeneration.model_id == model_id,
                DBResponseGeneration.structure_key.is_(None),
            )
            .distinct(DBResponseGeneration.task_id)
            .order_by(
                DBResponseGeneration.task_id,
                DBResponseGeneration.created_at.desc(),
            )
            .all()
        )
        null_map = {r.task_id: r.status for r in rows_null}

    cells = 0
    for task_id in task_ids:
        for sk in structures:
            if sk is not None:
                status_val = exact_map.get((task_id, sk))
                if status_val is None:
                    status_val = null_map.get(task_id)
            else:
                status_val = null_map.get(task_id)
            if status_val is None or status_val == "failed":
                cells += 1
    return cells


@router.post("/cost-estimate", response_model=CostEstimateResponse)
def estimate_cost(
    request: CostEstimateRequest,
    raw_request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> CostEstimateResponse:
    """Estimate total cost for a planned generation or evaluation trigger."""

    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(raw_request)
    if not check_project_accessible(db, current_user, request.project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Pick the right model set to price.
    target_models = list(request.model_ids)
    if request.mode == "evaluation" and request.judge_models:
        # For evaluation cost, the spend is on the judge calls — the target
        # model has already been called during generation.
        target_models = list(request.judge_models)

    if not target_models:
        raise HTTPException(status_code=400, detail="model_ids required (or judge_models for evaluation)")

    # Sample texts to estimate input length.
    # - generation: raw task data (Sachverhalt) is what fills the prompt.
    # - evaluation: the judge sees `judge_prompt + reference + prediction`
    #   where the prediction (prior generation output) is by far the
    #   largest variable component. Sampling raw tasks here under-counts
    #   eval input tokens by 3-5× on Gutachten-style outputs and
    #   produces an embarrassingly small dollar figure.
    if request.mode == "evaluation":
        sample_texts = sample_prediction_inputs(
            db=db,
            project_id=request.project_id,
            sample_size=request.task_sample_size,
            seed=42,
        )
    else:
        sample_texts = sample_task_texts(
            db=db,
            project_id=request.project_id,
            sample_size=request.task_sample_size,
            seed=42,
        )
    if not sample_texts:
        sample_texts = [""]

    from project_models import Task

    total_tasks = db.query(Task).filter(Task.project_id == request.project_id).count()
    if total_tasks == 0:
        raise HTTPException(status_code=400, detail="Project has no tasks to estimate against")

    # Project-default max_tokens is the fallback when a model has no
    # per-model override. Per-model values (e.g. 32 000 for gpt-5.5-pro)
    # are read inside the loop because they vary by model.
    project_gen_config = project.generation_config or {}
    gen_params = project_gen_config.get("selected_configuration", {}).get("parameters", {})
    project_default_max_tokens = int(gen_params.get("max_tokens", 4000) or 4000)

    # Subject counting (issue #69): when the eval modal sends configs, size
    # the cost by actual (subject × prediction_field) cells the run will
    # touch, narrowed by model_ids/annotator_user_ids. Falls back to the
    # legacy tasks-count multiplier ONLY when no configs are supplied so
    # the cell-counting endpoint stays backwards-compatible. When configs
    # ARE supplied but yield zero subjects (e.g. user narrowed to a model
    # with no generations) the cost is genuinely zero — gating on
    # `subject_count > 0` here would incorrectly flip back to a full-sweep
    # estimate, so we gate on `evaluation_configs` instead.
    subject_count = 0
    if request.mode == "evaluation":
        subject_count = _count_eval_subjects(
            db=db,
            project_id=request.project_id,
            evaluation_configs=request.evaluation_configs,
            model_ids=request.model_ids or None,
            annotator_user_ids=request.annotator_user_ids,
        )
    eval_uses_subject_count = (
        request.mode == "evaluation" and bool(request.evaluation_configs)
    )

    per_model_costs: List[PerModelCost] = []
    total_usd = 0.0
    token_breakdown: Optional[TokenBreakdown] = None

    for model_id in target_models:
        # Each model can carry its own max_tokens override and its own
        # reasoning-tier classification. Cost estimates must reflect what
        # the worker will actually send, not the project default.
        model_max_tokens = _resolve_max_tokens_for_model(
            project_gen_config, model_id, project_default_max_tokens
        )
        llm_model_row = db.query(LLMModel).filter(LLMModel.id == model_id).first()
        is_reasoning = bool(llm_model_row and _is_reasoning_model(llm_model_row))
        if request.mode == "evaluation":
            # Judges emit a small structured score + reasoning, not the
            # full max_tokens budget — see _EVAL_OUTPUT_UTILIZATION.
            utilization = _EVAL_OUTPUT_UTILIZATION
        elif is_reasoning:
            utilization = _REASONING_OUTPUT_UTILIZATION
        else:
            utilization = _DEFAULT_OUTPUT_UTILIZATION

        # Cell count is per-model and per-mode:
        # - generation: count (task × structure) cells with no recent
        #   successful response_generations row (for mode=missing).
        # - evaluation: count (task × run_index) judge calls with no
        #   successful evaluation_judge_runs row for this judge model.
        # Without the eval-specific path the estimator would query the
        # generations table for evaluation runs — counting whichever
        # generations were missing instead of which judge calls are
        # missing. Different question, different answer.
        if request.mode == "evaluation":
            cells = _count_evaluation_judge_calls(
                db=db,
                project_id=request.project_id,
                judge_model_id=model_id,
                runs_per_call=request.runs_per_call,
                generation_mode=request.generation_mode,
            )
            # The judge-call count already factors run_index, so don't
            # multiply by runs_per_call again below.
            runs_already_counted = True
        else:
            cells = _count_cells_to_generate(
                db=db,
                project_id=request.project_id,
                model_id=model_id,
                structure_keys=request.structure_keys,
                generation_mode=request.generation_mode,
            )
            runs_already_counted = False

        token_est = estimate_tokens_for_calls(
            project_id=request.project_id,
            model_id=model_id,
            prompt_samples=sample_texts,
            max_output_tokens=model_max_tokens,
            output_utilization=utilization,
        )
        if token_breakdown is None:
            token_breakdown = TokenBreakdown(
                input_mean=token_est.input_mean,
                input_p95=token_est.input_p95,
                output_estimate=token_est.output_estimate,
                encoding=token_est.encoding_name,
            )

        pricing = _resolve_pricing(db, model_id)
        pricing is not None
        if pricing is None:
            per_model_costs.append(PerModelCost(
                model_id=model_id,
                per_call_usd=0.0,
                per_run_usd=0.0,
                total_usd=0.0,
                pricing_known=False,
                cells_to_generate=cells,
            ))
            continue

        per_call = (
            (token_est.input_mean / 1000.0) * pricing["input_per_1k"]
            + (token_est.output_estimate / 1000.0) * pricing["output_per_1k"]
        )
        # Eval mode with explicit configs (issue #69) prices the actual
        # (subject × prediction_field) cell count. Otherwise, the legacy
        # cells-based formula applies — for generation that's
        # `tasks × structure_keys × samples_per_task` (so structure_keys
        # multiplication from main is preserved); for eval-without-configs
        # `cells` is `(tasks × run_index)` and the runs multiplier is
        # already folded in (`runs_already_counted=True`).
        if eval_uses_subject_count:
            per_run = per_call * subject_count * request.samples_per_task
            model_total = per_run * request.runs_per_call
        else:
            per_run = per_call * cells * request.samples_per_task
            model_total = per_run if runs_already_counted else per_run * request.runs_per_call

        per_model_costs.append(PerModelCost(
            model_id=model_id,
            per_call_usd=round(per_call, 4),
            per_run_usd=round(per_run, 4),
            total_usd=round(model_total, 2),
            pricing_known=True,
            cells_to_generate=cells,
        ))
        total_usd += model_total

    if token_breakdown is None:  # all models lacked pricing; still surface tokens
        token_breakdown = TokenBreakdown(
            input_mean=0.0,
            input_p95=0.0,
            output_estimate=0.0,
            encoding="unavailable",
        )

    mode_note = (
        " Counting only the cells that would actually fire under "
        f"generation_mode='{request.generation_mode}'"
        if request.generation_mode == "missing"
        else " Counting every (task × structure) cell"
    )
    if request.mode == "evaluation":
        utilization_note = (
            " For evaluation, input is sampled from recent generation outputs "
            "(the prediction the judge sees) and output utilization is 15 % of "
            "max_tokens — judges emit a short score + rationale, not a full "
            "completion."
        )
    else:
        utilization_note = (
            " Output utilization is 90 % of max_tokens for reasoning-tier "
            "models (Pro/o-series) and 60 % otherwise."
        )
    # E2 (issue #69): the eval-with-configs path introduces additional
    # approximation sources beyond the ±20% disclaimer. Surface them when
    # active (see the `if eval_uses_subject_count` branch below) so the
    # user knows the variance band is wider for scoped runs.
    note = (
        "Estimate accuracy ± ~20%. Token counts use cl100k_base as a proxy "
        "for non-OpenAI models. Each model's max_tokens is read from "
        "selected_configuration.model_configs, falling back to the project "
        "default." + utilization_note + mode_note + "."
    )
    if eval_uses_subject_count:
        note += (
            " Eval-mode estimates assume each generation populates every "
            "prediction_field and price every judge in the ensemble at the "
            "maximum runs across that ensemble. Sparse fields or asymmetric "
            "judge run counts can shift the actual cost by ±20–40%."
        )

    from datetime import datetime, timezone

    return CostEstimateResponse(
        mode=request.mode,
        runs_per_call=request.runs_per_call,
        sample_size=len(sample_texts),
        tasks_total=total_tasks,
        subject_count=subject_count,
        # UTC ISO timestamp; the frontend formats to local time for display.
        estimated_at=datetime.now(timezone.utc).isoformat(),
        per_model=per_model_costs,
        total_usd=round(total_usd, 2),
        token_estimate=token_breakdown,
        note=note,
    )

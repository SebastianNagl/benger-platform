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
from services.token_estimation import estimate_tokens_for_calls, sample_task_texts

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
                    f"when mode == 'generation'"
                )
        return self


class PerModelCost(BaseModel):
    model_id: str
    per_call_usd: float
    per_run_usd: float
    total_usd: float
    pricing_known: bool


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
            .filter(Task.project_id == project_id, Annotation.was_cancelled == False)  # noqa: E712
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

    # Sample task texts for prompt-length estimation. For evaluation we use
    # the same texts; the actual evaluation prompt wraps prediction +
    # reference but the order of magnitude is similar.
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

    # Use the project's configured max_tokens to bound the output estimate.
    gen_params = (project.generation_config or {}).get("selected_configuration", {}).get("parameters", {})
    max_tokens = int(gen_params.get("max_tokens", 4000) or 4000)

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
        token_est = estimate_tokens_for_calls(
            project_id=request.project_id,
            model_id=model_id,
            prompt_samples=sample_texts,
            max_output_tokens=max_tokens,
        )
        if token_breakdown is None:
            token_breakdown = TokenBreakdown(
                input_mean=token_est.input_mean,
                input_p95=token_est.input_p95,
                output_estimate=token_est.output_estimate,
                encoding=token_est.encoding_name,
            )

        pricing = _resolve_pricing(db, model_id)
        pricing_known = pricing is not None
        if pricing is None:
            per_model_costs.append(PerModelCost(
                model_id=model_id,
                per_call_usd=0.0,
                per_run_usd=0.0,
                total_usd=0.0,
                pricing_known=False,
            ))
            continue

        per_call = (
            (token_est.input_mean / 1000.0) * pricing["input_per_1k"]
            + (token_est.output_estimate / 1000.0) * pricing["output_per_1k"]
        )
        # Eval mode with explicit configs prices the actual cell count;
        # everything else (generation, or eval without configs) keeps the
        # tasks-based legacy formula.
        units_per_run = subject_count if eval_uses_subject_count else total_tasks
        per_run = per_call * units_per_run * request.samples_per_task
        model_total = per_run * request.runs_per_call

        per_model_costs.append(PerModelCost(
            model_id=model_id,
            per_call_usd=round(per_call, 4),
            per_run_usd=round(per_run, 4),
            total_usd=round(model_total, 2),
            pricing_known=True,
        ))
        total_usd += model_total

    if token_breakdown is None:  # all models lacked pricing; still surface tokens
        token_breakdown = TokenBreakdown(
            input_mean=0.0,
            input_p95=0.0,
            output_estimate=0.0,
            encoding="unavailable",
        )

    # E2: the eval-with-configs path introduces additional approximation
    # sources beyond the original ±20% disclaimer. Surface them when active
    # so the user knows the variance band is wider for scoped runs.
    note = (
        "Estimate accuracy ± ~20%. Token counts use cl100k_base as a proxy "
        "for non-OpenAI models; output utilization assumes 60% of the "
        "configured max_tokens. Pricing read from llm_models DB."
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

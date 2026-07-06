#!/usr/bin/env python3
"""Backfill `display_name` on existing project evaluation configs.

`EvaluationConfig.display_name` (stored inside ``project.evaluation_config``'s
``evaluation_configs`` list) is what the evaluations-page method dropdown shows.
Historically every config was seeded with the generic metric default (e.g.
``"Classic LLM Judge"``), so two `llm_judge_*` configs that differ only by judge
model render identically and can't be told apart.

This one-time backfill enriches judge-based configs by appending the resolved
judge model, matching the frontend helper ``computeDefaultEvalName`` in
``services/frontend/src/lib/evaluation/evalName.ts`` EXACTLY:

  * only ``llm_judge_*`` metrics with a resolved judge model are touched;
  * judge descriptor = per-distinct-model ``judge_model_id`` with runs SUMMED
    across ``metric_parameters.judges`` entries (default 1 run), rendered as
    ``model`` or ``f"{model} ×{runs}"``, first-appearance order, joined by
    ``" + "``; else the legacy ``metric_parameters.judge_model`` (1 run); else
    none. Run counts are included because two configs can share a model and
    differ only by run count (e.g. gpt-5-mini ×1 vs ×3);
  * base label = the config's existing ``display_name`` or its ``metric``;
  * result = ``f"{base} ({descriptor})"``;
  * idempotent: if ``base`` already ends with ``f"({descriptor})"`` it's left as-is;
  * non-judge configs (korrektur_*, automated metrics, judge-less) are untouched.

Only configs whose computed name actually differs from the stored one are
rewritten. Because ``evaluation_config`` is a JSON column, a nested in-place
mutation isn't seen by SQLAlchemy — we reassign the whole dict and
``flag_modified`` it. Committed once, only under ``--apply``.

Idempotent: rewritten rows already carry the enriched name, so re-running finds
nothing to change.

Usage (inside the api container):
  python /app/scripts/backfill_eval_config_display_names.py            # dry-run (default)
  python /app/scripts/backfill_eval_config_display_names.py --apply    # commit
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Optional

# --- Pure naming logic (no DB, unit-testable) --------------------------------
#
# Mirrors services/frontend/src/lib/evaluation/evalName.ts. Keep the two in sync.


def _resolve_judge_model(params: Any) -> Optional[str]:
    """Resolve the judge-model descriptor for a config's metric_parameters.

    Rule (must stay identical to the frontend ``evalName.ts``):
      1. Build ``(model_id, runs)`` pairs from ``judges`` — each element's
         ``judge_model_id`` with its ``runs`` (default 1 when missing). If
         ``judges`` is absent/empty but ``judge_model`` is set, treat as a single
         ``(judge_model, 1)``.
      2. Sum runs per DISTINCT model, preserving first-appearance order.
      3. Per model token = ``model`` when summed runs <= 1, else
         ``f"{model} ×{runs}"`` (× multiplication sign).
      4. Join tokens with ``" + "``.

    Returns ``None`` when no model resolves.
    """
    if not isinstance(params, dict):
        return None

    pairs: list[tuple[str, int]] = []
    judges = params.get("judges")
    if isinstance(judges, list) and judges:
        for j in judges:
            if not isinstance(j, dict):
                continue
            mid = j.get("judge_model_id")
            if not isinstance(mid, str) or not mid:
                continue
            raw_runs = j.get("runs")
            runs = raw_runs if isinstance(raw_runs, int) and not isinstance(raw_runs, bool) else 1
            pairs.append((mid, runs))
    else:
        legacy = params.get("judge_model")
        if isinstance(legacy, str) and legacy:
            pairs.append((legacy, 1))

    if not pairs:
        return None

    order: list[str] = []
    runs_by_model: dict[str, int] = {}
    for model, runs in pairs:
        if model not in runs_by_model:
            order.append(model)
        runs_by_model[model] = runs_by_model.get(model, 0) + runs

    tokens = [
        model if runs_by_model[model] <= 1 else f"{model} ×{runs_by_model[model]}"
        for model in order
    ]
    return " + ".join(tokens)


def compute_default_eval_name(config: dict) -> str:
    """Compute the enriched display name for a single eval-config dict.

    Returns the name unchanged for non-judge / judge-less configs, and is
    idempotent for already-enriched names.
    """
    metric = config.get("metric") or ""
    base = config.get("display_name") or metric
    model = _resolve_judge_model(config.get("metric_parameters"))
    if metric.startswith("llm_judge_") and model:
        if base.endswith(f"({model})"):
            return base
        return f"{base} ({model})"
    return base


def _configs_of(evaluation_config: Any) -> Optional[list]:
    """Return the ``evaluation_configs`` list if the project config is shaped
    like ``{"evaluation_configs": [...]}``; otherwise ``None``."""
    if not isinstance(evaluation_config, dict):
        return None
    configs = evaluation_config.get("evaluation_configs")
    if not isinstance(configs, list):
        return None
    return configs


def plan_project(evaluation_config: Any) -> list[tuple[int, str, str]]:
    """Pure planner: return the list of ``(index, old_name, new_name)`` changes
    for a single project's ``evaluation_config`` dict. Empty when nothing
    changes. Does not mutate the input."""
    configs = _configs_of(evaluation_config)
    if configs is None:
        return []
    changes: list[tuple[int, str, str]] = []
    for i, cfg in enumerate(configs):
        if not isinstance(cfg, dict):
            continue
        old = cfg.get("display_name") or cfg.get("metric") or ""
        new = compute_default_eval_name(cfg)
        if new != old:
            changes.append((i, old, new))
    return changes


# --- DB wiring (lazy heavy imports live in main) -----------------------------


def _bootstrap_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (
        "/shared",
        "/app",
        os.path.dirname(here),  # services/api when run from the repo
        os.path.join(os.path.dirname(os.path.dirname(here)), "shared"),  # services/shared
    ):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="print the plan, do not commit (default)",
    )
    mode.add_argument("--apply", action="store_true", help="commit the backfill")
    args = parser.parse_args()
    apply_mode = bool(args.apply)

    _bootstrap_path()
    import models  # noqa: F401  — register User/... before relationships
    import project_models  # noqa: F401
    from sqlalchemy.orm import attributes
    from database import SessionLocal
    from project_models import Project

    db = SessionLocal()
    scanned = 0
    projects_changed = 0
    configs_changed = 0
    try:
        if not apply_mode:
            print("=== DRY RUN (no changes will be committed) ===")

        projects = (
            db.query(Project)
            .filter(Project.evaluation_config.isnot(None))
            .all()
        )
        for project in projects:
            configs = _configs_of(project.evaluation_config)
            if configs is None:
                continue
            scanned += 1
            changes = plan_project(project.evaluation_config)
            if not changes:
                continue
            projects_changed += 1
            configs_changed += len(changes)
            print(f"\nproject={project.id}: {len(changes)} config(s) to rename")
            for idx, old, new in changes:
                print(f"  [{idx}] {old!r} -> {new!r}")
            if apply_mode:
                for idx, _old, new in changes:
                    configs[idx]["display_name"] = new
                # JSON column: reassign + flag so SQLAlchemy detects the change.
                attributes.flag_modified(project, "evaluation_config")

        print("\n=== summary ===")
        print(f"  projects scanned (with evaluation_configs): {scanned}")
        print(f"  projects with changes:                      {projects_changed}")
        print(f"  configs renamed:                            {configs_changed}")

        if apply_mode:
            db.commit()
            print("\napplied: committed display_name updates.")
        else:
            print("\n(dry run — re-run with --apply to commit)")
        return 0
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"ERROR: {e}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

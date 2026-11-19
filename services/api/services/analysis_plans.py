"""Analysis plans: named analysis specs saved with a project's evaluation
configuration (``evaluation_config.analysis_plans``, CORE 2.69).

A plan is ``{id, name, spec, spec_hash, saved_at, saved_by}``. ``spec`` is
the spec as its author wrote it; ``spec_hash`` is the hash of its normalized
form (``analysis.spec.spec_hash``), the same hash an analysis run started
from that spec records, so a run links to the plan it used by hash alone.
``spec_hash``, ``saved_at`` and ``saved_by`` are server-owned: whatever a
client sends for them is replaced. ``saved_at`` and ``saved_by`` change only
when a plan's spec hash changes (or the plan is new), so renaming a plan
keeps the record of when its spec was saved.

Both writers of ``evaluation_config`` (``PUT /evaluations/projects/{id}/
evaluation-config`` and ``PATCH /projects/{id}``) run
:func:`validate_analysis_plans` through ``validate_evaluation_config_write``
and then stamp with :func:`apply_analysis_plans_write`. The list replaces
the stored list as a whole, like every list of the document, and ``null``
deletes it. The engine validates each spec (``analysis.spec.normalize_spec``);
a refused save answers 422 ``invalid_analysis_plan`` with every problem,
each prefixed with the plan's path (``/analysis_plans/<i>/spec/...``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

ANALYSIS_PLANS_KEY = "analysis_plans"
MAX_PLANS = 50
MAX_PLAN_NAME = 200
MAX_PLAN_ID = 64


def _spec_path(index: int, error: str) -> str:
    """An engine message (``/inputs: ...`` or ``/: ...``) under the plan."""
    base = f"/{ANALYSIS_PLANS_KEY}/{index}/spec"
    if error.startswith("/: "):
        return base + error[1:]
    if error.startswith("/"):
        return base + error
    return f"{base}: {error}"


def _normalize_plans(value: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Each plan as ``{id (or None), name, spec, spec_hash}`` and every
    problem found. Server-owned and unknown keys are dropped."""
    from analysis.spec import SpecError, normalize_spec, spec_hash

    if not isinstance(value, list):
        return [], [f"/{ANALYSIS_PLANS_KEY}: must be a list of plans"]
    errors: List[str] = []
    if len(value) > MAX_PLANS:
        errors.append(f"/{ANALYSIS_PLANS_KEY}: at most {MAX_PLANS} plans")
    plans: List[Dict[str, Any]] = []
    seen_ids: Dict[str, int] = {}
    for i, entry in enumerate(value[:MAX_PLANS]):
        where = f"/{ANALYSIS_PLANS_KEY}/{i}"
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object with name and spec")
            continue
        plan_id = entry.get("id")
        if plan_id is not None:
            if not isinstance(plan_id, str) or not plan_id.strip() or len(plan_id) > MAX_PLAN_ID:
                errors.append(f"{where}/id: must be a non-empty string of at most {MAX_PLAN_ID} characters")
                plan_id = None
            elif plan_id in seen_ids:
                errors.append(f"{where}/id: duplicate plan id {plan_id!r} (also plan {seen_ids[plan_id]})")
            else:
                seen_ids[plan_id] = i
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{where}/name: must be a non-empty string")
            name = None
        elif len(name.strip()) > MAX_PLAN_NAME:
            errors.append(f"{where}/name: at most {MAX_PLAN_NAME} characters")
        spec = entry.get("spec")
        if not isinstance(spec, dict):
            errors.append(f"{where}/spec: must be an analysis spec object")
            continue
        try:
            digest = spec_hash(normalize_spec(spec))
        except SpecError as exc:
            errors.extend(_spec_path(i, e) for e in exc.errors)
            continue
        if name is not None:
            plans.append({"id": plan_id, "name": name.strip(), "spec": spec, "spec_hash": digest})
    return plans, errors


def validate_analysis_plans(value: Any) -> None:
    """Raise 422 ``invalid_analysis_plan`` unless ``value`` is a valid plan
    list (``None`` deletes the key and passes)."""
    if value is None:
        return
    _, errors = _normalize_plans(value)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_analysis_plan",
                "message": "An analysis plan is invalid",
                "errors": errors,
            },
        )


def apply_analysis_plans_write(
    stored_config: Any,
    merged: Dict[str, Any],
    body: Any,
    *,
    actor_id: Optional[str],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """``merged`` with the body's plans normalized and stamped.

    Call after :func:`validate_analysis_plans` passed. A body without the
    key leaves the stored plans as they are. A new plan gets an id; a plan
    whose id and spec hash match a stored plan keeps its ``saved_at`` and
    ``saved_by``, any other plan is stamped with ``now`` and ``actor_id``.
    """
    if not isinstance(body, dict) or body.get(ANALYSIS_PLANS_KEY) is None:
        return merged
    plans, errors = _normalize_plans(body[ANALYSIS_PLANS_KEY])
    if errors:  # validate_analysis_plans ran first; keep the write safe anyway
        validate_analysis_plans(body[ANALYSIS_PLANS_KEY])
    stored = stored_config.get(ANALYSIS_PLANS_KEY) if isinstance(stored_config, dict) else None
    previous = {
        p.get("id"): p
        for p in (stored if isinstance(stored, list) else [])
        if isinstance(p, dict) and isinstance(p.get("id"), str)
    }
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    out = []
    for plan in plans:
        plan_id = plan["id"] or str(uuid.uuid4())
        before = previous.get(plan_id)
        if before is not None and before.get("spec_hash") == plan["spec_hash"]:
            saved_at, saved_by = before.get("saved_at"), before.get("saved_by")
        else:
            saved_at, saved_by = stamp, actor_id
        out.append(
            {
                "id": plan_id,
                "name": plan["name"],
                "spec": plan["spec"],
                "spec_hash": plan["spec_hash"],
                "saved_at": saved_at,
                "saved_by": saved_by,
            }
        )
    result = dict(merged)
    result[ANALYSIS_PLANS_KEY] = out
    return result

"""Prompt profiles and the structured assessment block of ``llm_judge_rubric``.

Two opt-in ``metric_parameters`` of the rubric judge live here:

``prompt_profile``
    Selects the fixed system prompt and closing rules that wrap the stored
    template. ``"default"`` is the Bewertungsbogen wording in
    ``llm_judge_evaluator``; editions register more (the extended package
    registers ``"zweites_examen"``) via :func:`register_rubric_prompt_profile`.
    An unknown profile is a config error, never a silent fallback: grading a
    second-exam file under first-exam framing would look like a valid score.

``structured_assessment``
    Asks the judge for the diagnosis block of the second-exam assessor
    (``benger_assessor_v1``, Benchmark v2): ``assessment_status``,
    ``work_products``, ``supplementary_reviews``, ``error_chains``,
    ``review_reasons`` and ``improvements``. The block is diagnosis only. It
    never changes a score; the total and the grade stay computed in code.
    Status semantics follow the proposal's reference post-processor:

    * ``scored`` — a normal row.
    * ``review_required`` — scores are provisional
      (``score_status="provisional"``, ``aggregation_eligible=False``); the
      row is kept, never dropped.
    * ``not_evaluable`` — inputs missing or broken: no value, no grade
      (``score_status="unavailable"``). An empty or refused answer is NOT
      this status; it is scorable with 0.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

ASSESSMENT_STATUSES = ("scored", "review_required", "not_evaluable")
WORK_PRODUCT_STATUSES = ("fulfilled", "partial", "missing", "wrong_product", "unclear")
SUPPLEMENTARY_STATUSES = ("not_required", "fulfilled", "partial", "missing", "unclear")
MAX_IMPROVEMENTS = 3

SCORE_STATUS_BY_ASSESSMENT = {
    "scored": "scored",
    "review_required": "provisional",
    "not_evaluable": "unavailable",
}

_PROFILES: Dict[str, Dict[str, str]] = {}


def register_rubric_prompt_profile(name: str, system_prompt: str, closing_rules: str) -> None:
    """Register (or replace) a rubric judge prompt profile."""
    if not name or not system_prompt or not closing_rules:
        raise ValueError("a rubric prompt profile needs a name, a system prompt and closing rules")
    _PROFILES[name] = {"system_prompt": system_prompt, "closing_rules": closing_rules}


def get_rubric_prompt_profile(name: str) -> Optional[Dict[str, str]]:
    """The registered profile, or None when no edition registered it."""
    return _PROFILES.get(name)


def registered_rubric_prompt_profiles() -> List[str]:
    return sorted(_PROFILES)


def _closed_object(properties: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_STRING = {"type": "string"}
_STRING_LIST = {"type": "array", "items": _STRING}


def assessment_schema_properties() -> Dict[str, Any]:
    """Top-level properties added to the strict rubric schema.

    Strict-mode subset only (no ``multipleOf``/``if``/``maxItems``); the
    rules the schema cannot express are enforced by
    :func:`normalize_assessment`.
    """
    return {
        "assessment_status": {"type": "string", "enum": list(ASSESSMENT_STATUSES)},
        "work_products": {
            "type": "array",
            "items": _closed_object(
                {
                    "product": _STRING,
                    "requirement_basis": _STRING,
                    "status": {"type": "string", "enum": list(WORK_PRODUCT_STATUSES)},
                    "reason": _STRING,
                }
            ),
        },
        "supplementary_reviews": {
            "type": "array",
            "items": _closed_object(
                {
                    "subject": _STRING,
                    "requirement_basis": _STRING,
                    "status": {"type": "string", "enum": list(SUPPLEMENTARY_STATUSES)},
                    "assumption": {"type": ["string", "null"]},
                    "reason": _STRING,
                }
            ),
        },
        "error_chains": {
            "type": "array",
            "items": _closed_object(
                {
                    "root_error": _STRING,
                    "dependent_consequences": _STRING_LIST,
                    "grading_treatment": _STRING,
                }
            ),
        },
        "review_reasons": _STRING_LIST,
        "improvements": _STRING_LIST,
    }


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _text_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [t for t in (_text(v) for v in value) if t]


def _entries(
    value: Any,
    text_keys: Tuple[str, ...],
    statuses: Tuple[str, ...],
    name: str,
    warnings: List[str],
    nullable_keys: Tuple[str, ...] = (),
) -> List[Dict[str, Any]]:
    """Keep well-formed list entries; report and drop the rest.

    Only OpenAI strict mode enforces the schema. Other providers can return
    anything, and one bad entry must not cost the whole diagnosis.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(f"{name}: not a list")
        return []
    kept: List[Dict[str, Any]] = []
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            warnings.append(f"{name}[{i}]: not an object")
            continue
        entry: Dict[str, Any] = {key: _text(item.get(key)) for key in text_keys}
        status = item.get("status")
        if status not in statuses:
            warnings.append(f"{name}[{i}].status: {status!r} is not one of {list(statuses)}")
            continue
        if not all(entry.values()):
            warnings.append(f"{name}[{i}]: empty text field")
            continue
        entry["status"] = status
        for key in nullable_keys:
            entry[key] = _text(item.get(key)) or None
        kept.append(entry)
    return kept


def normalize_assessment(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """The validated diagnosis block from a parsed judge body.

    Lenient where the reference post-processor is strict: a malformed field
    is dropped with a warning instead of failing the row, because the scores
    in the same body are still valid. Two rules fall back to a safe status:

    * an unknown or missing ``assessment_status`` becomes ``review_required``;
    * ``review_required``/``not_evaluable`` without any reason also becomes
      ``review_required`` with a generated reason, so a row never claims a
      problem nobody can see.
    """
    warnings: List[str] = []
    status = parsed.get("assessment_status")
    if status not in ASSESSMENT_STATUSES:
        warnings.append(f"assessment_status: {status!r} is not one of {list(ASSESSMENT_STATUSES)}")
        status = "review_required"

    review_reasons = _text_list(parsed.get("review_reasons"))
    if status == "scored" and review_reasons:
        warnings.append("scored with review_reasons: reasons kept, status unchanged")
    if status != "scored" and not review_reasons:
        if status == "not_evaluable":
            warnings.append("not_evaluable without review_reasons: downgraded to review_required")
            status = "review_required"
        review_reasons = ["Der Judge hat keinen Nachprüfungsgrund angegeben."]

    work_products = _entries(
        parsed.get("work_products"),
        ("product", "requirement_basis", "reason"),
        WORK_PRODUCT_STATUSES,
        "work_products",
        warnings,
    )
    supplementary_reviews = _entries(
        parsed.get("supplementary_reviews"),
        ("subject", "requirement_basis", "reason"),
        SUPPLEMENTARY_STATUSES,
        "supplementary_reviews",
        warnings,
        nullable_keys=("assumption",),
    )
    if not supplementary_reviews:
        warnings.append("supplementary_reviews: empty (the rubric asks for at least one entry)")

    error_chains: List[Dict[str, Any]] = []
    raw_chains = parsed.get("error_chains")
    if raw_chains is not None and not isinstance(raw_chains, list):
        warnings.append("error_chains: not a list")
    for i, item in enumerate(raw_chains if isinstance(raw_chains, list) else []):
        if not isinstance(item, dict) or not _text(item.get("root_error")):
            warnings.append(f"error_chains[{i}]: missing root_error")
            continue
        error_chains.append(
            {
                "root_error": _text(item.get("root_error")),
                "dependent_consequences": _text_list(item.get("dependent_consequences")),
                "grading_treatment": _text(item.get("grading_treatment")),
            }
        )

    improvements = _text_list(parsed.get("improvements"))
    if len(improvements) > MAX_IMPROVEMENTS:
        warnings.append(f"improvements: {len(improvements)} given, kept the first {MAX_IMPROVEMENTS}")
        improvements = improvements[:MAX_IMPROVEMENTS]

    return {
        "assessment_status": status,
        "score_status": SCORE_STATUS_BY_ASSESSMENT[status],
        "aggregation_eligible": status == "scored",
        "work_products": work_products,
        "supplementary_reviews": supplementary_reviews,
        "error_chains": error_chains,
        "review_reasons": review_reasons,
        "improvements": improvements,
        "validation_warnings": warnings,
    }


def not_evaluable_message(assessment: Dict[str, Any]) -> str:
    reasons = "; ".join(assessment.get("review_reasons") or [])
    return f"Judge: nicht bewertbar ({reasons})" if reasons else "Judge: nicht bewertbar"

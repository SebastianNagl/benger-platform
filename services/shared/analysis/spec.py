"""Analysis specs: validation, normalization and hashing.

A spec (JSON, ``schemas/analysis_spec.schema.json``) declares one analysis
of a variant experiment: which designs, systems and prompt structures feed
the frame, which measures derive outcomes from parsed fields, factors and
gold, which estimands (estimator, terms, fixed effects, variance estimator,
contrasts, equivalence bounds) to compute, and which families of tests to
adjust for multiplicity.

:func:`validate_spec` checks the structure against the JSON Schema and then
the semantic rules the schema cannot express. :func:`normalize_spec` fills
every default, in particular the inference conventions of every estimand,
so the stored normalized spec names each convention explicitly and its hash
(:func:`spec_hash`) changes whenever a convention does.

This module is pure Python (jsonschema only): the API validates specs
without the numeric stack.
"""

from __future__ import annotations

import copy
import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from analysis.canonical import json_hash
from analysis.expression import ExpressionError, parse_expression
from analysis.version import SPEC_VERSION

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schemas", "analysis_spec.schema.json")

#: Columns every frame carries; measure ids and factor names may not reuse them.
BASE_COLUMNS: Tuple[str, ...] = (
    "generation_id",
    "task_id",
    "system",
    "model_id",
    "structure_key",
    "run_index",
    "design",
    "unit",
    "parse_ok",
    "refusal",
    "truncated",
    "retried",
    "finish_reason",
)

#: The engine's defaults. Every estimand of a normalized spec carries the
#: full set, merged as: these defaults < spec ``conventions`` < estimand
#: ``conventions``.
DEFAULT_CONVENTIONS: Dict[str, Any] = {
    # Small-sample factor of robust variances. "statsmodels": cluster
    # G/(G-1) * (N-1)/(N-K) per clustering dimension (K = regressors left
    # after absorbing fixed effects), HC1 N/(N-K), iid RSS/(N-K).
    # "fixest": K also counts the fixed-effect levels not nested in a
    # cluster, two-way clustering uses min(G) for every component.
    # "none": no factor.
    "ssc": "statsmodels",
    # "normal": z statistics and normal quantiles. "t": t with G-1 degrees
    # of freedom for cluster variances (G = smallest cluster count), N-K
    # otherwise.
    "inference": "normal",
    "ci_level": 0.95,
    # "exact": the quantile of the inference distribution; a number fixes
    # the critical value (1.96 reproduces analyses that hard-code it).
    "ci_critical": "exact",
    # Equivalence: the contrast is equivalent when the (tost_level) CI lies
    # strictly inside the bounds; p_tost is the larger one-sided p.
    "tost_level": 0.90,
    # Drop regressors that are identically zero after absorbing fixed
    # effects (and say so) instead of fitting a singular design.
    "drop_zero_columns": True,
    # p-value of a contrast with a zero standard error: "nan", or
    # "null_match" (1 when the estimate equals the null within 1e-9, else 0).
    "degenerate_p": "nan",
    # Several fixed-effect sets under the within method are absorbed by
    # alternating projections until the largest change is below this.
    "fe_tolerance": 1e-12,
    "fe_max_iter": 10000,
}

ESTIMATOR_PARAMETER = {"mean_rate": "(mean)", "paired_within": "(difference)"}


class SpecError(ValueError):
    """An invalid spec. ``errors`` lists every problem found."""

    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors) if self.errors else "invalid spec")


@lru_cache(maxsize=1)
def spec_schema() -> Dict[str, Any]:
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _validator():
    import jsonschema

    schema = spec_schema()
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema)


def _path(err) -> str:
    parts = [str(p) for p in err.absolute_path]
    return "/" + "/".join(parts) if parts else "/"


def _schema_errors(spec: Any) -> List[str]:
    import jsonschema

    validator = _validator()
    errors = []
    for err in sorted(validator.iter_errors(spec), key=lambda e: list(map(str, e.absolute_path))):
        best = jsonschema.exceptions.best_match([err])
        errors.append(f"{_path(best)}: {best.message}")
    return errors[:50]


def _check_expression(text: str, where: str, errors: List[str]) -> Set[str]:
    try:
        return set(parse_expression(text).names)
    except ExpressionError as exc:
        errors.append(f"{where}: {exc}")
        return set()


def _measure_dependencies(measures: Mapping[str, Any], errors: List[str]) -> Dict[str, Set[str]]:
    deps: Dict[str, Set[str]] = {}
    for mid, m in measures.items():
        kind = m.get("kind")
        if kind == "expression":
            names = _check_expression(m["expr"], f"/measures/{mid}/expr", errors)
            deps[mid] = {n for n in names if n in measures}
        elif kind == "field" and "by" in m:
            deps[mid] = {m["by"]} & set(measures)
        else:
            deps[mid] = set()
    return deps


def measure_order(measures: Mapping[str, Any]) -> List[str]:
    """Measure ids in an order where every measure follows its dependencies
    (ties in spec order). Raises :class:`SpecError` on a cycle."""
    deps = _measure_dependencies(measures, [])
    order: List[str] = []
    state: Dict[str, int] = {}

    def visit(mid: str, stack: List[str]) -> None:
        if state.get(mid) == 2:
            return
        if state.get(mid) == 1:
            cycle = stack[stack.index(mid) :] + [mid]
            raise SpecError([f"/measures: cycle {' -> '.join(cycle)}"])
        state[mid] = 1
        for dep in sorted(deps[mid], key=list(measures).index):
            visit(dep, stack + [mid])
        state[mid] = 2
        order.append(mid)

    for mid in measures:
        visit(mid, [])
    return order


def _check_semantics(spec: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    measures = spec.get("measures") or {}
    for mid in measures:
        if mid in BASE_COLUMNS:
            errors.append(f"/measures/{mid}: {mid!r} is a reserved column name")
    _measure_dependencies(measures, errors)
    try:
        measure_order(measures)
    except SpecError as exc:
        errors.extend(e for e in exc.errors if "cycle" in e)
    if spec.get("filter"):
        _check_expression(spec["filter"], "/filter", errors)

    estimands = spec.get("estimands") or []
    seen_estimands: Set[str] = set()
    contrasts_of: Dict[str, Set[str]] = {}
    for i, est in enumerate(estimands):
        where = f"/estimands/{i}"
        eid = est["id"]
        if eid in seen_estimands:
            errors.append(f"{where}/id: duplicate estimand id {eid!r}")
        seen_estimands.add(eid)
        if est["outcome"] in BASE_COLUMNS:
            errors.append(f"{where}/outcome: {est['outcome']!r} is not an outcome")
        if est.get("subset"):
            _check_expression(est["subset"], f"{where}/subset", errors)
        kind = est["estimator"]
        fe_only = ("terms", "fixed_effects", "method", "intercept")
        paired_only = ("pair_by", "treatment", "min_n")
        if kind == "fe_ols":
            if not est.get("terms"):
                errors.append(f"{where}: fe_ols needs 'terms'")
            for key in paired_only:
                if key in est:
                    errors.append(f"{where}/{key}: only for paired_within")
            fes = est.get("fixed_effects") or []
            if fes and est.get("intercept"):
                errors.append(f"{where}/intercept: an intercept is absorbed by the fixed effects")
            if est.get("method") and not fes:
                errors.append(f"{where}/method: 'method' needs 'fixed_effects'")
        else:
            for key in fe_only:
                if key in est:
                    errors.append(f"{where}/{key}: only for fe_ols")
            if kind == "paired_within":
                for key in ("pair_by", "treatment"):
                    if key not in est:
                        errors.append(f"{where}: paired_within needs {key!r}")
                treat = est.get("treatment") or {}
                if "treatment" in est and "reference" not in treat:
                    errors.append(f"{where}/treatment: paired_within needs a 'reference' level")
                if treat.get("subset"):
                    _check_expression(treat["subset"], f"{where}/treatment/subset", errors)
            elif "pair_by" in est or "treatment" in est or "min_n" in est:
                errors.append(f"{where}: pair_by, treatment and min_n are only for paired_within")
        vcov = est.get("vcov") or {}
        for by in vcov.get("by") or []:
            cols = [by] if isinstance(by, str) else by
            if len(set(cols)) != len(cols):
                errors.append(f"{where}/vcov/by: a cluster dimension repeats a column")
        names: Set[str] = set()
        contrasts = est.get("contrasts", "terms")
        if isinstance(contrasts, list):
            for j, c in enumerate(contrasts):
                if c["id"] in names:
                    errors.append(f"{where}/contrasts/{j}/id: duplicate contrast id {c['id']!r}")
                names.add(c["id"])
                tosts = c.get("tost") or []
                for t in [tosts] if isinstance(tosts, dict) else tosts:
                    if "bounds" in t and not t["bounds"][0] < t["bounds"][1]:
                        errors.append(f"{where}/contrasts/{j}/tost/bounds: lower must be below upper")
        contrasts_of[eid] = names if isinstance(contrasts, list) else {"*terms*"}
        for j, scope in enumerate(est.get("scopes") or []):
            if isinstance(scope, dict) and len(set(scope["by"])) != len(scope["by"]):
                errors.append(f"{where}/scopes/{j}/by: repeats a column")

    seen_families: Set[str] = set()
    for i, fam in enumerate(spec.get("families") or []):
        where = f"/families/{i}"
        if fam["id"] in seen_families:
            errors.append(f"{where}/id: duplicate family id {fam['id']!r}")
        seen_families.add(fam["id"])
        if fam["method"] == "bh" and fam.get("missing_p") == "count":
            errors.append(f"{where}/missing_p: 'count' is defined for holm and bonferroni only")
        if fam["method"] == "bh" and not fam.get("exploratory"):
            errors.append(
                f"{where}/method: Benjamini-Hochberg is for exploratory families only "
                "(set exploratory: true)"
            )
        for j, member in enumerate(fam["members"]):
            eid = member["estimand"]
            if eid not in seen_estimands:
                errors.append(f"{where}/members/{j}/estimand: unknown estimand {eid!r}")
                continue
            cid = member.get("contrast", "*")
            known = contrasts_of.get(eid, set())
            if cid != "*" and "*terms*" not in known and cid not in known:
                errors.append(f"{where}/members/{j}/contrast: unknown contrast {cid!r} of {eid!r}")
            scope = member.get("scope", "*")
            if not (scope in ("*", "pooled") or scope.startswith("by:") or "=" in scope):
                errors.append(
                    f"{where}/members/{j}/scope: use 'pooled', 'by:<columns>', "
                    "'<column>=<value>' or '*'"
                )
    return errors


def validate_spec(spec: Any) -> None:
    """Raise :class:`SpecError` listing every problem of ``spec``."""
    errors = _schema_errors(spec)
    if errors:
        raise SpecError(errors)
    errors = _check_semantics(spec)
    if errors:
        raise SpecError(errors)


def merged_conventions(*layers: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    out = dict(DEFAULT_CONVENTIONS)
    for layer in layers:
        if layer:
            out.update(layer)
    return out


def normalize_spec(spec: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate ``spec`` and return it with every default filled in."""
    validate_spec(spec)
    out = copy.deepcopy(dict(spec))
    out.setdefault("measures", {})
    out.setdefault("families", [])
    out.setdefault("description", "")
    out["inputs"] = dict(out["inputs"])
    out["inputs"].setdefault("factor_types", {})
    spec_conv = out.pop("conventions", None) or {}
    out["conventions"] = merged_conventions(spec_conv)
    for m in out["measures"].values():
        if m["kind"] in ("field", "gold"):
            m.setdefault("type", "number")
    estimands = []
    for est in out["estimands"]:
        est = dict(est)
        est["conventions"] = merged_conventions(spec_conv, est.get("conventions"))
        est.setdefault("scopes", ["pooled"])
        est.setdefault("vcov", {"type": "iid"})
        est.setdefault("contrasts", "terms")
        if est["estimator"] == "fe_ols":
            est.setdefault("fixed_effects", [])
            if est["fixed_effects"]:
                est.setdefault("method", "within")
                est["intercept"] = False
            else:
                est.setdefault("intercept", True)
        if isinstance(est["contrasts"], list):
            contrasts = []
            for c in est["contrasts"]:
                c = dict(c)
                c.setdefault("kind", "linear")
                if c["kind"] == "linear":
                    c.setdefault("null", 0.0)
                    if c.get("tost"):
                        raw = c["tost"] if isinstance(c["tost"], list) else [c["tost"]]
                        tosts = []
                        for t in raw:
                            t = dict(t)
                            if "margin" in t:
                                m = float(t.pop("margin"))
                                t["bounds"] = [-m, m]
                            t["bounds"] = [float(b) for b in t["bounds"]]
                            t.setdefault("level", est["conventions"]["tost_level"])
                            tosts.append(t)
                        c["tost"] = tosts
                else:
                    c.setdefault("scale", 1.0)
                    c.setdefault("min_abs_denominator", 0.0)
                    for part in ("numerator", "denominator"):
                        c[part] = dict(c[part])
                        c[part].setdefault("constant", 0.0)
                contrasts.append(c)
            est["contrasts"] = contrasts
        estimands.append(est)
    out["estimands"] = estimands
    families = []
    for fam in out["families"]:
        fam = dict(fam)
        fam.setdefault("exploratory", False)
        fam.setdefault("split_by", [])
        fam.setdefault("missing_p", "skip")
        fam["members"] = [
            {"estimand": m["estimand"], "contrast": m.get("contrast", "*"), "scope": m.get("scope", "*")}
            for m in fam["members"]
        ]
        families.append(fam)
    out["families"] = families
    return out


def spec_hash(normalized: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical JSON of a normalized spec."""
    return json_hash(normalized)


__all__ = [
    "BASE_COLUMNS",
    "DEFAULT_CONVENTIONS",
    "ESTIMATOR_PARAMETER",
    "SPEC_VERSION",
    "SpecError",
    "measure_order",
    "merged_conventions",
    "normalize_spec",
    "spec_hash",
    "spec_schema",
    "validate_spec",
]

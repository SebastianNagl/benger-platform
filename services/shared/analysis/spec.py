"""Analysis specs: validation, normalization and hashing.

A spec (JSON, ``schemas/analysis_spec.schema.json``) declares one analysis
of a variant experiment: which designs, systems and prompt structures feed
the frame, which measures derive outcomes from parsed fields, factors,
gold, lists and codes (text pattern sets, coder plugins, judge codes),
which estimands (estimator, terms, fixed effects, variance estimator,
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
    "project_id",
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

#: Conventions only some estimators take, with their defaults. A normalized
#: estimand of one of these estimators carries them next to
#: :data:`DEFAULT_CONVENTIONS`; the other estimands do not.
ESTIMATOR_CONVENTIONS: Dict[str, Dict[str, Any]] = {
    # Maximum likelihood by Newton-Raphson: stop when the largest step is
    # below ml_tolerance * (1 + max|b|). informative_only drops the
    # fixed-effect groups whose outcome does not vary (their effect is
    # infinite). A parameter beyond separation_bound in absolute value (or
    # with a standard error below 1e-8 or not finite) counts as separated:
    # contrasts on it keep their estimate but get no p-value.
    "logit": {"ml_tolerance": 1e-10, "ml_max_iter": 100, "informative_only": True, "separation_bound": 8.0},
    "bradley_terry": {"ml_tolerance": 1e-10, "ml_max_iter": 100, "informative_only": True, "separation_bound": 8.0},
    "plackett_luce": {"ml_tolerance": 1e-10, "ml_max_iter": 100},
    "clogit_rank1": {"ml_tolerance": 1e-10, "ml_max_iter": 100},
    # statsmodels MixedLM (random intercept): the optimizers are tried in
    # order and a fit is accepted only when it converged and every fixed
    # effect's standard error is finite and at most mixedlm_max_se_ratio
    # times the outcome's standard deviation.
    "mixedlm": {"reml": True, "mixedlm_optimizers": ["lbfgs", "powell", "bfgs"], "mixedlm_max_se_ratio": 100.0},
}

ESTIMATOR_PARAMETER = {"mean_rate": "(mean)", "paired_within": "(difference)", "spearman": "(rho)"}

#: Estimand keys each estimator takes besides the common ones.
ESTIMATOR_KEYS: Dict[str, Tuple[str, ...]] = {
    "fe_ols": ("terms", "fixed_effects", "method", "intercept"),
    "mean_rate": (),
    "paired_within": ("pair_by", "treatment", "min_n"),
    "logit": ("terms", "fixed_effects", "method", "intercept"),
    "bradley_terry": ("players", "reference", "levels", "link", "terms", "fixed_effects", "method"),
    "mixedlm": ("terms", "intercept", "groups"),
    "plackett_luce": ("terms", "choice_set", "stages"),
    "clogit_rank1": ("terms", "choice_set"),
    "spearman": ("x",),
}
REQUIRED_KEYS: Dict[str, Tuple[str, ...]] = {
    "fe_ols": ("terms",),
    "paired_within": ("pair_by", "treatment"),
    "logit": ("terms",),
    "bradley_terry": ("players", "reference"),
    "mixedlm": ("terms", "groups"),
    "plackett_luce": ("terms",),
    "clogit_rank1": ("terms",),
    "spearman": ("x",),
}
#: Estimators fitted by maximum likelihood with the engine's own sandwich
#: variances (small-sample factor "statsmodels" or "none").
ML_ESTIMATORS = ("logit", "plackett_luce", "clogit_rank1")
SLOT_COLUMN = "slot"
IDX = "{idx}"


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


def _slot_ref_errors(ref: Any, unit: str, where: str, *, own_allowed: bool) -> List[str]:
    if ref == "own" and (unit != "slot" or not own_allowed):
        return [f"{where}: 'own' is the row's slot{'' if unit == 'slot' else ' and needs a slot frame'}"
                + ("" if unit != "slot" else "; use the slot factor's column instead")]
    if ref == "other" and unit != "slot":
        return [f"{where}: 'other' needs a slot frame (frame.unit = slot)"]
    return []


def _check_measures(spec: Mapping[str, Any], errors: List[str]) -> None:
    measures = spec.get("measures") or {}
    unit = (spec.get("frame") or {}).get("unit", "generation")
    for mid, m in measures.items():
        where = f"/measures/{mid}"
        if mid in BASE_COLUMNS or mid == SLOT_COLUMN:
            errors.append(f"{where}: {mid!r} is a reserved column name")
        kind = m.get("kind")
        if kind == "field":
            names = [m["field"]] if "field" in m else list(m["fields"].values())
            templated = [n for n in names if IDX in n]
            for n in templated:
                if n.count(IDX) != 1:
                    errors.append(f"{where}: {n!r} must contain {IDX} once")
            if templated and len(templated) != len(names):
                errors.append(f"{where}: either every field name has {IDX} or none")
            if "slot" in m:
                if not templated:
                    errors.append(f"{where}/slot: 'slot' needs {IDX} in the field name")
                errors.extend(_slot_ref_errors(m["slot"], unit, f"{where}/slot", own_allowed=True))
            elif templated and unit != "slot":
                errors.append(
                    f"{where}: a field with {IDX} needs a slot frame (frame.unit = slot) or a 'slot' index"
                )
        elif kind == "slot_factor":
            errors.extend(_slot_ref_errors(m["slot"], unit, f"{where}/slot", own_allowed=False))
        elif kind == "slot_aggregate" and m["field"].count(IDX) != 1:
            errors.append(f"{where}/field: must contain {IDX} once")


def _check_lookups(spec: Mapping[str, Any], errors: List[str]) -> None:
    measures = spec.get("measures") or {}
    seen_ids: Set[str] = set()
    seen_cols: Set[str] = set()
    for i, lk in enumerate(spec.get("lookups") or []):
        where = f"/lookups/{i}"
        if lk["id"] in seen_ids:
            errors.append(f"{where}/id: duplicate lookup id {lk['id']!r}")
        seen_ids.add(lk["id"])
        for col in lk["columns"]:
            if col in BASE_COLUMNS or col == SLOT_COLUMN or col in measures:
                errors.append(f"{where}/columns/{col}: {col!r} is already a frame column or measure")
            if col in seen_cols:
                errors.append(f"{where}/columns/{col}: another lookup adds {col!r}")
            seen_cols.add(col)
        for col in lk.get("fill") or {}:
            if col not in lk["columns"]:
                errors.append(f"{where}/fill/{col}: not one of the lookup's columns")
        if "rows" in lk:
            wanted = set(lk["keys"].values()) | set(lk["columns"].values())
            for j, row in enumerate(lk["rows"]):
                missing = sorted(wanted - set(row))
                if missing:
                    errors.append(f"{where}/rows/{j}: missing {', '.join(missing)}")
                    break


def _check_estimand(est: Mapping[str, Any], where: str, spec: Mapping[str, Any], errors: List[str]) -> None:
    kind = est["estimator"]
    unit = (spec.get("frame") or {}).get("unit", "generation")
    own = set(ESTIMATOR_KEYS[kind])
    specific = {key for keys in ESTIMATOR_KEYS.values() for key in keys}
    for key in sorted(specific - own):
        if key in est:
            takers = [k for k, ks in ESTIMATOR_KEYS.items() if key in ks]
            errors.append(f"{where}/{key}: only for {', '.join(takers)}")
    for key in REQUIRED_KEYS.get(kind, ()):
        if key not in est:
            errors.append(f"{where}: {kind} needs {key!r}")
    fes = est.get("fixed_effects") or []
    if kind in ("fe_ols", "logit"):
        if fes and est.get("intercept"):
            errors.append(f"{where}/intercept: an intercept is absorbed by the fixed effects")
        if est.get("method") and not fes:
            errors.append(f"{where}/method: 'method' needs 'fixed_effects'")
    if kind in ("logit", "bradley_terry") and est.get("method", "dummies") != "dummies":
        errors.append(f"{where}/method: {kind} takes its fixed effects as dummies only")
    if kind == "bradley_terry":
        if est.get("method") and not fes:
            errors.append(f"{where}/method: 'method' needs 'fixed_effects'")
        players = est.get("players") or []
        if len(set(players)) != len(players):
            errors.append(f"{where}/players: the two player columns must differ")
        levels = est.get("levels")
        if levels is not None and "reference" in est:
            labels = [str(v) for v in levels]
            if len(set(labels)) != len(labels):
                errors.append(f"{where}/levels: levels repeat")
            if str(est["reference"]) not in labels:
                errors.append(f"{where}/reference: not one of the levels")
    if kind == "paired_within":
        treat = est.get("treatment") or {}
        if "treatment" in est and "reference" not in treat:
            errors.append(f"{where}/treatment: paired_within needs a 'reference' level")
        if treat.get("subset"):
            _check_expression(treat["subset"], f"{where}/treatment/subset", errors)
    if kind in ("plackett_luce", "clogit_rank1") and "choice_set" not in est and unit != "slot":
        errors.append(
            f"{where}/choice_set: {kind} ranks the slots of a generation by default and needs a slot "
            "frame (frame.unit = slot), or name the choice_set columns"
        )
    vcov = est.get("vcov") or {}
    vtype = vcov.get("type")
    if kind == "spearman" and "vcov" in est:
        errors.append(f"{where}/vcov: spearman has no variance estimator")
    if kind == "mixedlm" and vtype not in (None, "iid"):
        errors.append(f"{where}/vcov: mixedlm reports the model-based (iid) variance only")
    if kind in ("plackett_luce", "clogit_rank1") and vtype == "hc1":
        errors.append(f"{where}/vcov: {kind} takes iid or cluster")
    for by in vcov.get("by") or []:
        cols = [by] if isinstance(by, str) else by
        if len(set(cols)) != len(cols):
            errors.append(f"{where}/vcov/by: a cluster dimension repeats a column")
    conv = est.get("conventions") or {}
    allowed = set(DEFAULT_CONVENTIONS) | set(ESTIMATOR_CONVENTIONS.get(kind, {}))
    for key in conv:
        if key not in allowed:
            errors.append(f"{where}/conventions/{key}: not a convention of {kind}")
    ssc = conv.get("ssc", (spec.get("conventions") or {}).get("ssc", DEFAULT_CONVENTIONS["ssc"]))
    ml = kind in ML_ESTIMATORS or (kind == "bradley_terry" and est.get("link", "logit") == "logit")
    if ml and ssc == "fixest":
        errors.append(f"{where}/conventions/ssc: {kind} takes 'statsmodels' or 'none'")
    contrasts = est.get("contrasts", "terms")
    if kind == "spearman" and contrasts != "terms":
        errors.append(f"{where}/contrasts: spearman reports its correlation only")
    if kind == "spearman" and est.get("joint_tests"):
        errors.append(f"{where}/joint_tests: spearman has no parameters to test jointly")
    if isinstance(contrasts, list):
        for j, c in enumerate(contrasts):
            if c.get("kind") == "ame" and kind != "logit":
                errors.append(f"{where}/contrasts/{j}: average marginal effects are for logit only")


def _check_codes(spec: Mapping[str, Any], errors: List[str]) -> None:
    """Pattern sets, text-pattern references and list measures."""
    from analysis.list_measures import check_list_measure
    from analysis.text_patterns import PatternSetError, validate_pattern_set

    valid_sets: Dict[str, Mapping[str, Any]] = {}
    for sid, doc in (spec.get("pattern_sets") or {}).items():
        try:
            validate_pattern_set(doc, f"/pattern_sets/{sid}")
            valid_sets[sid] = doc
        except PatternSetError as exc:
            errors.extend(exc.errors)
    for mid, m in (spec.get("measures") or {}).items():
        where = f"/measures/{mid}"
        kind = m.get("kind")
        if kind == "text_pattern":
            ref = m["set"]
            if isinstance(ref, str):
                if ref not in (spec.get("pattern_sets") or {}):
                    errors.append(f"{where}/set: unknown pattern set {ref!r}")
                    continue
                doc = valid_sets.get(ref)
            else:
                try:
                    validate_pattern_set(ref, f"{where}/set")
                    doc = ref
                except PatternSetError as exc:
                    errors.extend(exc.errors)
                    continue
            if doc is not None and m["code"] not in doc["codes"]:
                errors.append(f"{where}/code: the pattern set has no code {m['code']!r}")
        elif kind == "list":
            errors.extend(check_list_measure(m, where))


def _check_semantics(spec: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    measures = spec.get("measures") or {}
    _check_measures(spec, errors)
    _check_lookups(spec, errors)
    _check_codes(spec, errors)
    _measure_dependencies(measures, errors)
    try:
        measure_order(measures)
    except SpecError as exc:
        errors.extend(e for e in exc.errors if "cycle" in e)
    if spec.get("filter"):
        _check_expression(spec["filter"], "/filter", errors)
    seen_projects: Set[str] = set()
    for i, inp in enumerate((spec.get("inputs") or {}).get("projects") or []):
        if inp["project_id"] in seen_projects:
            errors.append(f"/inputs/projects/{i}/project_id: listed twice")
        seen_projects.add(inp["project_id"])

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
        _check_estimand(est, where, spec, errors)
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
        tests: Set[str] = set()
        for j, jt in enumerate(est.get("joint_tests") or []):
            if jt["id"] in tests or jt["id"] in names:
                errors.append(f"{where}/joint_tests/{j}/id: {jt['id']!r} is already a contrast or joint test")
            tests.add(jt["id"])
            if isinstance(contrasts, list):
                for cid in jt.get("contrasts") or []:
                    if cid not in names:
                        errors.append(f"{where}/joint_tests/{j}/contrasts: unknown contrast {cid!r}")
        contrasts_of[eid] = (names if isinstance(contrasts, list) else {"*terms*"}) | tests
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


def merged_conventions(*layers: Optional[Mapping[str, Any]], estimator: Optional[str] = None) -> Dict[str, Any]:
    """The defaults overridden by each layer in turn. With ``estimator``,
    the estimator's own conventions join the defaults and keys the
    estimator does not take are left out (a spec-level ``reml`` does not
    reach an ``fe_ols`` estimand)."""
    out = dict(DEFAULT_CONVENTIONS)
    extra = ESTIMATOR_CONVENTIONS.get(estimator or "", {})
    out.update(copy.deepcopy(extra))
    allowed = set(out) if estimator is not None else None
    for layer in layers:
        if layer:
            out.update(
                {k: copy.deepcopy(v) for k, v in layer.items() if allowed is None or k in allowed}
            )
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
    from analysis.text_patterns import normalize_pattern_set

    if "pattern_sets" in out:
        # Only when declared, so the hash of a spec without codes is the
        # same as before pattern sets existed.
        out["pattern_sets"] = {sid: normalize_pattern_set(doc) for sid, doc in out["pattern_sets"].items()}
    unit = (out.get("frame") or {}).get("unit", "generation")
    for m in out["measures"].values():
        if m["kind"] in ("field", "gold"):
            m.setdefault("type", "number")
        if m["kind"] == "field" and unit == "slot" and "slot" not in m:
            names = [m["field"]] if "field" in m else list(m["fields"].values())
            if any(IDX in name for name in names):
                m["slot"] = "own"
        elif m["kind"] == "text_pattern":
            m.setdefault("input", "answer")
            if isinstance(m["set"], dict):
                m["set"] = normalize_pattern_set(m["set"])
        elif m["kind"] == "coder":
            m.setdefault("input", "answer")
            m.setdefault("parameters", {})
        elif m["kind"] == "judge_code":
            m.setdefault("type", "text")
            m.setdefault("run_index", 0)
        elif m["kind"] == "list":
            m.setdefault("normalize", [])
    for lk in out.get("lookups") or []:
        lk.setdefault("fill", {})
    estimands = []
    for est in out["estimands"]:
        est = dict(est)
        kind = est["estimator"]
        est["conventions"] = merged_conventions(spec_conv, est.get("conventions"), estimator=kind)
        est.setdefault("scopes", ["pooled"])
        if kind != "spearman":
            est.setdefault("vcov", {"type": "iid"})
        est.setdefault("contrasts", "terms")
        if kind in ("fe_ols", "logit"):
            est.setdefault("fixed_effects", [])
            if est["fixed_effects"]:
                est.setdefault("method", "within" if kind == "fe_ols" else "dummies")
                est["intercept"] = False
            else:
                est.setdefault("intercept", True)
        elif kind == "bradley_terry":
            est.setdefault("link", "logit")
            est.setdefault("terms", [])
            est.setdefault("fixed_effects", [])
            if est["fixed_effects"]:
                est.setdefault("method", "dummies")
        elif kind == "mixedlm":
            est.setdefault("intercept", True)
        elif kind in ("plackett_luce", "clogit_rank1"):
            est.setdefault("choice_set", ["generation_id"])
        if isinstance(est["contrasts"], list):
            contrasts = []
            for c in est["contrasts"]:
                c = dict(c)
                c.setdefault("kind", "linear")
                if c["kind"] == "ame":
                    c.setdefault("scale", 1.0)
                if c["kind"] in ("linear", "ame"):
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
    "ESTIMATOR_CONVENTIONS",
    "ESTIMATOR_KEYS",
    "ESTIMATOR_PARAMETER",
    "SLOT_COLUMN",
    "SPEC_VERSION",
    "SpecError",
    "measure_order",
    "merged_conventions",
    "normalize_spec",
    "spec_hash",
    "spec_schema",
    "validate_spec",
]

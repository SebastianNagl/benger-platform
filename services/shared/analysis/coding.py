"""Coding projects and code validations, the Label Studio way.

A coding project is an ordinary project made from a sample of another
project's answers: each task shows one answer (``data.answer``) and the
context copied from its task, the coding scheme is the project's label
config, human codes are the annotations and automatic codes are what a code
gives for the same answer (a text-pattern code, a coder plugin, or a judge
system's generations on the coding project, which are its predictions).
Each task records where its answer came from in ``tasks.meta.coding``
(``source_project_id``, ``source_task_id``, ``source_generation_id``,
``answer_source``, ``sample_rank``); ``meta`` is never shown to annotators.

A code validation compares the automatic codes of one code with the human
codes of one control of the scheme and records the agreement (Cohen's kappa,
observed and chance agreement, precision, recall and F1 per category, the
confusion matrix, agreement per human coder and between coders) together
with the code's identity hash. An analysis run accepts a code measure's
``validation`` only for that hash (:mod:`analysis.codes`).

This module is pure: sampling ranks, the validation request format and the
agreement statistics. The database side lives in the API (creating coding
projects) and the workers (running validations).
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from analysis.canonical import json_hash

#: Version of the coding-project sample rule and the validation statistics.
CODING_VERSION = 1

MISSING_LABEL = "(missing)"


class CodingError(ValueError):
    """An invalid coding-project or validation request. ``errors`` lists
    the problems."""

    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


# --------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------


def sample_rank(seed: int, generation_id: str) -> str:
    """The rank key of an answer in a seeded sample: SHA-256 of
    ``"<seed>:<generation id>"``. Sorting by it gives an order that depends
    only on the seed and the ids, never on database order, so the same seed
    draws the same answers and adding answers keeps earlier ones in place
    relative to each other."""
    return hashlib.sha256(f"{int(seed)}:{generation_id}".encode("utf-8")).hexdigest()


def draw_sample(generation_ids: Iterable[str], seed: int, size: Optional[int] = None) -> List[Tuple[str, str]]:
    """``[(generation id, rank)]`` of the first ``size`` answers by rank
    (all of them when ``size`` is None), in rank order."""
    ranked = sorted((sample_rank(seed, g), g) for g in set(generation_ids))
    if size is not None:
        ranked = ranked[: int(size)]
    return [(g, r) for r, g in ranked]


def sample_hash(generation_ids: Iterable[str]) -> str:
    """SHA-256 of the sorted generation ids of a sample."""
    return json_hash(sorted(generation_ids))


# --------------------------------------------------------------------------
# Validation requests
# --------------------------------------------------------------------------

CODE_KINDS = ("text_pattern", "coder", "judge_code")


MAX_SYSTEM_LENGTH = 200
MAX_FIELD_LENGTH = 99


def normalize_validation_code(
    code: Any,
    *,
    coding_project_id: str,
    answer_source: Any,
) -> Dict[str, Any]:
    """A validation's code as a normalized code measure.

    ``code`` is shaped like the measure it validates, without ``input`` and
    ``validation``: ``{"kind": "text_pattern", "set": {...}, "code": "x"}``,
    ``{"kind": "coder", "coder": "name", "version": "1", "output": "y",
    "parameters": {...}}`` or ``{"kind": "judge_code", "system": "...",
    "structure": "...", "run_index": 0}`` (its ``field`` is the validated
    control unless given). The input is the coding project's answer source,
    and a judge code's coding project is the validation's, so the identity
    hash equals that of the analysis measure that reads the same code."""
    from analysis.codes import normalized_input
    from analysis.text_patterns import PatternSetError, normalize_pattern_set

    errors: List[str] = []
    if not isinstance(code, Mapping):
        raise CodingError(["/code: must be an object"])
    kind = code.get("kind")
    if kind not in CODE_KINDS:
        raise CodingError([f"/code/kind: must be one of {', '.join(CODE_KINDS)}"])
    allowed = {
        "text_pattern": {"kind", "set", "code", "description"},
        "coder": {"kind", "coder", "version", "output", "parameters", "description"},
        "judge_code": {"kind", "system", "structure", "run_index", "field", "type", "description"},
    }[kind]
    extra = sorted(set(code) - allowed)
    if extra:
        errors.append(f"/code: unknown key(s) {', '.join(extra)} for a {kind} code")
    out: Dict[str, Any] = {"kind": kind}
    if kind == "text_pattern":
        if not isinstance(code.get("set"), Mapping):
            errors.append("/code/set: give the pattern set itself")
        else:
            try:
                out["set"] = normalize_pattern_set(code["set"], "/code/set")
            except PatternSetError as exc:
                errors.extend(exc.errors)
        cid = code.get("code")
        if not isinstance(cid, str) or not cid:
            errors.append("/code/code: name the code of the set")
        elif "set" in out and cid not in out["set"]["codes"]:
            errors.append(f"/code/code: the pattern set has no code {cid!r}")
        out["code"] = cid
        out["input"] = normalized_input(answer_source)
    elif kind == "coder":
        for key in ("coder", "output"):
            if not isinstance(code.get(key), str) or not code.get(key):
                errors.append(f"/code/{key}: required")
        out["coder"] = code.get("coder")
        out["output"] = code.get("output")
        if code.get("version") is not None:
            if not isinstance(code["version"], str):
                errors.append("/code/version: must be a string")
            out["version"] = code["version"]
        params = code.get("parameters", {})
        if not isinstance(params, Mapping):
            errors.append("/code/parameters: must be an object")
            params = {}
        out["parameters"] = dict(params)
        out["input"] = normalized_input(answer_source)
    else:
        system = code.get("system")
        if not isinstance(system, str) or not system:
            errors.append("/code/system: name the coding system (a system key or a model id)")
        elif len(system) > MAX_SYSTEM_LENGTH:
            errors.append(f"/code/system: at most {MAX_SYSTEM_LENGTH} characters")
        out["coding_project"] = coding_project_id
        out["system"] = code.get("system")
        structure = code.get("structure")
        if structure is not None and not isinstance(structure, str):
            errors.append("/code/structure: must be a string")
        if structure is not None:
            out["structure"] = structure
        run_index = code.get("run_index", 0)
        if isinstance(run_index, bool) or not isinstance(run_index, int) or run_index < 0:
            errors.append("/code/run_index: must be a whole number >= 0")
            run_index = 0
        out["run_index"] = run_index
        field = code.get("field")
        if field is not None:
            if not isinstance(field, str) or not field or len(field) > MAX_FIELD_LENGTH:
                errors.append(f"/code/field: a control name of at most {MAX_FIELD_LENGTH} characters")
            out["field"] = field
        out["type"] = "text"
    if errors:
        raise CodingError(errors)
    return out


# --------------------------------------------------------------------------
# Values
# --------------------------------------------------------------------------


def code_label(value: Any, value_map: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """A code value as the label it is compared with: canonical text
    (``1.0`` is ``"1"``), mapped through ``value_map``; None when missing.
    A one-element list counts as its element; a longer list is not a single
    code (None)."""
    from analysis.measures import as_text

    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            return None
        value = value[0]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = as_text(value)
    if text is None or text == "":
        return None
    if value_map and text in value_map:
        return value_map[text]
    return text


# --------------------------------------------------------------------------
# Agreement
# --------------------------------------------------------------------------


def _kappa(a: Sequence[str], b: Sequence[str]) -> Dict[str, Any]:
    from bg_statistics.agreement import cohens_kappa

    if not a:
        return {"n": 0, "kappa": None, "observed_agreement": None, "expected_agreement": None}
    res = cohens_kappa(list(a), list(b))
    if "error" in res:
        return {"n": len(a), "kappa": None, "observed_agreement": None, "expected_agreement": None}
    return {
        "n": len(a),
        "kappa": res["kappa"],
        "observed_agreement": res["observed_agreement"],
        "expected_agreement": res["expected_agreement"],
    }


def _per_category(reference: Sequence[str], automatic: Sequence[str], categories: Sequence[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for c in categories:
        tp = sum(1 for r, a in zip(reference, automatic) if r == c and a == c)
        support = sum(1 for r in reference if r == c)
        predicted = sum(1 for a in automatic if a == c)
        precision = tp / predicted if predicted else None
        recall = tp / support if support else None
        if precision is None or recall is None:
            f1 = None
        else:
            f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        out[c] = {"support": support, "predicted": predicted, "true_positives": tp,
                  "precision": precision, "recall": recall, "f1": f1}
    return out


def _majority(values: Sequence[str]) -> Optional[str]:
    counts: Dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    best = max(counts.values())
    winners = [v for v, c in counts.items() if c == best]
    return winners[0] if len(winners) == 1 else None


def validation_metrics(items: Sequence[Mapping[str, Any]], *, missing: str = "category") -> Dict[str, Any]:
    """Agreement of automatic with human codes.

    ``items``: ``[{"task_id", "automatic": label or None, "human": {coder:
    label}}]`` (labels from :func:`code_label`; coders without a code for
    the item are left out of ``human``). The reference code of an item is
    its human code, or the majority of its human codes; an item whose human
    codes tie has no reference and is counted in ``ties``. A missing
    automatic code counts as the category ``(missing)`` (``missing:
    "category"``, the default: a code that gives nothing disagrees) or
    leaves the item out (``"exclude"``).

    Cohen's kappa is unweighted, over the categories either side uses
    (:func:`bg_statistics.agreement.cohens_kappa`); precision, recall and F1
    per category take the human reference as truth."""
    if missing not in ("category", "exclude"):
        raise CodingError(["/missing: use 'category' or 'exclude'"])
    ref_labels: List[str] = []
    auto_labels: List[str] = []
    ties = 0
    no_human = 0
    missing_automatic = 0
    per_coder: Dict[str, Tuple[List[str], List[str]]] = {}
    coders = sorted({c for it in items for c in (it.get("human") or {})}, key=str)
    for it in items:
        human = {c: v for c, v in (it.get("human") or {}).items() if v is not None}
        auto = it.get("automatic")
        if auto is None:
            missing_automatic += 1 if human else 0
            if missing == "exclude":
                continue
            auto = MISSING_LABEL
        if not human:
            no_human += 1
            continue
        for c, v in human.items():
            a, h = per_coder.setdefault(c, ([], []))
            a.append(auto)
            h.append(v)
        ref = _majority(list(human.values()))
        if ref is None:
            ties += 1
            continue
        ref_labels.append(ref)
        auto_labels.append(auto)
    categories = sorted(set(ref_labels) | set(auto_labels))
    confusion = {r: {a: 0 for a in categories} for r in categories}
    for r, a in zip(ref_labels, auto_labels):
        confusion[r][a] += 1
    main = _kappa(ref_labels, auto_labels)
    main.update(
        confusion=confusion,
        per_category=_per_category(ref_labels, auto_labels, categories),
    )
    by_coder = {c: _kappa(per_coder[c][1], per_coder[c][0]) for c in coders if c in per_coder}
    between = None
    if len(coders) >= 2:
        from bg_statistics.agreement import fleiss_kappa, percent_agreement

        matrix = []
        for it in items:
            human = it.get("human") or {}
            row = [human.get(c) for c in coders]
            if sum(1 for v in row if v is not None) >= 2:
                matrix.append(row)
        pairwise = {}
        for i, a in enumerate(coders):
            for b in coders[i + 1 :]:
                pa, pb = [], []
                for row in matrix:
                    va, vb = row[coders.index(a)], row[coders.index(b)]
                    if va is not None and vb is not None:
                        pa.append(va)
                        pb.append(vb)
                pairwise[f"{a}__{b}"] = _kappa(pa, pb)
        fk = fleiss_kappa(matrix) if matrix else {}
        between = {
            "coders": len(coders),
            "items": len(matrix),
            "pairwise": pairwise,
            "fleiss_kappa": fk.get("kappa") if matrix else None,
            "percent_agreement": percent_agreement(matrix) if matrix else None,
        }
    return {
        "version": CODING_VERSION,
        "items": len(items),
        "compared": len(ref_labels),
        "ties": ties,
        "no_human_code": no_human,
        "missing_automatic": missing_automatic,
        "missing": missing,
        "categories": categories,
        "automatic_vs_reference": main,
        "automatic_vs_coders": by_coder,
        "between_coders": between,
    }


__all__ = [
    "CODING_VERSION",
    "CodingError",
    "MISSING_LABEL",
    "code_label",
    "draw_sample",
    "normalize_validation_code",
    "sample_hash",
    "sample_rank",
    "validation_metrics",
]

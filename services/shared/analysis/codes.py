"""Codes in an analysis: text patterns, coder plugins and judge codes.

A code is a measure whose value is read off an answer by a procedure rather
than taken from a parsed field: a regex set (``text_pattern``), a coder
plugin (``coder``) or another system's coding of the answer in a coding
project (``judge_code``). This module evaluates those measures over a frame's
rows, identifies each code by a hash (:func:`code_identity`), and holds the
rule that a code enters a confirmatory analysis only with a recorded
validation (:func:`confirmatory_code_measures`).

Code identity. The hash covers everything that decides the code's values:

* ``text_pattern``: the pattern set's hash, the code and the input (the full
  answer or a named field);
* ``coder``: the coder's code hash (name, version, outputs and source), the
  output, the input and the measure's parameters;
* ``judge_code``: the coding project, the field, the system and prompt
  structure whose answers code it, and the run index.

A code validation (:mod:`analysis.coding`) records the identity hash of the
code it validated; an analysis run accepts a measure's ``validation`` only
when the hashes are equal, so a validation of one version never vouches for
another.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from analysis.canonical import json_hash

#: Version of the code identity rules (part of every code hash).
CODE_IDENTITY_VERSION = 1

CODE_KINDS = ("text_pattern", "coder", "judge_code")


class CodeError(ValueError):
    """A code measure that cannot be evaluated (unknown coder, inactive
    package, missing pattern set)."""


def normalized_input(value: Any) -> Any:
    """``"answer"`` or ``{"field": name}``."""
    if isinstance(value, Mapping) and "field" in value:
        return {"field": value["field"]}
    return "answer"


def input_label(value: Any) -> str:
    value = normalized_input(value)
    return "answer" if value == "answer" else f"field:{value['field']}"


def pattern_set_of(m: Mapping[str, Any], pattern_sets: Mapping[str, Any]) -> Mapping[str, Any]:
    ref = m["set"]
    if isinstance(ref, Mapping):
        return ref
    found = pattern_sets.get(ref)
    if found is None:
        raise CodeError(f"pattern set {ref!r} is not declared in pattern_sets")
    return found


def code_identity(
    m: Mapping[str, Any],
    *,
    pattern_sets: Optional[Mapping[str, Any]] = None,
    coder=None,
) -> Dict[str, Any]:
    """The identity record of a (normalized) code measure: ``kind``, a
    readable ``ref``, ``version``, ``hash`` and the parts the hash covers.
    ``coder`` is the :class:`analysis.coders.RegisteredCoder` a ``coder``
    measure resolves to."""
    kind = m["kind"]
    if kind == "text_pattern":
        from analysis.text_patterns import pattern_set_hash

        normalized = pattern_set_of(m, pattern_sets or {})
        set_hash = pattern_set_hash(normalized)
        parts = {
            "kind": kind,
            "set_hash": set_hash,
            "code": m["code"],
            "input": normalized_input(m.get("input")),
        }
        return {
            "kind": kind,
            "ref": f"{normalized['name']}@{normalized['version']}:{m['code']}",
            "name": normalized["name"],
            "version": normalized["version"],
            "set_hash": set_hash,
            "code": m["code"],
            "input": parts["input"],
            "hash": json_hash({"identity": CODE_IDENTITY_VERSION, **parts}),
        }
    if kind == "coder":
        if coder is None:
            raise CodeError(f"coder {m['coder']!r} is not resolved")
        parts = {
            "kind": kind,
            "code_hash": coder.code_hash,
            "output": m["output"],
            "input": normalized_input(m.get("input")),
            "parameters": dict(m.get("parameters") or {}),
        }
        return {
            "kind": kind,
            "ref": f"{coder.ref}:{m['output']}",
            "name": coder.name,
            "version": coder.version,
            "code_hash": coder.code_hash,
            "owner": coder.owner,
            "output": m["output"],
            "input": parts["input"],
            "parameters": parts["parameters"],
            "hash": json_hash({"identity": CODE_IDENTITY_VERSION, **parts}),
        }
    if kind == "judge_code":
        parts = {
            "kind": kind,
            "coding_project": m["coding_project"],
            "field": m["field"],
            "system": m["system"],
            "structure": m.get("structure"),
            "run_index": int(m.get("run_index", 0)),
        }
        return {
            **parts,
            "ref": f"{m['system']}:{m['field']}",
            "version": None,
            "hash": json_hash({"identity": CODE_IDENTITY_VERSION, **parts}),
        }
    raise CodeError(f"{kind!r} is not a code")


# --------------------------------------------------------------------------
# Which code measures a confirmatory analysis reads
# --------------------------------------------------------------------------


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for k, v in value.items():
            if isinstance(k, str):
                yield k
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def _expression_names(text: Optional[str]) -> Set[str]:
    if not text:
        return set()
    from analysis.expression import ExpressionError, parse_expression

    try:
        return set(parse_expression(text).names)
    except ExpressionError:
        return set()


def _measure_closure(names: Set[str], measures: Mapping[str, Any]) -> Set[str]:
    seen: Set[str] = set()
    stack = [n for n in names if n in measures]
    while stack:
        mid = stack.pop()
        if mid in seen:
            continue
        seen.add(mid)
        m = measures[mid]
        deps: Set[str] = set()
        if m.get("kind") == "expression":
            deps = _expression_names(m.get("expr"))
        elif m.get("kind") == "field" and "by" in m:
            deps = {m["by"]}
        stack.extend(d for d in deps if d in measures and d not in seen)
    return seen


def estimand_names(est: Mapping[str, Any]) -> Set[str]:
    """Every column name an estimand can read (an over-approximation: any
    string in it, plus the names of its expressions)."""
    names = set(_strings({k: v for k, v in est.items() if k not in ("subset", "treatment")}))
    names |= _expression_names(est.get("subset"))
    treat = est.get("treatment") or {}
    if treat:
        names |= {treat.get("factor")} if isinstance(treat.get("factor"), str) else set()
        names |= _expression_names(treat.get("subset"))
    return names


def confirmatory_code_measures(spec: Mapping[str, Any]) -> Dict[str, List[str]]:
    """Code measure id -> the confirmatory estimands that read it.

    An estimand is confirmatory when it is a member of a family that is not
    ``exploratory``. It reads a measure when the measure (or a measure it
    is derived from) is its outcome, a term, a fixed effect, a cluster, a
    scope or pairing column, or a name in its subset or the global filter.
    """
    measures = spec.get("measures") or {}
    confirmatory: Set[str] = set()
    for fam in spec.get("families") or []:
        if fam.get("exploratory"):
            continue
        for member in fam.get("members") or []:
            confirmatory.add(member["estimand"])
    global_names = _expression_names(spec.get("filter"))
    out: Dict[str, List[str]] = {}
    for est in spec.get("estimands") or []:
        if est["id"] not in confirmatory:
            continue
        for mid in sorted(_measure_closure(estimand_names(est) | global_names, measures)):
            if measures[mid].get("kind") in CODE_KINDS:
                out.setdefault(mid, []).append(est["id"])
    return out


# --------------------------------------------------------------------------
# Evaluating code measures over a frame
# --------------------------------------------------------------------------


@dataclass
class CodeInputs:
    """What code measures read besides the parsed fields and task data.

    ``texts`` are the full answers per row, ``factors`` the rows' design
    factors, ``generation_ids`` the rows' generations; ``judge_values`` maps a
    ``judge_code`` measure id to ``{generation_id: value}`` (read from the
    coding project by :mod:`analysis.db_source`); ``coders`` is the coder
    registry (default: :data:`analysis.coders.coder_registry`). ``report``
    receives one identity record per code measure evaluated."""

    texts: Sequence[Optional[str]] = ()
    factors: Sequence[Mapping[str, Any]] = ()
    generation_ids: Sequence[str] = ()
    pattern_sets: Mapping[str, Any] = field(default_factory=dict)
    judge_values: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    judge_stats: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    coders: Any = None
    report: List[Dict[str, Any]] = field(default_factory=list)
    _compiled: Dict[str, Any] = field(default_factory=dict)
    _coder_rows: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)


def text_of(value: Any) -> Optional[str]:
    """A parsed field value as text: a string, or the string of a
    one-element list; anything else is missing."""
    if isinstance(value, (list, tuple)) and len(value) == 1:
        value = value[0]
    return value if isinstance(value, str) else None


def _row_texts(m: Mapping[str, Any], fields: Sequence[Mapping[str, Any]], inputs: CodeInputs, n: int) -> List[Optional[str]]:
    source = normalized_input(m.get("input"))
    if source == "answer":
        texts = list(inputs.texts)
        if len(texts) != n:
            raise CodeError("the answers' texts are not available to this frame")
        return [t if isinstance(t, str) else None for t in texts]
    name = source["field"]
    return [text_of(f.get(name)) for f in fields]


def _missing_count(values: Sequence[Any]) -> int:
    return sum(1 for v in values if v is None or (isinstance(v, float) and math.isnan(v)))


def evaluate_code_measure(
    mid: str,
    m: Mapping[str, Any],
    fields: Sequence[Mapping[str, Any]],
    task_data: Sequence[Mapping[str, Any]],
    n: int,
    inputs: CodeInputs,
) -> tuple:
    """``(values, kind)`` of one code measure over the rows; ``kind`` is
    ``number`` or ``text``. Appends the code's identity to ``inputs.report``."""
    kind = m["kind"]
    if kind == "text_pattern":
        from analysis.text_patterns import CompiledPatternSet, code_type

        normalized = pattern_set_of(m, inputs.pattern_sets)
        key = json_hash(normalized)
        compiled = inputs._compiled.get(key)
        if compiled is None:
            compiled = CompiledPatternSet(normalized)
            inputs._compiled[key] = compiled
        texts = _row_texts(m, fields, inputs, n)
        values = [compiled.code(m["code"], t, d) for t, d in zip(texts, task_data)]
        vtype = code_type(normalized, m["code"])
        identity = code_identity(m, pattern_sets=inputs.pattern_sets)
    elif kind == "coder":
        from analysis.coders import CoderContext, CoderError, coder_registry

        registry = inputs.coders or coder_registry
        try:
            entry = registry.resolve(m["coder"], m.get("version"))
        except CoderError as exc:
            raise CodeError(f"measure {mid!r}: {exc}") from None
        output = m["output"]
        if output not in entry.outputs:
            raise CodeError(
                f"measure {mid!r}: coder {entry.ref} has no output {output!r} "
                f"(it has {', '.join(sorted(entry.outputs))})"
            )
        params = dict(m.get("parameters") or {})
        memo_key = json_hash({"coder": entry.code_hash, "input": normalized_input(m.get("input")), "parameters": params})
        rows = inputs._coder_rows.get(memo_key)
        if rows is None:
            texts = _row_texts(m, fields, inputs, n)
            factors = list(inputs.factors) if len(inputs.factors) == n else [{}] * n
            rows = []
            try:
                for t, f, d, fac in zip(texts, fields, task_data, factors):
                    rows.append(entry.run(t, CoderContext(fields=f, task_data=d, factors=fac, parameters=params)))
            except CoderError as exc:
                raise CodeError(f"measure {mid!r}: {exc}") from None
            inputs._coder_rows[memo_key] = rows
        values = [r.get(output) for r in rows]
        vtype = "text" if entry.outputs[output] == "text" else "number"
        identity = code_identity(m, coder=entry)
    elif kind == "judge_code":
        from analysis.measures import coerce

        vtype = m.get("type", "text")
        lookup = inputs.judge_values.get(mid) or {}
        gids = list(inputs.generation_ids)
        if len(gids) != n:
            raise CodeError("the rows' generations are not available to this frame")
        values = [coerce(lookup.get(g), vtype) for g in gids]
        vtype = "text" if vtype == "text" else "number"
        identity = code_identity(m)
        stats = inputs.judge_stats.get(mid)
        if stats:
            identity["coding"] = dict(stats)
    else:  # pragma: no cover - dispatch only sends code kinds
        raise CodeError(f"{kind!r} is not a code")
    identity = {"measure": mid, **identity, "missing": _missing_count(values), "rows": n}
    if m.get("validation"):
        identity["validation"] = m["validation"]
    inputs.report.append(identity)
    return values, vtype


__all__ = [
    "CODE_IDENTITY_VERSION",
    "CODE_KINDS",
    "CodeError",
    "CodeInputs",
    "code_identity",
    "confirmatory_code_measures",
    "estimand_names",
    "evaluate_code_measure",
    "input_label",
    "normalized_input",
    "text_of",
]

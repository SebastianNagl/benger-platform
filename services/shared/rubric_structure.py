"""Bewertungsbogen structure: the canonical hierarchical rubric contract.

A per-task grading rubric (``task_rubrics`` row) is edited, imported and
rendered as an ordered OUTLINE (``structure``) and graded against the flat
``criteria`` dict that the multi-dim LLM judge and the human grading form
consume. This module owns the shape of both and every pure transformation
between them, so the api, the workers and the extended overlay share one
implementation:

- ``structure`` (JSONB, nullable for legacy rows): ``{"version": 1, "nodes":
  [...]}`` — flat, depth-first, ordered. ``section`` nodes carry a heading and
  an optional ``note``; ``step`` nodes carry a schema ``key``, ``max_score``
  (Bewertungseinheiten, multiples of 0.5), an optional ``emphasis``
  (``"schwerpunkt"``) and guidance ``hints``.
- ``criteria`` is DERIVED from ``structure`` on every write
  (``criteria_from_structure``); legacy rows without a structure keep their
  hand-written criteria and can be lifted with ``structure_from_flat_criteria``.
- ``grade_scale`` (JSONB, nullable): a per-rubric Notenschlüssel — 18
  non-decreasing thresholds (minimum points for Notenpunkte 1..18), a rounding
  rule and a pass grade. ``None`` means the default Falllösung table scaled to
  the rubric total.

Deliberately pydantic-free and SQLAlchemy-free at import time: the workers have
no pydantic dependency and both containers import this as
``from rubric_structure import ...`` with ``/shared`` on ``sys.path``.
"""

from __future__ import annotations

import math
import re
import unicodedata
from bisect import bisect_right
from typing import Any, Dict, Iterator, List, Optional, Tuple

STRUCTURE_VERSION = 1
NODE_KINDS = ("section", "step")
EMPHASIS_VALUES = ("schwerpunkt",)
ROUNDING_MODES = ("floor", "ceil", "nearest", "none")
# Identical to benger_extended.workers.bewertungsbogen_constants.STEP_KEY_PATTERN.
STEP_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

MAX_NODES = 500
MAX_HINTS_PER_STEP = 20
MAX_STEP_POINTS = 1000
MAX_LABEL_LEN = 20
MAX_TITLE_LEN = 500
MAX_NOTE_LEN = 500
MAX_HINT_LEN = 1000
GRADE_COUNT = 18

# The existing Falllösung table (FALLOESUNG_GRADE_TABLE upper bounds) expressed
# as MINIMUM points for Notenpunkte 1..18 on a 100-point total:
# 0-12→0, 13-25→1, 26-38→2, 39-49→3, 50-53→4, 54-56→5, 57-59→6, 60-63→7,
# 64-66→8, 67-69→9, 70-73→10, 74-76→11, 77-79→12, 80-83→13, 84-86→14,
# 87-89→15, 90-93→16, 94-96→17, 97-100→18.
DEFAULT_GRADE_THRESHOLDS = [13, 26, 39, 50, 54, 57, 60, 64, 67, 70, 74, 77, 80, 84, 87, 90, 94, 97]
DEFAULT_PASS_GRADE = 4
DEFAULT_ROUNDING = "floor"
DEFAULT_GRADE_UNIT = "BE"

_STEP_KEY_ORDER = re.compile(r"^s(\d+)_")


# ---------------------------------------------------------------------------
# Step keys
# ---------------------------------------------------------------------------

_UMLAUTS = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"}
)


def slugify_step_key(title: str, index: int) -> str:
    """``"Anspruch entstanden (§ 433 II BGB)"`` → ``"s03_anspruch_entstanden_433_ii_bgb"``.

    Prefixing the 1-based index guarantees uniqueness and a stable step order
    even for duplicate titles; the result always matches STEP_KEY_PATTERN.

    Verbatim copy of ``benger_extended.workers.bewertungsbogen_constants
    .slugify_step_key`` so the AI generator's keys and the keys derived from a
    structure coincide (the generator's persistence invariant depends on it).
    """
    text = (title or "").translate(_UMLAUTS)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    slug = f"s{index:02d}_{text}" if text else f"s{index:02d}_schritt"
    return slug[:60].rstrip("_")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_half_multiple(value: float) -> bool:
    return math.isfinite(value) and abs(value * 2 - round(value * 2)) < 1e-9


def _coerce_points(value: Any) -> Any:
    """Half-point number as ``int`` when integral, else ``float``."""
    number = float(value)
    return int(number) if number.is_integer() else number


def format_points(value: Any) -> str:
    """``1`` → ``"1"``, ``0.5`` → ``"0.5"``, ``72.5`` → ``"72.5"`` (dot decimals)."""
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def iter_steps(structure: Optional[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    """Yield the ``step`` nodes of a structure in document order."""
    if not isinstance(structure, dict):
        return
    for node in structure.get("nodes") or []:
        if isinstance(node, dict) and node.get("kind") == "step":
            yield node


def total_points_from_structure(structure: Optional[Dict[str, Any]]) -> Any:
    """Sum of the step max scores (exact for halves; ``int`` when integral)."""
    doubled = 0
    for step in iter_steps(structure):
        score = step.get("max_score")
        if _is_number(score):
            doubled += int(round(float(score) * 2))
    return _coerce_points(doubled / 2)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_structure(structure: Any) -> List[str]:
    """Contract violations of a structure (empty list == valid)."""
    errors: List[str] = []
    if not isinstance(structure, dict):
        return ["structure must be an object"]
    if structure.get("version") != STRUCTURE_VERSION:
        errors.append(f"structure.version must be {STRUCTURE_VERSION}")
    nodes = structure.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        errors.append("structure.nodes must be a non-empty list")
        return errors
    if len(nodes) > MAX_NODES:
        errors.append(f"structure.nodes has {len(nodes)} entries, max {MAX_NODES}")
        return errors

    seen_ids: set = set()
    prev_level = -1
    step_count = 0
    for index, node in enumerate(nodes):
        where = f"node {index + 1}"
        if not isinstance(node, dict):
            errors.append(f"{where}: must be an object")
            prev_level = max(prev_level, 0)
            continue

        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            errors.append(f"{where}: id must be a non-empty string")
        elif node_id in seen_ids:
            errors.append(f"{where}: duplicate id {node_id!r}")
        else:
            seen_ids.add(node_id)

        level = node.get("level")
        if not isinstance(level, int) or isinstance(level, bool) or level < 0:
            errors.append(f"{where}: level must be an integer >= 0")
            level = prev_level if prev_level >= 0 else 0
        elif index == 0 and level != 0:
            errors.append(f"{where}: the first node must have level 0")
        elif level > prev_level + 1:
            errors.append(
                f"{where}: level {level} skips a depth (previous node has level {prev_level})"
            )
        prev_level = level

        kind = node.get("kind")
        if kind not in NODE_KINDS:
            errors.append(f"{where}: kind must be one of {', '.join(NODE_KINDS)}")

        label = node.get("label")
        if label is not None and (not isinstance(label, str) or len(label) > MAX_LABEL_LEN):
            errors.append(f"{where}: label must be a string of at most {MAX_LABEL_LEN} characters")

        title = node.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{where}: title must be a non-empty string")
        elif len(title.strip()) > MAX_TITLE_LEN:
            errors.append(f"{where}: title exceeds {MAX_TITLE_LEN} characters")

        note = node.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE_LEN):
            errors.append(f"{where}: note must be a string of at most {MAX_NOTE_LEN} characters")

        if kind == "step":
            step_count += 1
            score = node.get("max_score")
            if not _is_number(score):
                errors.append(f"{where}: max_score must be a number")
            else:
                score_f = float(score)
                if not math.isfinite(score_f) or score_f <= 0:
                    errors.append(f"{where}: max_score must be > 0")
                elif not _is_half_multiple(score_f):
                    errors.append(f"{where}: max_score must be a multiple of 0.5")
                elif score_f > MAX_STEP_POINTS:
                    errors.append(f"{where}: max_score exceeds {MAX_STEP_POINTS}")
            emphasis = node.get("emphasis")
            if emphasis is not None and emphasis not in EMPHASIS_VALUES:
                errors.append(
                    f"{where}: emphasis must be null or one of {', '.join(EMPHASIS_VALUES)}"
                )
            hints = node.get("hints")
            if hints is not None:
                if not isinstance(hints, list):
                    errors.append(f"{where}: hints must be a list of strings")
                else:
                    if len(hints) > MAX_HINTS_PER_STEP:
                        errors.append(f"{where}: more than {MAX_HINTS_PER_STEP} hints")
                    for hint in hints:
                        if not isinstance(hint, str):
                            errors.append(f"{where}: hints must be strings")
                            break
                        if len(hint) > MAX_HINT_LEN:
                            errors.append(f"{where}: a hint exceeds {MAX_HINT_LEN} characters")
                            break
            key = node.get("key")
            if key is not None and not isinstance(key, str):
                errors.append(f"{where}: key must be a string")
        elif kind == "section":
            if node.get("max_score") is not None:
                errors.append(f"{where}: section nodes carry no max_score")
            if node.get("key") is not None:
                errors.append(f"{where}: section nodes carry no key")
            if node.get("hints"):
                errors.append(f"{where}: section nodes carry no hints (use note)")
            if node.get("emphasis") is not None:
                errors.append(f"{where}: section nodes carry no emphasis")

    if step_count == 0:
        errors.append("structure needs at least one step node with max_score")
    return errors


def validate_grade_scale(scale: Any, total_points: Any = None) -> List[str]:
    """Contract violations of a Notenschlüssel (empty list == valid).

    ``thresholds`` are the MINIMUM points for Notenpunkte 1..18 (exactly 18,
    non-decreasing, >= 0, <= ``total_points`` when given).
    """
    errors: List[str] = []
    if not isinstance(scale, dict):
        return ["grade_scale must be an object"]

    thresholds = scale.get("thresholds")
    if not isinstance(thresholds, list) or len(thresholds) != GRADE_COUNT:
        errors.append(f"grade_scale.thresholds must list exactly {GRADE_COUNT} values")
    else:
        prev = None
        for i, value in enumerate(thresholds):
            if not _is_number(value) or not math.isfinite(float(value)):
                errors.append(f"grade_scale.thresholds[{i}] must be a number")
                prev = None
                continue
            value_f = float(value)
            if value_f < 0:
                errors.append(f"grade_scale.thresholds[{i}] must be >= 0")
            if prev is not None and value_f < prev:
                errors.append(f"grade_scale.thresholds[{i}] is lower than its predecessor")
            if _is_number(total_points) and value_f > float(total_points):
                errors.append(
                    f"grade_scale.thresholds[{i}] ({format_points(value_f)}) exceeds the "
                    f"total of {format_points(total_points)} points"
                )
            prev = value_f

    rounding = scale.get("rounding")
    if rounding is not None and rounding not in ROUNDING_MODES:
        errors.append(f"grade_scale.rounding must be one of {', '.join(ROUNDING_MODES)}")

    pass_grade = scale.get("pass_grade")
    if pass_grade is not None and (
        not isinstance(pass_grade, int)
        or isinstance(pass_grade, bool)
        or not 0 <= pass_grade <= GRADE_COUNT
    ):
        errors.append(f"grade_scale.pass_grade must be an integer between 0 and {GRADE_COUNT}")

    max_points = scale.get("max_points")
    if max_points is not None and (not _is_number(max_points) or float(max_points) <= 0):
        errors.append("grade_scale.max_points must be a positive number")

    unit = scale.get("unit")
    if unit is not None and (not isinstance(unit, str) or len(unit) > MAX_LABEL_LEN):
        errors.append(f"grade_scale.unit must be a string of at most {MAX_LABEL_LEN} characters")
    return errors


# ---------------------------------------------------------------------------
# Normalization + derivations
# ---------------------------------------------------------------------------


def normalize_grade_scale(scale: Dict[str, Any]) -> Dict[str, Any]:
    """Canonical copy of a (validated) Notenschlüssel for storage.

    ``{"unit", "thresholds", "rounding", "pass_grade"}`` with defaults filled
    in, thresholds coerced (int when integral) and ``max_points`` kept only
    when given.
    """
    out: Dict[str, Any] = {
        "unit": _clean_text(scale.get("unit")) or DEFAULT_GRADE_UNIT,
        "thresholds": [
            _coerce_points(t) if _is_number(t) else t for t in (scale.get("thresholds") or [])
        ],
        "rounding": scale.get("rounding") if scale.get("rounding") in ROUNDING_MODES else DEFAULT_ROUNDING,
        "pass_grade": (
            scale["pass_grade"]
            if isinstance(scale.get("pass_grade"), int) and not isinstance(scale.get("pass_grade"), bool)
            else DEFAULT_PASS_GRADE
        ),
    }
    if _is_number(scale.get("max_points")):
        out["max_points"] = _coerce_points(scale["max_points"])
    return out


def normalize_structure(structure: Dict[str, Any]) -> Dict[str, Any]:
    """Canonical copy of a (validated) structure.

    Trims strings, coerces ``max_score`` (int when integral), drops empty
    hints, assigns ids ``n1..nN`` and ALWAYS regenerates the step keys from
    (title, step ordinal). Client-supplied keys are ignored: keys are a
    server-side derivation and editors must not assume key stability across
    edits (old gradings keep their own ``details.scores`` snapshot).
    """
    nodes_out: List[Dict[str, Any]] = []
    step_ordinal = 0
    for index, node in enumerate(structure.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        kind = node.get("kind")
        level = node.get("level")
        level = int(level) if _is_number(level) and level >= 0 else 0
        note = _clean_text(node.get("note")) or None
        out: Dict[str, Any] = {
            "id": f"n{len(nodes_out) + 1}",
            "level": level,
            "kind": kind,
            "label": _clean_text(node.get("label")),
            "title": _clean_text(node.get("title")),
            "note": note,
        }
        if kind == "step":
            step_ordinal += 1
            out["key"] = slugify_step_key(out["title"], step_ordinal)
            score = node.get("max_score")
            out["max_score"] = _coerce_points(score) if _is_number(score) else score
            out["emphasis"] = (
                node.get("emphasis") if node.get("emphasis") in EMPHASIS_VALUES else None
            )
            hints = node.get("hints") if isinstance(node.get("hints"), list) else []
            out["hints"] = [
                _clean_text(hint) for hint in hints if isinstance(hint, str) and hint.strip()
            ]
        nodes_out.append(out)
    return {"version": STRUCTURE_VERSION, "nodes": nodes_out}


def _ancestor_chain(nodes: List[Dict[str, Any]], index: int) -> List[Dict[str, Any]]:
    """Nearest preceding node per level below the node at ``index``."""
    node = nodes[index]
    level = node.get("level") or 0
    chain: List[Dict[str, Any]] = []
    want = level - 1
    for prev in reversed(nodes[:index]):
        prev_level = prev.get("level") or 0
        if prev_level == want:
            chain.append(prev)
            want -= 1
            if want < 0:
                break
    chain.reverse()
    return chain


def _heading(node: Dict[str, Any], *, with_note: bool = False) -> str:
    label = _clean_text(node.get("label"))
    title = _clean_text(node.get("title"))
    text = f"{label} {title}".strip() if label else title
    note = _clean_text(node.get("note"))
    if with_note and note:
        text = f"{text} ({note})"
    return text


def criteria_from_structure(structure: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Flat judge/human criteria ``{key: {name, description, rubric, max_score}}``.

    Depth-first order; ``name`` is the step title, ``description`` the hint
    bullets, ``rubric`` factual prose the judge reads: the ancestor context
    (section notes in parentheses), the Gliederungspunkt with its BE budget,
    the Schwerpunkt marker and the hints.
    """
    nodes = [n for n in (structure.get("nodes") or []) if isinstance(n, dict)]
    criteria: Dict[str, Dict[str, Any]] = {}
    step_ordinal = 0
    for index, node in enumerate(nodes):
        if node.get("kind") != "step":
            continue
        step_ordinal += 1
        title = _clean_text(node.get("title"))
        key = node.get("key") or slugify_step_key(title, step_ordinal)
        hints = [
            _clean_text(h) for h in (node.get("hints") or []) if isinstance(h, str) and h.strip()
        ]
        lines: List[str] = []
        chain = _ancestor_chain(nodes, index)
        if chain:
            lines.append(
                "Kontext: " + " › ".join(_heading(a, with_note=True) for a in chain)
            )
        budget = format_points(node.get("max_score"))
        lines.append(
            f"Gliederungspunkt: {_heading(node)} — max. {budget} BE (halbe BE zulässig)"
        )
        note = _clean_text(node.get("note"))
        if note:
            lines.append(f"Anmerkung: {note}")
        if node.get("emphasis") == "schwerpunkt":
            lines.append("Schwerpunkt der Klausur: ausführliche Prüfung erwartet.")
        if hints:
            lines.append("Hinweise:")
            lines.extend(f"- {h}" for h in hints)
        criteria[key] = {
            "name": title,
            "description": "\n".join(hints),
            "rubric": "\n".join(lines),
            "max_score": node.get("max_score"),
        }
    return criteria


def _flat_sort_key(item: Tuple[str, Any]) -> Tuple[int, int]:
    match = _STEP_KEY_ORDER.match(item[0] or "")
    return (0, int(match.group(1))) if match else (1, 0)


def structure_from_flat_criteria(criteria: Any) -> Dict[str, Any]:
    """Lift legacy flat criteria into level-0 step nodes (lossy by design).

    Ordered by the ``s<NN>_`` key prefix when present (JSONB objects do not
    keep key order), else insertion order. ``title = name or key``; hints are
    the description plus the rubric lines. Entries without a usable
    ``max_score`` never drove grading and are skipped.
    """
    items = list((criteria or {}).items()) if isinstance(criteria, dict) else []
    if any(_STEP_KEY_ORDER.match(str(k)) for k, _ in items):
        items.sort(key=_flat_sort_key)
    nodes: List[Dict[str, Any]] = []
    for key, step in items:
        if not isinstance(step, dict):
            continue
        score = step.get("max_score")
        if not _is_number(score) or float(score) <= 0:
            continue
        hints: List[str] = []
        for text in (step.get("description"), step.get("rubric")):
            for line in _clean_text(text).splitlines():
                line = line.strip()
                if line and line not in hints:
                    hints.append(line)
        nodes.append(
            {
                "id": f"n{len(nodes) + 1}",
                "level": 0,
                "kind": "step",
                "label": "",
                "title": _clean_text(step.get("name")) or str(key),
                "note": None,
                "key": str(key),
                "max_score": _coerce_points(score),
                "emphasis": None,
                "hints": hints[:MAX_HINTS_PER_STEP],
            }
        )
    return {"version": STRUCTURE_VERSION, "nodes": nodes}


# ---------------------------------------------------------------------------
# Rendering (prompt injection + task.data mirror)
# ---------------------------------------------------------------------------


def render_flat_criteria_text(criteria: Any) -> str:
    """Generic rendering of flat criteria (the pre-structure judge fallback).

    The ``[Schlüssel: …]`` suffix lets the model map each step to its schema
    key. Byte-identical to the former ``cell_evaluator._render_rubric_text``
    criteria branch.
    """
    lines = []
    for i, (key, step) in enumerate((criteria or {}).items(), start=1):
        if not isinstance(step, dict):
            continue
        name = step.get("name") or key
        pts = step.get("max_score")
        lines.append(f"{i}. {name} ({pts} Punkte) [Schlüssel: {key}]")
        for text in (step.get("description"), step.get("rubric")):
            text = (text or "").strip()
            for ln in text.splitlines():
                lines.append(f"   {ln}")
    return "\n".join(lines)


def render_grade_scale_text(scale: Dict[str, Any]) -> str:
    """``NOTENSCHLÜSSEL`` block for an effective scale (see ``effective_grade_scale``)."""
    unit = scale.get("unit") or DEFAULT_GRADE_UNIT
    thresholds = scale.get("thresholds") or []
    parts = [f"0 NP unter {format_points(thresholds[0])} {unit}"] if thresholds else []
    for grade, minimum in enumerate(thresholds, start=1):
        parts.append(f"{grade} NP ab {format_points(minimum)} {unit}")
    rounding = scale.get("rounding") or DEFAULT_ROUNDING
    rounding_text = {
        "floor": f"halbe {unit} werden abgerundet",
        "ceil": f"halbe {unit} werden aufgerundet",
        "nearest": f"halbe {unit} werden kaufmännisch gerundet",
        "none": "keine Rundung",
    }.get(rounding, "keine Rundung")
    pass_grade = scale.get("pass_grade")
    if pass_grade is None:
        pass_grade = DEFAULT_PASS_GRADE
    lines = [
        f"NOTENSCHLÜSSEL ({unit} → Notenpunkte): " + "; ".join(parts),
        f"Rundung: {rounding_text}.",
        f"Bestanden ab {pass_grade} Notenpunkten.",
    ]
    return "\n".join(lines)


def render_structure_text(
    structure: Dict[str, Any],
    total_points: Any,
    grade_scale: Optional[Dict[str, Any]] = None,
    *,
    title: Optional[str] = None,
    include_grade_scale: bool = False,
) -> str:
    """Indented outline for prompt injection and the task.data mirror.

    Two spaces per level; steps end in ``(N BE) [Schlüssel: key]`` with a
    ``SCHWERPUNKT`` marker when emphasised and ``– Hinweis:`` lines below.
    Dot decimals on purpose: the judge emits JSON numbers. The optional
    trailing Notenschlüssel block is for the task.data mirror only; the judge
    prompt omits it because the grade is derived server-side.
    """
    total = format_points(total_points) if total_points is not None else format_points(
        total_points_from_structure(structure)
    )
    header_title = _clean_text(title)
    header = (
        f"BEWERTUNGSBOGEN: {header_title} (insgesamt {total} BE; halbe BE zulässig)"
        if header_title
        else f"BEWERTUNGSBOGEN (insgesamt {total} BE; halbe BE zulässig)"
    )
    lines = [header]
    for node in structure.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        indent = "  " * int(node.get("level") or 0)
        if node.get("kind") == "step":
            marker = " SCHWERPUNKT" if node.get("emphasis") == "schwerpunkt" else ""
            lines.append(
                f"{indent}{_heading(node)} ({format_points(node.get('max_score'))} BE)"
                f"{marker} [Schlüssel: {node.get('key')}]"
            )
            note = _clean_text(node.get("note"))
            if note:
                lines.append(f"{indent}  – Anmerkung: {note}")
            for hint in node.get("hints") or []:
                hint = _clean_text(hint)
                if hint:
                    lines.append(f"{indent}  – Hinweis: {hint}")
        else:
            lines.append(f"{indent}{_heading(node, with_note=True)}")
    if include_grade_scale:
        lines.append("")
        lines.append(render_grade_scale_text(effective_grade_scale(grade_scale, total_points)))
    return "\n".join(lines)


def rubric_prompt_text(rubric: Any, include_grade_scale: bool = False) -> str:
    """Judge-facing text of a rubric row (or row-like object).

    Precedence: a pre-rendered ``generation_metadata.rendered_text`` (written
    by the AI generator; carries document-level context the structure cannot)
    → the structure outline → the flat criteria. A malformed structure falls
    through to the flat rendering instead of raising.
    """
    metadata = getattr(rubric, "generation_metadata", None) or {}
    rendered = metadata.get("rendered_text") if isinstance(metadata, dict) else None
    if isinstance(rendered, str) and rendered.strip():
        return rendered

    structure = getattr(rubric, "structure", None)
    if isinstance(structure, dict) and not validate_structure(structure):
        try:
            return render_structure_text(
                structure,
                getattr(rubric, "total_points", None),
                getattr(rubric, "grade_scale", None),
                title=getattr(rubric, "title", None),
                include_grade_scale=include_grade_scale,
            )
        except Exception:  # pragma: no cover - defensive, falls through to flat
            pass
    return render_flat_criteria_text(getattr(rubric, "criteria", None))


def mirror_rubric_into_task_data(task: Any, rubric: Any) -> None:
    """Mirror the ACTIVE rubric into ``task.data["bewertungsbogen"]``.

    The Bewertungsbogen belongs next to Sachverhalt and Musterlösung as
    task-level data (visible on the data page, included in task exports,
    referenceable as ``$bewertungsbogen`` in prompt structures). The
    ``task_rubrics`` row stays the source of truth; this is a synced snapshot
    of the active rubric's rendering (with the Notenschlüssel). Pass
    ``rubric=None`` when no active rubric remains to remove the key. Callers
    must be in a session that will be committed.
    """
    from sqlalchemy.orm.attributes import flag_modified

    data = dict(task.data or {})
    if rubric is None:
        if "bewertungsbogen" not in data:
            return
        data.pop("bewertungsbogen", None)
    else:
        data["bewertungsbogen"] = rubric_prompt_text(rubric, include_grade_scale=True)
    task.data = data
    flag_modified(task, "data")


# ---------------------------------------------------------------------------
# Grades (Notenpunkte)
# ---------------------------------------------------------------------------


def effective_grade_scale(scale: Any, total_points: Any) -> Dict[str, Any]:
    """The scale actually applied: the rubric's own, or the default table
    scaled to ``total_points`` (``source`` = ``"rubric"`` | ``"default"``)."""
    total = float(total_points) if _is_number(total_points) and float(total_points) > 0 else 100.0
    if isinstance(scale, dict) and isinstance(scale.get("thresholds"), list) and len(
        scale["thresholds"]
    ) == GRADE_COUNT:
        thresholds = [float(t) if _is_number(t) else 0.0 for t in scale["thresholds"]]
        pass_grade = scale.get("pass_grade")
        max_points = scale.get("max_points")
        return {
            "unit": scale.get("unit") or DEFAULT_GRADE_UNIT,
            "thresholds": [_coerce_points(t) for t in thresholds],
            "rounding": scale.get("rounding") if scale.get("rounding") in ROUNDING_MODES else DEFAULT_ROUNDING,
            "pass_grade": pass_grade if isinstance(pass_grade, int) and not isinstance(pass_grade, bool) else DEFAULT_PASS_GRADE,
            "max_points": _coerce_points(max_points) if _is_number(max_points) else _coerce_points(total),
            "source": "rubric",
        }
    factor = total / 100.0
    return {
        "unit": DEFAULT_GRADE_UNIT,
        "thresholds": [_coerce_points(round(t * factor, 6)) for t in DEFAULT_GRADE_THRESHOLDS],
        "rounding": DEFAULT_ROUNDING,
        "pass_grade": DEFAULT_PASS_GRADE,
        "max_points": _coerce_points(total),
        "source": "default",
    }


def _apply_rounding(points: float, rounding: str) -> float:
    if rounding == "floor":
        return float(math.floor(points))
    if rounding == "ceil":
        return float(math.ceil(points))
    if rounding == "nearest":
        # kaufmännisch: halves round away from zero
        return float(math.floor(points + 0.5))
    return points


def grade_from_points(
    points: Any, total_points: Any, scale: Any = None
) -> Tuple[int, bool]:
    """``(Notenpunkte 0..18, passed)`` for ``points`` on a rubric.

    Rounding applies first (``floor`` by default: 39.5 → 39), then the grade
    is the number of thresholds at or below the rounded points (capped at
    18); ``passed`` is ``grade >= pass_grade``. ``None``/NaN points → (0, False).
    """
    if not _is_number(points):
        return 0, False
    value = float(points)
    if not math.isfinite(value):
        return 0, False
    effective = effective_grade_scale(scale, total_points)
    value = _apply_rounding(max(0.0, value), effective["rounding"])
    thresholds = [float(t) for t in effective["thresholds"]]
    grade = min(GRADE_COUNT, bisect_right(thresholds, value))
    return grade, grade >= int(effective["pass_grade"])


def grade_for_rubric(rubric: Any, points: Any, fallback_total: Any) -> Tuple[int, bool, str]:
    """``(grade, passed, scale_source)`` for a rubric row (or row-like object).

    The rubric's ``total_points`` wins over ``fallback_total`` (the judge's
    summed ``total_max``); ``scale_source`` is ``"rubric"`` when the row
    carries its own Notenschlüssel, else ``"default"``.
    """
    total = getattr(rubric, "total_points", None)
    if not _is_number(total) or float(total) <= 0:
        total = fallback_total
    scale = getattr(rubric, "grade_scale", None)
    grade, passed = grade_from_points(points, total, scale)
    source = effective_grade_scale(scale, total)["source"]
    return grade, passed, source

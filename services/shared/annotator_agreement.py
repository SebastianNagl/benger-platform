"""Inter-annotator agreement over overlapping annotations, per control.

A task that two or more people annotated gives one comparable item per
control (the Label Studio ``from_name``) they both answered. For every
control with such overlap this module reports the agreement that
``bg_statistics.compute_agreement`` computes over (annotator, task, value)
triples:

* ``choices`` (single or multiple selection) and ``rating`` controls:
  Fleiss' kappa over all annotators, Cohen's kappa for every pair of
  annotators with at least two shared tasks, and percent agreement. A
  multiple selection counts as one category per distinct set of choices,
  so two annotations agree only when they picked exactly the same set.
* ``number`` controls: Pearson's r for every pair and the mean absolute
  deviation from the per-task mean.

Free text, spans and other controls have no defined category or number,
so they are listed under ``unsupported_controls`` and not scored.

Only active annotations count (``was_cancelled = false``); the partial
unique index on ``annotations`` keeps one per (task, user). Annotators are
labelled with ``user_display.masked_name`` (the pseudonym rule the report
and the leaderboards use), because the result is shown to project members
and frozen into published, possibly public, reports.

The result is ``None`` when no task has two annotators, so callers hide the
block entirely.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from bg_statistics import compute_agreement
from user_display import masked_name

# Control types with a defined value to compare, and the score type
# ``compute_agreement`` uses for each.
_SCORE_TYPES = {
    "choices": "categorical",
    "rating": "ordinal",
    "number": "numeric",
}

# Pairwise rows kept per control. A project with many annotators has
# n * (n - 1) / 2 pairs; the summary numbers cover all of them, and the
# list keeps the pairs with the most shared tasks so a frozen report
# snapshot stays small.
MAX_PAIRS_PER_CONTROL = 50

# Annotations of tasks that at least two different people annotated.
OVERLAP_ANNOTATIONS_SQL = """
SELECT a.task_id, a.completed_by, a.result, u.pseudonym
FROM annotations a
JOIN users u ON u.id = a.completed_by
WHERE a.project_id = :project_id
  AND a.was_cancelled = false
  AND a.task_id IN (
      SELECT task_id FROM annotations
      WHERE project_id = :project_id AND was_cancelled = false
      GROUP BY task_id
      HAVING COUNT(DISTINCT completed_by) >= 2
  )
"""


def _control_values(result: Any) -> Dict[str, Tuple[str, Any]]:
    """Control name -> (control type, comparable value) of one annotation.

    Keeps the first result per control, like ``analysis.observations``'s
    ``typed_field_values``. Values that cannot be compared (missing, empty
    or of an unexpected shape) are left out; an unsupported control type
    keeps its type with the value ``None`` so it can be listed."""
    out: Dict[str, Tuple[str, Any]] = {}
    if not isinstance(result, list):
        return out
    for item in result:
        if not isinstance(item, Mapping):
            continue
        name = item.get("from_name")
        if not isinstance(name, str) or not name or name in out:
            continue
        value = item.get("value")
        kind = item.get("type")
        if not isinstance(kind, str) or not kind:
            if isinstance(value, Mapping):
                kind = next((k for k in _SCORE_TYPES if k in value), "unknown")
            else:
                kind = "unknown"
        kind = kind.lower()
        if kind not in _SCORE_TYPES or not isinstance(value, Mapping):
            out[name] = (kind, None)
            continue
        raw = value.get(kind)
        comparable: Any = None
        if kind == "choices":
            if isinstance(raw, (list, tuple)):
                choices = sorted({str(c) for c in raw if c is not None and str(c) != ""})
                if choices:
                    comparable = choices[0] if len(choices) == 1 else tuple(choices)
            elif isinstance(raw, str) and raw:
                comparable = raw
        elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
            # Whole numbers stay ints so rating categories read "4", not "4.0".
            comparable = int(raw) if float(raw).is_integer() else float(raw)
        out[name] = (kind, comparable)
    return out


def _category_label(value: Any) -> str:
    return " + ".join(value) if isinstance(value, tuple) else str(value)


def agreement_by_control(
    rows: Iterable[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Agreement per control over annotation rows.

    Each row has ``task_id``, ``completed_by``, ``result`` (the Label
    Studio result list) and optionally ``pseudonym``. Rows of tasks with a
    single annotator are ignored. Returns ``None`` when no task has two
    annotators."""
    labels: Dict[str, str] = {}
    # control -> task -> annotator -> value
    values: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    kinds: Dict[str, str] = {}
    unsupported: Dict[str, str] = {}
    annotators_by_task: Dict[str, set] = defaultdict(set)

    for row in rows:
        task_id = str(row["task_id"])
        user_id = str(row["completed_by"])
        annotators_by_task[task_id].add(user_id)
        if user_id not in labels:
            labels[user_id] = masked_name(user_id=user_id, pseudonym=row.get("pseudonym"))
        for control, (kind, value) in _control_values(row.get("result")).items():
            if kind not in _SCORE_TYPES:
                unsupported.setdefault(control, kind)
                continue
            kinds.setdefault(control, kind)
            if value is not None and kinds[control] == kind:
                values[control][task_id][user_id] = value

    overlap_tasks = {t for t, users in annotators_by_task.items() if len(users) >= 2}
    if not overlap_tasks:
        return None

    controls: List[Dict[str, Any]] = []
    for control in sorted(values):
        kind = kinds[control]
        score_type = _SCORE_TYPES[kind]
        per_task = {
            t: by_user for t, by_user in values[control].items()
            if t in overlap_tasks and len(by_user) >= 2
        }
        if not per_task:
            continue
        triples = [(u, t, v) for t, by_user in per_task.items() for u, v in by_user.items()]
        report = compute_agreement(triples, score_type=score_type)

        pair_n: Dict[Tuple[str, str], int] = defaultdict(int)
        for by_user in per_task.values():
            users = sorted(by_user, key=str)
            for i, a in enumerate(users):
                for b in users[i + 1:]:
                    pair_n[(a, b)] += 1

        pairs: List[Dict[str, Any]] = []
        for (a, b), n in pair_n.items():
            # Both measures are symmetric, so the pair reads in label order.
            label_a, label_b = sorted((labels[a], labels[b]), key=str.lower)
            entry: Dict[str, Any] = {
                "annotator_a": label_a,
                "annotator_b": label_b,
                "n_items": n,
            }
            if score_type == "numeric":
                entry["pearson_r"] = report.pearson_r_pairwise.get((a, b))
            else:
                entry["cohens_kappa"] = report.cohens_kappa_pairwise.get((a, b))
            pairs.append(entry)
        pairs.sort(key=lambda p: (-p["n_items"], p["annotator_a"], p["annotator_b"]))

        kappas = list(report.cohens_kappa_pairwise.values())
        pearsons = [r for r in report.pearson_r_pairwise.values() if r is not None]
        categories = sorted({_category_label(v) for _u, _t, v in triples}) if score_type != "numeric" else []
        controls.append({
            "control": control,
            "type": kind,
            "score_type": score_type,
            "multi_select": kind == "choices" and any(isinstance(v, tuple) for _u, _t, v in triples),
            "n_items": len(per_task),
            "n_annotators": report.n_raters,
            "n_annotations": len(triples),
            "categories": categories,
            "fleiss_kappa": report.fleiss_kappa,
            "cohens_kappa_mean": round(sum(kappas) / len(kappas), 4) if kappas else None,
            "percent_agreement": report.percent_agreement,
            "pearson_r_mean": round(sum(pearsons) / len(pearsons), 4) if pearsons else None,
            "mean_absolute_deviation": report.mean_absolute_deviation,
            "pairs": pairs[:MAX_PAIRS_PER_CONTROL],
            "pairs_total": len(pairs),
        })

    overlap_annotators = {u for t in overlap_tasks for u in annotators_by_task[t]}
    return {
        "overlap_task_count": len(overlap_tasks),
        "annotator_count": len(overlap_annotators),
        "controls": controls,
        "unsupported_controls": [
            {"control": name, "type": kind}
            for name, kind in sorted(unsupported.items())
            if name not in kinds
        ],
    }


def load_overlap_rows(db: Session, project_id: str) -> Sequence[Mapping[str, Any]]:
    """Active annotations of the project's tasks with two or more annotators."""
    return db.execute(text(OVERLAP_ANNOTATIONS_SQL), {"project_id": project_id}).mappings().all()


def project_annotator_agreement(db: Session, project_id: str) -> Optional[Dict[str, Any]]:
    """Agreement per control for one project (``None`` without overlap)."""
    return agreement_by_control(load_overlap_rows(db, project_id))

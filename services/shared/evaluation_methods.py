"""Evaluation methods with alternative configs, and research data.

A project can grade one method with several evaluation configs, for example
the same judge prompt on two judge models. The teacher-facing views (the
results grid, the cell modal, the per-submission results export) show such
a group as ONE method: for every subject one config of the group is the
official one, the others are research data, kept and exported in full but
hidden until the viewer asks for research data. A config can also be
research data on its own.

Where the grouping comes from
-----------------------------
Only from an extension package: the ``evaluation_method_selection`` hook
(``services/api/extensions.py``, SINGLE_OWNER) is called as
``hook(db, project, configs, user_ids)`` with the project's enabled configs
and the account ids whose answers the view shows, and may return a dict
(every key optional):

``{"groups": {group: {"config_ids": [...], "label": str}},
"official": {group: config_id},
"official_by_user": {user_id: {group: config_id}},
"research_only": [config_id, ...]}``

``groups`` names the configs that grade one method and its label (else the
official config's ``display_name``), ``official`` the group's default
official config (else the group's first config in list order),
``official_by_user`` decides per submitting account (an answer's official
config can differ by who submitted it), and ``research_only`` marks configs
that are research data for every subject. An unknown config id in an answer
is ignored. Generations always use the default official config.

Without an answer (no package implements the hook, or it failed) every
config is its own method.

The score a teacher view shows
------------------------------
The official choice is per account, but a subject can lack a successful
grading by its official config while another config of the group graded it,
for example an account whose answers one config graded on one task and the
other config on another. :func:`teacher_current_rows` is the one rule every
teacher view uses (the results grid, the cell modal, the per-submission
results export and the ``is_method_current`` marker of the comprehensive
export): per cell of a method group (subject, prediction field, reference
field), the official config's current rows when one of them carries a
score, else the current rows of the first other config of the group (in the
group's config order) that has a scored one, marked with the official config
it stands in for. A row of a config that grades once per prediction field
covers every reference field of its subject. When no config of the group has
a score, the official config's rows stay, so a failure stays visible. Views
with history use :func:`teacher_rows`: the superseded rows of the config
that supplies the cell. Research views keep reading ``is_official``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set

import current_scores


@dataclass
class MethodSelection:
    """Which config of each method group is official, per subject."""

    config_ids: List[str] = field(default_factory=list)
    groups: Dict[str, List[str]] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    default_official: Dict[str, str] = field(default_factory=dict)
    official_by_user: Dict[str, Dict[str, str]] = field(default_factory=dict)
    research_only: Set[str] = field(default_factory=set)

    @property
    def group_of(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for group, members in self.groups.items():
            for config_id in members:
                out.setdefault(config_id, group)
        return out

    def official_config(self, group: str, user_id: Optional[str] = None) -> Optional[str]:
        members = self.groups.get(group) or []
        if user_id is not None:
            chosen = (self.official_by_user.get(str(user_id)) or {}).get(group)
            if chosen in members:
                return chosen
        chosen = self.default_official.get(group)
        if chosen in members:
            return chosen
        return members[0] if members else None

    def is_official(self, config_id: Optional[str], user_id: Optional[str] = None) -> bool:
        """Whether rows of ``config_id`` are official (not research data) for
        a subject submitted by ``user_id`` (``None``: a generation, or no
        submitting account)."""
        if not config_id:
            return True
        if config_id in self.research_only:
            return False
        group = self.group_of.get(config_id)
        if group is None:
            return True
        return self.official_config(group, user_id) == config_id

    def default_research_config_ids(self) -> Set[str]:
        """Configs that are research data for a subject without a per-user
        answer: the default views leave them out."""
        return {cid for cid in self.config_ids if not self.is_official(cid)}

    def method_key(self, config_id: str) -> str:
        """The view's key of the method a config belongs to."""
        group = self.group_of.get(config_id)
        return f"group:{group}" if group is not None else config_id

    def to_public(self, display_names: Mapping[str, str]) -> Dict[str, Any]:
        """The shape the frontend reads (no per-user answers)."""
        groups = []
        for group, members in self.groups.items():
            official = self.official_config(group)
            label = self.labels.get(group) or display_names.get(official or "", "") or group
            groups.append(
                {
                    "key": group,
                    "method_key": f"group:{group}",
                    "label": label,
                    "config_ids": list(members),
                    "default_official_config_id": official,
                }
            )
        return {
            "groups": groups,
            "research_config_ids": sorted(self.default_research_config_ids()),
        }


def _row_has_score(row: Any) -> bool:
    return current_scores.row_has_score(current_scores._get(row, "metrics"))


def _covering(by_config: Mapping[str, Mapping[str, List[Any]]], member: str, ref: str) -> List[Any]:
    """The rows of ``member`` in the cell of reference field ``ref``: its
    rows of ``ref`` and the ones graded once per prediction field."""
    by_ref = by_config.get(member) or {}
    return list(by_ref.get(ref, [])) + (list(by_ref.get("", [])) if ref else [])


def teacher_current_rows(
    selection: MethodSelection,
    rows: Iterable[Any],
    submitter_of: Optional[Mapping[Any, Any]] = None,
    configs_by_id: Optional[Mapping[str, Mapping[str, Any]]] = None,
    *,
    has_score: Optional[Callable[[Any], bool]] = None,
) -> Dict[str, Optional[str]]:
    """The rows a teacher view shows as the current score of their method.

    ``rows`` are current rows (``current_scores.pick_current``), ``submitter_of``
    maps an annotation id to the account that submitted it (generation rows
    and rows without a submission use the default official config),
    ``configs_by_id`` are the project's configs (``current_scores.configs_by_id``,
    which decide a row's cell) and ``has_score`` tells whether a row carries
    a score (default: the ``metrics`` of the row, ``current_scores.row_has_score``).

    The config that supplies the score is chosen per cell of the method:
    subject, prediction field and reference field. A row of a config that
    grades once per prediction field (reference part ``""``) covers every
    reference field of its subject and prediction field.

    Returns ``{row id: stands in for}`` for every shown row: ``None`` for a
    row of a config outside any group or of the subject's official config,
    else the id of the official config whose missing score the row replaces
    (see the module docstring). Rows of research-only configs, and of a
    group's other configs while the official one has a score, are left out.
    """
    scored = has_score or _row_has_score
    submitters = {str(k): v for k, v in (submitter_of or {}).items()}
    group_of = selection.group_of
    shown: Dict[str, Optional[str]] = {}
    buckets: Dict[tuple, Dict[str, Dict[str, List[Any]]]] = {}
    for row in rows:
        kind, subject_id, config_id, pred, ref = current_scores.cell_key(row, configs_by_id)
        if config_id in selection.research_only:
            continue
        group = group_of.get(config_id)
        if group is None:
            shown[current_scores.row_id(row)] = None
            continue
        bucket = buckets.setdefault((kind, subject_id, group, pred), {})
        bucket.setdefault(config_id, {}).setdefault(ref, []).append(row)
    for (kind, subject_id, group, _pred), by_config in buckets.items():
        user_id = submitters.get(subject_id) if kind == current_scores.SUBJECT_ANNOTATION else None
        official = selection.official_config(group, None if user_id is None else str(user_id))
        refs = sorted({ref for by_ref in by_config.values() for ref in by_ref if ref}) or [""]
        for ref in refs:
            supplier = official
            if not any(scored(r) for r in _covering(by_config, official, ref)):
                supplier = next(
                    (
                        member
                        for member in selection.groups.get(group) or []
                        if member != official and any(scored(r) for r in _covering(by_config, member, ref))
                    ),
                    official,
                )
            for row in _covering(by_config, supplier, ref):
                shown[current_scores.row_id(row)] = None if supplier == official else official
    return shown


def teacher_rows(
    selection: MethodSelection,
    rows: Iterable[Any],
    submitter_of: Optional[Mapping[Any, Any]] = None,
    configs_by_id: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Optional[str]]:
    """:func:`teacher_current_rows` over ``rows`` with their history.

    ``rows`` may hold current and superseded rows. A superseded row is shown
    when the current row of its cell is, and stands in for the same official
    config, so a view with history shows the rows of the same config as the
    view without it.
    """
    rows = list(rows)
    current = current_scores.pick_current(rows, configs_by_id)
    shown = teacher_current_rows(selection, current.values(), submitter_of, configs_by_id)
    out: Dict[str, Optional[str]] = {}
    for row in rows:
        current_id = current_scores.row_id(current[current_scores.cell_key(row, configs_by_id)])
        if current_id in shown:
            out[current_scores.row_id(row)] = shown[current_id]
    return out


def _enabled(configs: Iterable[Any]) -> List[Dict[str, Any]]:
    out = []
    for config in configs or []:
        if isinstance(config, Mapping) and config.get("id") and config.get("enabled", True) is not False:
            out.append(dict(config))
    return out


def build_method_selection(configs: Iterable[Any], hook_answer: Any = None) -> MethodSelection:
    """The method selection an extension's answer gives ``configs``."""
    enabled = _enabled(configs)
    ids = [str(c["id"]) for c in enabled]
    known = set(ids)
    selection = MethodSelection(config_ids=ids)

    answer = hook_answer if isinstance(hook_answer, Mapping) else {}
    for group, spec in (answer.get("groups") or {}).items():
        if not isinstance(group, str) or not isinstance(spec, Mapping):
            continue
        grouped = set(selection.group_of)
        members = [
            str(c) for c in spec.get("config_ids") or [] if str(c) in known and str(c) not in grouped
        ]
        if not members:
            continue
        selection.groups[group] = sorted(set(members), key=ids.index)
        label = spec.get("label")
        if isinstance(label, str) and label.strip():
            selection.labels[group] = label.strip()
    for group, config_id in (answer.get("official") or {}).items():
        if str(config_id) in (selection.groups.get(group) or []):
            selection.default_official[group] = str(config_id)
    for user_id, choice in (answer.get("official_by_user") or {}).items():
        if not isinstance(choice, Mapping):
            continue
        picked = {
            g: str(c) for g, c in choice.items() if str(c) in (selection.groups.get(g) or [])
        }
        if picked:
            selection.official_by_user[str(user_id)] = picked
    for config_id in answer.get("research_only") or []:
        if str(config_id) in known:
            selection.research_only.add(str(config_id))

    # A one-config group is no group: nothing to choose between.
    for group in [g for g, members in selection.groups.items() if len(members) < 2]:
        del selection.groups[group]
        selection.default_official.pop(group, None)
    return selection


def project_configs(project: Any) -> List[Dict[str, Any]]:
    """The enabled evaluation configs stored on a project."""
    evaluation_config = getattr(project, "evaluation_config", None)
    if not isinstance(evaluation_config, Mapping):
        return []
    return _enabled(evaluation_config.get("evaluation_configs") or [])

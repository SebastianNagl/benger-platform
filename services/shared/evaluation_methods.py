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
Static, in the stored config (``project.evaluation_config.evaluation_configs``):

``method_group`` (str)
    Configs with the same value are alternatives of one method.
``method_label`` (str, optional)
    Label of that method in the views; else the official config's
    ``display_name``.
``method_official`` (bool, optional)
    Marks the group's default official config; else the first config of the
    group in list order is.
``research_only`` (bool, optional)
    The config is research data for every subject.

Dynamic, from an extension package: the ``evaluation_method_selection`` hook
(``services/api/extensions.py``, SINGLE_OWNER) is called as
``hook(db, project, configs, user_ids)`` with the project's enabled configs
and the account ids whose answers the view shows, and may return a dict
(every key optional):

``{"groups": {group: {"config_ids": [...], "label": str}},
"official": {group: config_id},
"official_by_user": {user_id: {group: config_id}},
"research_only": [config_id, ...]}``

Its groups and labels are added to (and override) the static ones, its
``official`` answers replace the static default, ``official_by_user``
decides per submitting account (an answer's official config can differ by
who submitted it), and ``research_only`` adds to the static flags. An
unknown config id in an answer is ignored. Generations always use the
default official config.

Without any of this every config is its own method, as before.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set


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


def _enabled(configs: Iterable[Any]) -> List[Dict[str, Any]]:
    out = []
    for config in configs or []:
        if isinstance(config, Mapping) and config.get("id") and config.get("enabled", True) is not False:
            out.append(dict(config))
    return out


def build_method_selection(configs: Iterable[Any], hook_answer: Any = None) -> MethodSelection:
    """Combine the static config fields with an extension's answer."""
    enabled = _enabled(configs)
    ids = [str(c["id"]) for c in enabled]
    known = set(ids)
    selection = MethodSelection(config_ids=ids)

    for config in enabled:
        cid = str(config["id"])
        group = config.get("method_group")
        if isinstance(group, str) and group.strip():
            group = group.strip()
            selection.groups.setdefault(group, []).append(cid)
            label = config.get("method_label")
            if isinstance(label, str) and label.strip() and group not in selection.labels:
                selection.labels[group] = label.strip()
            if config.get("method_official") is True and group not in selection.default_official:
                selection.default_official[group] = cid
        if config.get("research_only") is True:
            selection.research_only.add(cid)

    answer = hook_answer if isinstance(hook_answer, Mapping) else {}
    for group, spec in (answer.get("groups") or {}).items():
        if not isinstance(group, str) or not isinstance(spec, Mapping):
            continue
        members = [str(c) for c in spec.get("config_ids") or [] if str(c) in known]
        if not members:
            continue
        # A config belongs to one group: the answer's group takes it over.
        for other, other_members in list(selection.groups.items()):
            if other != group:
                selection.groups[other] = [c for c in other_members if c not in members]
                if not selection.groups[other]:
                    del selection.groups[other]
        selection.groups[group] = sorted(members, key=ids.index)
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

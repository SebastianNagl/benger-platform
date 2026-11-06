"""Data shape of ``projects.exam_tools`` (migration 127).

A project lists the tools (Hilfsmittel) its writers may use in the exam
interface and, for content tools, the whitelist of providers and codes::

    {"tools": [{"id": "calculator"},
               {"id": "law_texts",
                "config": {"codes": ["BGB", "StGB"], "search": true,
                           "sources": [{"provider": "lexmea", "mode": "student"},
                                       {"provider": "lexmea", "mode": "org",
                                        "connection_id": "..."},
                                       {"provider": "gii", "mode": "builtin"}]}}]}

NULL means the project never chose (the interfaces keep their built-in
defaults). The tools themselves, the validation of each tool's ``config`` and
the endpoint that writes the column live in the extended edition; this module
only holds the generic shape helpers export and import need.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

# Keys of a tool config that point at rows of this deployment (an org's
# connection to a tool provider). They are dropped when the project leaves
# the deployment; the importer re-selects a connection in the settings.
_DEPLOYMENT_BOUND_CONFIG_KEYS = ("connection_id",)


def _without_bound_keys(value: Any) -> Any:
    """Deep copy of ``value`` without deployment-bound keys at any depth
    (v2 keeps ``connection_id`` inside the ``sources`` list)."""
    if isinstance(value, dict):
        return {
            k: _without_bound_keys(v)
            for k, v in value.items()
            if k not in _DEPLOYMENT_BOUND_CONFIG_KEYS
        }
    if isinstance(value, list):
        return [_without_bound_keys(v) for v in value]
    return copy.deepcopy(value)


def portable_exam_tools(value: Any) -> Optional[dict]:
    """The exam tools an exported or imported copy carries.

    Returns ``None`` for anything that is not a well-formed exam tools
    document, drops malformed tool entries and strips deployment-bound
    references from each tool's config.
    """
    if not isinstance(value, dict):
        return None
    tools = value.get("tools")
    if not isinstance(tools, list):
        return None
    portable = []
    for tool in tools:
        if not isinstance(tool, dict) or not isinstance(tool.get("id"), str):
            continue
        entry: dict = {"id": tool["id"]}
        config = tool.get("config")
        if isinstance(config, dict):
            entry["config"] = _without_bound_keys(config)
        portable.append(entry)
    return {"tools": portable}

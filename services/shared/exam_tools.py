"""Data shape of ``projects.exam_tools`` (migration 127).

A project lists the tools (Hilfsmittel) its writers may use in the exam
interface, e.g. a calculator, a calendar or law texts::

    {"version": 1,
     "tools": [{"id": "calculator"},
               {"id": "law_texts",
                "config": {"provider": "gii", "connection_id": null,
                           "codes": ["BGB", "StGB"], "search": true}}]}

NULL means the project never chose (the interfaces keep their built-in
defaults). The tools themselves, the validation of each tool's ``config`` and
the endpoint that writes the column live in the extended edition; this module
only holds the generic shape helpers export and import need.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

EXAM_TOOLS_VERSION = 1

# Keys of a tool config that point at rows of this deployment (an org's
# connection to a tool provider). They are dropped when the project leaves
# the deployment; the importer re-selects a connection in the settings.
_DEPLOYMENT_BOUND_CONFIG_KEYS = ("connection_id",)


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
            entry["config"] = {
                k: copy.deepcopy(v)
                for k, v in config.items()
                if k not in _DEPLOYMENT_BOUND_CONFIG_KEYS
            }
        portable.append(entry)
    version = value.get("version")
    return {
        "version": version if isinstance(version, int) else EXAM_TOOLS_VERSION,
        "tools": portable,
    }

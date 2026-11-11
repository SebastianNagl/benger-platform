"""The prompts of the requirement-level rubric judge, for readers outside
the worker (the project page's Prompts card).

A Bewertungsbogen whose steps list requirements is graded per requirement,
and that lane owns its prompts: the grading template a project stores for
the rubric judge is not used there. The texts live in the worker
(``ml_evaluation/checklist_scoring.py``), which the API process cannot
import; ``rubric_requirement_prompts.json`` next to this module is written
from the worker code (``services/workers/scripts/write_rubric_requirement_prompts.py``)
and pinned to it by the workers test suite.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

_FILE = Path(__file__).resolve().parent / "rubric_requirement_prompts.json"


@lru_cache(maxsize=1)
def _document() -> Dict[str, Any]:
    return json.loads(_FILE.read_text(encoding="utf-8"))


def requirement_judge_prompts() -> Dict[str, Any]:
    """``{default_unit, alternatives, user_template, paths_rule, units}``.

    ``units`` maps each requirement unit (``binary``: met or not met, the
    default; ``bullet``: three levels) to its ``system_prompt`` and
    ``closing_rules`` as sent for a sheet with other solution paths.
    ``paths_rule`` is the one rule of both texts that a sheet without such
    paths does not get. ``user_template`` carries the placeholders the worker
    fills per task. A fresh copy on every call."""
    document = copy.deepcopy(_document())
    document.pop("note", None)
    return document

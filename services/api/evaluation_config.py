"""Backward-compatibility shim for the open-core metric-registration contract.

The former top-level ``evaluation_config`` module was split during the Tier-2
decomposition into ``services/evaluation/config.py`` (+ ``human_eval_runs.py``).
All *platform-internal* callers were updated to the new path, but the top-level
``evaluation_config`` import path is part of the **open-core contract surface**:

  * ``benger_extended`` registers its proprietary metrics at import time via
    ``from evaluation_config import register_extended_metrics`` (see
    ``benger_extended/__init__.py::_register_extended_metrics`` — the import is
    wrapped in ``try/except ImportError: pass``, so a broken path does not crash,
    it *silently* drops ``llm_judge_falloesung`` / ``korrektur_custom`` from the
    evaluation wizard).
  * The open-core metric-contract behavioral test imports ``AnswerType`` /
    ``get_metrics_for_answer_type`` from here.

This import path is part of the stable contract (it predates the 2.x handshake
bumps and has survived them unchanged), so we keep this thin re-export rather
than break the extended overlay. Remove only alongside a coordinated handshake
bump + an extended import update.
"""

from services.evaluation.config import (  # noqa: F401  (re-export surface)
    ANSWER_TYPE_TO_METRICS,
    AnswerType,
    AnswerTypeDetector,
    get_available_methods_for_project,
    get_metric_defaults,
    get_metric_parameters,
    get_metrics_for_answer_type,
    get_selected_metrics_for_field,
    lookup_available_methods,
    normalize_metric_selection,
    normalize_selected_methods,
    register_extended_metrics,
    update_project_evaluation_config,
    validate_metric_selection,
)

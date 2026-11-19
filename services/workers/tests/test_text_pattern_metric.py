"""The ``text_pattern`` evaluation metric: a text pattern code of a
prediction as a TaskEvaluation value."""

from __future__ import annotations

import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation import metric_registry  # noqa: E402
from ml_evaluation.sample_evaluator import SampleEvaluator  # noqa: E402

PATTERN_SET = {
    "name": "parties",
    "version": "3",
    "codes": {
        "names_party": {"mode": "count", "patterns": [r"\b{{task.party}}\b"]},
        "names_claimant": {"mode": "any", "patterns": ["Claimant"]},
        "side": {"mode": "first", "default": "none", "rules": [
            {"value": "P", "patterns": ["Claimant"]}, {"value": "D", "patterns": ["Respondent"]}]},
    },
}


def _params(code):
    return {"pattern_set": PATTERN_SET, "code": code}


def test_registered_and_reference_free():
    handler = metric_registry.get("text_pattern")
    assert handler is not None and handler.reference_free and handler.uses_task_data


def test_values_and_details():
    handler = metric_registry.get("text_pattern")
    out = handler.compute(None, "Meier and Meier, the Claimant", "text", _params("names_party"),
                          task_data={"party": "Meier"})
    assert out["value"] == 2.0 and out["error"] is None
    assert out["details"]["pattern_set"]["ref"] == "parties@3"
    assert len(out["details"]["pattern_set"]["hash"]) == 64
    assert out["details"]["codes"] == {"names_party": 2.0, "names_claimant": 1.0, "side": "P"}
    first = handler.compute(None, "the Respondent", "text", _params("side"), task_data={})
    assert first["value"] == 1.0 and first["details"]["label"] == "D"
    default = handler.compute(None, "nobody", "text", _params("side"), task_data={})
    assert default["value"] == 0.0 and default["details"]["label"] == "none"


def test_errors_are_values_none_with_a_reason():
    handler = metric_registry.get("text_pattern")
    unresolved = handler.compute(None, "Meier", "text", _params("names_party"), task_data={})
    assert unresolved["value"] is None and "does not resolve" in unresolved["error"]
    assert handler.compute(None, None, "text", _params("side"))["error"] == "the prediction has no text to code"
    bad_set = handler.compute(None, "x", "text", {"pattern_set": {"name": "x"}, "code": "a"})
    assert bad_set["value"] is None and "invalid pattern set" in bad_set["error"]
    bad_code = handler.compute(None, "x", "text", _params("nope"))
    assert "no code 'nope'" in bad_code["error"]


def test_the_sample_evaluator_passes_raw_text_and_task_data():
    """Other metrics see lower-cased, stripped values; a regex code must see
    the text as the system wrote it, and its task literals the task data."""
    ev = SampleEvaluator("e", {"f": {"type": "text"}}, {"f": {"text_pattern": _params("names_claimant")}})
    row = ev.evaluate_sample(task_id="t", field_name="f", ground_truth=None, prediction="  The Claimant  ",
                             metrics_to_compute=["text_pattern"], task_data={"party": "Meier"})
    assert row["metrics"]["text_pattern"]["value"] == 1.0
    ev2 = SampleEvaluator("e", {"f": {"type": "text"}}, {"f": {"text_pattern": _params("names_party")}})
    row2 = ev2.evaluate_sample(task_id="t", field_name="f", ground_truth=None, prediction="Meier",
                               metrics_to_compute=["text_pattern"], task_data={"party": "Meier"})
    assert row2["metrics"]["text_pattern"]["value"] == 1.0

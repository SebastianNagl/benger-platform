"""Which reference fields a config grades under (shared/metric_filters.py).

A judge that reads its reference fields itself grades once per prediction
field; any other config once per reference field.
"""

import pytest

from metric_filters import graded_reference_fields, judge_reads_references_itself

pytestmark = pytest.mark.unit

REFS = ["task.musterloesung", "task.bewertungsbogen"]


def _cfg(metric, refs=REFS, template=None):
    params = {"custom_prompt_template": template} if template is not None else {}
    return {"metric": metric, "reference_fields": refs, "metric_parameters": params}


@pytest.mark.parametrize(
    "config, expected",
    [
        # The prompt names a reference field: one call sees all of them.
        (_cfg("llm_judge_custom", template="{ground_truth} {bewertungsbogen} {prediction}"), True),
        (_cfg("llm_judge_custom", template="{{ musterloesung }} {prediction}"), True),
        (_cfg("llm_judge_custom", refs=["musterloesung", "sheet"], template="{sheet}"), True),
        # Only {ground_truth}: each reference field is its own grading.
        (_cfg("llm_judge_custom", template="{ground_truth} {prediction}"), False),
        (_cfg("llm_judge_custom"), False),
        # Judges that take their reference from the task itself.
        (_cfg("llm_judge_falloesung"), True),
        (_cfg("llm_judge_rubric"), True),
        # One reference field, or no judge at all: nothing to collapse.
        (_cfg("llm_judge_rubric", refs=["task.musterloesung"]), False),
        (_cfg("bleu", template="{bewertungsbogen}"), False),
        ({"metric": None, "reference_fields": REFS}, False),
    ],
)
def test_judge_reads_references_itself(config, expected):
    assert judge_reads_references_itself(config) is expected


def test_graded_reference_fields():
    assert graded_reference_fields(_cfg("llm_judge_rubric")) == ["task.musterloesung"]
    assert graded_reference_fields(
        _cfg("llm_judge_custom", template="{ground_truth}")
    ) == REFS
    assert graded_reference_fields(_cfg("bleu")) == REFS
    assert graded_reference_fields(_cfg("text_pattern")) == [""]
    assert graded_reference_fields({"metric": "llm_judge_rubric"}) == []

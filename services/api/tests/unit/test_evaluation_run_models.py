"""Unit tests for the run model label rules in ``evaluation_run_models``."""

from evaluation_run_models import (
    MULTI_MODEL_RUN_LABEL,
    run_evaluated_model_ids,
    run_model_label,
)


class TestRunModelLabel:
    def test_one_model_is_the_label(self):
        assert run_model_label(["gpt-5.4"]) == "gpt-5.4"

    def test_repeats_of_one_model_are_one_model(self):
        assert run_model_label(["gpt-5.4", "gpt-5.4"]) == "gpt-5.4"

    def test_several_models_get_the_neutral_label(self):
        assert run_model_label(["gpt-5.4", "gemini-2.5-pro"]) == MULTI_MODEL_RUN_LABEL

    def test_no_model_gets_the_neutral_label(self):
        assert run_model_label([]) == MULTI_MODEL_RUN_LABEL
        assert run_model_label([None, ""]) == MULTI_MODEL_RUN_LABEL


class TestRunEvaluatedModelIds:
    def test_recorded_list_wins(self):
        meta = {"evaluated_model_ids": ["a", "b", "a"]}
        assert run_evaluated_model_ids("unknown", meta) == ["a", "b"]

    def test_label_names_the_model_without_a_list(self):
        assert run_evaluated_model_ids("gpt-5.4", {}) == ["gpt-5.4"]
        assert run_evaluated_model_ids("gpt-5.4", None) == ["gpt-5.4"]

    def test_empty_list_falls_back_to_the_label(self):
        assert run_evaluated_model_ids("gpt-5.4", {"evaluated_model_ids": []}) == [
            "gpt-5.4"
        ]

    def test_pseudo_labels_name_no_model(self):
        for label in ("unknown", "human", "immediate", None, ""):
            assert run_evaluated_model_ids(label, {}) == []

    def test_malformed_list_entries_are_dropped(self):
        meta = {"evaluated_model_ids": ["a", None, 3, ""]}
        assert run_evaluated_model_ids("unknown", meta) == ["a"]

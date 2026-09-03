"""Inline ``$field`` references inside literal prompts (the shape the project
wizard writes) are substituted with task values — regression for prompts that
reached the model with the literal placeholder."""

import pytest

from generation_structure_parser import GenerationStructureParser


@pytest.fixture
def parser():
    return GenerationStructureParser()


TASK = {
    "id": "t1",
    "sachverhalt": "A schlägt B.",
    "musterloesung": "geheim",
    "meta": {"area": "Strafrecht", "tags": ["a", "b"]},
    "answer": "leak",
}


class TestInlineRefs:
    def test_inline_ref_in_literal_prompt_is_substituted(self, parser):
        prompt = "Sachverhalt:\n$sachverhalt\n\nErstellen Sie ein Gutachten."
        assert parser._build_single_prompt(TASK, prompt) == (
            "Sachverhalt:\nA schlägt B.\n\nErstellen Sie ein Gutachten."
        )

    def test_nested_and_array_refs(self, parser):
        assert parser._build_single_prompt(TASK, "Gebiet: $meta.area") == "Gebiet: Strafrecht"
        assert parser._build_single_prompt(TASK, "Erstes Tag: $meta.tags[0]") == "Erstes Tag: a"

    def test_dict_value_is_json_serialized(self, parser):
        out = parser._build_single_prompt(TASK, "Meta: $meta")
        assert '"area": "Strafrecht"' in out

    def test_unknown_ref_is_left_untouched(self, parser):
        assert parser._build_single_prompt(TASK, "Preis: $price") == "Preis: $price"

    def test_literal_without_dollar_unchanged(self, parser):
        assert parser._build_single_prompt(TASK, "literal text") == "literal text"

    def test_whole_string_ref_still_works(self, parser):
        assert parser._build_single_prompt(TASK, "$sachverhalt") == "A schlägt B."

    def test_sensitive_inline_ref_is_blanked(self, parser):
        # Reference answers must never leak into a prompt, even inline.
        out = parser._build_single_prompt(TASK, "Lösung: $answer / $musterloesung")
        assert "leak" not in out
        assert out.startswith("Lösung:  / ")
        # musterloesung is not in SENSITIVE_FIELDS (it is the exam reference the
        # judge reads, excluded by the project's exclude_fields when needed).
        assert out.endswith("geheim")

    def test_end_to_end_via_process_generation_structure(self, parser):
        structure = {
            "system_prompt": "Du bist $meta.area-Jurist.",
            "instruction_prompt": "Sachverhalt:\n$sachverhalt",
        }
        prompts, _ = parser.process_generation_structure(
            task_data=TASK, generation_structure=structure, fallback_instruction="fb"
        )
        assert prompts["system_prompt"] == "Du bist Strafrecht-Jurist."
        assert prompts["instruction_prompt"] == "Sachverhalt:\nA schlägt B."

"""The generation record stores the task fields the prompt drew on
(``prompt_inputs``), never the whole task (compliance prep, 2026-10-13).

``GenerationStructureParser.prompt_input_fields`` walks the same references
the prompt builder resolves; ``_placeholder_prompt_inputs`` covers the
legacy ``{key}`` interpolation without a structure. Reference fields are
never recorded on either path.
"""

import pytest

import tasks  # noqa: F401  (loads the generation package through its entry point)
from generation.llm_generation_service import _placeholder_prompt_inputs
from generation_structure_parser import GenerationStructureParser


@pytest.fixture
def parser():
    return GenerationStructureParser()


TASK = {
    "sachverhalt": "A schlägt B.",
    "bearbeitervermerk": "Auf Verjährung ist nicht einzugehen.",
    "musterloesung": "GEHEIM",
    "rubric": {"steps": ["x"]},
    "meta": {"area": "Strafrecht", "tags": ["a", "b"]},
    "answer": "leak",
}


class TestReferencedPaths:
    def test_literal_prompts_with_inline_refs(self, parser):
        structure = {
            "system_prompt": "Du bist $meta.area-Jurist.",
            "instruction_prompt": "Sachverhalt:\n$sachverhalt\n$bearbeitervermerk\n$sachverhalt",
        }
        assert parser.referenced_paths(structure) == ["meta.area", "sachverhalt", "bearbeitervermerk"]

    def test_whole_string_template_and_context_fields(self, parser):
        structure = {
            "system_prompt": "$meta",
            "instruction_prompt": {
                "template": "{{fall}} {{vermerk}}",
                "fields": {"fall": "$sachverhalt", "vermerk": "$bearbeitervermerk", "lit": "x"},
            },
            "context_fields": ["$meta.tags[0]", "literal"],
        }
        assert parser.referenced_paths(structure) == [
            "meta", "sachverhalt", "bearbeitervermerk", "meta.tags[0]",
        ]

    def test_tolerates_odd_shapes(self, parser):
        assert parser.referenced_paths({}) == []
        assert parser.referenced_paths({"system_prompt": 3, "instruction_prompt": None}) == []
        assert parser.referenced_paths({"instruction_prompt": {"fields": "nope"}}) == []


class TestPromptInputFields:
    def test_records_only_resolved_non_sensitive_refs(self, parser):
        structure = {
            "system_prompt": "Du bist $meta.area-Jurist.",
            "instruction_prompt": "Fall: $sachverhalt\nVermerk: $bearbeitervermerk\n$missing",
        }
        assert parser.prompt_input_fields(TASK, structure) == {
            "meta.area": "Strafrecht",
            "sachverhalt": "A schlägt B.",
            "bearbeitervermerk": "Auf Verjährung ist nicht einzugehen.",
        }

    def test_reference_material_is_never_recorded_even_when_a_template_maps_it(self, parser):
        structure = {
            "instruction_prompt": {
                "template": "{{fall}}\n{{loesung}}\n{{rubric}}\n{{antwort}}",
                "fields": {
                    "fall": "$sachverhalt",
                    "loesung": "$musterloesung",
                    "rubric": "$rubric",
                    "antwort": "$answer",
                },
            },
            "context_fields": ["$musterloesung"],
        }
        assert parser.prompt_input_fields(TASK, structure) == {"sachverhalt": "A schlägt B."}

    def test_nested_and_indexed_paths(self, parser):
        # A literal prompt with inline refs (a prompt STARTING with "$" is a
        # whole-string reference instead).
        structure = {"instruction_prompt": "Tags: $meta.tags[1] / $meta"}
        assert parser.prompt_input_fields(TASK, structure) == {
            "meta.tags[1]": "b",
            "meta": {"area": "Strafrecht", "tags": ["a", "b"]},
        }

    def test_empty_inputs_for_missing_structure_or_task(self, parser):
        assert parser.prompt_input_fields(TASK, None) == {}
        assert parser.prompt_input_fields(None, {"instruction_prompt": "$sachverhalt"}) == {}
        assert parser.prompt_input_fields(TASK, {"instruction_prompt": "no refs"}) == {}


class TestPlaceholderPromptInputs:
    def test_records_used_placeholders_without_reference_fields(self):
        prompt = "Fall: {sachverhalt}\nVermerk: {bearbeitervermerk}\nLösung: {musterloesung} {answer}"
        assert _placeholder_prompt_inputs(prompt, TASK) == {
            "sachverhalt": "A schlägt B.",
            "bearbeitervermerk": "Auf Verjährung ist nicht einzugehen.",
        }

    def test_unused_keys_and_odd_inputs(self):
        assert _placeholder_prompt_inputs("no placeholders", TASK) == {}
        assert _placeholder_prompt_inputs("{sachverhalt}", None) == {}
        assert _placeholder_prompt_inputs(None, TASK) == {}

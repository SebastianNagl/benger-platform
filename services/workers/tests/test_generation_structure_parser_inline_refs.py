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
        # Reference answers must never leak into a prompt, even inline. The
        # Musterlösung is reference material too (SENSITIVE_FIELDS since
        # 2026-10-13); the rubric worker renders it through a template
        # mapping, which this inline path does not touch.
        out = parser._build_single_prompt(TASK, "Lösung: $answer / $musterloesung")
        assert "leak" not in out
        assert "geheim" not in out
        assert out == "Lösung:  / "

    @pytest.mark.parametrize(
        "ref",
        ["$musterloesung", "$Musterloesung", "$loesung", "$rubric",
         "$korrekturhinweise", "$korrektur", "$case.musterloesung"],
    )
    def test_reference_material_refs_are_skipped_with_warning(self, parser, ref, caplog):
        # VARIABLE_PATTERN is ASCII-only, so the umlaut spellings can never be
        # referenced inline; they are covered on the mapping path below.
        task = {
            **TASK,
            "loesung": "geheim", "rubric": "geheim", "korrekturhinweise": "geheim",
            "korrektur": "geheim", "Musterloesung": "geheim",
            "case": {"musterloesung": "geheim"},
        }
        with caplog.at_level("WARNING", logger="generation_structure_parser"):
            out = parser._build_single_prompt(task, f"Fall: $sachverhalt\nLösung: {ref}")
        assert "geheim" not in out
        assert out == "Fall: A schlägt B.\nLösung: "
        assert f"Skipping sensitive inline field reference: {ref}" in caplog.text

    @pytest.mark.parametrize("path", ["musterlösung", "lösung", "Musterlösung", "musterloesung"])
    def test_reference_material_mappings_are_skipped_with_warning(self, parser, path, caplog):
        task = {**TASK, "musterlösung": "geheim", "lösung": "geheim", "Musterlösung": "geheim"}
        with caplog.at_level("WARNING", logger="generation_structure_parser"):
            out = parser.filter_task_data(task, {"fall": "sachverhalt", "ml": path})
        assert out == {"fall": "A schlägt B."}
        assert f"Skipping sensitive field: {path}" in caplog.text

    def test_bearbeitervermerk_stays_available_to_the_model(self, parser):
        task = {**TASK, "bearbeitervermerk": "Auf Verjährung ist nicht einzugehen."}
        out = parser._build_single_prompt(task, "Vermerk: $bearbeitervermerk")
        assert out == "Vermerk: Auf Verjährung ist nicht einzugehen."

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

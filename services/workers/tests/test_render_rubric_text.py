"""``_render_rubric_text`` — the {bewertungsbogen} injection renderer.

The helper takes the resolved TaskRubric ROW (not bare criteria): when the
extended generation worker stored a pre-rendered full-document text in
``generation_metadata.rendered_text``, that string wins (it carries
document-level context — Schwerpunkte, alternative Lösungswege, warnings —
that flat criteria cannot express); otherwise the flat criteria render
generically with the ``[Schlüssel: …]`` mapping suffix. The extended edit
endpoint DROPS ``rendered_text`` when a human edits criteria, so the
fallback is the live path for edited rubrics.
"""

from types import SimpleNamespace

from evaluation.cell_evaluator import _render_rubric_text

CRITERIA = {
    "s01_anspruch_entstanden": {
        "name": "Anspruch entstanden (§ 433 II BGB)",
        "description": "Prüfung der Anspruchsgrundlage",
        "rubric": "Volle Punkte bei vollständiger Herleitung",
        "max_score": 40,
    },
    "s02_anspruch_durchsetzbar": {
        "name": "Anspruch durchsetzbar",
        "description": "",
        "rubric": "Volle Punkte bei geprüfter Einrede",
        "max_score": 60,
    },
}


def _row(rendered=None, criteria=CRITERIA):
    metadata = {"rendered_text": rendered} if rendered is not None else {}
    return SimpleNamespace(criteria=criteria, generation_metadata=metadata)


def test_prefers_stored_rendered_text():
    text = _render_rubric_text(_row(rendered="BEWERTUNGSBOGEN (100 Rohpunkte)\n…"))
    assert text.startswith("BEWERTUNGSBOGEN (100 Rohpunkte)")


def test_blank_rendered_text_falls_back_to_criteria():
    text = _render_rubric_text(_row(rendered="   "))
    assert "[Schlüssel: s01_anspruch_entstanden]" in text
    assert "Anspruch entstanden (§ 433 II BGB)" in text


def test_edited_rubric_without_rendered_text_renders_flat():
    # The edit endpoint pops rendered_text; only criteria remain.
    text = _render_rubric_text(_row())
    assert "1. Anspruch entstanden (§ 433 II BGB) (40 Punkte)" in text
    assert "2. Anspruch durchsetzbar (60 Punkte)" in text
    assert "Volle Punkte bei geprüfter Einrede" in text


def test_none_metadata_and_empty_criteria_are_safe():
    row = SimpleNamespace(criteria=None, generation_metadata=None)
    assert _render_rubric_text(row) == ""


def test_non_dict_criteria_entries_are_skipped():
    criteria = dict(CRITERIA)
    criteria["broken"] = "not-a-dict"
    text = _render_rubric_text(_row(criteria=criteria))
    assert "broken" not in text
    assert "[Schlüssel: s01_anspruch_entstanden]" in text

"""The shared ``rubric_structure`` module must import under the workers' path.

The judge paths (``cell_evaluator`` / ``judge_evaluator``) resolve
``from rubric_structure import …`` through ``/shared`` on ``sys.path`` — the
same way ``models`` resolves. A pydantic or api-only import creeping into the
module would only surface at grading time, so pin the import here.
"""

from types import SimpleNamespace


def test_rubric_structure_imports_and_grades():
    from rubric_structure import grade_for_rubric, rubric_prompt_text

    rubric = SimpleNamespace(
        total_points=100,
        grade_scale=None,
        structure=None,
        criteria={"s01_x": {"name": "X", "rubric": "r", "max_score": 100}},
        generation_metadata=None,
        title=None,
    )
    assert grade_for_rubric(rubric, 80, 100) == (13, True, "default")
    assert "[Schlüssel: s01_x]" in rubric_prompt_text(rubric)

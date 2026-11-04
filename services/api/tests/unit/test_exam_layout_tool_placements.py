"""``ExamLayoutPrefs.tool_placements`` (core 2.50): where each exam tool sits
in the modern layout. A display preference, validated like the rest of the
layout object."""

import pytest
from pydantic import ValidationError

from schemas.auth_schemas import ExamLayoutPrefs, ExamLayoutUpdate, TOOL_PLACEMENTS_MAX


def _prefs(placements):
    return ExamLayoutPrefs(mode="modern", tool_placements=placements)


def test_valid_placements_round_trip():
    placements = {
        "law_texts": {"zone": "right", "order": 0, "width": 480},
        "calculator": {"zone": "float", "x": 60, "y": 10, "w": 30, "h": 40},
        "notes": {"zone": "left"},
        "calendar": {"zone": "hidden"},
    }
    dumped = _prefs(placements).model_dump(exclude_none=True)
    assert dumped["tool_placements"] == placements
    # The update body carries it unchanged.
    body = ExamLayoutUpdate(exam_layout_prefs={"mode": "modern", "tool_placements": placements})
    assert body.exam_layout_prefs.tool_placements["calculator"].w == 30


def test_absent_placements_stay_absent():
    assert "tool_placements" not in ExamLayoutPrefs(mode="modern").model_dump(exclude_none=True)


@pytest.mark.parametrize(
    "placements",
    [
        {"calculator": {"zone": "top"}},
        {"Calculator": {"zone": "left"}},
        {"law-texts": {"zone": "left"}},
        {"calculator": {"zone": "float", "w": 5}},
        {"calculator": {"zone": "float", "x": 80, "w": 30}},
        {"calculator": {"zone": "float", "y": 95, "h": 10}},
        {"law_texts": {"zone": "left", "width": 2000}},
        {"law_texts": {"zone": "left", "order": 51}},
        {f"t_{'a' * (i % 30 + 1)}{'b' * (i // 30)}": {"zone": "hidden"} for i in range(TOOL_PLACEMENTS_MAX + 1)},
    ],
)
def test_invalid_placements_are_refused(placements):
    with pytest.raises(ValidationError):
        _prefs(placements)

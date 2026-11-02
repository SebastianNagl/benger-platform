"""``exam_tools.portable_exam_tools``: what an exported/imported copy keeps."""

from exam_tools import EXAM_TOOLS_VERSION, portable_exam_tools


def test_non_documents_become_none():
    for value in (None, "calculator", [], {"tools": "calculator"}, {"version": 1}):
        assert portable_exam_tools(value) is None


def test_connection_ids_are_dropped_and_config_copied():
    stored = {
        "version": 1,
        "tools": [
            {"id": "calculator"},
            {
                "id": "law_texts",
                "config": {"provider": "lexmea", "connection_id": "c1", "codes": ["BGB"]},
            },
        ],
    }
    portable = portable_exam_tools(stored)
    assert portable == {
        "version": 1,
        "tools": [
            {"id": "calculator"},
            {"id": "law_texts", "config": {"provider": "lexmea", "codes": ["BGB"]}},
        ],
    }
    # A deep copy: editing the copy leaves the stored document alone.
    portable["tools"][1]["config"]["codes"].append("StGB")
    assert stored["tools"][1]["config"]["codes"] == ["BGB"]


def test_malformed_entries_are_skipped_and_version_defaults():
    portable = portable_exam_tools(
        {"tools": [{"id": "notes", "config": "x"}, {"config": {}}, "calendar", {"id": 3}]}
    )
    assert portable == {"version": EXAM_TOOLS_VERSION, "tools": [{"id": "notes"}]}

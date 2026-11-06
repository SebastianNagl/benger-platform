"""``exam_tools.portable_exam_tools``: what an exported/imported copy keeps."""

from exam_tools import portable_exam_tools


def test_non_documents_become_none():
    for value in (None, "calculator", [], {"tools": "calculator"}, {}):
        assert portable_exam_tools(value) is None


def test_connection_ids_inside_sources_are_dropped_and_config_copied():
    stored = {
        "tools": [
            {"id": "calculator"},
            {
                "id": "law_texts",
                "config": {
                    "codes": ["BGB"],
                    "sources": [
                        {"provider": "lexmea", "mode": "student"},
                        {"provider": "lexmea", "mode": "org", "connection_id": "c1"},
                    ],
                },
            },
        ],
    }
    portable = portable_exam_tools(stored)
    assert portable == {
        "tools": [
            {"id": "calculator"},
            {
                "id": "law_texts",
                "config": {
                    "codes": ["BGB"],
                    "sources": [
                        {"provider": "lexmea", "mode": "student"},
                        {"provider": "lexmea", "mode": "org"},
                    ],
                },
            },
        ],
    }
    # A deep copy: editing the copy leaves the stored document alone.
    portable["tools"][1]["config"]["codes"].append("StGB")
    assert stored["tools"][1]["config"]["codes"] == ["BGB"]
    assert stored["tools"][1]["config"]["sources"][1]["connection_id"] == "c1"


def test_malformed_entries_are_skipped():
    portable = portable_exam_tools(
        {"tools": [{"id": "notes", "config": "x"}, {"config": {}}, "calendar", {"id": 3}]}
    )
    assert portable == {"tools": [{"id": "notes"}]}

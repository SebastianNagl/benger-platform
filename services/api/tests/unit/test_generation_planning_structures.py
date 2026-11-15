"""``run_structure_keys``: which structures a generation run (and its cost
estimate) covers. A project with generation structures must name them; a
project without any cannot generate."""

import pytest

from services.generation_planning import (
    NoPromptStructures,
    StructureKeysRequired,
    UnknownStructureKeys,
    run_structure_keys,
)


def test_requested_keys_win():
    cfg = {"prompt_structures": {"a": {}, "b": {}}}
    assert run_structure_keys(cfg, ["b"]) == ["b"]


@pytest.mark.parametrize("requested", [None, []])
def test_project_with_structures_must_name_them(requested):
    cfg = {"prompt_structures": {"a": {}, "b": {}, "rubric": {"exclude_from_generation": True}}}
    with pytest.raises(StructureKeysRequired) as exc:
        run_structure_keys(cfg, requested)
    assert exc.value.available == ["a", "b"]


@pytest.mark.parametrize(
    "cfg",
    [
        None,
        {},
        {"prompt_structures": {}},
        {"prompt_structures": {"rubric": {"exclude_from_generation": True}}},
    ],
)
def test_project_without_generation_structures_cannot_generate(cfg):
    """No built-in default prompt: a project without (non-excluded)
    generation structures cannot generate at all."""
    with pytest.raises(NoPromptStructures):
        run_structure_keys(cfg, None)


def test_legacy_list_shape_also_requires_keys():
    cfg = {"prompt_structures": [{"key": "a"}, {"key": "b"}]}
    with pytest.raises(StructureKeysRequired):
        run_structure_keys(cfg, None)


@pytest.mark.parametrize(
    "cfg, available",
    [
        (None, []),
        ({}, []),
        ({"prompt_structures": {}}, []),
        ({"prompt_structures": {"a": {}, "b": {}}}, ["a", "b"]),
        ({"prompt_structures": [{"key": "a"}]}, ["a"]),
    ],
)
def test_requested_keys_must_exist(cfg, available):
    """A requested key the project does not define is refused, also when the
    project has no structures at all (it used to queue jobs that all fail)."""
    with pytest.raises(UnknownStructureKeys) as exc:
        run_structure_keys(cfg, ["a", "missing"])
    assert exc.value.unknown == ["missing"] if available else ["a", "missing"]
    assert exc.value.available == available
    assert "Unknown structure keys" in str(exc.value)


def test_requested_keys_may_name_excluded_structures():
    cfg = {"prompt_structures": {"a": {}, "rubric": {"exclude_from_generation": True}}}
    assert run_structure_keys(cfg, ["rubric"]) == ["rubric"]

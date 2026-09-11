"""Forwarding the Falllösung judge prompt version into the extended hook.

The Falllösung judge prompt is versioned (contract v5): v1 still carries the
0–18 conversion table, v2 leaves the grade to the server, and the choice
lives in ``metric_parameters.prompt_version``. Platform owns the bulk-eval
loop, so it has to carry that string key across the open-core seam — without
deciding anything about it, and without breaking against a benger_extended
that predates the parameter.

Two things are pinned here: what the helper does, and that BOTH bulk call
sites use it (the generation-cell branch and the annotation-cell branch).
Dropping it on one of the two would silently grade half the lanes on the old
prompt.
"""

import ast
import inspect

from evaluation import cell_evaluator
from evaluation.cell_evaluator import _falloesung_prompt_version_kwargs


def _versioned_hook(*, sachverhalt="", prompt_version="v1"):
    pass


def _old_hook(*, sachverhalt=""):
    pass


class TestPromptVersionKwargs:
    def test_a_configured_version_reaches_a_hook_that_takes_it(self):
        assert _falloesung_prompt_version_kwargs(
            _versioned_hook, {"judge_model": "gpt-5-mini", "prompt_version": "v2"}
        ) == {"prompt_version": "v2"}

    def test_an_unset_version_is_not_passed_at_all(self):
        # The hook's own default ("v1") must stay in charge, so that every
        # project configured before the versioning keeps its prompt.
        for params in ({}, None, {"judge_model": "gpt-5-mini"}, {"prompt_version": "  "}):
            assert _falloesung_prompt_version_kwargs(_versioned_hook, params) == {}

    def test_a_non_string_version_is_ignored(self):
        assert _falloesung_prompt_version_kwargs(_versioned_hook, {"prompt_version": 2}) == {}
        assert (
            _falloesung_prompt_version_kwargs(_versioned_hook, {"prompt_version": None}) == {}
        )

    def test_an_older_extended_never_sees_the_kwarg(self):
        # Passing it to a hook without the parameter would TypeError the cell.
        assert _falloesung_prompt_version_kwargs(_old_hook, {"prompt_version": "v2"}) == {}

    def test_platform_does_not_validate_the_value(self):
        # Which versions exist is extended's business; platform only carries
        # the string (the extended normalizer falls back to its default).
        assert _falloesung_prompt_version_kwargs(
            _versioned_hook, {"prompt_version": "v99"}
        ) == {"prompt_version": "v99"}

    def test_the_value_is_trimmed(self):
        assert _falloesung_prompt_version_kwargs(
            _versioned_hook, {"prompt_version": " v2 "}
        ) == {"prompt_version": "v2"}


def _bulk_call_sources():
    source = inspect.getsource(cell_evaluator)
    tree = ast.parse(source)
    return [
        ast.get_source_segment(source, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "falloesung_bulk_fn"
    ]


class TestBothCallSitesForwardIt:
    """The branch itself needs a real evaluator, judge model and provider, so
    the wiring is pinned at the source level."""

    def test_there_are_exactly_two_bulk_call_sites(self):
        assert len(_bulk_call_sources()) == 2

    def test_each_one_forwards_the_configured_version(self):
        for segment in _bulk_call_sources():
            assert "_falloesung_prompt_version_kwargs" in segment
            assert "metric_parameters" in segment

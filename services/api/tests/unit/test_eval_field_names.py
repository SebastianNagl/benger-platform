"""The role-prefix rule: what a prediction-field selector is CALLED.

`human:`/`model:` records WHERE an answer came from, not what the field is
named. Which form a config or a stored row carries depends only on how it was
authored — the field picker offers `human:loesung`, a config written in code
usually says `loesung` — so the two must name one field for pairing, grouping
and row-to-config matching.

That rule had been re-implemented at nearly a dozen call sites before it lived
here; these tests pin the version everything else now delegates to, including
extended's human-grading field resolver and the worker's row matcher.
"""

from __future__ import annotations

import pytest

from eval_field_classification import (
    BULK_SELECTORS,
    ROLE_PREFIXES,
    bare_field_name,
    same_field,
)


class TestBareFieldName:
    @pytest.mark.parametrize(
        "selector,expected",
        [
            ("human:loesung", "loesung"),
            ("model:loesung", "loesung"),
            ("loesung", "loesung"),
            ("  human:gliederung  ", "gliederung"),
            ("human: loesung", "loesung"),
        ],
    )
    def test_it_names_the_field(self, selector, expected):
        assert bare_field_name(selector) == expected

    @pytest.mark.parametrize(
        "selector", ["", "   ", None, "human:", "model:  ", *BULK_SELECTORS]
    )
    def test_selectors_naming_no_single_field_yield_none(self, selector):
        # The caller must fall through to another source rather than store a
        # label that names nothing.
        assert bare_field_name(selector) is None

    def test_only_a_role_prefix_is_stripped(self):
        # A colon elsewhere is part of the name, not a role marker.
        assert bare_field_name("teil:eins") == "teil:eins"
        assert bare_field_name("human:teil:eins") == "teil:eins"

    def test_every_declared_prefix_is_handled(self):
        for prefix in ROLE_PREFIXES:
            assert bare_field_name(f"{prefix}feld") == "feld"

    def test_it_is_idempotent(self):
        once = bare_field_name("human:loesung")
        assert bare_field_name(once) == once


class TestSameField:
    def test_the_prefixed_and_bare_form_are_one_field(self):
        assert same_field("human:loesung", "loesung")
        assert same_field("loesung", "model:loesung")

    def test_different_fields_stay_different(self):
        assert not same_field("human:loesung", "human:gliederung")
        assert not same_field("loesung", "gliederung")

    def test_identical_selectors_match_even_when_unnameable(self):
        # Two `__all_human__` rows are the same selector; neither names a
        # field, so the bare comparison alone would have said "no".
        assert same_field("__all_human__", "__all_human__")
        assert same_field(None, None)

    def test_a_bulk_selector_does_not_match_a_named_field(self):
        assert not same_field("__all_human__", "loesung")
        assert not same_field("__all_human__", "__all_model__")

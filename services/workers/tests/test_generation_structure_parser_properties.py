"""Property-based tests for generation_structure_parser (hypothesis).

These assert INVARIANTS that hold for all inputs of the template-interpolation
and nested-extraction machinery, not hand-picked examples — which is what kills
the off-by-one / wrong-branch / boundary mutants that example tests miss (the
mutation co-gate, issue: meaningful-coverage program).

Module under test exposes a single class ``GenerationStructureParser`` with the
pure methods exercised here:

Invariants covered:
  * interpolate_template
      - identity: a template with NO ``{{placeholder}}`` tokens is returned
        byte-for-byte unchanged regardless of the placeholders dict.
      - full substitution: once every present placeholder has a (brace-free)
        value, the result contains no residual ``{{name}}`` for any supplied
        name, and re-interpolating is a no-op (idempotent).
      - determinism: same inputs -> identical output.
  * extract_nested_value
      - round-trip: a value planted at a dotted path is exactly what
        ``extract_nested_value(data, path)`` returns.
      - missing paths and array indices never raise; out-of-range -> None.
  * process_generation_structure / validate_structure / parse_structure
      - no-crash + deterministic on arbitrary dict input (and on the
        always-None / always-(False, msg) degenerate branches).
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generation_structure_parser import GenerationStructureParser

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid placeholder names must match TEMPLATE_PATTERN: [a-zA-Z_][a-zA-Z0-9_]*
_ident = st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,7}", fullmatch=True)

# Text that can never contain a {{...}} token nor a '$' variable marker, so it
# is safe to use as a SUBSTITUTED value without re-introducing placeholders.
_brace_free_text = st.text(
    alphabet=st.characters(blacklist_characters="{}$", blacklist_categories=("Cs",)),
    max_size=20,
)

# Scalar leaf values usable inside nested dicts for the round-trip test. We keep
# them hashable/JSON-ish and avoid floats (NaN equality headaches).
_leaf = st.one_of(
    st.text(max_size=10),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
    st.none(),
)

# Arbitrary JSON-ish dicts to fuzz the no-crash methods.
_json_scalar = st.one_of(
    st.none(), st.booleans(), st.integers(-1000, 1000), st.text(max_size=12)
)
_arbitrary_dict = st.dictionaries(
    keys=st.text(max_size=10),
    values=st.recursive(
        _json_scalar,
        lambda children: st.one_of(
            st.lists(children, max_size=4),
            st.dictionaries(st.text(max_size=8), children, max_size=4),
        ),
        max_leaves=10,
    ),
    max_size=6,
)


def _make_parser() -> GenerationStructureParser:
    return GenerationStructureParser()


class TestInterpolateTemplateIdentity:
    @settings(max_examples=60, deadline=None)
    @given(text=_brace_free_text, mapping=st.dictionaries(_ident, _brace_free_text, max_size=5))
    def test_no_placeholder_template_unchanged(self, text, mapping):
        # A template with no {{...}} tokens is returned verbatim, whatever the
        # placeholders dict contains (nothing to match -> nothing to replace).
        p = _make_parser()
        assert p.interpolate_template(text, mapping) == text

    @settings(max_examples=40, deadline=None)
    @given(text=_brace_free_text, mapping=st.dictionaries(_ident, _brace_free_text, max_size=5))
    def test_deterministic(self, text, mapping):
        p = _make_parser()
        a = p.interpolate_template(text, dict(mapping))
        b = p.interpolate_template(text, dict(mapping))
        assert a == b


class TestInterpolateTemplateSubstitution:
    @settings(max_examples=60, deadline=None)
    @given(
        names=st.lists(_ident, min_size=1, max_size=4, unique=True),
        values=st.lists(_brace_free_text, min_size=1, max_size=4),
    )
    def test_full_substitution_leaves_no_residual_and_is_idempotent(self, names, values):
        p = _make_parser()
        # Build a template that references every name as a {{token}}, joined by
        # brace-free literal glue so the only braces are the placeholders.
        mapping = {name: values[i % len(values)] for i, name in enumerate(names)}
        template = "prefix " + " | ".join(f"{{{{{n}}}}}" for n in names) + " suffix"

        result = p.interpolate_template(template, mapping)

        # Every supplied placeholder token must be gone (values are brace-free,
        # so they cannot re-introduce a {{name}} for any name we supplied).
        for name in names:
            assert f"{{{{{name}}}}}" not in result
        # Each value appears in the output.
        for name in names:
            assert mapping[name] in result
        # Idempotence: re-running over the already-substituted text changes
        # nothing (no placeholders remain to match).
        assert p.interpolate_template(result, mapping) == result

    @settings(max_examples=40, deadline=None)
    @given(name=_ident, value=_brace_free_text, missing=_ident)
    def test_allow_missing_preserves_unmapped_placeholder(self, name, value, missing):
        # With allow_missing=True a placeholder absent from the dict survives
        # unchanged, while a mapped one is substituted.
        p = _make_parser()
        template = f"{{{{{name}}}}}-{{{{{missing}}}}}"
        result = p.interpolate_template(template, {name: value}, allow_missing=True)
        if missing != name:
            assert f"{{{{{missing}}}}}" in result


class TestExtractNestedValue:
    @settings(max_examples=60, deadline=None)
    @given(
        path_parts=st.lists(_ident, min_size=1, max_size=4, unique=True),
        leaf=_leaf,
    )
    def test_dotted_path_roundtrip(self, path_parts, leaf):
        # Plant `leaf` at the nested dotted path, then read it straight back.
        p = _make_parser()
        data = {}
        cursor = data
        for part in path_parts[:-1]:
            cursor[part] = {}
            cursor = cursor[part]
        cursor[path_parts[-1]] = leaf

        path = ".".join(path_parts)
        assert p.extract_nested_value(data, path) == leaf

    @settings(max_examples=40, deadline=None)
    @given(data=_arbitrary_dict, path=st.text(max_size=15))
    def test_never_raises_on_arbitrary_path(self, data, path):
        # Arbitrary (possibly nonsensical) paths must return cleanly, not crash.
        p = _make_parser()
        p.extract_nested_value(data, path)  # no exception is the assertion

    @settings(max_examples=40, deadline=None)
    @given(key=_ident, items=st.lists(_leaf, min_size=1, max_size=5))
    def test_array_index_roundtrip_and_out_of_range_none(self, key, items):
        p = _make_parser()
        data = {key: list(items)}
        # In-range index returns the element.
        for i, expected in enumerate(items):
            assert p.extract_nested_value(data, f"{key}[{i}]") == expected
        # Out-of-range index returns None (no IndexError).
        assert p.extract_nested_value(data, f"{key}[{len(items)}]") is None

    def test_empty_inputs_return_none(self):
        p = _make_parser()
        assert p.extract_nested_value({}, "a") is None
        assert p.extract_nested_value({"a": 1}, "") is None
        assert p.extract_nested_value(None, "a") is None


class TestNoCrashAndDeterminism:
    @settings(max_examples=60, deadline=None)
    @given(structure=_arbitrary_dict, task=_arbitrary_dict)
    def test_process_generation_structure_never_raises_and_is_deterministic(
        self, structure, task
    ):
        p = _make_parser()
        a = p.process_generation_structure(task, structure)
        b = p.process_generation_structure(task, structure)
        # Returns a (prompts, filtered) tuple and is reproducible.
        assert isinstance(a, tuple) and len(a) == 2
        assert isinstance(a[0], dict) and isinstance(a[1], dict)
        assert a == b

    @settings(max_examples=60, deadline=None)
    @given(structure=_arbitrary_dict)
    def test_validate_structure_never_raises_and_is_deterministic(self, structure):
        p = _make_parser()
        a = p.validate_structure(structure)
        b = p.validate_structure(structure)
        # Contract: (bool, Optional[str]).
        assert isinstance(a, tuple) and len(a) == 2
        assert isinstance(a[0], bool)
        assert a[1] is None or isinstance(a[1], str)
        assert a == b

    @settings(max_examples=40, deadline=None)
    @given(structure=_arbitrary_dict)
    def test_parse_structure_dict_roundtrip(self, structure):
        # A dict input is returned as-is (truthy dict) or None (empty dict).
        p = _make_parser()
        result = p.parse_structure(structure)
        if structure:
            assert result == structure
        else:
            assert result is None

    @settings(max_examples=30, deadline=None)
    @given(garbage=st.text(max_size=30))
    def test_parse_structure_non_json_string_returns_none(self, garbage):
        # Non-JSON / non-object strings parse to None, never raise.
        import json as _json

        p = _make_parser()
        result = p.parse_structure(garbage)
        try:
            decoded = _json.loads(garbage)
            is_object = isinstance(decoded, dict)
        except Exception:
            is_object = False
        if not is_object:
            assert result is None

"""Surgical mutation-kill tests for the PURE score-parsing + schema-building
helpers of the LLM-as-judge evaluator
(``ml_evaluation/llm_judge_evaluator.py``).

LLM-as-judge is a central benchmark methodology for this research-grade
platform: a bug in score extraction or the rubric schema silently yields
wrong judge scores. The existing test files
(test_llm_judge_evaluator*.py, test_llm_judge_multidim_parse_branches.py)
are coverage-shaped (happy paths + the fallback arms). This file adds the
surgical *mutation-kill* layer: every expected value is HAND-COMPUTED in the
test docstring, so each assertion pins one (or more) specific source
operator against the obvious mutants (``*2`` vs ``*3``, ``round`` vs trunc,
``range(n+1)`` vs ``range(n)``, ``i/2`` vs ``i``, schema constant values,
required-key lists, ``additionalProperties`` False, etc.).

All targets here are PURE: module-level functions take no instance, and the
two instance methods exercised (``_extract_nested_value``,
``_apply_field_mappings``) never touch the AI service, so a bare
``LLMJudgeEvaluator(ai_service=None)`` suffices.

Validated only with the docker pytest runner.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.llm_judge_evaluator import (  # noqa: E402
    LLMJudgeEvaluator,
    _build_rubric_json_schema,
    _extract_call_metadata,
    _half_point_enum,
    _parse_multidim_response,
    _preprocess_jinja_placeholders,
)


def _make_evaluator(**kwargs):
    """Minimal constructor: the methods under test never call the AI service.

    ``__init__`` only stores ``ai_service``/``judge_model`` and merges
    criteria dicts; ``ai_service=None`` is fine for ``_extract_nested_value``
    and ``_apply_field_mappings`` (both pure dict walks over ``field_mappings``
    / ``task_data``). See llm_judge_evaluator.py:361-438.
    """
    defaults = {"ai_service": None, "judge_model": "judge-x"}
    defaults.update(kwargs)
    return LLMJudgeEvaluator(**defaults)


# ============================================================================
# _half_point_enum  (llm_judge_evaluator.py:87-95)
#   n = int(round(max_score * 2)); return [round(i / 2, 1) for i in range(n + 1)]
# ============================================================================


class TestHalfPointEnum:
    def test_max_score_5_exact_eleven_element_list(self):
        """max_score=5: n = int(round(5*2)) = int(round(10.0)) = 10.
        range(11) -> i in 0..10. round(i/2,1) -> 0.0,0.5,...,5.0. EXACTLY 11
        elements ending at 5.0.

        Kills:
          * ``* 2`` -> ``* 3`` (would give n=15, 16 elems, last 7.5),
          * ``range(n + 1)`` -> ``range(n)`` (would drop the final 5.0, 10 elems),
          * ``i / 2`` -> ``i`` (would give [0,1,2,...,10]).
        """
        assert _half_point_enum(5) == [
            0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0
        ]
        assert len(_half_point_enum(5)) == 11

    def test_max_score_3_seven_elements_ending_3(self):
        """max_score=3: n = int(round(6.0)) = 6. range(7) -> 7 elements
        [0.0,0.5,1.0,1.5,2.0,2.5,3.0], last is 3.0.

        Pins the count formula AND that the final element equals max_score
        (so ``range(n)`` instead of ``range(n+1)`` would lose the 3.0).
        """
        out = _half_point_enum(3)
        assert out == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        assert len(out) == 7
        assert out[-1] == 3.0

    def test_max_score_1_three_elements(self):
        """max_score=1: n = int(round(2.0)) = 2. range(3) -> [0.0, 0.5, 1.0].

        Smallest integral case: distinguishes ``*2`` (n=2, 3 elems) from
        ``*1``/``*3`` and ``range(n+1)`` (3) from ``range(n)`` (2 elems).
        """
        assert _half_point_enum(1) == [0.0, 0.5, 1.0]

    def test_max_score_2_5_ends_at_2_5_six_elements(self):
        """Fractional max_score=2.5: n = int(round(2.5*2)) = int(round(5.0)) = 5.
        range(6) -> [0.0,0.5,1.0,1.5,2.0,2.5]. Six elements, last EXACTLY 2.5.

        round(2.5*2)=round(5.0)=5 — pins that the *2 happens before round and
        that ``round`` (not ``int()`` truncation of a noisy float) is used.
        """
        out = _half_point_enum(2.5)
        assert out == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
        assert len(out) == 6
        assert out[-1] == 2.5

    def test_max_score_0_5_two_elements(self):
        """Fractional below 1: max_score=0.5: n = int(round(1.0)) = 1.
        range(2) -> [0.0, 0.5]. Exactly two elements.

        Distinguishes ``round`` from ``int()`` truncation: int(0.5*2)=int(1.0)=1
        happens to agree here, but pairs with the 2.5 case (round(5.0)) and
        guards the lower boundary of the enum.
        """
        assert _half_point_enum(0.5) == [0.0, 0.5]

    def test_max_score_0_single_zero_element(self):
        """max_score=0: n = int(round(0.0)) = 0. range(1) -> [0.0].

        Pins ``range(n + 1)`` vs ``range(n)`` at the degenerate floor:
        range(n+1)=range(1)=[0] (one element) vs range(n)=range(0)=[] (empty).
        """
        assert _half_point_enum(0) == [0.0]

    def test_elements_are_rounded_to_one_decimal(self):
        """``round(i/2, 1)`` keeps one decimal place. i=3 -> round(1.5,1)=1.5;
        i=7 -> round(3.5,1)=3.5. All half-points are clean — pins the rounding
        digit (round(..,1) vs round(..,0) which would collapse 0.5->0).
        """
        out = _half_point_enum(4)
        # round(..,0) would give [0,0,1,2,2,3,4,4] style collapse; assert the
        # genuine half points survive.
        assert 0.5 in out and 1.5 in out and 3.5 in out
        assert out == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]


# ============================================================================
# _build_rubric_json_schema  (llm_judge_evaluator.py:98-146)
# ============================================================================


class TestBuildRubricJsonSchema:
    def test_single_criterion_with_max_score_full_schema(self):
        """One criterion ``clarity`` with max_score=3 -> EXACT schema.

        Hand-computed:
          * scores.properties.clarity.properties.score.enum ==
            _half_point_enum(3.0) == [0.0,0.5,1.0,1.5,2.0,2.5,3.0],
          * scores.properties.clarity.properties.max.const == 3 (the RAW
            value, not float-coerced: source passes ``max_score`` straight to
            const but ``float(max_score)`` only to the enum),
          * per-criterion required == ["score","max","reason"],
            additionalProperties False,
          * scores.required == ["clarity"], scores.additionalProperties False,
          * top-level required == ["scores","total_score","overall_assessment"],
            top-level additionalProperties False.
        """
        schema = _build_rubric_json_schema({"clarity": {"max_score": 3}})
        assert schema == {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "object",
                    "properties": {
                        "clarity": {
                            "type": "object",
                            "properties": {
                                "score": {
                                    "type": "number",
                                    "enum": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
                                },
                                "max": {"type": "number", "const": 3},
                                "reason": {"type": "string"},
                            },
                            "required": ["score", "max", "reason"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["clarity"],
                    "additionalProperties": False,
                },
                "total_score": {"type": "number"},
                "overall_assessment": {"type": "string"},
            },
            "required": ["scores", "total_score", "overall_assessment"],
            "additionalProperties": False,
        }

    def test_criterion_without_max_score_is_skipped(self):
        """A criterion lacking ``max_score`` is skipped (continue at 118-119):
        not in scores.properties, not in scores.required. Only ``has_max``
        survives.

        Pins the ``if max_score is None: continue`` guard — a mutant that
        dropped the guard would add ``no_max`` with enum/const built from None.
        """
        schema = _build_rubric_json_schema(
            {
                "has_max": {"max_score": 1},
                "no_max": {"name": "No Max", "description": "skipped"},
            }
        )
        props = schema["properties"]["scores"]["properties"]
        assert "has_max" in props
        assert "no_max" not in props
        assert schema["properties"]["scores"]["required"] == ["has_max"]
        # has_max enum is _half_point_enum(1) == [0.0, 0.5, 1.0]
        assert props["has_max"]["properties"]["score"]["enum"] == [0.0, 0.5, 1.0]
        assert props["has_max"]["properties"]["max"]["const"] == 1

    def test_empty_criteria_yields_empty_score_block(self):
        """No criteria -> scores.properties == {} and scores.required == [].
        The outer scaffold (total_score / overall_assessment / top-level
        required) is unconditional.

        Pins that the loop body never runs and that the surrounding fixed
        structure is emitted regardless.
        """
        schema = _build_rubric_json_schema({})
        assert schema["properties"]["scores"]["properties"] == {}
        assert schema["properties"]["scores"]["required"] == []
        assert schema["required"] == [
            "scores",
            "total_score",
            "overall_assessment",
        ]
        assert schema["additionalProperties"] is False
        assert schema["properties"]["scores"]["additionalProperties"] is False

    def test_two_criteria_required_preserves_insertion_order(self):
        """Two criteria with max_score -> scores.required lists BOTH keys in
        insertion order ["a","b"]. Pins that ``score_required.append(key)``
        runs once per kept criterion and order is dict-insertion order.
        """
        schema = _build_rubric_json_schema(
            {"a": {"max_score": 2}, "b": {"max_score": 5}}
        )
        assert schema["properties"]["scores"]["required"] == ["a", "b"]
        props = schema["properties"]["scores"]["properties"]
        assert props["a"]["properties"]["max"]["const"] == 2
        assert props["b"]["properties"]["max"]["const"] == 5
        # b's enum runs to 5.0 (11 elems), a's to 2.0 (5 elems)
        assert props["a"]["properties"]["score"]["enum"] == [
            0.0, 0.5, 1.0, 1.5, 2.0
        ]
        assert props["b"]["properties"]["score"]["enum"][-1] == 5.0
        assert len(props["b"]["properties"]["score"]["enum"]) == 11

    def test_max_const_is_raw_value_enum_uses_float(self):
        """``max.const`` is the raw ``max_score`` (here int 4), while the enum
        is built from ``float(max_score)``. _half_point_enum(4.0) ==
        [0.0,...,4.0] (9 elems). Pins that const keeps the un-coerced value.
        """
        schema = _build_rubric_json_schema({"c": {"max_score": 4}})
        crit = schema["properties"]["scores"]["properties"]["c"]
        assert crit["properties"]["max"]["const"] == 4
        assert crit["properties"]["score"]["enum"] == [
            0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0
        ]
        assert crit["required"] == ["score", "max", "reason"]
        assert crit["additionalProperties"] is False


# ============================================================================
# _parse_multidim_response  (llm_judge_evaluator.py:149-199)
#   stage 1: json.loads ; stage 2: ```json fence ; stage 3: largest "{...}"
#   containing "scores"; else None.
# ============================================================================


class TestParseMultidimResponse:
    def test_stage1_direct_clean_json_with_scores(self):
        """Clean JSON object -> stage-1 json.loads returns it verbatim,
        including nested scores. Pins that stage 1 fires (no fence/brace work
        needed) and returns the FULL dict, not a slice.
        """
        content = '{"scores": {"d1": {"score": 4.0, "max": 5}}, "total_score": 4.0}'
        out = _parse_multidim_response(content)
        assert out == {
            "scores": {"d1": {"score": 4.0, "max": 5}},
            "total_score": 4.0,
        }

    def test_stage2_markdown_json_fence(self):
        """A ```json fenced block with prose around it: stage 1 fails on the
        prose, stage 2's regex ``r"```(?:json)?\\s*(\\{.*\\})\\s*```"`` captures
        the inner object and json.loads succeeds.
        """
        content = (
            "Sure, here is my evaluation:\n"
            "```json\n"
            '{"scores": {"clarity": {"score": 2.5}}, "total_score": 2.5}\n'
            "```\n"
            "Hope that helps!"
        )
        out = _parse_multidim_response(content)
        assert out == {"scores": {"clarity": {"score": 2.5}}, "total_score": 2.5}

    def test_stage2_bare_fence_without_json_word(self):
        """The fence language tag is optional (``(?:json)?``). A bare ``` fence
        still matches and parses. Pins the optional-group in the regex.
        """
        content = '```\n{"scores": {"a": {"score": 1.0}}}\n```'
        out = _parse_multidim_response(content)
        assert out == {"scores": {"a": {"score": 1.0}}}

    def test_stage3_scores_object_embedded_in_prose(self):
        """No fence; a scores-bearing object sits inside prose. Stage 1 fails,
        stage 2 finds no fence, stage 3 brace-matches the object, sees the
        substring ``"scores"``, and json.loads it.
        """
        content = (
            'The model did well. Final: {"scores": {"x": {"score": 3.0}}, '
            '"total_score": 3.0} -- end of review.'
        )
        out = _parse_multidim_response(content)
        assert out == {"scores": {"x": {"score": 3.0}}, "total_score": 3.0}

    def test_stage3_picks_longest_scores_candidate_first(self):
        """Two balanced objects, only the LONGER one carries ``"scores"``.
        candidates.sort(key=len, reverse=True) puts it first, so it is the one
        returned. Pins the ``reverse=True`` longest-first ordering AND the
        ``"scores"`` membership filter.
        """
        content = (
            '{"note": "short"} '
            '{"scores": {"a": {"score": 5.0}}, "total_score": 5.0, "pad": "longer"}'
        )
        out = _parse_multidim_response(content)
        assert out == {
            "scores": {"a": {"score": 5.0}},
            "total_score": 5.0,
            "pad": "longer",
        }

    def test_garbage_unbalanced_braces_returns_none(self):
        """Unbalanced/garbage input: stage 1 fails, no fence, the lone ``{``
        never closes so no candidate is captured (depth never returns to 0) ->
        None. Pins the depth-tracking brace matcher and the final ``return None``.
        """
        content = "totally not json {scores: oops with no close brace"
        assert _parse_multidim_response(content) is None

    def test_plain_prose_no_braces_returns_none(self):
        """Prose with zero braces: every stage misses, candidates empty -> None."""
        assert _parse_multidim_response("Just some words, no JSON here.") is None

    def test_json_list_passes_through_stage1_unchanged(self):
        """A valid JSON *list* (not a dict) parses at stage 1 and is returned
        AS-IS: source does ``return json.loads(content)`` with no dict-type
        guard (llm_judge_evaluator.py:163-164). Pins that stage 1 does not
        require a dict — the list short-circuits before the scores logic.
        """
        out = _parse_multidim_response('[1, 2, 3]')
        assert out == [1, 2, 3]

    def test_empty_string_returns_none(self):
        """Empty string: json.loads("") raises JSONDecodeError -> stage 1 pass;
        ``content or ""`` keeps regex/loop safe; no candidates -> None.
        """
        assert _parse_multidim_response("") is None

    def test_brace_object_without_scores_substring_returns_none(self):
        """A balanced object lacking the ``"scores"`` substring is skipped by
        the ``if '"scores"' not in candidate: continue`` filter -> None.
        Pins the membership guard distinct from a generic JSON parse.
        """
        content = 'prefix {"total_score": 4.0, "overall_assessment": "ok"} suffix'
        assert _parse_multidim_response(content) is None


# ============================================================================
# _extract_call_metadata  (llm_judge_evaluator.py:55-74)
# ============================================================================


class TestExtractCallMetadata:
    def test_token_fields_mapped_from_usage(self):
        """input/output/total come from usage.prompt_tokens /
        completion_tokens / total_tokens respectively. Pins the exact source
        keys (a swap of prompt<->completion would flip input/output).
        """
        out = _extract_call_metadata(
            {"usage": {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33}}
        )
        assert out["input_tokens"] == 11
        assert out["output_tokens"] == 22
        assert out["total_tokens"] == 33

    def test_missing_usage_and_metadata_defaults_to_none(self):
        """Absent usage/metadata: the three token fields default to None
        (``usage.get(...)`` on ``{}``), and no allow-listed keys are added.
        Pins the ``response.get("usage") or {}`` fallbacks.
        """
        out = _extract_call_metadata({})
        assert out == {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }

    def test_only_allowlisted_metadata_keys_surface(self):
        """metadata keys in _CALL_METADATA_KEYS are copied; others dropped.
        ``seed`` and ``finish_reason`` are on the list; ``mystery`` is not.
        Pins the ``if key in meta`` allow-list loop.
        """
        out = _extract_call_metadata(
            {
                "metadata": {
                    "seed": 7,
                    "finish_reason": "length",
                    "provider_name": "deepinfra",
                    "mystery": "drop me",
                }
            }
        )
        assert out["seed"] == 7
        assert out["finish_reason"] == "length"
        assert out["provider_name"] == "deepinfra"
        assert "mystery" not in out

    def test_none_usage_and_metadata_blocks_are_tolerated(self):
        """Explicit ``None`` for usage/metadata still falls back to ``{}`` via
        ``or {}`` — pins that ``None`` is treated like absent, no AttributeError.
        """
        out = _extract_call_metadata({"usage": None, "metadata": None})
        assert out["input_tokens"] is None
        assert out["total_tokens"] is None
        # no metadata keys present
        assert set(out.keys()) == {"input_tokens", "output_tokens", "total_tokens"}

    def test_falsy_zero_metadata_value_is_kept(self):
        """A metadata key present with a falsy value (retry_count=0) is still
        surfaced — the guard is ``if key in meta`` (membership), not truthiness.
        Pins ``in`` vs ``meta.get(key)`` (the latter would drop 0/"").
        """
        out = _extract_call_metadata({"metadata": {"retry_count": 0}})
        assert "retry_count" in out
        assert out["retry_count"] == 0


# ============================================================================
# _preprocess_jinja_placeholders  (llm_judge_evaluator.py:77-84)
#   re.sub(r"\{\{(\w+)\}\}", r"{\1}", template)
# ============================================================================


class TestPreprocessJinjaPlaceholders:
    def test_double_brace_collapses_to_single(self):
        """``{{prediction}}`` -> ``{prediction}``. Pins the core transform:
        the \\w+ capture group is re-wrapped in single braces.
        """
        assert (
            _preprocess_jinja_placeholders("Score {{prediction}} now")
            == "Score {prediction} now"
        )

    def test_single_brace_passes_through_unchanged(self):
        """A pre-existing single-brace ``{var}`` does NOT match ``\\{\\{...\\}\\}``
        and is left intact — so str.format() still sees it. Pins that the regex
        requires DOUBLE braces.
        """
        assert (
            _preprocess_jinja_placeholders("Already {var} here")
            == "Already {var} here"
        )

    def test_multiple_placeholders_all_converted(self):
        """Every ``{{...}}`` occurrence is converted (re.sub replaces all).
        Two placeholders -> two single-brace results.
        """
        assert (
            _preprocess_jinja_placeholders("{{a}} and {{b}}")
            == "{a} and {b}"
        )

    def test_non_word_content_inside_braces_not_matched(self):
        """``\\w+`` matches [A-Za-z0-9_] only. ``{{a.b}}`` contains a dot, so the
        whole token does NOT match and is left untouched. Pins the \\w+ class
        (a ``.``-permissive mutant would rewrite it).
        """
        assert (
            _preprocess_jinja_placeholders("{{a.b}}")
            == "{{a.b}}"
        )

    def test_empty_braces_not_matched(self):
        """``{{}}`` has no \\w+ to capture, so the regex does not match and it
        passes through unchanged. Pins the ``+`` (one-or-more) quantifier.
        """
        assert _preprocess_jinja_placeholders("{{}}") == "{{}}"

    def test_no_placeholders_identity(self):
        """A template with no braces is returned identically."""
        assert _preprocess_jinja_placeholders("plain text") == "plain text"


# ============================================================================
# _extract_nested_value  (llm_judge_evaluator.py:462-485)  [instance method]
# ============================================================================


class TestExtractNestedValue:
    def setup_method(self):
        self.ev = _make_evaluator()

    def test_top_level_key(self):
        """Single (dotless) path returns the top-level value.
        path="jurisdiction" -> data["jurisdiction"].
        """
        assert self.ev._extract_nested_value({"jurisdiction": "DE"}, "jurisdiction") == "DE"

    def test_dotted_leaf_path(self):
        """Dotted path walks nested dicts: "context.jurisdiction" ->
        data["context"]["jurisdiction"]. Pins the ``path.split(".")`` walk.
        """
        data = {"context": {"jurisdiction": "BY", "court": "BGH"}}
        assert self.ev._extract_nested_value(data, "context.jurisdiction") == "BY"

    def test_deep_three_level_path(self):
        """Three-segment path "a.b.c" descends two dict levels. Pins that the
        loop iterates over EVERY part, not just the first/last.
        """
        data = {"a": {"b": {"c": 99}}}
        assert self.ev._extract_nested_value(data, "a.b.c") == 99

    def test_missing_key_returns_none(self):
        """A part not present in the current dict hits the else-branch and
        returns None immediately (llm_judge_evaluator.py:482-483).
        """
        assert self.ev._extract_nested_value({"a": 1}, "b") is None

    def test_partial_path_into_missing_returns_none(self):
        """First segment exists, second doesn't -> None. Pins the per-segment
        membership check rather than only checking the final key.
        """
        assert self.ev._extract_nested_value({"a": {"x": 1}}, "a.y") is None

    def test_descend_into_non_dict_returns_none(self):
        """When ``current`` becomes a non-dict (here an int), the next segment
        fails the ``isinstance(current, dict)`` guard and returns None. Pins the
        isinstance check (no index/attr access on a scalar).
        """
        assert self.ev._extract_nested_value({"a": 5}, "a.b") is None

    def test_array_value_is_returned_as_leaf_but_not_indexable(self):
        """The method has NO list-index handling: a list leaf is returned
        whole, and descending past it (numeric segment) returns None because a
        list is not a dict. Pins the dict-only walk (no ``[int]`` support).
        """
        data = {"items": [10, 20, 30]}
        # leaf list returned as-is
        assert self.ev._extract_nested_value(data, "items") == [10, 20, 30]
        # numeric index past a list -> not a dict -> None
        assert self.ev._extract_nested_value(data, "items.0") is None

    def test_empty_data_or_empty_path_returns_none(self):
        """Guard clause ``if not data or not path: return None``. Empty dict,
        None data, and empty-string path all short-circuit to None.
        """
        assert self.ev._extract_nested_value({}, "a") is None
        assert self.ev._extract_nested_value(None, "a") is None
        assert self.ev._extract_nested_value({"a": 1}, "") is None

    def test_value_of_none_returned_as_none(self):
        """A key whose stored value IS None: the key is present so the walk
        succeeds and returns None — indistinguishable from 'missing' by value,
        which is the documented contract. Confirms no crash on a None leaf.
        """
        assert self.ev._extract_nested_value({"a": None}, "a") is None


# ============================================================================
# _apply_field_mappings  (llm_judge_evaluator.py:487-516)  [instance method]
# ============================================================================


class TestApplyFieldMappings:
    def test_no_mappings_returns_template_vars_unchanged(self):
        """With empty field_mappings the guard returns template_vars as-is.
        Pins ``if not self.field_mappings ... : return template_vars``.
        """
        ev = _make_evaluator(field_mappings={})
        tv = {"existing": "v"}
        assert ev._apply_field_mappings({"a": 1}, tv) == {"existing": "v"}

    def test_empty_task_data_returns_template_vars_unchanged(self):
        """Mappings present but task_data empty -> guard short-circuits and
        returns template_vars untouched (no KeyError attempts).
        """
        ev = _make_evaluator(field_mappings={"jur": "$jurisdiction"})
        assert ev._apply_field_mappings({}, {"k": "v"}) == {"k": "v"}

    def test_dollar_prefix_is_stripped(self):
        """``$jurisdiction`` -> path "jurisdiction" via lstrip('$'). The mapped
        value lands under the template-var NAME (the dict key), not the path.
        Pins the ``$`` strip and the name<-value direction.
        """
        ev = _make_evaluator(field_mappings={"jurisdiction": "$jurisdiction"})
        out = ev._apply_field_mappings({"jurisdiction": "Bayern"}, {})
        assert out == {"jurisdiction": "Bayern"}

    def test_path_without_dollar_used_verbatim(self):
        """A field_path lacking ``$`` is used as-is (the ``if startswith('$')``
        branch is skipped). "court" -> task_data["court"].
        """
        ev = _make_evaluator(field_mappings={"c": "court"})
        out = ev._apply_field_mappings({"court": "BGH"}, {})
        assert out == {"c": "BGH"}

    def test_dotted_path_resolves_nested(self):
        """``$context.jurisdiction`` strips to "context.jurisdiction" and
        resolves via _extract_nested_value. Pins integration of the strip +
        nested walk.
        """
        ev = _make_evaluator(field_mappings={"jur": "$context.jurisdiction"})
        out = ev._apply_field_mappings({"context": {"jurisdiction": "NRW"}}, {})
        assert out == {"jur": "NRW"}

    def test_missing_value_is_not_added(self):
        """When the mapped path resolves to None (missing), the
        ``if value is not None`` guard skips it — the template-var is NOT set.
        Pins that absent fields don't inject a literal 'None' string.
        """
        ev = _make_evaluator(field_mappings={"jur": "$does_not_exist"})
        out = ev._apply_field_mappings({"present": "x"}, {"keep": "me"})
        assert out == {"keep": "me"}
        assert "jur" not in out

    def test_non_string_value_is_stringified(self):
        """A non-string mapped value is coerced with ``str(value)``. int 5 ->
        "5"; a list -> its repr string. Pins the ``str(value) if not
        isinstance(value, str)`` coercion.
        """
        ev = _make_evaluator(field_mappings={"n": "$count", "lst": "$tags"})
        out = ev._apply_field_mappings({"count": 5, "tags": [1, 2]}, {})
        assert out["n"] == "5"
        assert out["n"] != 5  # coerced to str, not left as int
        assert out["lst"] == "[1, 2]"

    def test_existing_string_value_kept_without_recoercion(self):
        """An already-string value passes the isinstance check and is stored
        verbatim (the ``else value`` branch). "DE" stays "DE".
        """
        ev = _make_evaluator(field_mappings={"jur": "$jur"})
        out = ev._apply_field_mappings({"jur": "DE"}, {})
        assert out == {"jur": "DE"}

    def test_zero_value_is_added_not_skipped(self):
        """Value 0 is NOT None, so it passes the ``is not None`` guard and is
        added as "0". Pins ``is not None`` vs a truthiness check (which would
        wrongly drop 0).
        """
        ev = _make_evaluator(field_mappings={"z": "$zero"})
        out = ev._apply_field_mappings({"zero": 0}, {})
        assert out == {"z": "0"}

    def test_template_vars_mutated_and_returned(self):
        """Pre-existing template_vars are preserved alongside newly mapped
        ones (the method extends, not replaces). Pins that the loop adds to the
        passed-in dict.
        """
        ev = _make_evaluator(field_mappings={"new": "$field"})
        out = ev._apply_field_mappings({"field": "val"}, {"old": "kept"})
        assert out == {"old": "kept", "new": "val"}

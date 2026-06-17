"""Residual parse-fallback branches for ml_evaluation/llm_judge_evaluator.py.

``_parse_multidim_response`` has a three-stage extraction strategy
(direct json.loads -> fenced ```json block -> largest brace-matched object
containing "scores"). test_llm_judge_evaluator_branches.py covers the
*success* of each stage and the all-fail None return, but not the
intra-stage failure arms:

  * a fenced block present but containing INVALID JSON -> the
    ``except json.JSONDecodeError: pass`` arm (lines 172-173),
  * a brace candidate that does NOT contain ``"scores"`` -> the
    ``continue`` at line 192 (the existing brace test puts the longest,
    valid, scores-bearing candidate first so it returns before reaching
    a scores-less one),
  * a brace candidate that DOES contain ``"scores"`` but is invalid JSON
    -> the ``except json.JSONDecodeError: continue`` arm (lines 195-196).

Pure string-in / dict-or-None-out. No AI service, no model. Mirrors the
direct-call idiom in test_llm_judge_evaluator_branches.py::TestParseMultidimResponse.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.llm_judge_evaluator import _parse_multidim_response  # noqa: E402


class TestParseMultidimFallbackArms:
    def test_fenced_block_with_invalid_json_falls_through(self):
        """A ```json fence whose contents are not valid JSON trips the fenced
        except-pass (172-173). With no scores-bearing brace candidate after it,
        the function returns None."""
        content = "Here:\n```json\n{not: valid, json here}\n```\n"
        assert _parse_multidim_response(content) is None

    def test_fenced_invalid_then_valid_brace_candidate_recovers(self):
        """The fenced block is invalid (172-173), but a later brace-matched
        object carrying "scores" parses successfully -> stage 3 recovers it."""
        content = (
            "```json\n{broken}\n```\n"
            'and the real one: {"scores": {"d": {"score": 4}}, "total_score": 4}'
        )
        out = _parse_multidim_response(content)
        assert out is not None
        assert out["scores"]["d"]["score"] == 4

    def test_brace_candidate_without_scores_key_is_skipped(self):
        """Top-level text makes direct json.loads fail; the only brace object
        lacks "scores" -> the `continue` at 192 runs and the function returns
        None."""
        content = 'preamble {"note": 1, "other": 2} trailing'
        assert _parse_multidim_response(content) is None

    def test_brace_candidate_with_scores_but_invalid_json_continues(self):
        """A brace object that contains the substring "scores" but is not valid
        JSON trips the stage-3 except-continue (195-196). No other valid
        candidate -> None."""
        content = 'noise {"scores": this-is-not-json} tail'
        assert _parse_multidim_response(content) is None

    def test_invalid_scores_candidate_then_valid_one_recovers(self):
        """An invalid scores-bearing candidate is skipped (195-196) and a later
        valid scores-bearing candidate is returned. The valid one is longer so
        it sorts first AND parses, but we still assert recovery semantics by
        making the invalid candidate the longer string."""
        # Longer invalid candidate sorts first -> hits 195-196 -> continue;
        # shorter valid candidate parses next.
        content = (
            '{"scores": COMPLETELY BROKEN LONGER CANDIDATE HERE!!!} '
            '{"scores": {"x": 1}}'
        )
        out = _parse_multidim_response(content)
        assert out == {"scores": {"x": 1}}

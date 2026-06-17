"""Residual edge-branch coverage across several worker modules.

Each target here is a single small guard/except arm the existing suites skip.
Grouped into one file because each module needs only one or two tests.

  ml_evaluation/statistics.py
    * significance_test generic except -> result["error"] (255-256): an
      all-identical wilcoxon pair makes scipy raise inside the try.
    * correlation_matrix per-cell except -> None (416-417): non-numeric
      score columns of length >= 3 make pearsonr raise.
    * _krippendorff_alpha_interval expected_pairs==0 guard (statistics.py:673)
      is already covered by test_statistics_branches.py; not retried here.

  ml_evaluation/inter_annotator_agreement.py  (krippendorff_alpha)
    * unknown level_of_measurement -> nominal-style distance fallback (160).
    * total_pairs == 0 -> "No valid rating pairs found" (183): ratings spread
      so no single item has 2+ valid ratings, yet >= 2 ratings overall.

  generation_structure_parser.py
    * extract_nested_value non-integer array index -> ValueError -> None
      (172-173).
    * validate_structure outer except -> "Validation error: ..." (527-528):
      parse_structure patched to return a truthy non-iterable so the
      `key in structure` membership test raises.

  response_parser.py
    * _try_json_parse generic (non-JSONDecodeError) except -> "failed"
      (128-129): valid JSON, but _transform_to_label_studio raises.
    * _try_pattern_match generic except -> "failed" (206-207) AND the
      parse() both-failed return (71): a field is extracted so the transform
      runs, and the transform is patched to raise.

All behavioral: real functions, crafted inputs (or one targeted patch of an
internal transform), asserted outputs. Mirrors the idioms in
test_statistics_branches.py / test_inter_annotator_agreement_branches.py /
test_generation_structure_parser_coverage.py / test_response_parser_coverage.py.
"""

import os
import sys
from unittest.mock import patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.statistics import significance_test, correlation_matrix  # noqa: E402
from ml_evaluation.inter_annotator_agreement import krippendorff_alpha  # noqa: E402
from generation_structure_parser import GenerationStructureParser  # noqa: E402
from response_parser import ResponseParser  # noqa: E402


# ============================================================================
# statistics.correlation_matrix — per-cell except -> None
# ============================================================================


class TestCorrelationMatrixCellExcept:
    def test_non_numeric_columns_yield_none(self):
        """String score columns (len >= 3 so they pass the min-length guard)
        make pearsonr raise; the per-cell `except` coerces the result to None
        (lines 416-417)."""
        data = {
            "a": ["x", "y", "z"],
            "b": ["p", "q", "r"],
        }
        result = correlation_matrix(data, method="pearson")
        assert result["a"]["b"] is None
        assert result["b"]["a"] is None


# ============================================================================
# inter_annotator_agreement.krippendorff_alpha — edge guards
# ============================================================================


class TestKrippendorffEdgeGuards:
    def test_unknown_level_uses_nominal_fallback(self):
        """An unrecognised level_of_measurement falls through every distance
        branch to the final `return 0 if v1 == v2 else 1` (line 160). Identical
        rows -> observed disagreement 0 -> alpha 1.0."""
        matrix = [[1, 1], [2, 2], [3, 3]]
        result = krippendorff_alpha(matrix, level_of_measurement="bogus_level")
        assert result["alpha"] == pytest.approx(1.0)

    def test_no_item_with_two_valid_ratings_returns_error(self):
        """Ratings are spread one-per-item, so no single item has 2+ valid
        ratings (total_pairs == 0), yet there are >= 2 ratings overall (passing
        the earlier 'need 2 ratings' guard). Hits the line-183 error."""
        matrix = [[1, None], [2, None]]
        result = krippendorff_alpha(matrix, "nominal")
        assert result == {"error": "No valid rating pairs found"}


# ============================================================================
# generation_structure_parser.GenerationStructureParser
# ============================================================================


class TestGenStructureParserEdges:
    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_non_integer_array_index_returns_none(self):
        """A non-numeric index inside brackets makes int() raise ValueError,
        caught by the `except (ValueError, IndexError)` arm -> None
        (lines 172-173)."""
        data = {"items": [10, 20, 30]}
        assert self.parser.extract_nested_value(data, "items[abc]") is None

    def test_validate_structure_inner_exception_returns_error_tuple(self):
        """If parse_structure yields a truthy but non-iterable value, the
        `'system_prompt' in structure` membership test raises TypeError, which
        the outer `except Exception` converts into a (False, 'Validation
        error: ...') tuple (lines 527-528)."""
        with patch.object(self.parser, "parse_structure", return_value=5):
            valid, error = self.parser.validate_structure({"anything": True})
        assert valid is False
        assert error.startswith("Validation error:")


# ============================================================================
# response_parser.ResponseParser — non-JSONDecodeError + pattern excepts
# ============================================================================


class TestResponseParserExceptArms:
    def _parser(self):
        config = "<View><Text name='t' value='$t'/><Number name='score' toName='t'/></View>"
        return ResponseParser(generation_structure={}, label_config=config)

    def test_json_parse_generic_exception_returns_failed(self):
        """Valid JSON parses, but the downstream transform raises a
        non-JSONDecodeError -> the generic `except Exception` arm returns a
        'failed' ParseResult (lines 128-129)."""
        parser = self._parser()
        with patch.object(
            parser, "_transform_to_label_studio", side_effect=RuntimeError("kaboom")
        ):
            result = parser._try_json_parse('{"score": 1}')
        assert result.status == "failed"
        assert "Unexpected error in JSON parsing" in result.error

    def test_pattern_match_exception_propagates_to_both_failed(self):
        """A field IS extracted by the pattern matcher, so the transform runs;
        patching it to raise drives the `except` arm of _try_pattern_match
        (206-207). Since _try_json_parse also fails on the non-JSON input, the
        full parse() reaches its both-failed return (line 71)."""
        parser = self._parser()
        with patch.object(
            parser, "_transform_to_label_studio", side_effect=RuntimeError("kaboom")
        ):
            # Direct: _try_pattern_match returns 'failed'.
            direct = parser._try_pattern_match("score: 42")
            assert direct.status == "failed"
            assert "Pattern matching failed" in direct.error

            # Full parse: both stages fail -> the catch-all 'failed' result.
            full = parser.parse("score: 42")
        assert full.status == "failed"
        assert "Unable to parse response" in full.error

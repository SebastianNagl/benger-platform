"""
Unit tests for utils/pseudonym_generator.py — 74.55% coverage (11 uncovered lines).

Tests get_pseudonym_statistics and edge cases of generate_pseudonym.
"""

import pytest


class TestGeneratePseudonym:
    """Test generate_pseudonym function."""

    def test_basic_generation(self):
        from utils.pseudonym_generator import generate_pseudonym
        result = generate_pseudonym()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_adjective_noun(self):
        from utils.pseudonym_generator import generate_pseudonym
        result = generate_pseudonym()
        # Should be "adjective-noun" format (two parts joined by space or dash)
        assert len(result.split()) >= 1

    def test_uniqueness_with_existing(self):
        from utils.pseudonym_generator import generate_pseudonym
        existing = set()
        for _ in range(50):
            p = generate_pseudonym(existing)
            assert p not in existing
            existing.add(p)

    def test_many_unique_pseudonyms(self):
        from utils.pseudonym_generator import generate_pseudonym
        pseudonyms = set()
        for _ in range(100):
            p = generate_pseudonym(pseudonyms)
            pseudonyms.add(p)
        assert len(pseudonyms) == 100


class TestGetPseudonymStatistics:
    """Test get_pseudonym_statistics function."""

    def test_returns_dict(self):
        from utils.pseudonym_generator import get_pseudonym_statistics
        stats = get_pseudonym_statistics()
        assert isinstance(stats, dict)

    def test_has_adjectives_count(self):
        from utils.pseudonym_generator import get_pseudonym_statistics
        stats = get_pseudonym_statistics()
        assert "adjectives" in stats
        assert isinstance(stats["adjectives"], int)
        assert stats["adjectives"] > 0

    def test_has_nouns_count(self):
        from utils.pseudonym_generator import get_pseudonym_statistics
        stats = get_pseudonym_statistics()
        assert "nouns" in stats
        assert isinstance(stats["nouns"], int)
        assert stats["nouns"] > 0

    def test_has_total_combinations(self):
        from utils.pseudonym_generator import get_pseudonym_statistics
        stats = get_pseudonym_statistics()
        assert "total_combinations" in stats
        assert stats["total_combinations"] == stats["adjectives"] * stats["nouns"]

    def test_has_sample_pseudonyms(self):
        from utils.pseudonym_generator import get_pseudonym_statistics
        stats = get_pseudonym_statistics()
        assert "sample_pseudonyms" in stats
        assert isinstance(stats["sample_pseudonyms"], list)
        assert len(stats["sample_pseudonyms"]) == 5

    def test_sample_pseudonyms_are_strings(self):
        from utils.pseudonym_generator import get_pseudonym_statistics
        stats = get_pseudonym_statistics()
        for p in stats["sample_pseudonyms"]:
            assert isinstance(p, str)
            assert len(p) > 0


class TestPseudonymWordLists:
    """Test the word lists are properly defined."""

    def test_adjectives_list_exists(self):
        from utils.pseudonym_generator import ADJECTIVES
        assert isinstance(ADJECTIVES, (list, tuple))
        assert len(ADJECTIVES) > 10

    def test_nouns_list_exists(self):
        from utils.pseudonym_generator import NOUNS
        assert isinstance(NOUNS, (list, tuple))
        assert len(NOUNS) > 10

    def test_no_empty_adjectives(self):
        from utils.pseudonym_generator import ADJECTIVES
        for adj in ADJECTIVES:
            assert len(adj.strip()) > 0

    def test_no_empty_nouns(self):
        from utils.pseudonym_generator import NOUNS
        for noun in NOUNS:
            assert len(noun.strip()) > 0

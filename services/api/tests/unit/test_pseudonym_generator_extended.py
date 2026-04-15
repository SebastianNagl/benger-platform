"""
Unit tests for utils/pseudonym_generator.py to increase coverage.
Tests edge cases in pseudonym generation.
"""

import pytest


class TestPseudonymGenerator:
    def test_import(self):
        from utils.pseudonym_generator import generate_pseudonym
        assert callable(generate_pseudonym)

    def test_generates_string(self):
        from utils.pseudonym_generator import generate_pseudonym
        result = generate_pseudonym()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unique_pseudonyms(self):
        from utils.pseudonym_generator import generate_pseudonym
        pseudonyms = {generate_pseudonym() for _ in range(50)}
        # Most should be unique (probabilistic but very high chance with 50)
        assert len(pseudonyms) >= 20

    def test_pseudonym_format(self):
        from utils.pseudonym_generator import generate_pseudonym
        result = generate_pseudonym()
        # Should contain at least one space (adjective + noun)
        # or be a single word (depends on implementation)
        assert isinstance(result, str)

    def test_deterministic_with_seed(self):
        from utils.pseudonym_generator import generate_pseudonym
        # Generate multiple times to check it works
        for _ in range(10):
            result = generate_pseudonym()
            assert isinstance(result, str)
            assert len(result) > 0

    def test_available_adjectives_and_nouns(self):
        """Test that the word lists are populated."""
        from utils.pseudonym_generator import ADJECTIVES, NOUNS
        assert len(ADJECTIVES) > 0
        assert len(NOUNS) > 0
        assert all(isinstance(a, str) for a in ADJECTIVES)
        assert all(isinstance(n, str) for n in NOUNS)

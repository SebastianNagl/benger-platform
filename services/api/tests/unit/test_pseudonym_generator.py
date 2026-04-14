"""
Tests for pseudonym generator utility.

Targets: utils/pseudonym_generator.py lines 186-187, 211-238, 248-249, 259-266
"""

from unittest.mock import Mock, patch

import pytest


class TestGeneratePseudonym:
    """Test the generate_pseudonym function."""

    def test_generates_pseudonym(self):
        from utils.pseudonym_generator import generate_pseudonym
        result = generate_pseudonym()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generates_unique_pseudonym(self):
        from utils.pseudonym_generator import generate_pseudonym
        existing = {"SwiftEagle", "WiseScholar"}
        result = generate_pseudonym(existing)
        assert result not in existing

    def test_raises_when_exhausted(self):
        from utils.pseudonym_generator import generate_pseudonym, ADJECTIVES, NOUNS
        # Create a set with all possible combinations
        all_pseudonyms = {f"{adj}{noun}" for adj in ADJECTIVES for noun in NOUNS}
        with pytest.raises(ValueError) as exc_info:
            generate_pseudonym(all_pseudonyms, max_attempts=100)
        assert "Unable to generate unique pseudonym" in str(exc_info.value)

    def test_none_existing_treated_as_empty(self):
        from utils.pseudonym_generator import generate_pseudonym
        result = generate_pseudonym(None)
        assert isinstance(result, str)

    def test_multiple_generations_unique(self):
        from utils.pseudonym_generator import generate_pseudonym
        results = set()
        existing = set()
        for _ in range(50):
            p = generate_pseudonym(existing)
            results.add(p)
            existing.add(p)
        assert len(results) == 50


class TestAssignPseudonymsToExistingUsers:
    """Test the assign_pseudonyms_to_existing_users function."""

    def test_no_users_without_pseudonyms(self):
        from utils.pseudonym_generator import assign_pseudonyms_to_existing_users
        mock_db = Mock()
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.all.return_value = []
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        result = assign_pseudonyms_to_existing_users(mock_db)
        assert result == 0

    def test_assigns_pseudonyms(self):
        from utils.pseudonym_generator import assign_pseudonyms_to_existing_users
        mock_db = Mock()

        user1 = Mock()
        user1.id = "user-1"
        user1.pseudonym = None

        user2 = Mock()
        user2.id = "user-2"
        user2.pseudonym = None

        existing_user = Mock()
        existing_user.pseudonym = "SwiftEagle"

        # Setup query chain
        call_count = [0]
        def query_side_effect(model_or_field):
            call_count[0] += 1
            mock_q = Mock()
            if call_count[0] == 1:
                # First call: users without pseudonyms
                mock_f = Mock()
                mock_f.all.return_value = [user1, user2]
                mock_q.filter.return_value = mock_f
            else:
                # Second call: existing pseudonyms
                mock_f = Mock()
                mock_f.all.return_value = [("SwiftEagle",)]
                mock_q.filter.return_value = mock_f
            return mock_q

        mock_db.query.side_effect = query_side_effect

        result = assign_pseudonyms_to_existing_users(mock_db)
        assert result == 2
        assert user1.pseudonym is not None
        assert user2.pseudonym is not None
        mock_db.commit.assert_called_once()


class TestGetPseudonymStatistics:
    """Test the get_pseudonym_statistics function."""

    def test_returns_statistics(self):
        from utils.pseudonym_generator import get_pseudonym_statistics, ADJECTIVES, NOUNS
        stats = get_pseudonym_statistics()
        assert stats["adjectives"] == len(ADJECTIVES)
        assert stats["nouns"] == len(NOUNS)
        assert stats["total_combinations"] == len(ADJECTIVES) * len(NOUNS)
        assert len(stats["sample_pseudonyms"]) == 5

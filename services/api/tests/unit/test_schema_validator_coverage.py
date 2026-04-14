"""
Unit tests for schema_validator.py to increase coverage.
"""

from unittest.mock import Mock, patch

import pytest

from schema_validator import (
    get_expected_schema,
    validate_table_exists,
    get_table_columns,
    generate_fix_commands,
)


class TestGetExpectedSchema:
    def test_returns_dict(self):
        schema = get_expected_schema()
        assert isinstance(schema, dict)

    def test_has_tables(self):
        schema = get_expected_schema()
        assert len(schema) > 0

    def test_users_table(self):
        schema = get_expected_schema()
        assert "users" in schema

    def test_projects_table(self):
        schema = get_expected_schema()
        assert "projects" in schema

    def test_tasks_table(self):
        schema = get_expected_schema()
        assert "tasks" in schema

    def test_annotations_table(self):
        schema = get_expected_schema()
        assert "annotations" in schema

    def test_organizations_table(self):
        schema = get_expected_schema()
        assert "organizations" in schema

    def test_each_table_has_columns(self):
        schema = get_expected_schema()
        for table_name, columns in schema.items():
            assert isinstance(columns, (dict, list, set)), f"{table_name} columns invalid"


class TestValidateTableExists:
    def test_table_exists(self):
        mock_inspector = Mock()
        mock_inspector.has_table.return_value = True
        result = validate_table_exists(mock_inspector, "users")
        assert result is True

    def test_table_not_exists(self):
        mock_inspector = Mock()
        mock_inspector.has_table.return_value = False
        result = validate_table_exists(mock_inspector, "nonexistent")
        assert result is False

    def test_sqlalchemy_error(self):
        from sqlalchemy.exc import SQLAlchemyError

        mock_inspector = Mock()
        mock_inspector.has_table.side_effect = SQLAlchemyError("error")
        result = validate_table_exists(mock_inspector, "users")
        assert result is False


class TestGetTableColumns:
    def test_returns_columns(self):
        mock_inspector = Mock()
        mock_inspector.get_columns.return_value = [
            {"name": "id", "type": Mock()},
            {"name": "name", "type": Mock()},
        ]
        result = get_table_columns(mock_inspector, "users")
        assert isinstance(result, (dict, list, set))

    def test_empty_table(self):
        mock_inspector = Mock()
        mock_inspector.get_columns.return_value = []
        result = get_table_columns(mock_inspector, "empty")
        assert isinstance(result, (dict, list, set))


class TestGenerateFixCommands:
    def test_with_mock_engine(self):
        mock_engine = Mock()
        mock_inspector = Mock()
        mock_inspector.has_table.return_value = True
        mock_inspector.get_columns.return_value = [{"name": "id"}]

        with patch("schema_validator.inspect", return_value=mock_inspector):
            result = generate_fix_commands(mock_engine)
            assert isinstance(result, list)

    def test_with_missing_tables(self):
        mock_engine = Mock()
        mock_inspector = Mock()
        mock_inspector.has_table.return_value = False

        with patch("schema_validator.inspect", return_value=mock_inspector):
            result = generate_fix_commands(mock_engine)
            assert isinstance(result, list)
            # No commands generated for missing tables
            assert len(result) == 0

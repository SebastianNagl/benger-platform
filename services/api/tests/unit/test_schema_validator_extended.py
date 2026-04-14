"""
Extended unit tests for schema_validator.py — targeting validate_schema, validate_data_integrity,
generate_fix_commands column type inference, and main function.
"""

from unittest.mock import MagicMock, patch, call

import pytest


class TestValidateSchema:
    """Test validate_schema function that checks tables and columns."""

    def test_all_tables_present_all_columns(self):
        from schema_validator import get_expected_schema, validate_schema

        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True

        schema = get_expected_schema()
        # Return all expected columns for each table
        def get_cols(table):
            if table in schema:
                return [{"name": col} for col in schema[table]]
            return []

        mock_inspector.get_columns.side_effect = get_cols

        mock_engine = MagicMock()
        with patch("schema_validator.get_database_engine", return_value=mock_engine), \
             patch("schema_validator.inspect", return_value=mock_inspector):
            result = validate_schema()
        assert result is True

    def test_missing_table_fails(self):
        from schema_validator import validate_schema

        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = False
        mock_inspector.get_columns.return_value = []

        mock_engine = MagicMock()
        with patch("schema_validator.get_database_engine", return_value=mock_engine), \
             patch("schema_validator.inspect", return_value=mock_inspector):
            result = validate_schema()
        assert result is False

    def test_missing_columns_fails(self):
        from schema_validator import validate_schema

        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True
        # Return only 'id' column for all tables, missing many
        mock_inspector.get_columns.return_value = [{"name": "id"}]

        mock_engine = MagicMock()
        with patch("schema_validator.get_database_engine", return_value=mock_engine), \
             patch("schema_validator.inspect", return_value=mock_inspector):
            result = validate_schema()
        assert result is False

    def test_extra_columns_dont_fail(self):
        from schema_validator import get_expected_schema, validate_schema

        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True

        schema = get_expected_schema()

        def get_cols(table):
            if table in schema:
                cols = [{"name": col} for col in schema[table]]
                cols.append({"name": "extra_col"})
                return cols
            return []

        mock_inspector.get_columns.side_effect = get_cols

        mock_engine = MagicMock()
        with patch("schema_validator.get_database_engine", return_value=mock_engine), \
             patch("schema_validator.inspect", return_value=mock_inspector):
            result = validate_schema()
        assert result is True


class TestValidateDataIntegrity:
    """Test validate_data_integrity."""

    def test_no_orphans_passes(self):
        from schema_validator import validate_data_integrity

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result1 = MagicMock()
        mock_result1.fetchone.return_value = (0,)
        mock_result2 = MagicMock()
        mock_result2.fetchone.return_value = (0,)

        mock_conn.execute.side_effect = [mock_result1, mock_result2]
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn

        with patch("schema_validator.get_database_engine", return_value=mock_engine):
            result = validate_data_integrity()
        assert result is True

    def test_orphaned_tasks_fails(self):
        from schema_validator import validate_data_integrity

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result1 = MagicMock()
        mock_result1.fetchone.return_value = (5,)  # 5 orphaned tasks
        mock_result2 = MagicMock()
        mock_result2.fetchone.return_value = (0,)

        mock_conn.execute.side_effect = [mock_result1, mock_result2]
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn

        with patch("schema_validator.get_database_engine", return_value=mock_engine):
            result = validate_data_integrity()
        assert result is False

    def test_orphaned_evaluations_fails(self):
        from schema_validator import validate_data_integrity

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result1 = MagicMock()
        mock_result1.fetchone.return_value = (0,)
        mock_result2 = MagicMock()
        mock_result2.fetchone.return_value = (3,)  # 3 orphaned evaluations

        mock_conn.execute.side_effect = [mock_result1, mock_result2]
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn

        with patch("schema_validator.get_database_engine", return_value=mock_engine):
            result = validate_data_integrity()
        assert result is False

    def test_db_error_fails(self):
        from schema_validator import validate_data_integrity
        from sqlalchemy.exc import SQLAlchemyError

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = SQLAlchemyError("db error")
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn

        with patch("schema_validator.get_database_engine", return_value=mock_engine):
            result = validate_data_integrity()
        assert result is False


class TestGenerateFixCommandsColumnTypes:
    """Test column type inference in generate_fix_commands."""

    def test_encrypted_col_gets_text(self):
        from schema_validator import generate_fix_commands

        mock_engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True
        mock_inspector.get_columns.return_value = [{"name": "id"}]

        with patch("schema_validator.inspect", return_value=mock_inspector):
            commands = generate_fix_commands(mock_engine)

        encrypted_cmds = [c for c in commands if "encrypted_" in c]
        assert len(encrypted_cmds) > 0
        for cmd in encrypted_cmds:
            assert "TEXT" in cmd

    def test_id_col_gets_uuid(self):
        from schema_validator import generate_fix_commands

        mock_engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True
        mock_inspector.get_columns.return_value = [{"name": "id"}]

        with patch("schema_validator.inspect", return_value=mock_inspector):
            commands = generate_fix_commands(mock_engine)

        id_cmds = [c for c in commands if c.endswith("_id UUID;") or "_id UUID;" in c]
        assert len(id_cmds) > 0

    def test_at_col_gets_timestamp(self):
        from schema_validator import generate_fix_commands

        mock_engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True
        mock_inspector.get_columns.return_value = [{"name": "id"}]

        with patch("schema_validator.inspect", return_value=mock_inspector):
            commands = generate_fix_commands(mock_engine)

        ts_cmds = [c for c in commands if "TIMESTAMP" in c]
        assert len(ts_cmds) > 0

    def test_is_active_gets_boolean(self):
        from schema_validator import generate_fix_commands

        mock_engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True
        mock_inspector.get_columns.return_value = [{"name": "id"}]

        with patch("schema_validator.inspect", return_value=mock_inspector):
            commands = generate_fix_commands(mock_engine)

        bool_cmds = [c for c in commands if "is_active" in c]
        for cmd in bool_cmds:
            assert "BOOLEAN" in cmd

    def test_name_col_gets_varchar(self):
        from schema_validator import generate_fix_commands

        mock_engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True
        mock_inspector.get_columns.return_value = [{"name": "id"}]

        with patch("schema_validator.inspect", return_value=mock_inspector):
            commands = generate_fix_commands(mock_engine)

        name_cmds = [c for c in commands if " name " in c]
        for cmd in name_cmds:
            assert "VARCHAR" in cmd

    def test_description_col_gets_varchar(self):
        from schema_validator import generate_fix_commands

        mock_engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True
        mock_inspector.get_columns.return_value = [{"name": "id"}]

        with patch("schema_validator.inspect", return_value=mock_inspector):
            commands = generate_fix_commands(mock_engine)

        desc_cmds = [c for c in commands if "description " in c]
        for cmd in desc_cmds:
            assert "VARCHAR" in cmd

    def test_other_col_gets_text(self):
        from schema_validator import generate_fix_commands

        mock_engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True
        mock_inspector.get_columns.return_value = [{"name": "id"}]

        with patch("schema_validator.inspect", return_value=mock_inspector):
            commands = generate_fix_commands(mock_engine)

        # Check that columns like 'status', 'message', etc. get TEXT
        status_cmds = [c for c in commands if "status " in c and "TEXT" in c]
        assert len(status_cmds) > 0

    def test_all_commands_have_if_not_exists(self):
        from schema_validator import generate_fix_commands

        mock_engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True
        mock_inspector.get_columns.return_value = [{"name": "id"}]

        with patch("schema_validator.inspect", return_value=mock_inspector):
            commands = generate_fix_commands(mock_engine)

        for cmd in commands:
            assert "IF NOT EXISTS" in cmd

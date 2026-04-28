"""Unit tests for the feedback→korrektur Alembic rename migration's
data-backfill helper.

The schema rename itself is exercised by alembic up/down round-trips elsewhere;
here we focus on `_backfill_korrektur_classic_eval_config`, which mutates JSON
inside the projects table to reflect the wizard-driven enablement model.
"""

from __future__ import annotations

import importlib.util
import json
import os
from unittest.mock import MagicMock, patch

import pytest

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "031_rename_feedback_to_korrektur.py",
    )
)


def _load_migration_module():
    """Load the migration as a standalone module so we can call helpers
    without running the alembic infrastructure."""
    spec = importlib.util.spec_from_file_location(
        "rename_korrektur_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migration():
    return _load_migration_module()


def _make_bind(rows):
    """Construct a mock SQLAlchemy bind whose `execute()` returns `rows` for
    SELECT and records UPDATE invocations on the returned mock."""
    bind = MagicMock(name="bind")

    def execute(stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        if "SELECT" in sql:
            result.fetchall.return_value = rows
        else:
            result.fetchall.return_value = []
        bind._last_call = (sql, params)
        return result

    bind.execute.side_effect = execute
    return bind


def test_backfill_adds_korrektur_classic_when_missing(migration):
    rows = [("project-1", None)]
    bind = _make_bind(rows)
    with patch.object(migration.op, "get_bind", return_value=bind):
        migration._backfill_korrektur_classic_eval_config()

    update_calls = [
        call for call in bind.execute.call_args_list if "UPDATE" in str(call.args[0])
    ]
    assert len(update_calls) == 1
    params = update_calls[0].args[1]
    assert params["pid"] == "project-1"

    cfg = json.loads(params["cfg"])
    assert "evaluation_configs" in cfg
    metrics = [c["metric"] for c in cfg["evaluation_configs"]]
    assert "korrektur_classic" in metrics


def test_backfill_is_idempotent_when_korrektur_classic_already_present(migration):
    existing = {
        "evaluation_configs": [
            {
                "id": "korrektur_classic-existing",
                "metric": "korrektur_classic",
                "display_name": "Korrektur (Classic)",
                "prediction_fields": [],
                "reference_fields": [],
                "enabled": True,
            }
        ]
    }
    rows = [("project-2", existing)]
    bind = _make_bind(rows)
    with patch.object(migration.op, "get_bind", return_value=bind):
        migration._backfill_korrektur_classic_eval_config()

    update_calls = [
        call for call in bind.execute.call_args_list if "UPDATE" in str(call.args[0])
    ]
    assert update_calls == [], (
        "Should not write when korrektur_classic is already present in eval configs"
    )


def test_backfill_preserves_other_eval_configs(migration):
    """Adding korrektur_classic must not drop any pre-existing metric entries."""
    existing = {
        "evaluation_configs": [
            {"id": "x", "metric": "rouge", "enabled": True},
            {"id": "y", "metric": "llm_judge_falloesung", "enabled": True},
        ]
    }
    rows = [("project-3", existing)]
    bind = _make_bind(rows)
    with patch.object(migration.op, "get_bind", return_value=bind):
        migration._backfill_korrektur_classic_eval_config()

    update_calls = [
        call for call in bind.execute.call_args_list if "UPDATE" in str(call.args[0])
    ]
    assert len(update_calls) == 1
    cfg = json.loads(update_calls[0].args[1]["cfg"])
    metrics = sorted(c["metric"] for c in cfg["evaluation_configs"])
    assert metrics == ["korrektur_classic", "llm_judge_falloesung", "rouge"]


def test_backfill_handles_eval_config_stored_as_json_string(migration):
    """Some installs may have stored evaluation_config as a serialized string."""
    rows = [("project-4", json.dumps({"evaluation_configs": []}))]
    bind = _make_bind(rows)
    with patch.object(migration.op, "get_bind", return_value=bind):
        migration._backfill_korrektur_classic_eval_config()

    update_calls = [
        call for call in bind.execute.call_args_list if "UPDATE" in str(call.args[0])
    ]
    assert len(update_calls) == 1
    cfg = json.loads(update_calls[0].args[1]["cfg"])
    assert any(c["metric"] == "korrektur_classic" for c in cfg["evaluation_configs"])


def test_backfill_handles_malformed_json_string_gracefully(migration):
    """A garbage string in evaluation_config is treated as empty config."""
    rows = [("project-5", "not valid json {{")]
    bind = _make_bind(rows)
    with patch.object(migration.op, "get_bind", return_value=bind):
        migration._backfill_korrektur_classic_eval_config()

    update_calls = [
        call for call in bind.execute.call_args_list if "UPDATE" in str(call.args[0])
    ]
    assert len(update_calls) == 1
    cfg = json.loads(update_calls[0].args[1]["cfg"])
    metrics = [c["metric"] for c in cfg["evaluation_configs"]]
    assert metrics == ["korrektur_classic"]


def test_backfill_only_targets_korrektur_enabled_projects(migration):
    """The SELECT must filter on korrektur_enabled = true so projects without
    the flag are left alone."""
    bind = _make_bind([])
    with patch.object(migration.op, "get_bind", return_value=bind):
        migration._backfill_korrektur_classic_eval_config()

    select_calls = [
        call for call in bind.execute.call_args_list if "SELECT" in str(call.args[0])
    ]
    assert len(select_calls) == 1
    sql = str(select_calls[0].args[0])
    assert "korrektur_enabled = true" in sql, sql


def test_backfill_inserted_entry_has_required_eval_config_shape(migration):
    """The new entry must match the EvaluationConfig contract used by the
    wizard / KorrekturPage gating logic — `metric`, not `metric_name`."""
    rows = [("project-6", {"evaluation_configs": []})]
    bind = _make_bind(rows)
    with patch.object(migration.op, "get_bind", return_value=bind):
        migration._backfill_korrektur_classic_eval_config()

    update_calls = [
        call for call in bind.execute.call_args_list if "UPDATE" in str(call.args[0])
    ]
    cfg = json.loads(update_calls[0].args[1]["cfg"])
    entry = next(c for c in cfg["evaluation_configs"] if c["metric"] == "korrektur_classic")
    assert entry["display_name"] == "Korrektur (Classic)"
    assert entry["enabled"] is True
    assert entry["prediction_fields"] == []
    assert entry["reference_fields"] == []
    # Matches the id-prefix convention used by the wizard's generateEvaluationId
    assert entry["id"].startswith("korrektur_classic-")
    # Critical: uses `metric` key (not `metric_name`); KorrekturPage's
    # projectHasMetric() check would fail otherwise.
    assert "metric_name" not in entry

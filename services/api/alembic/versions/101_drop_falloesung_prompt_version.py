"""Drop the Falllösung judge's prompt_version from stored evaluation configs

The Falllösung judge prompt was briefly versioned: "v1" carried a hardcoded
0–18 conversion table, "v2" dropped it and left the grade to the server.
There is now exactly ONE prompt — the table-less one — because the table was
never load-bearing: `parse_falloesung_response` has always recomputed
`grade_points` from the dimension sum and the exam's own Notenschlüssel and
never read the model's value. Keeping two prompts alive only meant that an
exam created before the split was judged against a table that was not its own
key.

With the version gone from the code, `metric_parameters.prompt_version` is a
dead key in live config that would otherwise survive every export, import,
deep-merge and config UI. This strips it from every project.

Stored `task_evaluations.judge_prompts_used` is deliberately NOT touched: it
is provenance, and a row that records it was graded under the versioned
prompt should keep saying so.

Idempotent — rewrites only rows that still carry the key, and re-running
finds none. Downgrade is a no-op: the version the key selected no longer
exists, so putting the string back would be meaningless.

Revision ID: 101_drop_falloesung_prompt_version
Revises: 100_task_rubrics_structure
Create Date: 2026-09-11
"""

import json

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "101_drop_falloesung_prompt_version"
down_revision = "100_task_rubrics_structure"
branch_labels = None
depends_on = None

# Both key names an evaluation_config document has used for its config list.
_CONFIG_LIST_KEYS = ("evaluation_configs", "multi_field_evaluations")


def _strip(config):
    """Remove `metric_parameters.prompt_version`; return None when unchanged."""
    if not isinstance(config, dict):
        return None
    changed = False
    out = dict(config)
    for list_key in _CONFIG_LIST_KEYS:
        entries = out.get(list_key)
        if not isinstance(entries, list):
            continue
        new_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                new_entries.append(entry)
                continue
            params = entry.get("metric_parameters")
            if isinstance(params, dict) and "prompt_version" in params:
                new_params = {
                    k: v for k, v in params.items() if k != "prompt_version"
                }
                entry = {**entry, "metric_parameters": new_params}
                changed = True
            new_entries.append(entry)
        out[list_key] = new_entries
    return out if changed else None


def _config_column_type(conn) -> str:
    """`json` or `jsonb` — the column has been both across installs, and an
    UPDATE has to cast to the one this database actually has."""
    for column in inspect(conn).get_columns("projects"):
        if column["name"] == "evaluation_config":
            return "jsonb" if "JSONB" in str(column["type"]).upper() else "json"
    return "json"


def upgrade() -> None:
    conn = op.get_bind()
    cast_to = _config_column_type(conn)
    rows = conn.execute(
        sa.text(
            "SELECT id, evaluation_config FROM projects "
            "WHERE evaluation_config::text LIKE '%prompt_version%'"
        )
    ).fetchall()
    updated = 0
    for project_id, config in rows:
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except ValueError:
                continue
        stripped = _strip(config)
        if stripped is None:
            continue
        conn.execute(
            sa.text(
                "UPDATE projects SET evaluation_config = "
                f"CAST(:cfg AS {cast_to}) WHERE id = :pid"
            ),
            {"cfg": json.dumps(stripped), "pid": project_id},
        )
        updated += 1
    print(f"101: dropped prompt_version from {updated} project(s)")


def downgrade() -> None:
    # Nothing to restore: there is only one Falllösung judge prompt now, so a
    # reinstated version string would select nothing.
    pass

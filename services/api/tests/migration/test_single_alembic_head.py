"""Exactly one alembic head, always.

Two parallel branches adding migrations off the same parent produce two
heads; ``alembic upgrade head`` then refuses to run and every deploy is
blocked at startup. This happened twice on 2026-07-13 (076_add_lti_tables
vs 076_add_timer_pause_fields, then 078_add_lti_tables vs
078_evaluation_lifecycle_columns) — this test turns the collision into a
PR-time failure with an actionable message instead of a red main gate.
"""

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_exactly_one_head():
    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    assert len(heads) == 1, (
        f"Multiple alembic heads: {sorted(heads)}. Two migration branches "
        "share a parent — re-parent the newer one (rename + bump its number, "
        "point down_revision at the other head) so the chain is linear."
    )

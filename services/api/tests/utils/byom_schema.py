"""Idempotent schema backstop for the BYOM surface (migration 080) on
long-lived test databases.

The session-scoped ``_create_tables`` fixture builds the schema with
``Base.metadata.create_all``, which skips tables that already exist. A test
DB bootstrapped before migration 080 landed therefore has ``llm_models``
without the BYOM columns and CHECK constraints. (The two NEW tables —
``model_organizations`` and ``custom_model_credentials`` — are safe:
create_all only skips *existing* tables, so they are always created.)

This mirrors the established two-part pattern:
  - conftest's ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` patches for
    column drift on pre-existing tables, and
  - the per-file ``_ensure_constraints`` fixture in
    tests/integration/test_project_visibility_constraints.py for CHECKs.

Kept in tests/utils (not copy-pasted per file) because four test modules
need the same backstop.
"""

from sqlalchemy import text

# (column name, DDL) — matches migration 080 / LLMModel column definitions.
BYOM_LLM_MODEL_COLUMNS = [
    ("is_official", "BOOLEAN NOT NULL DEFAULT false"),
    ("created_by", "VARCHAR REFERENCES users(id) ON DELETE SET NULL"),
    ("is_private", "BOOLEAN NOT NULL DEFAULT false"),
    ("is_public", "BOOLEAN NOT NULL DEFAULT false"),
    ("base_url", "VARCHAR(500)"),
    ("endpoint_model_name", "VARCHAR(255)"),
    ("requires_api_key", "BOOLEAN NOT NULL DEFAULT true"),
]

# Same expressions as LLMModel.__table_args__ / migration 080.
BYOM_LLM_MODEL_CHECKS = [
    (
        "ck_llm_models_visibility_exclusive",
        "NOT (is_private AND is_public)",
    ),
    (
        "ck_llm_models_custom_endpoint_required",
        "is_official OR (base_url IS NOT NULL AND endpoint_model_name IS NOT NULL)",
    ),
    (
        "ck_llm_models_official_no_visibility_flags",
        "NOT is_official OR (NOT is_private AND NOT is_public)",
    ),
]


def ensure_byom_llm_schema(engine) -> None:
    """Add any missing BYOM columns/CHECKs to ``llm_models``, idempotently."""
    with engine.begin() as conn:
        had_is_official = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'llm_models' AND column_name = 'is_official'"
            )
        ).scalar()

        for name, ddl in BYOM_LLM_MODEL_COLUMNS:
            conn.execute(
                text(f"ALTER TABLE llm_models ADD COLUMN IF NOT EXISTS {name} {ddl}")
            )

        if not had_is_official:
            # Migration 080's CRITICAL backfill: every row that predates the
            # BYOM columns is by definition a catalog (official) row. Without
            # this, ck_llm_models_custom_endpoint_required below would reject
            # every pre-existing row.
            conn.execute(text("UPDATE llm_models SET is_official = true"))

        for name, expr in BYOM_LLM_MODEL_CHECKS:
            existing = conn.execute(
                text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
                {"name": name},
            ).scalar()
            if not existing:
                conn.execute(
                    text(f"ALTER TABLE llm_models ADD CONSTRAINT {name} CHECK ({expr})")
                )

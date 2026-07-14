"""The drift checker must ignore custom (BYOM) rows.

Custom models are DB-only by design — they never appear in
seeds/llm_models.yaml, so without the is_official exemption every
registered custom model would page ops as "drift" on the nightly cron
(scripts/check_model_catalog_drift.py) and fail `make check-model-drift`.

`diff()` builds its own engine from a URL, so it cannot see rows created
inside the per-test SAVEPOINT transaction of the shared Postgres fixture.
These tests instead build a throwaway on-disk SQLite database, seed it
through the real initialize_llm_models(), and point diff() at its URL —
the same fresh-DB-then-diff shape the Model Catalog Drift PR workflow uses.
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import initialize_llm_models
from models import LLMModel


@pytest.fixture(scope="module")
def drift():
    """Load the drift script as a module (same parent-walk as
    tests/unit/test_llm_models_recommended.py — the relative path differs
    between local dev and the test container)."""
    here = Path(__file__).resolve()
    candidates = [p / "scripts" / "check_model_catalog_drift.py" for p in here.parents]
    candidates += [Path("/app/scripts/check_model_catalog_drift.py")]
    script = next((c for c in candidates if c.exists()), None)
    assert script is not None, f"drift script not found near {here}"

    spec = importlib.util.spec_from_file_location("drift_custom_exempt", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seeded_sqlite_db(tmp_path):
    """(db_url, session) for a throwaway SQLite DB holding the real catalog."""
    db_url = f"sqlite:///{tmp_path / 'drift.sqlite'}"
    engine = create_engine(db_url)
    # Only the llm_models table is needed; SQLite doesn't resolve the
    # users.id FK reference until FK enforcement is switched on (it isn't).
    LLMModel.__table__.create(bind=engine)
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionFactory()
    initialize_llm_models(session)

    yield db_url, session

    session.close()
    engine.dispose()


def _custom_model(model_id="custom-drift-exempt"):
    # Both visibility flags false (org-scoped shape) so the drift-flip test
    # can set is_official=True without tripping
    # ck_llm_models_official_no_visibility_flags (SQLite enforces the
    # CHECKs from __table_args__ too).
    return LLMModel(
        id=model_id,
        name="Drift-exempt custom model",
        provider="Custom",
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=False,
        is_private=False,
        is_public=False,
        base_url="http://localhost:11434/v1",
        endpoint_model_name="llama3:8b",
        requires_api_key=True,
    )


def test_freshly_seeded_db_has_no_drift(drift, seeded_sqlite_db):
    """Baseline: seed-then-diff is clean (mirrors the PR CI workflow)."""
    db_url, _ = seeded_sqlite_db

    result = drift.diff(db_url)

    assert result["missing_in_db"] == []
    assert result["extra_in_db"] == []
    assert result["field_mismatches"] == []
    assert result["custom_rows"] == 0
    assert result["ok"] is True


def test_active_custom_row_is_exempt_from_drift(drift, seeded_sqlite_db):
    db_url, session = seeded_sqlite_db
    session.add(_custom_model())
    session.commit()

    result = drift.diff(db_url)

    assert result["ok"] is True
    assert "custom-drift-exempt" not in result["extra_in_db"]
    assert result["custom_rows"] == 1
    # Official comparison set is unaffected by the custom row.
    assert result["db_count"] == result["yaml_count"]


def test_flipping_is_official_makes_row_count_as_drift(drift, seeded_sqlite_db):
    """Sanity: the exemption is exactly the is_official flag. A custom row
    that (somehow) got flipped to official IS drift — an active official
    row with no YAML entry."""
    db_url, session = seeded_sqlite_db
    session.add(_custom_model())
    session.commit()

    row = session.query(LLMModel).filter(LLMModel.id == "custom-drift-exempt").one()
    row.is_official = True
    session.commit()

    result = drift.diff(db_url)

    assert result["ok"] is False
    assert "custom-drift-exempt" in result["extra_in_db"]
    assert result["custom_rows"] == 0

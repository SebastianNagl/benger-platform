"""BYOM safety of the llm_models seeder (database.initialize_llm_models).

Migration 080 added user-registered custom models to the same llm_models
table the YAML catalog seeds into. The seeder must therefore:
  - stamp every YAML-seeded row is_official=True,
  - keep deactivating OFFICIAL rows that dropped out of the YAML
    (historical-eval rows stay, just inactive), and
  - NEVER touch custom (is_official=False) rows — they are DB-only by
    design and would otherwise be deactivated on every startup/reseed.

Also covers the loader-side guard: the 'custom-' id namespace is reserved
for user-registered rows (generated PKs), so a YAML/overlay entry using it
is rejected outright by seeds.llm_models_loader._validate.

Runs the REAL YAML catalog against the test Postgres — same surface the
Model Catalog Drift PR workflow exercises.
"""

import uuid

import pytest

from database import initialize_llm_models
from models import LLMModel


@pytest.fixture(scope="module", autouse=True)
def _ensure_byom_schema():
    """Backstop for long-lived test DBs bootstrapped before migration 080
    (create_all skips the pre-existing llm_models table, so the BYOM
    columns/CHECKs can be missing). Same pattern as the _ensure_constraints
    fixture in tests/integration/test_project_visibility_constraints.py.
    """
    from tests.fixtures.database import _get_engine
    from tests.utils.byom_schema import ensure_byom_llm_schema

    engine, _ = _get_engine()
    ensure_byom_llm_schema(engine)
    yield


def _custom_model(**overrides):
    base = dict(
        id=f"custom-{uuid.uuid4().hex[:8]}",
        name="My vLLM model",
        provider="Custom",
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=False,
        is_private=True,
        is_public=False,
        base_url="http://vllm.internal:8000/v1",
        endpoint_model_name="meta-llama/Llama-3-8B",
        requires_api_key=True,
    )
    base.update(overrides)
    return LLMModel(**base)


class TestSeederCustomRowSafety:
    def test_custom_row_survives_reseed_untouched(self, test_db):
        test_db.add(_custom_model(id="custom-abc"))
        test_db.commit()

        initialize_llm_models(test_db)

        test_db.expire_all()
        row = test_db.query(LLMModel).filter(LLMModel.id == "custom-abc").first()
        assert row is not None
        # The deactivation sweep filters is_official — the custom row must
        # come out of a reseed exactly as it went in.
        assert row.is_active is True
        assert row.is_official is False
        assert row.is_private is True
        assert row.base_url == "http://vllm.internal:8000/v1"
        assert row.endpoint_model_name == "meta-llama/Llama-3-8B"
        assert row.requires_api_key is True

    def test_yaml_seeded_rows_are_official(self, test_db):
        from seeds.llm_models_loader import load_catalog

        initialize_llm_models(test_db)

        catalog_ids = [m["id"] for m in load_catalog().models]
        assert catalog_ids  # the real YAML is never empty
        rows = test_db.query(LLMModel).filter(LLMModel.id.in_(catalog_ids)).all()
        assert len(rows) == len(catalog_ids)
        assert all(r.is_official for r in rows)

    def test_departed_official_row_is_deactivated(self, test_db):
        """The official-only filter must not break the sweep itself: an
        official row whose id vanished from the YAML still gets flipped to
        is_active=False."""
        test_db.add(
            LLMModel(
                id="zz-departed-model",
                name="Departed Model",
                provider="openai",
                model_type="chat",
                capabilities=["text_generation"],
                is_active=True,
                is_official=True,
            )
        )
        test_db.commit()

        initialize_llm_models(test_db)

        test_db.expire_all()
        row = (
            test_db.query(LLMModel).filter(LLMModel.id == "zz-departed-model").first()
        )
        assert row is not None
        assert row.is_active is False
        # Sweep deactivates, never demotes.
        assert row.is_official is True


class TestLoaderCustomNamespaceGuard:
    def test_validate_rejects_custom_prefix(self):
        from seeds.llm_models_loader import _validate

        # All REQUIRED_FIELDS present so the reserved-prefix branch (not the
        # missing-fields one) is what raises.
        model = {
            "id": "custom-x",
            "name": "Sneaky YAML entry",
            "provider": "Custom",
            "model_type": "chat",
            "capabilities": [],
            "is_active": True,
        }
        with pytest.raises(ValueError, match="custom-"):
            _validate(model, "src")

    def test_real_yaml_loads_clean(self):
        from seeds.llm_models_loader import load_catalog

        catalog = load_catalog()  # must not raise
        assert catalog.models
        assert not any(str(m["id"]).startswith("custom-") for m in catalog.models)

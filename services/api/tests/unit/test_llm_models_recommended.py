"""Tests for the migration-046 `recommended_parameters` field on LLM models.

Covers three integration points end-to-end:
  1. The YAML loader preserves the new field (no silent drop).
  2. The drift checker's COMPARE_FIELDS includes it (so YAML/DB skew is caught).
  3. The public /api/llm_models/public/models endpoint surfaces it to the UI.
"""

from datetime import datetime, timezone

import pytest
from fastapi import status


# ─── 1. Loader round-trip ─────────────────────────────────────────────────
def test_yaml_loader_preserves_recommended_parameters():
    """The seed YAML carries recommended_parameters per migration 046; the
    loader must pass it through verbatim so the upsert in database.py can
    write it to the JSON column."""
    from seeds.llm_models_loader import load_catalog

    catalog = load_catalog()
    by_id = {m["id"]: m for m in catalog.models}

    # gpt-5 is hard-fixed to temperature=1.0 by API; the recommendation
    # mirrors the constraint to keep the UI consistent.
    gpt5 = by_id["gpt-5"]
    assert "recommended_parameters" in gpt5
    assert gpt5["recommended_parameters"]["default"]["temperature"] == 1.0

    # gpt-4o uses the gen/eval split — different temps per mode.
    gpt4o = by_id["gpt-4o"]
    rec = gpt4o["recommended_parameters"]
    assert rec["generation"]["temperature"] == 0.7
    assert rec["evaluation"]["temperature"] == 0.0

    # Provenance must always carry source + retrieved date so the audit
    # trail traces back to the docs version that informed the value.
    assert "source" in rec["provenance"]
    assert "retrieved" in rec["provenance"]


def test_yaml_gpt5_entries_declare_seed_unsupported():
    """Audit item D: every GPT-5 entry must explicitly declare
    constraints.seed.supported: false so the worker drops the seed
    parameter deterministically (not via provider-level inference)."""
    from seeds.llm_models_loader import load_catalog

    catalog = load_catalog()
    gpt5_ids = [m["id"] for m in catalog.models if m["id"].startswith("gpt-5")]
    assert len(gpt5_ids) >= 11, "Expected the full GPT-5 family"
    for mid in gpt5_ids:
        m = next(x for x in catalog.models if x["id"] == mid)
        seed = (m.get("constraints") or {}).get("seed") or {}
        assert seed.get("supported") == False, f"{mid} missing seed.supported: false"  # noqa: E712


# ─── 2. Drift checker awareness ───────────────────────────────────────────
def test_drift_checker_compares_recommended_parameters():
    """The drift checker is the safety net for "I edited the YAML but
    forgot to deploy". If recommended_parameters isn't in COMPARE_FIELDS,
    a stale DB row would silently pass."""
    import importlib.util
    from pathlib import Path

    # The script ships next to the api code, but the relative path differs
    # between local dev (services/api/scripts/...) and the test container
    # (/app/scripts/...). Walk parent dirs until found.
    here = Path(__file__).resolve()
    candidates = [p / "scripts" / "check_model_catalog_drift.py" for p in here.parents]
    candidates += [Path("/app/scripts/check_model_catalog_drift.py")]
    script = next((c for c in candidates if c.exists()), None)
    assert script is not None, f"drift script not found near {here}"

    spec = importlib.util.spec_from_file_location("drift", script)
    drift = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift)

    assert "recommended_parameters" in drift.COMPARE_FIELDS


# ─── 3. Public endpoint exposure ──────────────────────────────────────────
#
# The /public/models endpoint was migrated to the async DB lane, so these
# tests seed real LLMModel rows through async_test_db and read them back via
# async_test_client (the old Mock(spec=Session).query(...) shape no longer
# matches the async handler's `await db.execute(select(...))`).
def _model_with_recommendations(**overrides):
    from models import LLMModel as DBLLMModel

    # Use a test-only id to avoid colliding with real catalog rows that may
    # already be committed in the shared test DB (e.g. a seeded "gpt-4o").
    data = dict(
        id="test-gpt-4o-rec",
        name="GPT-4o",
        description="Multimodal model",
        provider="openai",
        model_type="chat",
        capabilities=["text-generation"],
        config_schema=None,
        default_config=None,
        input_cost_per_million=2.5,
        output_cost_per_million=10.0,
        parameter_constraints=None,
        recommended_parameters={
            "default": {"max_tokens": 4000},
            "generation": {"temperature": 0.7},
            "evaluation": {"temperature": 0.0},
            "provenance": {
                "source": "https://platform.openai.com/docs/models/gpt-4o",
                "retrieved": "2026-05-07",
            },
        },
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=None,
    )
    data.update(overrides)
    return DBLLMModel(**data)


@pytest.mark.asyncio
async def test_public_models_endpoint_returns_recommended_parameters(
    async_test_client, async_test_db
):
    """The frontend reads recommended_parameters off this endpoint to
    render the "Empfehlung / Verschiedene / Keine" badges next to each
    parameter input. If the response model omits the field, the badges
    silently degrade to "no recommendation" for every model."""
    async_test_db.add(_model_with_recommendations())
    await async_test_db.commit()

    response = await async_test_client.get("/api/llm_models/public/models")
    assert response.status_code == status.HTTP_200_OK
    by_id = {m["id"]: m for m in response.json()}
    assert "test-gpt-4o-rec" in by_id
    rec = by_id["test-gpt-4o-rec"]["recommended_parameters"]
    assert rec is not None
    assert rec["generation"]["temperature"] == 0.7
    assert rec["evaluation"]["temperature"] == 0.0
    assert rec["provenance"]["source"].startswith("https://")


@pytest.mark.asyncio
async def test_public_models_endpoint_returns_none_for_models_without_recommendations(
    async_test_client, async_test_db
):
    """Models without a studied recommendation carry NULL. The field should
    serialize as null (not omitted), so the UI's `getRecommendedParam`
    helper can branch on it cleanly."""
    async_test_db.add(
        _model_with_recommendations(
            id="obscure-community-model", recommended_parameters=None
        )
    )
    await async_test_db.commit()

    response = await async_test_client.get("/api/llm_models/public/models")
    assert response.status_code == status.HTTP_200_OK
    by_id = {m["id"]: m for m in response.json()}
    assert "obscure-community-model" in by_id
    assert "recommended_parameters" in by_id["obscure-community-model"]
    assert by_id["obscure-community-model"]["recommended_parameters"] is None

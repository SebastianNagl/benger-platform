"""Providers, and so the API key a call spends, come from the model catalog.

``get_provider_from_model`` used to decide the provider by substring-matching
the model id. The catalog (``services/shared/seeds/llm_models.yaml``) records
every official model's provider explicitly, and the heuristics cannot tell a
DeepInfra-hosted model whose id contains "gpt" or "mistral" from the vendor's
own model. Judges resolve their provider through this function, so such a
model would have graded on the wrong provider's key.

The module under test is loaded by file path, as in
``test_provider_capabilities_cost_kills.py``, so every test gets fresh caches
and no provider SDK is imported.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import types

import pytest

_workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_services_root = os.path.dirname(_workers_root)
_pc_path = os.path.join(
    _services_root, "shared", "ai_services", "provider_capabilities.py"
)


def _load_pc():
    spec = importlib.util.spec_from_file_location(
        "_provider_from_catalog_caps", _pc_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pc():
    return _load_pc()


class _Result:
    def __init__(self, models):
        self.models = models


def _install_fake_catalog(monkeypatch, models=None, error=None):
    """Replace the lazily imported loader with one that returns ``models``
    or raises ``error``. Returns the fake module so a test can wrap it."""
    loader_mod = types.ModuleType("seeds.llm_models_loader")

    def _load():
        if error is not None:
            raise error
        return _Result(list(models or []))

    loader_mod.load_catalog = _load
    if "seeds" not in sys.modules:
        seeds_pkg = types.ModuleType("seeds")
        seeds_pkg.__path__ = []
        monkeypatch.setitem(sys.modules, "seeds", seeds_pkg)
    monkeypatch.setitem(sys.modules, "seeds.llm_models_loader", loader_mod)
    return loader_mod


class TestTheRealCatalog:
    def test_every_catalog_provider_name_is_a_registry_key(self, pc):
        from seeds.llm_models_loader import load_catalog

        names = {str(m["provider"]) for m in load_catalog().models}
        unknown = {n for n in names if pc._normalize_catalog_provider(n) is None}
        assert unknown == set()

    def test_every_catalog_row_resolves_to_its_own_provider(self, pc):
        from seeds.llm_models_loader import load_catalog

        models = load_catalog().models
        assert models
        mismatches = []
        for model in models:
            expected = pc._normalize_catalog_provider(model["provider"])
            assert expected in pc.PROVIDER_CAPABILITIES, (model["id"], model["provider"])
            resolved = pc.get_provider_from_model(model["id"])
            if resolved != expected:
                mismatches.append((model["id"], model["provider"], resolved))
        assert mismatches == []


class TestCatalogBeatsTheHeuristics:
    def test_a_deepinfra_model_with_a_vendor_name_in_its_id(self, pc, monkeypatch):
        """The heuristics would send both of these to the vendor's own key."""
        _install_fake_catalog(monkeypatch, [
            {"id": "openai/gpt-oss-120b", "provider": "DeepInfra"},
            {"id": "mistralai/Mistral-Small-24B-Instruct", "provider": "DeepInfra"},
        ])
        assert pc.get_provider_from_model("openai/gpt-oss-120b") == "deepinfra"
        assert (
            pc.get_provider_from_model("mistralai/Mistral-Small-24B-Instruct")
            == "deepinfra"
        )

    def test_a_listed_id_is_found_in_any_case(self, pc, monkeypatch):
        _install_fake_catalog(
            monkeypatch, [{"id": "meta-llama/Llama-X", "provider": "DeepInfra"}]
        )
        assert pc.get_provider_from_model("meta-llama/llama-x") == "deepinfra"

    def test_display_names_and_short_forms_normalize(self, pc):
        assert pc._normalize_catalog_provider("OpenAI") == "openai"
        assert pc._normalize_catalog_provider("DeepInfra") == "deepinfra"
        assert pc._normalize_catalog_provider("Grok") == "grok"
        assert pc._normalize_catalog_provider("Grok (xAI)") == "grok"
        assert pc._normalize_catalog_provider("xAI") == "grok"
        assert pc._normalize_catalog_provider("Mistral AI") == "mistral"
        assert pc._normalize_catalog_provider("") is None
        assert pc._normalize_catalog_provider(None) is None
        assert pc._normalize_catalog_provider("Nonesuch") is None

    def test_a_row_with_an_unknown_provider_is_reported_not_guessed(
        self, pc, monkeypatch, caplog
    ):
        _install_fake_catalog(
            monkeypatch, [{"id": "gpt-mystery", "provider": "Nonesuch"}]
        )
        with caplog.at_level(logging.WARNING):
            # Not in the map, so the heuristic decides, and the catalog row
            # that could not be mapped is named in the log.
            assert pc.get_provider_from_model("gpt-mystery") == "openai"
        assert "unknown provider" in caplog.text
        assert "gpt-mystery" in caplog.text


class TestIdsTheCatalogDoesNotList:
    def test_unknown_ids_keep_the_heuristic(self, pc, monkeypatch):
        _install_fake_catalog(monkeypatch, [])
        assert pc.get_provider_from_model("claude-future-9") == "anthropic"
        assert pc.get_provider_from_model("gemini-next") == "google"
        assert pc.get_provider_from_model("qwen-next") == "deepinfra"
        assert pc.get_provider_from_model("totally-unknown") == "openai"

    def test_custom_ids_stay_custom(self, pc, monkeypatch):
        _install_fake_catalog(monkeypatch, [])
        assert pc.get_provider_from_model("custom-1234-abcd") == "custom"


class TestCaching:
    def test_an_unreadable_catalog_logs_once_and_falls_back(
        self, pc, monkeypatch, caplog
    ):
        loader = _install_fake_catalog(monkeypatch, error=OSError("catalog gone"))
        calls = []
        original = loader.load_catalog

        def counting():
            calls.append(1)
            return original()

        loader.load_catalog = counting
        with caplog.at_level(logging.WARNING):
            assert pc.get_provider_from_model("claude-x") == "anthropic"
            assert pc.get_provider_from_model("gpt-y") == "openai"
            assert pc.get_provider_from_model("custom-z") == "custom"
        assert len(calls) == 1
        assert caplog.text.count("could not be loaded") == 1

    def test_the_catalog_is_read_once(self, pc, monkeypatch):
        loader = _install_fake_catalog(
            monkeypatch, [{"id": "gpt-hosted", "provider": "DeepInfra"}]
        )
        calls = []
        original = loader.load_catalog

        def counting():
            calls.append(1)
            return original()

        loader.load_catalog = counting
        for _ in range(3):
            assert pc.get_provider_from_model("gpt-hosted") == "deepinfra"
        assert len(calls) == 1

    def test_reload_clears_the_provider_cache(self, pc, monkeypatch):
        _install_fake_catalog(
            monkeypatch, [{"id": "gpt-hosted", "provider": "DeepInfra"}]
        )
        assert pc.get_provider_from_model("gpt-hosted") == "deepinfra"
        _install_fake_catalog(
            monkeypatch, [{"id": "gpt-hosted", "provider": "OpenAI"}]
        )
        # Still the cached answer until the caches are reloaded.
        assert pc.get_provider_from_model("gpt-hosted") == "deepinfra"
        pc.reload_capability_caches()
        assert pc.get_provider_from_model("gpt-hosted") == "openai"

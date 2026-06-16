"""Kill-layer tests for the cost-computation source-of-truth in
``services/shared/ai_services/provider_capabilities.py``.

``calculate_cost()`` is called by EVERY provider client
(anthropic / google / deepinfra / grok / mistral / openai / cohere) to
compute the reported ``cost_usd``. Academic benchmarks report compute
cost, so a swapped input/output price, a wrong divisor, or a ``+`` that
became a ``-`` would silently corrupt every reported number. This file
pins the arithmetic, the per-model lookup (incl. the prefix-match
branch), and the catalog mapping with hand-computed exact values.

Every numeric assertion below is hand-computed in the docstring so the
test doubles as the spec. Values are deterministic and
catalog-independent: ``get_model_cost`` is monkeypatched to return a
known ``ModelCost`` so the arithmetic under test is the only variable.

Import style mirrors ``test_ai_service_metadata.py``: the module under
test is loaded by file path via ``importlib.util`` rather than through
the ``ai_services`` package ``__init__``, which would eagerly import
every provider SDK (openai, anthropic, google.genai, ...). The cost
helpers have no SDK dependency.
"""

from __future__ import annotations

import importlib.util
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
    """Load a *fresh* copy of provider_capabilities.py by file path.

    A fresh module per test means the in-process ``_COST_CACHE`` of one
    test can never leak into another, and monkeypatching module-level
    names (``get_model_cost``, ``_COST_CACHE``) is fully isolated.
    """
    spec = importlib.util.spec_from_file_location(
        "_cost_kills_provider_caps", _pc_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pc():
    return _load_pc()


# ---------------------------------------------------------------------------
# calculate_cost arithmetic
# ---------------------------------------------------------------------------
class TestCalculateCostArithmetic:
    """Pin the three arithmetic invariants in calculate_cost:

        input_cost  = (input_tokens  / 1_000_000) * model_cost.input
        output_cost = (output_tokens / 1_000_000) * model_cost.output
        return input_cost + output_cost
    """

    INPUT_PRICE = 3.0   # USD per million input tokens
    OUTPUT_PRICE = 15.0  # USD per million output tokens

    def _pin_cost(self, pc, monkeypatch):
        """Force get_model_cost to a known ModelCost(input=3, output=15)
        so the result depends only on the arithmetic under test."""
        known = pc.ModelCost(input=self.INPUT_PRICE, output=self.OUTPUT_PRICE)
        monkeypatch.setattr(pc, "get_model_cost", lambda provider, model: known)
        return known

    def test_combined_input_and_output_exact_18(self, pc, monkeypatch):
        """1_000_000 input + 1_000_000 output at $3/M in, $15/M out.

        input_cost  = (1_000_000 / 1_000_000) * 3  = 1 * 3  = 3.0
        output_cost = (1_000_000 / 1_000_000) * 15 = 1 * 15 = 15.0
        total       = 3.0 + 15.0                            = 18.0

        This single value pins THREE mutations at once:
          * divisor: a /1_000 would give 3000 + 15000 = 18000, not 18.
          * pairing: input*input_price / output*output_price. A swap
            (input_tokens * output_price + output_tokens * input_price)
            here gives 15 + 3 = 18 — the SAME — so the swap is caught by
            the asymmetric input-only / output-only tests below, not here.
          * operator: a '-' would give 3 - 15 = -12, not 18.
        """
        self._pin_cost(pc, monkeypatch)
        assert pc.calculate_cost("anthropic", "any-model", 1_000_000, 1_000_000) == 18.0

    def test_input_only_isolates_input_price(self, pc, monkeypatch):
        """output_tokens=0 -> output_cost term is 0, leaving input only.

        input_cost  = (1_000_000 / 1_000_000) * 3 = 3.0
        output_cost = (0 / 1_000_000) * 15        = 0.0
        total                                     = 3.0

        Kills the input/output SWAP: if input_tokens were multiplied by
        the OUTPUT price (15) the result would be 15.0, not 3.0.
        """
        self._pin_cost(pc, monkeypatch)
        assert pc.calculate_cost("anthropic", "any-model", 1_000_000, 0) == 3.0

    def test_output_only_isolates_output_price(self, pc, monkeypatch):
        """input_tokens=0 -> input_cost term is 0, leaving output only.

        input_cost  = (0 / 1_000_000) * 3         = 0.0
        output_cost = (1_000_000 / 1_000_000) * 15 = 15.0
        total                                      = 15.0

        Kills the input/output SWAP from the other side: if output_tokens
        were multiplied by the INPUT price (3) the result would be 3.0,
        not 15.0. Together with the input-only test this fully constrains
        the price->token pairing.
        """
        self._pin_cost(pc, monkeypatch)
        assert pc.calculate_cost("anthropic", "any-model", 0, 1_000_000) == 15.0

    def test_fractional_token_counts_pin_divisor(self, pc, monkeypatch):
        """500_000 input @ $3/M, 0 output.

        input_cost  = (500_000 / 1_000_000) * 3 = 0.5 * 3 = 1.5
        output_cost = 0
        total                                            = 1.5

        Sub-million counts pin the /1_000_000 divisor precisely: a
        /1_000 divisor would give 500 * 3 = 1500; integer division
        (500_000 // 1_000_000 == 0) would give 0.0.
        """
        self._pin_cost(pc, monkeypatch)
        assert pc.calculate_cost("anthropic", "any-model", 500_000, 0) == 1.5

    def test_mixed_fractional_both_sides(self, pc, monkeypatch):
        """250_000 input @ $3/M + 100_000 output @ $15/M.

        input_cost  = (250_000 / 1_000_000) * 3  = 0.25 * 3  = 0.75
        output_cost = (100_000 / 1_000_000) * 15 = 0.10 * 15 = 1.50
        total                                              = 2.25

        A realistic asymmetric request: distinct token counts AND distinct
        prices on each side, so neither a swap nor a divisor error nor a
        sign flip survives. Use pytest.approx for float assembly safety
        (0.75 + 1.5 == 2.25 is exact in binary, but approx is harmless).
        """
        self._pin_cost(pc, monkeypatch)
        result = pc.calculate_cost("anthropic", "any-model", 250_000, 100_000)
        assert result == pytest.approx(2.25)

    def test_zero_tokens_is_zero_cost(self, pc, monkeypatch):
        """0 input + 0 output -> 0.0 (not None: cost info IS available)."""
        self._pin_cost(pc, monkeypatch)
        assert pc.calculate_cost("anthropic", "any-model", 0, 0) == 0.0

    def test_no_cost_info_returns_none(self, pc, monkeypatch):
        """The `if not model_cost: return None` early-out branch.

        When get_model_cost yields None (unknown provider/model), the
        function must return None — NOT crash, and NOT silently report
        0.0 (which would understate cost in benchmark tables).
        """
        monkeypatch.setattr(pc, "get_model_cost", lambda provider, model: None)
        assert pc.calculate_cost("nope", "nope", 1_000_000, 1_000_000) is None


# ---------------------------------------------------------------------------
# get_model_cost lookup semantics
# ---------------------------------------------------------------------------
class TestGetModelCostLookup:
    """Pin the lookup table: exact hit, prefix-match branch, provider
    lower-casing, and the two None paths (unknown provider / model).

    We seed ``_COST_CACHE`` directly so the lookup is deterministic and
    independent of the YAML catalog on disk.
    """

    def _seed(self, pc):
        """Install a known two-provider cost cache.

        anthropic:
          "claude-3-5-sonnet" -> ModelCost(3, 15)   # short key (prefix source)
          "claude-opus-4"     -> ModelCost(15, 75)
        openai:
          "gpt-4o"            -> ModelCost(2.5, 10)
        """
        pc._COST_CACHE = {
            "anthropic": {
                "claude-3-5-sonnet": pc.ModelCost(input=3.0, output=15.0),
                "claude-opus-4": pc.ModelCost(input=15.0, output=75.0),
            },
            "openai": {
                "gpt-4o": pc.ModelCost(input=2.5, output=10.0),
            },
        }

    def test_exact_model_name_hit(self, pc):
        """Exact key match returns that provider's ModelCost verbatim."""
        self._seed(pc)
        cost = pc.get_model_cost("anthropic", "claude-opus-4")
        assert cost.input == 15.0
        assert cost.output == 75.0

    def test_prefix_match_for_snapshot_suffix(self, pc):
        """The prefix-match loop (source ~379-381):

            for key, cost in provider_costs.items():
                if model_lower.startswith(key.lower()):
                    return cost

        Requested "claude-3-5-sonnet-20241022" is NOT an exact key, but it
        startswith the catalog key "claude-3-5-sonnet", so the loop returns
        that ModelCost(3, 15). This is how dated API snapshots resolve to
        their base price entry.
        """
        self._seed(pc)
        cost = pc.get_model_cost("anthropic", "claude-3-5-sonnet-20241022")
        assert cost is not None
        assert cost.input == 3.0
        assert cost.output == 15.0

    def test_prefix_match_direction_request_startswith_key(self, pc):
        """Pin the prefix DIRECTION: it is request.startswith(key), not
        key.startswith(request).

        The catalog key "claude-opus-4" is itself a prefix of a longer
        requested name "claude-opus-4-1-20250805", so that resolves. But a
        request SHORTER than every key ("claude-op") must NOT match
        "claude-opus-4" — the request does not start with the key — so it
        falls through to None. A reversed-direction mutation would wrongly
        return ModelCost(15, 75) here.
        """
        self._seed(pc)
        assert pc.get_model_cost("anthropic", "claude-opus-4-1-20250805").input == 15.0
        assert pc.get_model_cost("anthropic", "claude-op") is None

    def test_provider_is_lowercased(self, pc):
        """Lookup lower-cases the provider: get_model_cost uses
        ``_COST_CACHE.get(provider.lower())``. A mixed-case "Anthropic"
        must resolve to the "anthropic" cache entry.
        """
        self._seed(pc)
        cost = pc.get_model_cost("Anthropic", "claude-opus-4")
        assert cost is not None
        assert cost.input == 15.0

    def test_unknown_provider_returns_none(self, pc):
        """Provider absent from the cache -> the `if not provider_costs:
        return None` branch, never an exception."""
        self._seed(pc)
        assert pc.get_model_cost("no-such-provider", "claude-opus-4") is None

    def test_unknown_model_returns_none(self, pc):
        """Known provider, model that is neither an exact key nor a prefix
        of any key -> falls through the loop to the final `return None`."""
        self._seed(pc)
        assert pc.get_model_cost("anthropic", "totally-unknown-model") is None

    def test_prefix_match_does_not_cross_providers(self, pc):
        """The prefix loop only scans the *requested* provider's dict. An
        OpenAI model name must not borrow an Anthropic prefix entry: it
        scans only openai's keys, finds no match, returns None.
        """
        self._seed(pc)
        assert pc.get_model_cost("openai", "claude-3-5-sonnet-x") is None


# ---------------------------------------------------------------------------
# _load_costs_from_catalog mapping
# ---------------------------------------------------------------------------
class TestLoadCostsFromCatalog:
    """Pin the catalog->ModelCost mapping:

      * input  <- input_cost_per_million   (NOT swapped with output)
      * output <- output_cost_per_million
      * a row missing EITHER cost is skipped (the
        `if ... is None: continue` guard at source ~277)
      * provider key is lower-cased

    ``_load_costs_from_catalog`` does ``from seeds.llm_models_loader
    import load_catalog`` lazily inside the function. We inject a fake
    ``seeds.llm_models_loader`` module so the test needs no real YAML on
    the import path and the model list is fully controlled.
    """

    def _install_fake_catalog(self, monkeypatch, models):
        loader_mod = types.ModuleType("seeds.llm_models_loader")

        class _Result:
            def __init__(self, models):
                self.models = models

        loader_mod.load_catalog = lambda: _Result(models)

        # Provide a minimal `seeds` parent package too, in case it is not
        # already importable in this environment.
        seeds_pkg = sys.modules.get("seeds")
        if seeds_pkg is None:
            seeds_pkg = types.ModuleType("seeds")
            seeds_pkg.__path__ = []  # mark as package
            monkeypatch.setitem(sys.modules, "seeds", seeds_pkg)
        monkeypatch.setitem(sys.modules, "seeds.llm_models_loader", loader_mod)

    def test_mapping_is_not_swapped(self, pc, monkeypatch):
        """A model with input=3, output=15 maps to ModelCost(input=3,
        output=15). If the mapping swapped the two columns the assertion
        on .input would see 15, failing — this is the test that catches a
        column swap at the catalog boundary (calculate_cost can't, because
        it trusts whatever ModelCost it is handed).
        """
        self._install_fake_catalog(
            monkeypatch,
            [
                {
                    "id": "claude-opus-4",
                    "provider": "Anthropic",  # mixed case on purpose
                    "input_cost_per_million": 3.0,
                    "output_cost_per_million": 15.0,
                }
            ],
        )
        by_provider = pc._load_costs_from_catalog()
        # provider key is lower-cased
        assert "anthropic" in by_provider
        cost = by_provider["anthropic"]["claude-opus-4"]
        assert cost.input == 3.0
        assert cost.output == 15.0

    def test_rows_missing_input_cost_are_skipped(self, pc, monkeypatch):
        """A row with output_cost_per_million but no input_cost_per_million
        is dropped (the `is None: continue` guard), so it never produces a
        half-populated ModelCost that would later compute a wrong total.
        """
        self._install_fake_catalog(
            monkeypatch,
            [
                {
                    "id": "missing-input",
                    "provider": "openai",
                    "input_cost_per_million": None,
                    "output_cost_per_million": 10.0,
                },
                {
                    "id": "complete",
                    "provider": "openai",
                    "input_cost_per_million": 2.5,
                    "output_cost_per_million": 10.0,
                },
            ],
        )
        by_provider = pc._load_costs_from_catalog()
        assert "missing-input" not in by_provider.get("openai", {})
        assert by_provider["openai"]["complete"].input == 2.5

    def test_rows_missing_output_cost_are_skipped(self, pc, monkeypatch):
        """Symmetric to the above: a row with input but no output cost is
        also dropped."""
        self._install_fake_catalog(
            monkeypatch,
            [
                {
                    "id": "missing-output",
                    "provider": "openai",
                    "input_cost_per_million": 2.5,
                    "output_cost_per_million": None,
                },
            ],
        )
        by_provider = pc._load_costs_from_catalog()
        assert "missing-output" not in by_provider.get("openai", {})

    def test_load_then_lookup_end_to_end(self, pc, monkeypatch):
        """Full path: _load_costs_from_catalog feeds get_model_cost which
        feeds calculate_cost, with no monkeypatched seam.

        Catalog: gpt-4o @ input $2/M, output $8/M.
        Request: 1_000_000 input + 1_000_000 output.
          input_cost  = 1 * 2 = 2.0
          output_cost = 1 * 8 = 8.0
          total              = 10.0
        Proves the column mapping and the arithmetic agree end-to-end.
        """
        self._install_fake_catalog(
            monkeypatch,
            [
                {
                    "id": "gpt-4o",
                    "provider": "openai",
                    "input_cost_per_million": 2.0,
                    "output_cost_per_million": 8.0,
                }
            ],
        )
        # Drive the real cache-population path inside get_model_cost.
        pc._COST_CACHE = None
        assert pc.calculate_cost("openai", "gpt-4o", 1_000_000, 1_000_000) == 10.0

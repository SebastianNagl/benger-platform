"""Tests for the worker's tiered parameter resolution helper.

`_resolve_param` is the single source of truth for the precedence chain
that picks per-call values for temperature/max_tokens/seed/top_p:

    prompt_metadata > user_per_model > user_project > recommended[mode]
                    > recommended[default] > SYSTEM_DEFAULTS

Constraint clamping (parameter_constraints.required_value, min/max) is
applied by callers AFTER this helper; it's a guardrail, not a tier.
"""

import pytest

from tasks import SYSTEM_DEFAULTS, _clamp_temperature_to_constraint, _resolve_param


# ─── Recommended-only resolution ─────────────────────────────────────────
def test_recommended_default_block_used_when_no_user_value():
    rec = {"default": {"temperature": 0.7}}
    value, source, rec_at_trigger = _resolve_param(
        "temperature", "generation", rec, project_cfg=None, per_model_cfg=None
    )
    assert (value, source) == (0.7, "recommended")
    assert rec_at_trigger == 0.7


def test_recommended_mode_block_overrides_default_block():
    rec = {"default": {"temperature": 0.7}, "evaluation": {"temperature": 0.0}}
    value, source, rec_at_trigger = _resolve_param(
        "temperature", "evaluation", rec, project_cfg=None, per_model_cfg=None
    )
    assert (value, source) == (0.0, "recommended")
    # rec_at_trigger reflects the mode-specific recommendation
    assert rec_at_trigger == 0.0


def test_recommended_default_used_when_mode_block_lacks_key():
    rec = {"default": {"max_tokens": 4000}, "evaluation": {"temperature": 0.0}}
    value, source, _ = _resolve_param(
        "max_tokens", "evaluation", rec, project_cfg=None, per_model_cfg=None
    )
    assert (value, source) == (4000, "recommended")


# ─── User overrides ───────────────────────────────────────────────────────
def test_user_project_overrides_recommended():
    rec = {"default": {"temperature": 0.7}}
    value, source, rec_at_trigger = _resolve_param(
        "temperature",
        "generation",
        rec,
        project_cfg={"temperature": 0.3},
        per_model_cfg=None,
    )
    assert (value, source, rec_at_trigger) == (0.3, "user_project", 0.7)


def test_per_model_overrides_project():
    rec = {"default": {"temperature": 0.7}}
    value, source, _ = _resolve_param(
        "temperature",
        "generation",
        rec,
        project_cfg={"temperature": 0.3},
        per_model_cfg={"temperature": 0.9},
    )
    assert (value, source) == (0.9, "user_per_model")


def test_prompt_metadata_overrides_per_model():
    rec = {"default": {"temperature": 0.7}}
    value, source, _ = _resolve_param(
        "temperature",
        "generation",
        rec,
        project_cfg={"temperature": 0.3},
        per_model_cfg={"temperature": 0.9},
        prompt_meta={"temperature": 1.2},
    )
    assert (value, source) == (1.2, "prompt_metadata")


# ─── System fallback ──────────────────────────────────────────────────────
def test_system_default_when_no_recommendation_or_user_value():
    value, source, rec_at_trigger = _resolve_param(
        "temperature",
        "generation",
        model_recommended=None,
        project_cfg=None,
        per_model_cfg=None,
    )
    assert (value, source, rec_at_trigger) == (
        SYSTEM_DEFAULTS["temperature"],
        "system",
        None,
    )


def test_system_default_when_recommendation_lacks_key():
    rec = {"default": {"temperature": 0.7}}  # no max_tokens
    value, source, rec_at_trigger = _resolve_param(
        "max_tokens", "generation", rec, project_cfg=None, per_model_cfg=None
    )
    assert (value, source, rec_at_trigger) == (
        SYSTEM_DEFAULTS["max_tokens"],
        "system",
        None,
    )


def test_unknown_key_returns_none_from_system_defaults():
    """SYSTEM_DEFAULTS only knows a small set; unrecognised keys fall through to None."""
    value, source, rec_at_trigger = _resolve_param(
        "frequency_penalty",
        "generation",
        model_recommended=None,
        project_cfg=None,
        per_model_cfg=None,
    )
    assert value is None
    assert source == "system"
    assert rec_at_trigger is None


# ─── Recommended-at-trigger semantics across all tiers ────────────────────
def test_recommended_at_trigger_persists_even_when_user_overrides():
    """The recommended value is captured at trigger time even if a user
    override wins, so analysts can later spot the deviation."""
    rec = {"default": {"temperature": 0.7}, "evaluation": {"temperature": 0.0}}
    _, _, rec_at_trigger = _resolve_param(
        "temperature",
        "evaluation",
        rec,
        project_cfg={"temperature": 0.5},
        per_model_cfg=None,
    )
    assert rec_at_trigger == 0.0  # evaluation block, not user value


def test_falsy_user_value_still_wins_over_recommendation():
    """A user-set 0.0 is a deliberate override, not "missing" — must beat
    the recommended 0.7."""
    rec = {"default": {"temperature": 0.7}}
    value, source, rec_at_trigger = _resolve_param(
        "temperature",
        "generation",
        rec,
        project_cfg={"temperature": 0.0},
        per_model_cfg=None,
    )
    assert (value, source, rec_at_trigger) == (0.0, "user_project", 0.7)


# ─── Mode plumbing ────────────────────────────────────────────────────────
@pytest.mark.parametrize("mode", ["generation", "evaluation"])
def test_default_block_applies_to_either_mode_when_no_mode_specific(mode):
    rec = {"default": {"temperature": 0.5}}
    value, source, _ = _resolve_param(
        "temperature", mode, rec, project_cfg=None, per_model_cfg=None
    )
    assert (value, source) == (0.5, "recommended")


def test_generation_block_isolated_from_evaluation_block():
    rec = {
        "default": {"temperature": 0.7},
        "generation": {"temperature": 0.9},
        "evaluation": {"temperature": 0.0},
    }
    gen_val = _resolve_param(
        "temperature", "generation", rec, project_cfg=None, per_model_cfg=None
    )[0]
    eval_val = _resolve_param(
        "temperature", "evaluation", rec, project_cfg=None, per_model_cfg=None
    )[0]
    assert (gen_val, eval_val) == (0.9, 0.0)


# ─── _clamp_temperature_to_constraint ─────────────────────────────────────
class TestClampTemperatureToConstraint:
    """Hard-constraint enforcement that runs AFTER tier resolution. Used by
    both generation and judge pipelines so they enforce identical rules."""

    def test_no_constraints_returns_value_unchanged(self):
        assert _clamp_temperature_to_constraint(0.5, None) == (0.5, None)
        assert _clamp_temperature_to_constraint(0.5, {}) == (0.5, None)

    def test_required_value_coerces_to_target(self):
        # Mirrors GPT-5 / o-series / Opus-4.7: temperature.supported=False
        # + required_value=1.0 → coerce, record clamped_from for audit.
        constraints = {"temperature": {"supported": False, "required_value": 1.0}}
        value, clamped_from = _clamp_temperature_to_constraint(0.0, constraints)
        assert value == 1.0
        assert clamped_from == 0.0

    def test_required_value_no_op_when_already_matches(self):
        constraints = {"temperature": {"supported": False, "required_value": 1.0}}
        value, clamped_from = _clamp_temperature_to_constraint(1.0, constraints)
        assert value == 1.0
        assert clamped_from is None

    def test_supported_false_without_required_value_passes_through(self):
        # Edge case: poorly-defined constraint. Don't crash, just don't clamp.
        constraints = {"temperature": {"supported": False}}
        value, clamped_from = _clamp_temperature_to_constraint(0.0, constraints)
        assert value == 0.0
        assert clamped_from is None

    def test_min_clamp(self):
        # DeepSeek-R1 / Qwen-Thinking: min 0.6 prevents endless repetitions.
        constraints = {"temperature": {"supported": True, "min": 0.6, "max": 2.0}}
        value, clamped_from = _clamp_temperature_to_constraint(0.0, constraints)
        assert value == 0.6
        assert clamped_from == 0.0

    def test_max_clamp(self):
        constraints = {"temperature": {"supported": True, "min": 0.0, "max": 1.0}}
        value, clamped_from = _clamp_temperature_to_constraint(1.5, constraints)
        assert value == 1.0
        assert clamped_from == 1.5

    def test_in_range_no_op(self):
        constraints = {"temperature": {"supported": True, "min": 0.0, "max": 2.0}}
        value, clamped_from = _clamp_temperature_to_constraint(0.7, constraints)
        assert value == 0.7
        assert clamped_from is None

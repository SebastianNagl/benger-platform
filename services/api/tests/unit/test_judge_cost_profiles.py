"""Registry of extension-provided judge cost profiles (judge_cost_profiles)."""

import pytest

import judge_cost_profiles as jcp

METRIC = "llm_judge_test_profile"


@pytest.fixture(autouse=True)
def _clean():
    yield
    jcp.unregister_judge_cost_profile(METRIC)


def test_unregistered_metric_has_no_profile():
    assert not jcp.has_judge_cost_profile(METRIC)
    assert jcp.judge_cost_profile(METRIC, task_data={}, prediction="x", metric_parameters={}) is None
    assert not jcp.has_judge_cost_profile(None)


def test_profile_receives_inputs_and_normalises_numbers():
    seen = []

    def profile(data, pred, params):
        seen.append((data, pred, params))
        return {"prompt": "P", "overhead_tokens": "90", "output_tokens": 3500}

    jcp.register_judge_cost_profile(METRIC, profile)
    result = jcp.judge_cost_profile(
        METRIC, task_data={"a": 1}, prediction=None, metric_parameters=None
    )
    assert result == jcp.JudgeCallProfile(prompt="P", overhead_tokens=90.0, output_tokens=3500.0)
    assert seen == [({"a": 1}, "", {})]


@pytest.mark.parametrize(
    "answer",
    [None, {"overhead_tokens": 5}, {"prompt": 42}, "a string"],
)
def test_profile_without_prompt_means_generic_sizing(answer):
    jcp.register_judge_cost_profile(METRIC, lambda d, p, m: answer)
    assert jcp.judge_cost_profile(METRIC, task_data={}, prediction="", metric_parameters={}) is None


def test_invalid_numbers_fall_back_to_defaults():
    jcp.register_judge_cost_profile(
        METRIC, lambda d, p, m: {"prompt": "P", "overhead_tokens": -1, "output_tokens": "lots"}
    )
    result = jcp.judge_cost_profile(METRIC, task_data={}, prediction="", metric_parameters={})
    assert result.overhead_tokens is None and result.output_tokens is None


def test_raising_profile_is_contained(caplog):
    def broken(d, p, m):
        raise RuntimeError("boom")

    jcp.register_judge_cost_profile(METRIC, broken)
    assert jcp.judge_cost_profile(METRIC, task_data={}, prediction="", metric_parameters={}) is None
    assert "judge cost profile" in caplog.text


def test_profile_of_inactive_package_is_ignored(monkeypatch):
    jcp.register_judge_cost_profile(METRIC, lambda d, p, m: {"prompt": "P"})
    monkeypatch.setitem(jcp._OWNERS, METRIC, "benger_extended")
    import extension_activation

    monkeypatch.setattr(extension_activation, "package_active", lambda name, *a, **k: False)
    assert not jcp.has_judge_cost_profile(METRIC)
    assert jcp.judge_cost_profile(METRIC, task_data={}, prediction="", metric_parameters={}) is None

    monkeypatch.setattr(extension_activation, "package_active", lambda name, *a, **k: True)
    assert jcp.judge_cost_profile(METRIC, task_data={}, prediction="", metric_parameters={}).prompt == "P"

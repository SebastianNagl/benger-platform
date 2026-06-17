"""Unit tests for services/token_estimation.py.

This module previously had no test coverage. Token estimation backs the
multi-run cost-preview endpoint: it tokenizes sampled prompt strings with
``tiktoken`` (falling back to a chars/4 heuristic when unavailable), caches
results per ``(project_id, model_id, prompt_hash)`` for an hour, and exposes
two DB-backed samplers that pull representative prediction / task texts.

Targets (behavioural, real-output assertions only):

- ``TokenEstimate.to_dict``: rounding + key shape.
- ``_encoding_for_model``: OpenAI direct map, non-OpenAI cl100k_base fallback.
- ``_hash_prompt``: deterministic 16-char sha256 prefix.
- ``_percentile``: empty list, single value, p0/p50/p95/p100 index math.
- ``estimate_tokens_for_calls``: real-tiktoken path (mean/p95/output/sample),
  empty-samples guard, output-utilization scaling, and the cache hit/miss
  branches (second call with identical args returns the cached object).
- ``sample_prediction_inputs``: pulls completed generations, cold-start
  fallback to task texts, deterministic seeded sampling, unseeded head slice.
- ``sample_task_texts``: empty project, dict/str/non-str ``data`` flattening,
  seeded vs unseeded selection.
"""

import uuid

import pytest

from services import token_estimation as te
from services.token_estimation import (
    TokenEstimate,
    _encoding_for_model,
    _hash_prompt,
    _percentile,
    estimate_tokens_for_calls,
    sample_prediction_inputs,
    sample_task_texts,
)

from models import Generation
from project_models import Project, Task


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts with an empty process-local cache so cache-hit
    assertions are deterministic and isolated."""
    te._CACHE.clear()
    yield
    te._CACHE.clear()


# ---------------------------------------------------------------------------
# TokenEstimate.to_dict
# ---------------------------------------------------------------------------


class TestTokenEstimateToDict:
    def test_to_dict_rounds_floats_to_one_decimal(self):
        est = TokenEstimate(
            input_mean=12.345,
            input_p95=99.987,
            output_estimate=60.04,
            sample_size=7,
            encoding_name="cl100k_base",
            cached_at=123.0,
        )
        d = est.to_dict()
        assert d == {
            "input_mean": 12.3,
            "input_p95": 100.0,
            "output_estimate": 60.0,
            "sample_size": 7,
            "encoding": "cl100k_base",
        }
        # cached_at is intentionally not surfaced in the dict.
        assert "cached_at" not in d


# ---------------------------------------------------------------------------
# _encoding_for_model
# ---------------------------------------------------------------------------


class TestEncodingForModel:
    def test_openai_model_maps_directly(self):
        enc = _encoding_for_model("gpt-4")
        assert enc is not None
        # gpt-4 uses cl100k_base under tiktoken.
        assert enc.name == "cl100k_base"

    def test_unknown_model_falls_back_to_cl100k(self):
        enc = _encoding_for_model("some-random-non-openai-model-xyz")
        assert enc is not None
        assert enc.name == "cl100k_base"

    def test_no_tiktoken_returns_none(self, monkeypatch):
        monkeypatch.setattr(te, "TIKTOKEN_AVAILABLE", False)
        assert _encoding_for_model("gpt-4") is None


# ---------------------------------------------------------------------------
# _hash_prompt
# ---------------------------------------------------------------------------


class TestHashPrompt:
    def test_deterministic_16_char_hex(self):
        h1 = _hash_prompt("hello world")
        h2 = _hash_prompt("hello world")
        assert h1 == h2
        assert len(h1) == 16
        assert all(c in "0123456789abcdef" for c in h1)

    def test_different_inputs_differ(self):
        assert _hash_prompt("a") != _hash_prompt("b")


# ---------------------------------------------------------------------------
# _percentile
# ---------------------------------------------------------------------------


class TestPercentile:
    def test_empty_returns_zero(self):
        assert _percentile([], 95) == 0.0

    def test_single_value(self):
        assert _percentile([42.0], 95) == 42.0

    def test_p0_is_min(self):
        assert _percentile([3.0, 1.0, 2.0], 0) == 1.0

    def test_p100_is_max(self):
        assert _percentile([3.0, 1.0, 2.0], 100) == 3.0

    def test_p50_midpoint(self):
        # 5 values, p50 -> index round(0.5 * 4) = 2 -> third smallest.
        assert _percentile([10.0, 20.0, 30.0, 40.0, 50.0], 50) == 30.0

    def test_p95_high_index(self):
        vals = [float(i) for i in range(1, 11)]  # 1..10
        # index = round(0.95 * 9) = round(8.55) = 9 -> last element (10.0)
        assert _percentile(vals, 95) == 10.0


# ---------------------------------------------------------------------------
# estimate_tokens_for_calls
# ---------------------------------------------------------------------------


class TestEstimateTokensForCalls:
    def test_basic_estimate_real_tiktoken(self):
        est = estimate_tokens_for_calls(
            project_id="p1",
            model_id="gpt-4",
            prompt_samples=["hello world", "the quick brown fox jumps"],
            max_output_tokens=1000,
        )
        assert isinstance(est, TokenEstimate)
        assert est.sample_size == 2
        assert est.input_mean > 0
        assert est.input_p95 >= est.input_mean
        # default output utilization is 0.6
        assert est.output_estimate == pytest.approx(600.0)
        assert est.encoding_name == "cl100k_base"

    def test_output_utilization_scales(self):
        est = estimate_tokens_for_calls(
            project_id="p1",
            model_id="gpt-4",
            prompt_samples=["abc"],
            max_output_tokens=2000,
            output_utilization=0.25,
        )
        assert est.output_estimate == pytest.approx(500.0)

    def test_empty_samples_guard(self):
        est = estimate_tokens_for_calls(
            project_id="p1",
            model_id="gpt-4",
            prompt_samples=[],
            max_output_tokens=100,
        )
        assert est.sample_size == 0
        # With no samples token_lengths falls back to [0.0] -> mean 0.
        assert est.input_mean == 0.0
        assert est.input_p95 == 0.0
        assert est.output_estimate == pytest.approx(60.0)

    def test_cache_hit_returns_same_object(self):
        kwargs = dict(
            project_id="proj-cache",
            model_id="gpt-4",
            prompt_samples=["same prompt text"],
            max_output_tokens=500,
        )
        first = estimate_tokens_for_calls(**kwargs)
        second = estimate_tokens_for_calls(**kwargs)
        # Identical inputs -> cache hit -> exact same cached instance.
        assert second is first

    def test_cache_miss_on_different_prompts(self):
        first = estimate_tokens_for_calls(
            project_id="proj",
            model_id="gpt-4",
            prompt_samples=["prompt one"],
            max_output_tokens=500,
        )
        second = estimate_tokens_for_calls(
            project_id="proj",
            model_id="gpt-4",
            prompt_samples=["prompt two different"],
            max_output_tokens=500,
        )
        assert second is not first

    def test_no_tiktoken_chars_over_4_fallback(self, monkeypatch):
        monkeypatch.setattr(te, "TIKTOKEN_AVAILABLE", False)
        # "12345678" -> 8 chars -> 8/4 = 2.0 tokens
        est = estimate_tokens_for_calls(
            project_id="p-no-tk",
            model_id="gpt-4",
            prompt_samples=["12345678"],
            max_output_tokens=100,
        )
        assert est.encoding_name == "chars/4 (no tiktoken)"
        assert est.input_mean == pytest.approx(2.0)

    def test_no_tiktoken_empty_samples(self, monkeypatch):
        monkeypatch.setattr(te, "TIKTOKEN_AVAILABLE", False)
        est = estimate_tokens_for_calls(
            project_id="p-no-tk-empty",
            model_id="gpt-4",
            prompt_samples=[],
            max_output_tokens=100,
        )
        assert est.encoding_name == "chars/4 (no tiktoken)"
        assert est.input_mean == 0.0
        assert est.sample_size == 0


# ---------------------------------------------------------------------------
# sample_task_texts  (DB-backed)
# ---------------------------------------------------------------------------


def _make_project(test_db, user_id):
    project = Project(
        id=_uid(),
        title="Token Est Project",
        label_config='<View><Text name="t" value="$text"/></View>',
        created_by=user_id,
    )
    test_db.add(project)
    test_db.flush()
    return project


def _make_task(test_db, project_id, user_id, inner_id, data):
    task = Task(
        id=_uid(),
        project_id=project_id,
        inner_id=inner_id,
        data=data,
        created_by=user_id,
        updated_by=user_id,
    )
    test_db.add(task)
    return task


@pytest.mark.integration
class TestSampleTaskTexts:
    def test_empty_project_returns_empty(self, test_db, test_users):
        project = _make_project(test_db, test_users[0].id)
        test_db.commit()
        assert sample_task_texts(db=test_db, project_id=project.id) == []

    def test_dict_data_flattened_to_string(self, test_db, test_users):
        project = _make_project(test_db, test_users[0].id)
        _make_task(
            test_db, project.id, test_users[0].id, 1,
            {"sachverhalt": "Ein Fall", "frage": "Was gilt?"},
        )
        test_db.commit()
        texts = sample_task_texts(db=test_db, project_id=project.id)
        assert len(texts) == 1
        # Both string values are joined with newline.
        assert "Ein Fall" in texts[0]
        assert "Was gilt?" in texts[0]
        assert "\n" in texts[0]

    def test_dict_with_non_string_value_stringified(self, test_db, test_users):
        project = _make_project(test_db, test_users[0].id)
        _make_task(
            test_db, project.id, test_users[0].id, 1,
            {"count": 7, "label": "ok"},
        )
        test_db.commit()
        texts = sample_task_texts(db=test_db, project_id=project.id)
        assert len(texts) == 1
        assert "7" in texts[0]
        assert "ok" in texts[0]

    def test_seeded_is_deterministic(self, test_db, test_users):
        project = _make_project(test_db, test_users[0].id)
        for i in range(20):
            _make_task(
                test_db, project.id, test_users[0].id, i + 1,
                {"text": f"task-text-{i}"},
            )
        test_db.commit()
        a = sample_task_texts(db=test_db, project_id=project.id, sample_size=5, seed=123)
        b = sample_task_texts(db=test_db, project_id=project.id, sample_size=5, seed=123)
        assert len(a) == 5
        # Same seed + same source ordering (ORDER BY id) -> identical selection.
        assert sorted(a) == sorted(b)

    def test_unseeded_takes_head_slice(self, test_db, test_users):
        project = _make_project(test_db, test_users[0].id)
        for i in range(8):
            _make_task(
                test_db, project.id, test_users[0].id, i + 1,
                {"text": f"text-{i}"},
            )
        test_db.commit()
        texts = sample_task_texts(db=test_db, project_id=project.id, sample_size=3)
        assert len(texts) == 3


# ---------------------------------------------------------------------------
# sample_prediction_inputs  (DB-backed)
# ---------------------------------------------------------------------------


def _make_generation(test_db, task_id, content, status="completed"):
    # Generation.generation_id is a NOT NULL FK to response_generations.id —
    # create the parent job first (mirrors the passing cost_estimate seed).
    from models import ResponseGeneration

    task = test_db.query(Task).filter(Task.id == task_id).first()
    project = test_db.query(Project).filter(Project.id == task.project_id).first()
    parent = ResponseGeneration(
        id=_uid(),
        project_id=task.project_id,
        task_id=task_id,
        model_id="gpt-4",
        status=status,
        created_by=project.created_by,
    )
    test_db.add(parent)
    test_db.flush()
    gen = Generation(
        id=_uid(),
        generation_id=parent.id,
        task_id=task_id,
        model_id="gpt-4",
        case_data="case",
        response_content=content,
        status=status,
    )
    test_db.add(gen)
    return gen


@pytest.mark.integration
class TestSamplePredictionInputs:
    def test_pulls_completed_generation_responses(self, test_db, test_users):
        project = _make_project(test_db, test_users[0].id)
        task = _make_task(
            test_db, project.id, test_users[0].id, 1, {"text": "raw task"}
        )
        test_db.flush()
        _make_generation(test_db, task.id, "Gutachten body one")
        test_db.commit()

        texts = sample_prediction_inputs(db=test_db, project_id=project.id)
        assert texts == ["Gutachten body one"]

    def test_cold_start_falls_back_to_task_texts(self, test_db, test_users):
        """No completed generations -> falls back to sample_task_texts."""
        project = _make_project(test_db, test_users[0].id)
        task = _make_task(
            test_db, project.id, test_users[0].id, 1, {"text": "fallback task text"}
        )
        test_db.flush()
        # A *failed* generation must be ignored (status filter).
        _make_generation(test_db, task.id, "should be ignored", status="failed")
        test_db.commit()

        texts = sample_prediction_inputs(db=test_db, project_id=project.id)
        assert texts == ["fallback task text"]

    def test_seeded_sampling_deterministic(self, test_db, test_users):
        project = _make_project(test_db, test_users[0].id)
        task = _make_task(
            test_db, project.id, test_users[0].id, 1, {"text": "t"}
        )
        test_db.flush()
        for i in range(15):
            _make_generation(test_db, task.id, f"prediction-{i}")
        test_db.commit()

        a = sample_prediction_inputs(
            db=test_db, project_id=project.id, sample_size=4, seed=7
        )
        b = sample_prediction_inputs(
            db=test_db, project_id=project.id, sample_size=4, seed=7
        )
        assert len(a) == 4
        # Identical seed against the same committed rows -> identical selection.
        # (Compared order-insensitively to stay robust against created_at ties
        # in the underlying ORDER BY created_at DESC fetch.)
        assert sorted(a) == sorted(b)

    def test_unseeded_returns_head_slice(self, test_db, test_users):
        project = _make_project(test_db, test_users[0].id)
        task = _make_task(
            test_db, project.id, test_users[0].id, 1, {"text": "t"}
        )
        test_db.flush()
        for i in range(6):
            _make_generation(test_db, task.id, f"pred-{i}")
        test_db.commit()

        texts = sample_prediction_inputs(
            db=test_db, project_id=project.id, sample_size=3
        )
        assert len(texts) == 3

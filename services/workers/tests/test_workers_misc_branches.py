"""Branch-coverage tests for several low-coverage worker helper modules.

Bundles the remaining testable, behavioral gaps in four modules whose own
dedicated suites left specific branches uncovered:

  * ml_evaluation/utils.py
        - load_task_data_from_label_studio: the httpx success path (dict-with-
          'results' and bare-list response shapes) and the exception -> [] path,
          all with httpx.Client fully mocked (no network).
        - extract_task_type_from_label_config: the exception branch (None input
          -> AttributeError caught -> None).
        - EvaluationTimer: __enter__/__exit__ success and failure paths +
          duration_seconds before/after completion.

  * ml_evaluation/registry.py
        - get_supported_metrics / validate_evaluator_compatibility inner
          try/except: an evaluator that *instantiates* fine but whose method
          raises (distinct from the existing BrokenEvaluator that raises in
          __init__).

  * model_parameter_config.py
        - the 'LOW' reproducibility-impact + temperature>0 -> MEDIUM downgrade.

  * database.py (the ~20%-covered module)
        - _upsert_llm_model insert / update-changed / update-unchanged branches,
        - initialize_task_types_and_evaluation_types insert + update branches,
        - initialize_llm_models bulk insert,
        - get_db generator lifecycle, init_db.
    All driven with a MagicMock Session and a stub `models` module injected into
    sys.modules at call time (database.py imports models lazily inside each
    function), so NO real Postgres / SQLAlchemy model metadata is needed.

Everything is behavioral: crafted inputs -> assert returned values / side
effects. Mirrors test_ml_evaluation_utils_coverage.py and
test_registry_coverage.py idioms.
"""

import os
import sys
import time
import types
from unittest.mock import MagicMock, patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.utils import (  # noqa: E402
    EvaluationTimer,
    extract_task_type_from_label_config,
    load_task_data_from_label_studio,
)
from ml_evaluation.registry import EvaluatorRegistry  # noqa: E402
from ml_evaluation.base_evaluator import BaseEvaluator, EvaluationResult  # noqa: E402
from model_parameter_config import get_model_generation_params  # noqa: E402


# ============================================================================
# utils.load_task_data_from_label_studio
# ============================================================================


def _mock_httpx_client(response):
    """Build a context-manager httpx.Client mock returning `response`."""
    client = MagicMock()
    client.get.return_value = response
    client.__enter__ = lambda self: client
    client.__exit__ = lambda *a: False
    return client


class TestLoadTaskDataFromLabelStudio:
    def test_dict_results_shape(self):
        resp = MagicMock()
        resp.json.return_value = {"results": [{"id": 1}, {"id": 2}]}
        resp.raise_for_status.return_value = None
        client = _mock_httpx_client(resp)
        with patch("ml_evaluation.utils.httpx.Client", return_value=client):
            tasks = load_task_data_from_label_studio(7, "http://ls", "key")
        assert tasks == [{"id": 1}, {"id": 2}]
        # Auth header + include params were sent
        _, kwargs = client.get.call_args
        assert kwargs["headers"]["Authorization"] == "Token key"
        assert "annotations" in kwargs["params"]["include"]

    def test_bare_list_response(self):
        resp = MagicMock()
        resp.json.return_value = [{"id": 5}]
        resp.raise_for_status.return_value = None
        client = _mock_httpx_client(resp)
        with patch("ml_evaluation.utils.httpx.Client", return_value=client):
            tasks = load_task_data_from_label_studio(7, "http://ls", "key")
        assert tasks == [{"id": 5}]

    def test_exception_returns_empty_list(self):
        client = MagicMock()
        client.get.side_effect = RuntimeError("network down")
        client.__enter__ = lambda self: client
        client.__exit__ = lambda *a: False
        with patch("ml_evaluation.utils.httpx.Client", return_value=client):
            tasks = load_task_data_from_label_studio(7, "http://ls", "key")
        assert tasks == []


# ============================================================================
# utils.extract_task_type_from_label_config — exception branch
# ============================================================================


class TestExtractTaskTypeException:
    def test_none_input_returns_none(self):
        # None.lower() raises AttributeError -> caught -> None
        assert extract_task_type_from_label_config(None) is None

    def test_non_string_input_returns_none(self):
        assert extract_task_type_from_label_config(12345) is None


# ============================================================================
# utils.EvaluationTimer
# ============================================================================


class TestEvaluationTimer:
    def test_success_path_records_duration(self):
        with EvaluationTimer("op") as t:
            time.sleep(0.001)
        assert t.duration_seconds is not None
        assert t.duration_seconds >= 0.0
        assert t.start_time is not None and t.end_time is not None

    def test_failure_path_still_records_duration(self):
        timer = EvaluationTimer("failing-op")
        with pytest.raises(ValueError):
            with timer:
                raise ValueError("boom")
        # __exit__ ran the error branch but still set end_time
        assert timer.duration_seconds is not None

    def test_duration_none_before_completion(self):
        t = EvaluationTimer()
        assert t.duration_seconds is None
        # Only start
        t.__enter__()
        assert t.duration_seconds is None  # end_time not set yet


# ============================================================================
# registry — inner try/except when an instantiated evaluator's method raises
# ============================================================================


class _MethodsRaiseEvaluator(BaseEvaluator):
    """Instantiates cleanly, but its query methods raise — this is what drives
    the *inner* try/except in get_supported_metrics / validate_*compatibility,
    which the existing BrokenEvaluator (raises in __init__) never reaches."""

    def evaluate(self, model_id, task_data, config):
        return EvaluationResult(metrics={}, metadata={})

    def get_supported_metrics(self):
        raise RuntimeError("metrics exploded")

    def validate_model_config(self, model_config):
        raise RuntimeError("validation exploded")


class TestRegistryMethodExceptionPaths:
    def setup_method(self):
        self.registry = EvaluatorRegistry()
        self.registry.register("raisey", _MethodsRaiseEvaluator)

    def test_get_supported_metrics_swallows_exception(self):
        # Evaluator constructs fine; get_supported_metrics raises -> [] via except
        assert self.registry.get_supported_metrics("raisey") == []

    def test_validate_compatibility_swallows_exception(self):
        # validate_model_config raises -> False via except
        assert self.registry.validate_evaluator_compatibility("raisey", {"model": "x"}) is False


# ============================================================================
# model_parameter_config — LOW-impact + nonzero-temp downgrade to MEDIUM
# ============================================================================


class TestModelParamLowImpactDowngrade:
    def test_low_impact_nonzero_temp_is_medium(self):
        model = MagicMock()
        model.parameter_constraints = {
            "reproducibility_impact": "LOW impact on determinism",
            "temperature": {"supported": True, "default": 0.7},
        }
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = model
        result = get_model_generation_params(db, "m", model_orm_class=MagicMock())
        assert result["temperature"] == 0.7
        # 'LOW' in impact AND temp > 0.0 -> MEDIUM downgrade
        assert result["reproducibility_level"] == "MEDIUM"

    def test_low_impact_zero_temp_stays_high(self):
        """Same LOW impact but temperature 0.0: the downgrade branch's
        temp>0 guard is False, so HIGH is retained."""
        model = MagicMock()
        model.parameter_constraints = {
            "reproducibility_impact": "LOW impact",
            "temperature": {"supported": True, "default": 0.0},
        }
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = model
        result = get_model_generation_params(db, "m", model_orm_class=MagicMock())
        assert result["temperature"] == 0.0
        assert result["reproducibility_level"] == "HIGH"


# ============================================================================
# database.py — upsert / init helpers with a stub `models` module
# ============================================================================


class _StubLLMModel:
    id = None  # class-level attr so `LLMModel.id == x` resolves

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _StubEvaluationType:
    id = None

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture
def stub_models():
    """Inject a fake `models` module (LLMModel / EvaluationType / Base) into
    sys.modules for the duration of a test, restoring the original afterwards.
    database.py imports `models` lazily inside each function, so no reload is
    needed."""
    saved = sys.modules.get("models")
    fake = types.ModuleType("models")
    fake.LLMModel = _StubLLMModel
    fake.EvaluationType = _StubEvaluationType
    fake.Base = MagicMock()
    sys.modules["models"] = fake
    try:
        yield fake
    finally:
        if saved is not None:
            sys.modules["models"] = saved
        else:
            sys.modules.pop("models", None)


@pytest.fixture
def stub_providers():
    """Inject available-by-default provider service modules used by
    initialize_llm_models."""
    names = [
        "anthropic_service",
        "deepinfra_service",
        "google_service",
        "openai_service",
    ]
    saved = {n: sys.modules.get(n) for n in names}
    for n in names:
        mod = types.ModuleType(n)
        svc = MagicMock()
        svc.is_available.return_value = True
        setattr(mod, n, svc)
        sys.modules[n] = mod
    try:
        yield
    finally:
        for n, prev in saved.items():
            if prev is not None:
                sys.modules[n] = prev
            else:
                sys.modules.pop(n, None)


class TestUpsertLLMModel:
    def test_insert_when_absent(self, stub_models):
        import database

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        database._upsert_llm_model(db, {"id": "m1", "name": "M1", "is_active": True})
        assert db.add.called
        added = db.add.call_args[0][0]
        assert isinstance(added, _StubLLMModel)
        assert added.id == "m1"
        assert added.is_active is True

    def test_update_changed_field(self, stub_models):
        import database

        existing = _StubLLMModel(id="m1", name="OLD", is_active=True)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing
        database._upsert_llm_model(db, {"id": "m1", "name": "NEW", "is_active": True})
        # Field mutated in place and the row re-added
        assert existing.name == "NEW"
        assert db.add.called

    def test_update_unchanged_skips_add(self, stub_models):
        import database

        existing = _StubLLMModel(id="m1", name="SAME", is_active=True)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing
        database._upsert_llm_model(db, {"id": "m1", "name": "SAME", "is_active": True})
        # Nothing changed -> not re-added
        assert not db.add.called


class TestInitializeTaskTypesAndEvaluationTypes:
    def test_insert_all_new(self, stub_models):
        import database

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        database.initialize_task_types_and_evaluation_types(db)
        # 7 evaluation types are seeded when none pre-exist
        assert db.add.call_count == 7
        assert db.commit.called
        # Each added object is a stub EvaluationType with an id
        added_ids = {c.args[0].id for c in db.add.call_args_list}
        assert "f1" in added_ids and "exact_match" in added_ids

    def test_update_existing(self, stub_models):
        import database

        # Return a fresh existing row for every lookup so the update branch runs
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = (
            lambda: _StubEvaluationType(id="placeholder", name="old")
        )
        database.initialize_task_types_and_evaluation_types(db)
        # Update branch never inserts
        assert not db.add.called
        assert db.commit.called


class TestInitializeLLMModels:
    def test_bulk_insert(self, stub_models, stub_providers):
        import database

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        database.initialize_llm_models(db)
        # 10 default model definitions are seeded
        assert db.add.call_count == 10
        assert db.commit.called


class TestGetDbAndInitDb:
    def test_get_db_yields_and_closes(self):
        import database

        sentinel = MagicMock()
        with patch.object(database, "SessionLocal", return_value=sentinel):
            gen = database.get_db()
            session = next(gen)
            assert session is sentinel
            # Exhausting the generator runs the finally -> close()
            with pytest.raises(StopIteration):
                next(gen)
            assert sentinel.close.called

    def test_init_db_creates_all(self, stub_models):
        import database

        with patch.object(database, "engine", MagicMock()) as eng:
            database.init_db()
            assert stub_models.Base.metadata.create_all.called
            # create_all bound to the module engine
            _, kwargs = stub_models.Base.metadata.create_all.call_args
            assert kwargs.get("bind") is eng

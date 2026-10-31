"""Branch-coverage tests for several low-coverage worker helper modules.

Bundles the remaining testable, behavioral gaps in two modules whose own
dedicated suites left specific branches uncovered:

  * ml_evaluation/registry.py
        - get_supported_metrics / validate_evaluator_compatibility inner
          try/except: an evaluator that *instantiates* fine but whose method
          raises (distinct from the existing BrokenEvaluator that raises in
          __init__).

  * database.py (the ~20%-covered module)
        - initialize_task_types_and_evaluation_types insert + update branches,
        - get_db generator lifecycle, init_db.
    All driven with a MagicMock Session and a stub `models` module injected into
    sys.modules at call time (database.py imports models lazily inside each
    function), so NO real Postgres / SQLAlchemy model metadata is needed.

Everything is behavioral: crafted inputs -> assert returned values / side
effects. Mirrors the test_registry_coverage.py idioms.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.registry import EvaluatorRegistry  # noqa: E402
from ml_evaluation.base_evaluator import BaseEvaluator, EvaluationResult  # noqa: E402


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
# database.py — init helpers with a stub `models` module
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

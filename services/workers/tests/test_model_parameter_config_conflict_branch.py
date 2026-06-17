"""Residual branch coverage for model_parameter_config.get_model_generation_params.

test_model_parameter_config.py::TestConflictingParams covers the case where a
constraint's ``conflicts_with`` list DOES contain ``"temperature"`` (the param
is omitted). It does not cover the complementary branch: a constraint dict that
carries a ``conflicts_with`` key whose list does NOT mention ``temperature`` —
there the inner ``if 'temperature' in conflicts and ...`` is False, the param is
left in place, and the loop simply moves on. This pins that branch (line ~119
false-edge) behaviorally: the non-temperature-conflicting param must NOT appear
in ``params_omitted`` and must NOT add a warning.

Mirrors the MagicMock-db helpers from test_model_parameter_config.py.
"""

from unittest.mock import MagicMock

from model_parameter_config import get_model_generation_params


def _mock_db_with_constraints(constraints):
    """Mock db session whose model.parameter_constraints == constraints."""
    db = MagicMock()
    model = MagicMock()
    model.parameter_constraints = constraints
    db.query.return_value.filter.return_value.first.return_value = model
    return db


class MockModelORM:
    id = "test-model"


class TestNonTemperatureConflictNotOmitted:
    def test_conflicts_with_other_param_does_not_omit(self):
        """conflicts_with=['top_k'] (no 'temperature') -> inner guard False ->
        the param is kept; nothing omitted, no conflict warning emitted."""
        constraints = {
            "top_p": {
                "conflicts_with": ["top_k"],
                "reason": "top_p and top_k interact",
            }
        }
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)

        assert "top_p" not in result["params_omitted"]
        assert not any("top_p" in w for w in result["warnings"])

    def test_mixed_constraints_only_temperature_conflict_omitted(self):
        """One constraint conflicts with temperature (omitted), another conflicts
        with something else (kept) — exercises both edges of the 119 branch in a
        single dispatch."""
        constraints = {
            "top_p": {"conflicts_with": ["temperature"], "reason": "x"},
            "frequency_penalty": {"conflicts_with": ["presence_penalty"], "reason": "y"},
        }
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)

        assert "top_p" in result["params_omitted"]
        assert "frequency_penalty" not in result["params_omitted"]

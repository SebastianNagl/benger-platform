"""
Unit tests for auth_module/user_service.py internal helpers — 53.64% coverage.

Tests: _validate_psychometric_scale, get_mandatory_profile_fields,
check_confirmation_due, create_profile_snapshot, _check_mandatory_fields_present.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


class TestValidatePsychometricScale:
    """Test _validate_psychometric_scale validation."""

    def test_valid_scale(self):
        from auth_module.user_service import _validate_psychometric_scale
        scale = {"item_1": 3, "item_2": 5, "item_3": 1, "item_4": 7}
        # Should not raise
        _validate_psychometric_scale("ati_s_scores", scale)

    def test_not_a_dict_raises(self):
        from auth_module.user_service import _validate_psychometric_scale
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", "not a dict")
        assert exc_info.value.status_code == 400
        assert "must be a JSON object" in exc_info.value.detail

    def test_wrong_keys_raises(self):
        from auth_module.user_service import _validate_psychometric_scale
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", {"item_1": 3, "item_2": 5})
        assert exc_info.value.status_code == 400
        assert "must have exactly keys" in exc_info.value.detail

    def test_extra_keys_raises(self):
        from auth_module.user_service import _validate_psychometric_scale
        scale = {"item_1": 3, "item_2": 5, "item_3": 1, "item_4": 7, "item_5": 2}
        with pytest.raises(HTTPException):
            _validate_psychometric_scale("ati_s_scores", scale)

    def test_non_integer_value_raises(self):
        from auth_module.user_service import _validate_psychometric_scale
        scale = {"item_1": 3.5, "item_2": 5, "item_3": 1, "item_4": 7}
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", scale)
        assert "must be an integer" in exc_info.value.detail

    def test_boolean_value_raises(self):
        from auth_module.user_service import _validate_psychometric_scale
        scale = {"item_1": True, "item_2": 5, "item_3": 1, "item_4": 7}
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", scale)
        assert "must be an integer" in exc_info.value.detail

    def test_value_below_1_raises(self):
        from auth_module.user_service import _validate_psychometric_scale
        scale = {"item_1": 0, "item_2": 5, "item_3": 1, "item_4": 7}
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", scale)
        assert "must be between 1 and 7" in exc_info.value.detail

    def test_value_above_7_raises(self):
        from auth_module.user_service import _validate_psychometric_scale
        scale = {"item_1": 3, "item_2": 8, "item_3": 1, "item_4": 7}
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", scale)
        assert "must be between 1 and 7" in exc_info.value.detail

    def test_string_value_raises(self):
        from auth_module.user_service import _validate_psychometric_scale
        scale = {"item_1": "three", "item_2": 5, "item_3": 1, "item_4": 7}
        with pytest.raises(HTTPException):
            _validate_psychometric_scale("ati_s_scores", scale)

    def test_boundary_values_valid(self):
        from auth_module.user_service import _validate_psychometric_scale
        scale = {"item_1": 1, "item_2": 7, "item_3": 1, "item_4": 7}
        _validate_psychometric_scale("ptt_a_scores", scale)

    def test_list_input_raises(self):
        from auth_module.user_service import _validate_psychometric_scale
        with pytest.raises(HTTPException):
            _validate_psychometric_scale("ki_experience_scores", [1, 2, 3, 4])


class TestGetMandatoryProfileFields:
    """Test get_mandatory_profile_fields with different expertise levels."""

    def _make_user(self, **kwargs):
        defaults = {
            "legal_expertise_level": None,
            "gender": None,
            "age": None,
            "german_proficiency": None,
            "subjective_competence_civil": None,
            "subjective_competence_public": None,
            "subjective_competence_criminal": None,
            "ati_s_scores": None,
            "ptt_a_scores": None,
            "ki_experience_scores": None,
            "degree_program_type": None,
            "grade_zwischenpruefung": None,
            "grade_vorgeruecktenubung": None,
            "grade_first_staatsexamen": None,
            "grade_second_staatsexamen": None,
            "job": None,
            "years_of_experience": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_all_fields_missing(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user()
        missing = get_mandatory_profile_fields(user)
        assert "legal_expertise_level" in missing
        assert "gender" in missing
        assert "age" in missing
        assert "german_proficiency" in missing
        assert "ati_s_scores" in missing

    def test_all_base_fields_present_no_expertise(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            gender="male", age=25, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        missing = get_mandatory_profile_fields(user)
        assert "legal_expertise_level" in missing
        assert "gender" not in missing

    def test_law_student_needs_grades(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            legal_expertise_level=SimpleNamespace(value="law_student"),
            gender="female", age=22, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" in missing
        assert "grade_vorgeruecktenubung" in missing
        assert "grade_first_staatsexamen" not in missing

    def test_referendar_needs_first_staatsexamen(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            legal_expertise_level=SimpleNamespace(value="referendar"),
            gender="male", age=28, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" in missing
        assert "grade_vorgeruecktenubung" in missing
        assert "grade_first_staatsexamen" in missing

    def test_graduated_needs_second_staatsexamen_and_job(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            legal_expertise_level=SimpleNamespace(value="graduated_no_practice"),
            gender="male", age=30, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_second_staatsexamen" in missing
        assert "job" in missing
        assert "years_of_experience" in missing

    def test_practicing_lawyer_all_needed(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            legal_expertise_level=SimpleNamespace(value="practicing_lawyer"),
            gender="female", age=35, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" in missing
        assert "grade_first_staatsexamen" in missing
        assert "grade_second_staatsexamen" in missing
        assert "job" in missing

    def test_llb_exempt_from_grades(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            legal_expertise_level=SimpleNamespace(value="law_student"),
            degree_program_type=SimpleNamespace(value="llb"),
            gender="male", age=22, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" not in missing
        assert "grade_vorgeruecktenubung" not in missing

    def test_llm_exempt_from_grades(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            legal_expertise_level=SimpleNamespace(value="referendar"),
            degree_program_type=SimpleNamespace(value="llm"),
            gender="female", age=26, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" not in missing
        assert "grade_first_staatsexamen" not in missing

    def test_graduated_llm_no_second_staatsexamen_but_needs_job(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            legal_expertise_level=SimpleNamespace(value="graduated_no_practice"),
            degree_program_type=SimpleNamespace(value="llm"),
            gender="male", age=30, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_second_staatsexamen" not in missing
        assert "job" in missing
        assert "years_of_experience" in missing

    def test_judge_professor_all_needed(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            legal_expertise_level=SimpleNamespace(value="judge_professor"),
            gender="male", age=50, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" in missing
        assert "grade_first_staatsexamen" in missing
        assert "grade_second_staatsexamen" in missing
        assert "job" in missing

    def test_fully_complete_law_student_profile(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            legal_expertise_level=SimpleNamespace(value="law_student"),
            degree_program_type=SimpleNamespace(value="staatsexamen"),
            gender="male", age=22, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
            grade_zwischenpruefung=Decimal("8.5"),
            grade_vorgeruecktenubung=Decimal("9.0"),
        )
        missing = get_mandatory_profile_fields(user)
        assert missing == []

    def test_string_expertise_level(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            legal_expertise_level="law_student",
            gender="male", age=22, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" in missing

    def test_string_degree_type(self):
        from auth_module.user_service import get_mandatory_profile_fields
        user = self._make_user(
            legal_expertise_level=SimpleNamespace(value="law_student"),
            degree_program_type="llb",
            gender="male", age=22, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" not in missing


class TestCheckConfirmationDue:
    """Test check_confirmation_due deadline logic."""

    def test_no_confirmation_ever(self):
        from auth_module.user_service import check_confirmation_due
        user = SimpleNamespace(profile_confirmed_at=None)
        is_due, next_deadline = check_confirmation_due(user)
        assert is_due is True
        assert next_deadline is not None

    def test_confirmed_recently(self):
        from auth_module.user_service import check_confirmation_due
        now = datetime.now(timezone.utc)
        user = SimpleNamespace(profile_confirmed_at=now)
        is_due, next_deadline = check_confirmation_due(user)
        assert is_due is False

    def test_confirmed_long_ago(self):
        from auth_module.user_service import check_confirmation_due
        old_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
        user = SimpleNamespace(profile_confirmed_at=old_date)
        is_due, next_deadline = check_confirmation_due(user)
        assert is_due is True

    def test_naive_datetime_handled(self):
        from auth_module.user_service import check_confirmation_due
        naive_old = datetime(2020, 6, 1)
        user = SimpleNamespace(profile_confirmed_at=naive_old)
        is_due, next_deadline = check_confirmation_due(user)
        assert is_due is True

    def test_next_deadline_is_future(self):
        from auth_module.user_service import check_confirmation_due
        user = SimpleNamespace(profile_confirmed_at=None)
        _, next_deadline = check_confirmation_due(user)
        now = datetime.now(timezone.utc)
        assert next_deadline > now


class TestCreateProfileSnapshot:
    """Test create_profile_snapshot function."""

    def test_basic_snapshot(self):
        from auth_module.user_service import create_profile_snapshot
        user = SimpleNamespace(
            legal_expertise_level=SimpleNamespace(value="law_student"),
            german_proficiency=SimpleNamespace(value="native"),
            degree_program_type=None,
            current_semester=4,
            gender=SimpleNamespace(value="male"),
            age=22,
            job=None,
            years_of_experience=None,
            subjective_competence_civil=3,
            subjective_competence_public=4,
            subjective_competence_criminal=5,
            grade_zwischenpruefung=Decimal("8.5"),
            grade_vorgeruecktenubung=Decimal("9.0"),
            grade_first_staatsexamen=None,
            grade_second_staatsexamen=None,
            ati_s_scores={"item_1": 3, "item_2": 5, "item_3": 1, "item_4": 7},
            ptt_a_scores={"item_1": 2, "item_2": 4, "item_3": 6, "item_4": 1},
            ki_experience_scores={"item_1": 7, "item_2": 7, "item_3": 7, "item_4": 7},
        )
        snapshot = create_profile_snapshot(user)
        assert snapshot["legal_expertise_level"] == "law_student"
        assert snapshot["german_proficiency"] == "native"
        assert snapshot["age"] == 22
        assert snapshot["grade_zwischenpruefung"] == 8.5  # Decimal -> float
        assert snapshot["degree_program_type"] is None

    def test_snapshot_with_missing_attrs(self):
        from auth_module.user_service import create_profile_snapshot
        user = SimpleNamespace()
        # All fields should return None when attrs don't exist
        snapshot = create_profile_snapshot(user)
        for key, val in snapshot.items():
            assert val is None

    def test_snapshot_decimal_conversion(self):
        from auth_module.user_service import create_profile_snapshot
        user = SimpleNamespace(
            legal_expertise_level=None,
            german_proficiency=None,
            degree_program_type=None,
            current_semester=None,
            gender=None,
            age=None,
            job=None,
            years_of_experience=None,
            subjective_competence_civil=None,
            subjective_competence_public=None,
            subjective_competence_criminal=None,
            grade_zwischenpruefung=Decimal("12.50"),
            grade_vorgeruecktenubung=None,
            grade_first_staatsexamen=None,
            grade_second_staatsexamen=None,
            ati_s_scores=None,
            ptt_a_scores=None,
            ki_experience_scores=None,
        )
        snapshot = create_profile_snapshot(user)
        assert snapshot["grade_zwischenpruefung"] == 12.5
        assert isinstance(snapshot["grade_zwischenpruefung"], float)


class TestCheckMandatoryFieldsPresent:
    """Test _check_mandatory_fields_present function."""

    def test_no_expertise_returns_false(self):
        from auth_module.user_service import _check_mandatory_fields_present
        assert _check_mandatory_fields_present() is False

    def test_missing_base_fields(self):
        from auth_module.user_service import _check_mandatory_fields_present
        result = _check_mandatory_fields_present(
            legal_expertise_level="law_student",
            gender=None,
        )
        assert result is False

    def test_law_student_complete(self):
        from auth_module.user_service import _check_mandatory_fields_present
        result = _check_mandatory_fields_present(
            legal_expertise_level="law_student",
            gender="male", age=22, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
            grade_zwischenpruefung=8.5, grade_vorgeruecktenubung=9.0,
        )
        assert result is True

    def test_law_student_missing_grade(self):
        from auth_module.user_service import _check_mandatory_fields_present
        result = _check_mandatory_fields_present(
            legal_expertise_level="law_student",
            gender="male", age=22, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
            grade_zwischenpruefung=None, grade_vorgeruecktenubung=9.0,
        )
        assert result is False

    def test_referendar_complete(self):
        from auth_module.user_service import _check_mandatory_fields_present
        result = _check_mandatory_fields_present(
            legal_expertise_level="referendar",
            gender="female", age=28, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
            grade_zwischenpruefung=8.5, grade_vorgeruecktenubung=9.0,
            grade_first_staatsexamen=10.0,
        )
        assert result is True

    def test_graduated_complete(self):
        from auth_module.user_service import _check_mandatory_fields_present
        result = _check_mandatory_fields_present(
            legal_expertise_level="graduated_no_practice",
            gender="male", age=30, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
            grade_zwischenpruefung=8.5, grade_vorgeruecktenubung=9.0,
            grade_first_staatsexamen=10.0, grade_second_staatsexamen=11.0,
            job="Lawyer", years_of_experience=3,
        )
        assert result is True

    def test_graduated_missing_job(self):
        from auth_module.user_service import _check_mandatory_fields_present
        result = _check_mandatory_fields_present(
            legal_expertise_level="graduated_no_practice",
            gender="male", age=30, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
            grade_zwischenpruefung=8.5, grade_vorgeruecktenubung=9.0,
            grade_first_staatsexamen=10.0, grade_second_staatsexamen=11.0,
            job=None, years_of_experience=3,
        )
        assert result is False

    def test_llb_student_no_grades_needed(self):
        from auth_module.user_service import _check_mandatory_fields_present
        result = _check_mandatory_fields_present(
            legal_expertise_level="law_student",
            degree_program_type="llb",
            gender="male", age=22, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
        )
        assert result is True

    def test_llm_graduated_no_second_staatsexamen_but_needs_job(self):
        from auth_module.user_service import _check_mandatory_fields_present
        result = _check_mandatory_fields_present(
            legal_expertise_level="graduated_no_practice",
            degree_program_type="llm",
            gender="male", age=30, german_proficiency="native",
            subjective_competence_civil=3, subjective_competence_public=4,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
            job="Researcher", years_of_experience=2,
        )
        assert result is True

    def test_judge_professor_complete(self):
        from auth_module.user_service import _check_mandatory_fields_present
        result = _check_mandatory_fields_present(
            legal_expertise_level="judge_professor",
            gender="male", age=55, german_proficiency="native",
            subjective_competence_civil=5, subjective_competence_public=5,
            subjective_competence_criminal=5, ati_s_scores={}, ptt_a_scores={},
            ki_experience_scores={},
            grade_zwischenpruefung=12.0, grade_vorgeruecktenubung=11.0,
            grade_first_staatsexamen=13.0, grade_second_staatsexamen=14.0,
            job="Professor", years_of_experience=20,
        )
        assert result is True

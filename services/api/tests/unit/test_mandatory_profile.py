"""
Unit tests for Issue #1206: Mandatory Demographic & Psychometric Profile

Tests the validation functions, mandatory field detection, confirmation scheduling,
and profile snapshot creation.
"""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from freezegun import freeze_time

_SENTINEL = object()

# === Fixtures ===


@pytest.fixture
def valid_psychometric_scale():
    return {"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6}


@pytest.fixture
def make_user():
    """Factory for creating mock user objects with configurable fields."""

    _DEFAULT_ATI = {"item_1": 5, "item_2": 4, "item_3": 3, "item_4": 6}
    _DEFAULT_PTT = {"item_1": 4, "item_2": 5, "item_3": 2, "item_4": 7}
    _DEFAULT_KI = {"item_1": 6, "item_2": 5, "item_3": 4, "item_4": 3}

    def _make(
        expertise="law_student",
        degree_program_type=None,
        gender="maennlich",
        age=25,
        job=None,
        years_of_experience=None,
        german_proficiency="native",
        subjective_competence_civil=5,
        subjective_competence_public=4,
        subjective_competence_criminal=3,
        grade_zwischenpruefung=2.3,
        grade_vorgeruecktenubung=2.5,
        grade_first_staatsexamen=None,
        grade_second_staatsexamen=None,
        ati_s_scores=_SENTINEL,
        ptt_a_scores=_SENTINEL,
        ki_experience_scores=_SENTINEL,
        profile_confirmed_at=None,
    ):
        if ati_s_scores is _SENTINEL:
            ati_s_scores = _DEFAULT_ATI
        if ptt_a_scores is _SENTINEL:
            ptt_a_scores = _DEFAULT_PTT
        if ki_experience_scores is _SENTINEL:
            ki_experience_scores = _DEFAULT_KI

        user = Mock()
        user.legal_expertise_level = Mock()
        user.legal_expertise_level.value = expertise
        user.german_proficiency = Mock()
        user.german_proficiency.value = german_proficiency
        if degree_program_type is not None:
            user.degree_program_type = Mock()
            user.degree_program_type.value = degree_program_type
        else:
            user.degree_program_type = None
        user.current_semester = None
        user.gender = gender
        user.age = age
        user.job = job
        user.years_of_experience = years_of_experience
        user.subjective_competence_civil = subjective_competence_civil
        user.subjective_competence_public = subjective_competence_public
        user.subjective_competence_criminal = subjective_competence_criminal
        user.grade_zwischenpruefung = grade_zwischenpruefung
        user.grade_vorgeruecktenubung = grade_vorgeruecktenubung
        user.grade_first_staatsexamen = grade_first_staatsexamen
        user.grade_second_staatsexamen = grade_second_staatsexamen
        user.ati_s_scores = ati_s_scores
        user.ptt_a_scores = ptt_a_scores
        user.ki_experience_scores = ki_experience_scores
        user.profile_confirmed_at = profile_confirmed_at
        return user

    return _make


# === Tests for _validate_psychometric_scale ===


class TestValidatePsychometricScale:
    def test_valid_scale(self, valid_psychometric_scale):
        from auth_module.user_service import _validate_psychometric_scale

        # Should not raise
        _validate_psychometric_scale("ati_s_scores", valid_psychometric_scale)

    def test_valid_scale_boundary_min(self):
        from auth_module.user_service import _validate_psychometric_scale

        scale = {"item_1": 1, "item_2": 1, "item_3": 1, "item_4": 1}
        _validate_psychometric_scale("ati_s_scores", scale)

    def test_valid_scale_boundary_max(self):
        from auth_module.user_service import _validate_psychometric_scale

        scale = {"item_1": 7, "item_2": 7, "item_3": 7, "item_4": 7}
        _validate_psychometric_scale("ptt_a_scores", scale)

    def test_not_a_dict(self):
        from auth_module.user_service import _validate_psychometric_scale

        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", "not a dict")
        assert exc_info.value.status_code == 400
        assert "must be a JSON object" in exc_info.value.detail

    def test_missing_keys(self):
        from auth_module.user_service import _validate_psychometric_scale

        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", {"item_1": 3, "item_2": 4})
        assert exc_info.value.status_code == 400
        assert "must have exactly keys" in exc_info.value.detail

    def test_extra_keys(self):
        from auth_module.user_service import _validate_psychometric_scale

        scale = {"item_1": 3, "item_2": 4, "item_3": 5, "item_4": 6, "item_5": 2}
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ki_experience_scores", scale)
        assert exc_info.value.status_code == 400

    def test_value_below_range(self):
        from auth_module.user_service import _validate_psychometric_scale

        scale = {"item_1": 0, "item_2": 4, "item_3": 5, "item_4": 6}
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", scale)
        assert exc_info.value.status_code == 400
        assert "between 1 and 7" in exc_info.value.detail

    def test_value_above_range(self):
        from auth_module.user_service import _validate_psychometric_scale

        scale = {"item_1": 4, "item_2": 8, "item_3": 5, "item_4": 6}
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ptt_a_scores", scale)
        assert exc_info.value.status_code == 400
        assert "between 1 and 7" in exc_info.value.detail

    def test_float_value_rejected(self):
        from auth_module.user_service import _validate_psychometric_scale

        scale = {"item_1": 3.5, "item_2": 4, "item_3": 5, "item_4": 6}
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", scale)
        assert exc_info.value.status_code == 400

    def test_string_value_rejected(self):
        from auth_module.user_service import _validate_psychometric_scale

        scale = {"item_1": "high", "item_2": 4, "item_3": 5, "item_4": 6}
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", scale)
        assert exc_info.value.status_code == 400

    def test_none_value_rejected(self):
        from auth_module.user_service import _validate_psychometric_scale

        scale = {"item_1": None, "item_2": 4, "item_3": 5, "item_4": 6}
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", scale)
        assert exc_info.value.status_code == 400

    def test_negative_value_rejected(self):
        from auth_module.user_service import _validate_psychometric_scale

        scale = {"item_1": -1, "item_2": 4, "item_3": 5, "item_4": 6}
        with pytest.raises(HTTPException) as exc_info:
            _validate_psychometric_scale("ati_s_scores", scale)
        assert exc_info.value.status_code == 400


# === Tests for get_mandatory_profile_fields ===


class TestGetMandatoryProfileFields:
    def test_complete_layperson_no_missing(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="layperson",
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert missing == []

    def test_complete_law_student_no_missing(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(expertise="law_student")
        missing = get_mandatory_profile_fields(user)
        assert missing == []

    def test_complete_referendar_no_missing(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="referendar",
            grade_first_staatsexamen=8.5,
        )
        missing = get_mandatory_profile_fields(user)
        assert missing == []

    def test_complete_graduated_no_missing(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="graduated_no_practice",
            job="Jurist",
            years_of_experience=3,
            grade_first_staatsexamen=8.5,
            grade_second_staatsexamen=9.0,
        )
        missing = get_mandatory_profile_fields(user)
        assert missing == []

    def test_complete_practicing_lawyer_no_missing(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="practicing_lawyer",
            job="Rechtsanwalt",
            years_of_experience=10,
            grade_first_staatsexamen=11.0,
            grade_second_staatsexamen=10.5,
        )
        missing = get_mandatory_profile_fields(user)
        assert missing == []

    def test_complete_judge_professor_no_missing(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="judge_professor",
            job="Professor",
            years_of_experience=20,
            grade_first_staatsexamen=14.0,
            grade_second_staatsexamen=13.0,
        )
        missing = get_mandatory_profile_fields(user)
        assert missing == []

    def test_layperson_missing_gender(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="layperson",
            gender=None,
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "gender" in missing

    def test_layperson_missing_age(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="layperson",
            age=None,
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "age" in missing

    def test_layperson_missing_psychometric(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="layperson",
            ati_s_scores=None,
            ptt_a_scores=None,
            ki_experience_scores=None,
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "ati_s_scores" in missing
        assert "ptt_a_scores" in missing
        assert "ki_experience_scores" in missing

    def test_layperson_missing_competence(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="layperson",
            subjective_competence_civil=None,
            subjective_competence_public=None,
            subjective_competence_criminal=None,
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "subjective_competence_civil" in missing
        assert "subjective_competence_public" in missing
        assert "subjective_competence_criminal" in missing

    def test_layperson_does_not_require_grades(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="layperson",
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
            grade_first_staatsexamen=None,
            grade_second_staatsexamen=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" not in missing
        assert "grade_vorgeruecktenubung" not in missing
        assert "grade_first_staatsexamen" not in missing
        assert "grade_second_staatsexamen" not in missing

    def test_layperson_does_not_require_job(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="layperson",
            job=None,
            years_of_experience=None,
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "job" not in missing
        assert "years_of_experience" not in missing

    def test_law_student_requires_zwischenpruefung_and_vorgeruecktenubung(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="law_student",
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" in missing
        assert "grade_vorgeruecktenubung" in missing

    def test_law_student_does_not_require_staatsexamen(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="law_student",
            grade_first_staatsexamen=None,
            grade_second_staatsexamen=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_first_staatsexamen" not in missing
        assert "grade_second_staatsexamen" not in missing

    def test_referendar_requires_first_staatsexamen(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="referendar",
            grade_first_staatsexamen=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_first_staatsexamen" in missing

    def test_referendar_does_not_require_second_staatsexamen(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="referendar",
            grade_first_staatsexamen=8.5,
            grade_second_staatsexamen=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_second_staatsexamen" not in missing

    def test_graduated_requires_job_and_experience(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="graduated_no_practice",
            job=None,
            years_of_experience=None,
            grade_first_staatsexamen=8.5,
            grade_second_staatsexamen=9.0,
        )
        missing = get_mandatory_profile_fields(user)
        assert "job" in missing
        assert "years_of_experience" in missing

    def test_graduated_requires_second_staatsexamen(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="practicing_lawyer",
            job="Anwalt",
            years_of_experience=5,
            grade_first_staatsexamen=8.5,
            grade_second_staatsexamen=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_second_staatsexamen" in missing

    def test_no_expertise_returns_expertise_missing(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(expertise="law_student")
        user.legal_expertise_level = None
        missing = get_mandatory_profile_fields(user)
        assert "legal_expertise_level" in missing

    def test_missing_german_proficiency(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="layperson", grade_zwischenpruefung=None, grade_vorgeruecktenubung=None
        )
        user.german_proficiency = None
        missing = get_mandatory_profile_fields(user)
        assert "german_proficiency" in missing

    def test_llm_law_student_no_grades_required(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="law_student",
            degree_program_type="llm",
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" not in missing
        assert "grade_vorgeruecktenubung" not in missing

    def test_llb_law_student_no_grades_required(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="law_student",
            degree_program_type="llb",
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" not in missing
        assert "grade_vorgeruecktenubung" not in missing

    def test_llm_referendar_no_staatsexamen_required(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="referendar",
            degree_program_type="llm",
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
            grade_first_staatsexamen=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" not in missing
        assert "grade_vorgeruecktenubung" not in missing
        assert "grade_first_staatsexamen" not in missing

    def test_llm_graduated_no_grades_but_job_required(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="graduated_no_practice",
            degree_program_type="llm",
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
            grade_first_staatsexamen=None,
            grade_second_staatsexamen=None,
            job=None,
            years_of_experience=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" not in missing
        assert "grade_vorgeruecktenubung" not in missing
        assert "grade_first_staatsexamen" not in missing
        assert "grade_second_staatsexamen" not in missing
        assert "job" in missing
        assert "years_of_experience" in missing

    def test_staatsexamen_still_requires_grades(self, make_user):
        from auth_module.user_service import get_mandatory_profile_fields

        user = make_user(
            expertise="law_student",
            degree_program_type="staatsexamen",
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        missing = get_mandatory_profile_fields(user)
        assert "grade_zwischenpruefung" in missing
        assert "grade_vorgeruecktenubung" in missing


# === Tests for check_confirmation_due ===


class TestCheckConfirmationDue:
    def test_never_confirmed_is_due(self, make_user):
        from auth_module.user_service import check_confirmation_due

        user = make_user(profile_confirmed_at=None)
        is_due, next_deadline = check_confirmation_due(user)
        assert is_due is True
        assert next_deadline is not None

    @freeze_time("2025-06-01")
    def test_confirmed_recently_not_due(self, make_user):
        from auth_module.user_service import check_confirmation_due

        # Confirmed May 2025 (after April 15 deadline), now June 2025
        confirmed = datetime(2025, 5, 1, tzinfo=timezone.utc)
        user = make_user(profile_confirmed_at=confirmed)
        is_due, next_deadline = check_confirmation_due(user)

        assert is_due is False
        assert next_deadline == datetime(2025, 10, 15, tzinfo=timezone.utc)

    @freeze_time("2025-05-01")
    def test_confirmed_before_april_is_due_after_april(self, make_user):
        from auth_module.user_service import check_confirmation_due

        # Confirmed in March, now it's May — past April 15 deadline
        confirmed = datetime(2025, 3, 1, tzinfo=timezone.utc)
        user = make_user(profile_confirmed_at=confirmed)
        is_due, next_deadline = check_confirmation_due(user)

        assert is_due is True

    @freeze_time("2025-11-01")
    def test_confirmed_before_october_is_due_after_october(self, make_user):
        from auth_module.user_service import check_confirmation_due

        # Confirmed in May, now it's November — past October 15 deadline
        confirmed = datetime(2025, 5, 1, tzinfo=timezone.utc)
        user = make_user(profile_confirmed_at=confirmed)
        is_due, next_deadline = check_confirmation_due(user)

        assert is_due is True
        assert next_deadline == datetime(2026, 4, 15, tzinfo=timezone.utc)

    @freeze_time("2025-12-01")
    def test_confirmed_after_october_not_due_until_april(self, make_user):
        from auth_module.user_service import check_confirmation_due

        # Confirmed in November, now it's December — next deadline is April next year
        confirmed = datetime(2025, 11, 1, tzinfo=timezone.utc)
        user = make_user(profile_confirmed_at=confirmed)
        is_due, next_deadline = check_confirmation_due(user)

        assert is_due is False
        assert next_deadline == datetime(2026, 4, 15, tzinfo=timezone.utc)

    @freeze_time("2025-01-15")
    def test_early_january_deadline_is_previous_october(self, make_user):
        from auth_module.user_service import check_confirmation_due

        # It's January 2025, most recent deadline was October 2024
        confirmed = datetime(2024, 9, 1, tzinfo=timezone.utc)  # Before Oct 2024
        user = make_user(profile_confirmed_at=confirmed)
        is_due, next_deadline = check_confirmation_due(user)

        assert is_due is True
        assert next_deadline == datetime(2025, 4, 15, tzinfo=timezone.utc)

    @freeze_time("2025-06-01")
    def test_naive_confirmed_at_handled(self, make_user):
        from auth_module.user_service import check_confirmation_due

        # Timezone-naive datetime should still work
        confirmed = datetime(2025, 5, 1)  # No tzinfo
        user = make_user(profile_confirmed_at=confirmed)
        is_due, next_deadline = check_confirmation_due(user)

        # Should not raise, should treat naive as UTC
        assert isinstance(is_due, bool)


# === Tests for create_profile_snapshot ===


class TestCreateProfileSnapshot:
    def test_snapshot_contains_all_fields(self, make_user):
        from auth_module.user_service import create_profile_snapshot

        user = make_user(expertise="referendar", grade_first_staatsexamen=8.5)
        snapshot = create_profile_snapshot(user)

        expected_keys = {
            "legal_expertise_level",
            "german_proficiency",
            "degree_program_type",
            "current_semester",
            "gender",
            "age",
            "job",
            "years_of_experience",
            "subjective_competence_civil",
            "subjective_competence_public",
            "subjective_competence_criminal",
            "grade_zwischenpruefung",
            "grade_vorgeruecktenubung",
            "grade_first_staatsexamen",
            "grade_second_staatsexamen",
            "ati_s_scores",
            "ptt_a_scores",
            "ki_experience_scores",
        }
        assert set(snapshot.keys()) == expected_keys

    def test_snapshot_extracts_enum_values(self, make_user):
        from auth_module.user_service import create_profile_snapshot

        user = make_user(expertise="law_student", gender="weiblich")
        snapshot = create_profile_snapshot(user)

        assert snapshot["legal_expertise_level"] == "law_student"
        assert snapshot["german_proficiency"] == "native"
        assert snapshot["gender"] == "weiblich"

    def test_snapshot_none_fields(self, make_user):
        from auth_module.user_service import create_profile_snapshot

        user = make_user(
            expertise="layperson",
            job=None,
            years_of_experience=None,
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        snapshot = create_profile_snapshot(user)
        assert snapshot["job"] is None
        assert snapshot["years_of_experience"] is None
        assert snapshot["grade_zwischenpruefung"] is None

    def test_snapshot_with_psychometric_data(self, make_user):
        from auth_module.user_service import create_profile_snapshot

        scales = {"item_1": 1, "item_2": 2, "item_3": 3, "item_4": 4}
        user = make_user(ati_s_scores=scales)
        snapshot = create_profile_snapshot(user)
        assert snapshot["ati_s_scores"] == scales


# === Tests for _check_mandatory_fields_present ===


class TestCheckMandatoryFieldsPresent:
    def test_layperson_all_present(self):
        from auth_module.user_service import _check_mandatory_fields_present

        result = _check_mandatory_fields_present(
            legal_expertise_level="layperson",
            gender="maennlich",
            age=30,
            german_proficiency="native",
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ki_experience_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
            grade_first_staatsexamen=None,
            grade_second_staatsexamen=None,
            job=None,
            years_of_experience=None,
        )
        assert result is True

    def test_no_expertise_returns_false(self):
        from auth_module.user_service import _check_mandatory_fields_present

        result = _check_mandatory_fields_present(
            legal_expertise_level=None,
            gender="maennlich",
            age=30,
            german_proficiency="native",
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ki_experience_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
        )
        assert result is False

    def test_missing_gender_returns_false(self):
        from auth_module.user_service import _check_mandatory_fields_present

        result = _check_mandatory_fields_present(
            legal_expertise_level="layperson",
            gender=None,
            age=30,
            german_proficiency="native",
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ki_experience_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
        )
        assert result is False

    def test_law_student_missing_grades_returns_false(self):
        from auth_module.user_service import _check_mandatory_fields_present

        result = _check_mandatory_fields_present(
            legal_expertise_level="law_student",
            gender="weiblich",
            age=22,
            german_proficiency="native",
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ki_experience_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        assert result is False

    def test_graduated_missing_job_returns_false(self):
        from auth_module.user_service import _check_mandatory_fields_present

        result = _check_mandatory_fields_present(
            legal_expertise_level="graduated_no_practice",
            gender="divers",
            age=35,
            german_proficiency="native",
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ki_experience_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            grade_zwischenpruefung=2.0,
            grade_vorgeruecktenubung=2.5,
            grade_first_staatsexamen=8.0,
            grade_second_staatsexamen=9.0,
            job=None,
            years_of_experience=5,
        )
        assert result is False

    def test_graduated_all_fields_present(self):
        from auth_module.user_service import _check_mandatory_fields_present

        result = _check_mandatory_fields_present(
            legal_expertise_level="practicing_lawyer",
            gender="weiblich",
            age=40,
            german_proficiency="native",
            subjective_competence_civil=6,
            subjective_competence_public=5,
            subjective_competence_criminal=7,
            ati_s_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ki_experience_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            grade_zwischenpruefung=2.0,
            grade_vorgeruecktenubung=2.5,
            grade_first_staatsexamen=11.0,
            grade_second_staatsexamen=10.5,
            job="Rechtsanwaeltin",
            years_of_experience=15,
        )
        assert result is True

    def test_referendar_missing_first_staatsexamen(self):
        from auth_module.user_service import _check_mandatory_fields_present

        result = _check_mandatory_fields_present(
            legal_expertise_level="referendar",
            gender="maennlich",
            age=28,
            german_proficiency="native",
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ki_experience_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            grade_zwischenpruefung=2.0,
            grade_vorgeruecktenubung=2.5,
            grade_first_staatsexamen=None,
        )
        assert result is False

    def test_llm_law_student_no_grades_needed(self):
        from auth_module.user_service import _check_mandatory_fields_present

        result = _check_mandatory_fields_present(
            legal_expertise_level="law_student",
            degree_program_type="llm",
            gender="weiblich",
            age=24,
            german_proficiency="native",
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ki_experience_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        assert result is True

    def test_llb_law_student_no_grades_needed(self):
        from auth_module.user_service import _check_mandatory_fields_present

        result = _check_mandatory_fields_present(
            legal_expertise_level="law_student",
            degree_program_type="llb",
            gender="maennlich",
            age=22,
            german_proficiency="native",
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ki_experience_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
        )
        assert result is True

    def test_llm_graduated_no_grades_but_job_needed(self):
        from auth_module.user_service import _check_mandatory_fields_present

        result = _check_mandatory_fields_present(
            legal_expertise_level="graduated_no_practice",
            degree_program_type="llm",
            gender="divers",
            age=35,
            german_proficiency="native",
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ki_experience_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
            grade_first_staatsexamen=None,
            grade_second_staatsexamen=None,
            job="Jurist",
            years_of_experience=5,
        )
        assert result is True

    def test_llm_graduated_missing_job_still_fails(self):
        from auth_module.user_service import _check_mandatory_fields_present

        result = _check_mandatory_fields_present(
            legal_expertise_level="graduated_no_practice",
            degree_program_type="llm",
            gender="divers",
            age=35,
            german_proficiency="native",
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            ki_experience_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 6},
            grade_zwischenpruefung=None,
            grade_vorgeruecktenubung=None,
            grade_first_staatsexamen=None,
            grade_second_staatsexamen=None,
            job=None,
            years_of_experience=5,
        )
        assert result is False


# === Tests for Gender enum validation ===


class TestGenderEnum:
    def test_valid_values(self):
        from models import Gender

        assert Gender("maennlich") == Gender.MAENNLICH
        assert Gender("weiblich") == Gender.WEIBLICH
        assert Gender("divers") == Gender.DIVERS
        assert Gender("keine_angabe") == Gender.KEINE_ANGABE

    def test_invalid_value(self):
        from models import Gender

        with pytest.raises(ValueError):
            Gender("invalid")

    def test_enum_is_string(self):
        from models import Gender

        assert isinstance(Gender.MAENNLICH, str)
        assert Gender.MAENNLICH == "maennlich"

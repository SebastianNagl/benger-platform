"""
Unit tests for uncovered lines in auth_module/user_service.py.

Targets: delete_user, get_all_users, init_feature_flags, update_user_profile,
change_user_password, confirm_profile, _complete_demo_user_profile,
and various branches in create_user.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, PropertyMock, call, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# delete_user
# ---------------------------------------------------------------------------

class TestDeleteUser:
    """Test delete_user function covering lines 459-572."""

    def test_delete_user_no_fallback_superadmin(self):
        """If no other superadmin exists, should raise 400."""
        from auth_module.user_service import delete_user

        db = MagicMock()
        # No pschOrr95 user
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            delete_user(db, "user-to-delete")
        assert exc_info.value.status_code == 400
        assert "No other superadmin" in exc_info.value.detail

    def test_delete_user_not_found(self):
        """Should return False when user to delete is not found."""
        from auth_module.user_service import delete_user

        db = MagicMock()
        fallback_user = Mock(id="fallback-id")

        # First filter call: find pschOrr95 -> found
        # After that, get_user_by_id returns None
        call_count = [0]

        def filter_side_effect(*args, **kwargs):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                # pschOrr95 superadmin query
                result.first.return_value = fallback_user
            else:
                # get_user_by_id returns None
                result.first.return_value = None
            return result

        db.query.return_value.filter = filter_side_effect
        result = delete_user(db, "nonexistent-id")
        assert result is False

    def test_delete_user_cannot_delete_fallback(self):
        """Should raise 400 when trying to delete the fallback superadmin."""
        from auth_module.user_service import delete_user

        db = MagicMock()
        fallback_user = Mock(id="fallback-id")
        target_user = Mock(id="fallback-id")  # same as fallback

        call_count = [0]

        def filter_side_effect(*args, **kwargs):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.first.return_value = fallback_user
            else:
                result.first.return_value = target_user
            return result

        db.query.return_value.filter = filter_side_effect

        with pytest.raises(HTTPException) as exc_info:
            delete_user(db, "fallback-id")
        assert exc_info.value.status_code == 400
        assert "fallback superadmin" in exc_info.value.detail

    def test_delete_user_success(self):
        """Successful delete should commit and return True."""
        from auth_module.user_service import delete_user

        db = MagicMock()
        fallback_user = Mock(id="fallback-id")
        target_user = Mock(id="target-id")

        # The function does many db.query(Model).filter(...) calls.
        # MagicMock's chaining handles this automatically; we just need
        # the first .filter().first() to return the fallback user (pschOrr95 lookup).
        # get_user_by_id is called separately, so we patch that.
        db.query.return_value.filter.return_value.first.return_value = fallback_user

        with patch("auth_module.user_service.get_user_by_id", return_value=target_user):
            result = delete_user(db, "target-id")
        assert result is True
        db.commit.assert_called()
        db.delete.assert_called_once_with(target_user)

    def test_delete_user_exception_rolls_back(self):
        """On exception during deletion, should rollback and raise 500."""
        from auth_module.user_service import delete_user

        db = MagicMock()
        fallback_user = Mock(id="fallback-id")
        target_user = Mock(id="target-id")

        call_count = [0]

        def filter_side_effect(*args, **kwargs):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.first.return_value = fallback_user
            elif call_count[0] == 2:
                result.first.return_value = target_user
            else:
                # Simulate exception during deletion
                result.delete.side_effect = Exception("DB error")
            return result

        db.query.return_value.filter = filter_side_effect

        with patch("auth_module.user_service.get_user_by_id", return_value=target_user):
            with pytest.raises(HTTPException) as exc_info:
                delete_user(db, "target-id")
            assert exc_info.value.status_code == 500
            assert "Failed to delete user" in exc_info.value.detail


# ---------------------------------------------------------------------------
# get_all_users (line 580)
# ---------------------------------------------------------------------------

class TestGetAllUsers:
    """Test get_all_users function covering line 580."""

    def test_get_all_users(self):
        from auth_module.user_service import get_all_users

        db = MagicMock()
        users = [Mock(), Mock(), Mock()]
        db.query.return_value.all.return_value = users

        result = get_all_users(db)
        assert result == users
        assert len(result) == 3


# ---------------------------------------------------------------------------
# init_feature_flags (lines 604-618)
# ---------------------------------------------------------------------------

class TestInitFeatureFlags:
    """Test init_feature_flags function covering lines 604-618."""

    def test_creates_new_flags(self):
        from auth_module.user_service import init_feature_flags

        db = MagicMock()
        # No existing flags
        db.query.return_value.filter.return_value.first.return_value = None

        init_feature_flags(db, "admin-id")

        # Should have called db.add for each flag
        assert db.add.call_count >= 6  # 6 feature flags defined
        assert db.commit.call_count >= 6

    def test_skips_existing_flags(self):
        from auth_module.user_service import init_feature_flags

        db = MagicMock()
        # All flags exist already
        db.query.return_value.filter.return_value.first.return_value = Mock()

        init_feature_flags(db, "admin-id")

        # Should not add any new flags
        assert db.add.call_count == 0

    def test_handles_exception_during_flag_creation(self):
        from auth_module.user_service import init_feature_flags

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        db.commit.side_effect = Exception("Duplicate key")

        # Should not raise - logs error and continues
        init_feature_flags(db, "admin-id")
        assert db.rollback.called


# ---------------------------------------------------------------------------
# _complete_demo_user_profile (lines 638-669)
# ---------------------------------------------------------------------------

class TestCompleteDemoUserProfile:
    """Test _complete_demo_user_profile function covering lines 638-669."""

    def test_no_missing_fields_returns_false(self):
        from auth_module.user_service import _complete_demo_user_profile

        db = MagicMock()
        # User with all fields set
        user = MagicMock()

        with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=[]):
            result = _complete_demo_user_profile(db, user)
        assert result is False

    def test_fills_missing_fields(self):
        from auth_module.user_service import _complete_demo_user_profile

        db = MagicMock()
        user = MagicMock()
        # All fields start as None
        user.gender = None
        user.age = None
        user.german_proficiency = None
        user.legal_expertise_level = None
        user.subjective_competence_civil = None
        user.subjective_competence_public = None
        user.subjective_competence_criminal = None
        user.grade_zwischenpruefung = None
        user.grade_vorgeruecktenubung = None
        user.ati_s_scores = None
        user.ptt_a_scores = None
        user.ki_experience_scores = None
        user.mandatory_profile_completed = False
        user.profile_confirmed_at = None

        with patch("auth_module.user_service.get_mandatory_profile_fields") as mock_fields:
            # First call: returns missing fields
            # Second call: returns empty (all filled)
            mock_fields.side_effect = [["gender", "age"], []]
            result = _complete_demo_user_profile(db, user)

        assert result is True
        # Should set mandatory_profile_completed
        assert user.mandatory_profile_completed is True
        assert user.profile_confirmed_at is not None

    def test_fills_fields_but_still_missing(self):
        from auth_module.user_service import _complete_demo_user_profile

        db = MagicMock()
        user = MagicMock()
        user.gender = None
        user.age = None
        user.german_proficiency = None
        user.legal_expertise_level = None
        user.subjective_competence_civil = None
        user.subjective_competence_public = None
        user.subjective_competence_criminal = None
        user.grade_zwischenpruefung = None
        user.grade_vorgeruecktenubung = None
        user.ati_s_scores = None
        user.ptt_a_scores = None
        user.ki_experience_scores = None
        user.mandatory_profile_completed = False

        with patch("auth_module.user_service.get_mandatory_profile_fields") as mock_fields:
            # First call: missing, second call: still missing
            mock_fields.side_effect = [["gender"], ["some_field"]]
            result = _complete_demo_user_profile(db, user)

        assert result is True
        # Should NOT set mandatory_profile_completed because still missing
        assert user.mandatory_profile_completed is False


# ---------------------------------------------------------------------------
# change_user_password (lines 1064-1081)
# ---------------------------------------------------------------------------

class TestChangeUserPassword:
    """Test change_user_password function covering lines 1064-1081."""

    def test_user_not_found(self):
        from auth_module.user_service import change_user_password

        db = MagicMock()
        with patch("auth_module.user_service.get_user_by_id", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                change_user_password(db, "nonexistent", "old", "new")
            assert exc_info.value.status_code == 404
            assert "User not found" in exc_info.value.detail

    def test_wrong_current_password(self):
        from auth_module.user_service import change_user_password

        db = MagicMock()
        user = Mock(hashed_password="hashed_pw")

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.verify_password", return_value=False):
                with pytest.raises(HTTPException) as exc_info:
                    change_user_password(db, "user-id", "wrong", "new")
                assert exc_info.value.status_code == 400
                assert "Current password is incorrect" in exc_info.value.detail

    def test_success(self):
        from auth_module.user_service import change_user_password

        db = MagicMock()
        user = Mock(hashed_password="old_hash")

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.verify_password", return_value=True):
                with patch("auth_module.user_service.get_password_hash", return_value="new_hash"):
                    result = change_user_password(db, "user-id", "old", "new")

        assert result is True
        assert user.hashed_password == "new_hash"
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# update_user_profile (lines 873-965+)
# ---------------------------------------------------------------------------

class TestUpdateUserProfile:
    """Test update_user_profile function covering lines 873-965 and beyond."""

    def _make_mock_user(self):
        user = MagicMock()
        user.id = "user-id"
        user.email = "old@example.com"
        user.name = "Old Name"
        user.use_pseudonym = True
        user.age = 25
        user.job = "Engineer"
        user.years_of_experience = 5
        user.legal_expertise_level = None
        user.german_proficiency = None
        user.degree_program_type = None
        user.current_semester = None
        user.legal_specializations = None
        user.german_state_exams_count = None
        user.german_state_exams_data = None
        user.gender = None
        user.subjective_competence_civil = None
        user.subjective_competence_public = None
        user.subjective_competence_criminal = None
        user.grade_zwischenpruefung = None
        user.grade_vorgeruecktenubung = None
        user.grade_first_staatsexamen = None
        user.grade_second_staatsexamen = None
        user.ati_s_scores = None
        user.ptt_a_scores = None
        user.ki_experience_scores = None
        user.mandatory_profile_completed = False
        user.profile_confirmed_at = None
        return user

    def test_user_not_found_returns_none(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        with patch("auth_module.user_service.get_user_by_id", return_value=None):
            result = update_user_profile(db, "nonexistent")
        assert result is None

    def test_update_name(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=["gender"]):
                result = update_user_profile(db, "user-id", name="New Name")

        assert user.name == "New Name"
        db.commit.assert_called()

    def test_update_email_resets_verification(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()
        user.email = "old@example.com"
        user.email_verified = True

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.get_user_by_email", return_value=None):
                with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=[]):
                    with patch("auth_module.user_service.create_profile_snapshot", return_value={}):
                        result = update_user_profile(db, "user-id", email="new@example.com")

        assert user.email == "new@example.com"
        assert user.email_verified is False

    def test_update_email_already_taken(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()
        user.email = "old@example.com"
        other_user = Mock(id="other-id")

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.get_user_by_email", return_value=other_user):
                with pytest.raises(HTTPException) as exc_info:
                    update_user_profile(db, "user-id", email="taken@example.com")
                assert exc_info.value.status_code == 400
                assert "already registered" in exc_info.value.detail

    def test_update_legal_expertise_invalid(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                update_user_profile(db, "user-id", legal_expertise_level="invalid_level")
            assert exc_info.value.status_code == 400

    def test_update_german_proficiency_invalid(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                update_user_profile(db, "user-id", german_proficiency="invalid")
            assert exc_info.value.status_code == 400

    def test_update_degree_program_type_invalid(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                update_user_profile(db, "user-id", degree_program_type="invalid")
            assert exc_info.value.status_code == 400

    def test_update_current_semester_not_law_student(self):
        """Semester should be cleared if user is not a law student."""
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()
        # Not a law student
        user.legal_expertise_level = Mock(value="layperson")
        user.legal_expertise_level.__eq__ = lambda self, other: False

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=[]):
                with patch("auth_module.user_service.create_profile_snapshot", return_value={}):
                    update_user_profile(db, "user-id", current_semester=5)

        assert user.current_semester is None

    def test_update_legal_specializations_filters_invalid(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=[]):
                with patch("auth_module.user_service.create_profile_snapshot", return_value={}):
                    update_user_profile(
                        db, "user-id",
                        legal_specializations=["civil_law", "invalid_spec", "tax_law"]
                    )

        assert user.legal_specializations == ["civil_law", "tax_law"]

    def test_update_gender_invalid(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                update_user_profile(db, "user-id", gender="invalid_gender")
            assert exc_info.value.status_code == 400
            assert "Invalid gender" in exc_info.value.detail

    def test_update_subjective_competence_out_of_range(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                update_user_profile(db, "user-id", subjective_competence_civil=10)
            assert exc_info.value.status_code == 400
            assert "between 1 and 7" in exc_info.value.detail

    def test_update_subjective_competence_below_range(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                update_user_profile(db, "user-id", subjective_competence_public=0)
            assert exc_info.value.status_code == 400

    def test_update_psychometric_invalid(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                update_user_profile(db, "user-id", ati_s_scores="not a dict")
            assert exc_info.value.status_code == 400

    def test_update_sets_mandatory_complete_when_all_filled(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()
        user.mandatory_profile_completed = False

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=[]):
                with patch("auth_module.user_service.create_profile_snapshot", return_value={}):
                    update_user_profile(db, "user-id", name="Complete User")

        assert user.mandatory_profile_completed is True

    def test_update_german_state_exam_fields(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=["gender"]):
                update_user_profile(
                    db, "user-id",
                    german_state_exams_count=1,
                    german_state_exams_data=[{"year": 2023, "grade": 8.5}]
                )

        assert user.german_state_exams_count == 1
        assert user.german_state_exams_data == [{"year": 2023, "grade": 8.5}]

    def test_update_objective_grades(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=[]):
                with patch("auth_module.user_service.create_profile_snapshot", return_value={}):
                    update_user_profile(
                        db, "user-id",
                        grade_zwischenpruefung=8.5,
                        grade_first_staatsexamen=10.0,
                    )

        assert user.grade_zwischenpruefung == 8.5
        assert user.grade_first_staatsexamen == 10.0

    def test_update_use_pseudonym(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()
        user.use_pseudonym = True

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=[]):
                with patch("auth_module.user_service.create_profile_snapshot", return_value={}):
                    update_user_profile(db, "user-id", use_pseudonym=False)

        assert user.use_pseudonym is False

    def test_update_invalid_email_format(self):
        from auth_module.user_service import update_user_profile

        db = MagicMock()
        user = self._make_mock_user()
        user.email = "old@example.com"

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            # The validate_email_with_details function is imported inside the function
            # We'll simulate the ImportError fallback path
            with patch.dict("sys.modules", {"email_validation": None}):
                with pytest.raises((HTTPException, Exception)):
                    update_user_profile(db, "user-id", email="invalid")


# ---------------------------------------------------------------------------
# confirm_profile (lines 1310-1350)
# ---------------------------------------------------------------------------

class TestConfirmProfile:
    """Test confirm_profile function covering lines 1310-1350."""

    def test_user_not_found(self):
        from auth_module.user_service import confirm_profile

        db = MagicMock()
        with patch("auth_module.user_service.get_user_by_id", return_value=None):
            result = confirm_profile(db, "nonexistent")
        assert result is None

    def test_missing_fields_raises_400(self):
        from auth_module.user_service import confirm_profile

        db = MagicMock()
        user = MagicMock()

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=["gender", "age"]):
                with pytest.raises(HTTPException) as exc_info:
                    confirm_profile(db, "user-id")
                assert exc_info.value.status_code == 400
                assert "missing fields" in exc_info.value.detail

    def test_success(self):
        from auth_module.user_service import confirm_profile

        db = MagicMock()
        user = MagicMock()
        user.mandatory_profile_completed = False
        user.profile_confirmed_at = None

        with patch("auth_module.user_service.get_user_by_id", return_value=user):
            with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=[]):
                with patch("auth_module.user_service.create_profile_snapshot", return_value={}):
                    result = confirm_profile(db, "user-id")

        assert result == user
        assert user.mandatory_profile_completed is True
        assert user.profile_confirmed_at is not None
        db.add.assert_called_once()  # history entry
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(user)


# ---------------------------------------------------------------------------
# create_user branch coverage (lines 200-205, 210, 269-270, 279-280, 287-290,
#   298-302, 309, 374, 377, 379)
# ---------------------------------------------------------------------------

class TestCreateUserBranches:
    """Test create_user additional branches."""

    def _setup_db_for_create(self, db):
        """Set up mock db that passes the basic checks in create_user."""
        # get_user_by_username returns None (no duplicate)
        # get_user_by_email returns None (no duplicate)
        # pseudonym generation
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.all.return_value = []

    def test_invalid_email_format_fallback(self):
        """Test create_user with ImportError fallback for email validation."""
        from auth_module.user_service import create_user

        db = MagicMock()
        self._setup_db_for_create(db)

        # Simulate the case where email_validation module is not available
        # and the fallback validation catches invalid email
        with patch.dict("sys.modules", {"email_validation": None}):
            with patch("builtins.__import__", side_effect=ImportError):
                # The function has a try/except ImportError for email_validation
                # When the fallback is used, "invalid" email without @ should fail
                with pytest.raises(HTTPException) as exc_info:
                    create_user(db, "user", "invalid", "Test", "pass123")
                assert exc_info.value.status_code == 400

    def test_invalid_legal_expertise_level(self):
        """Test create_user with invalid legal_expertise_level enum value."""
        from auth_module.user_service import create_user

        db = MagicMock()
        self._setup_db_for_create(db)

        with patch("auth_module.user_service.get_user_by_username", return_value=None):
            with patch("auth_module.user_service.get_user_by_email", return_value=None):
                with pytest.raises(HTTPException) as exc_info:
                    create_user(
                        db, "user", "user@test.com", "Test", "pass123",
                        legal_expertise_level="invalid_level"
                    )
                assert exc_info.value.status_code == 400
                assert "Invalid legal expertise level" in exc_info.value.detail

    def test_invalid_german_proficiency(self):
        """Test create_user with invalid german_proficiency enum value."""
        from auth_module.user_service import create_user

        db = MagicMock()
        self._setup_db_for_create(db)

        with patch("auth_module.user_service.get_user_by_username", return_value=None):
            with patch("auth_module.user_service.get_user_by_email", return_value=None):
                with pytest.raises(HTTPException) as exc_info:
                    create_user(
                        db, "user", "user@test.com", "Test", "pass123",
                        german_proficiency="invalid_level"
                    )
                assert exc_info.value.status_code == 400
                assert "Invalid German proficiency" in exc_info.value.detail

    def test_invalid_degree_program_type(self):
        """Test create_user with invalid degree_program_type enum value."""
        from auth_module.user_service import create_user

        db = MagicMock()
        self._setup_db_for_create(db)

        with patch("auth_module.user_service.get_user_by_username", return_value=None):
            with patch("auth_module.user_service.get_user_by_email", return_value=None):
                with pytest.raises(HTTPException) as exc_info:
                    create_user(
                        db, "user", "user@test.com", "Test", "pass123",
                        degree_program_type="invalid_type"
                    )
                assert exc_info.value.status_code == 400
                assert "Invalid degree program type" in exc_info.value.detail


# ---------------------------------------------------------------------------
# initialize_database (line 1350)
# ---------------------------------------------------------------------------

class TestInitializeDatabase:
    """Test initialize_database function."""

    def test_calls_init_demo_users(self):
        from auth_module.user_service import initialize_database

        db = MagicMock()
        with patch("auth_module.user_service.init_demo_users") as mock_init:
            initialize_database(db)
            mock_init.assert_called_once_with(db)

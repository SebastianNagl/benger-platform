"""
Integration tests for Issue #1206: Mandatory Demographic & Psychometric Profile

Tests the API endpoints, user creation with mandatory fields, profile update with
history tracking, and the mandatory-profile-status / confirm-profile / profile-history
endpoints.
"""

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from auth_module import create_access_token
from models import User, UserProfileHistory
from auth_module.user_service import get_password_hash

# NOTE: The HTTP endpoints exercised by TestMandatoryProfileStatus,
# TestConfirmProfile and TestProfileHistory moved to the async DB lane
# (GET /auth/mandatory-profile-status, POST /auth/confirm-profile,
# GET /auth/profile-history all use Depends(get_async_db)). A sync TestClient
# call into those async handlers fails with a cross-event-loop RuntimeError, so
# those classes are driven with async_test_client + async_test_db, overriding
# require_user. The remaining classes test sync service functions directly
# (confirm_profile / update_user_profile / create_user) or PUT /auth/profile
# (which deliberately stays sync) — they keep the sync test_db fixtures.
from auth_module.dependencies import require_user  # noqa: E402
from auth_module.models import User as AuthUser  # noqa: E402
from main import app  # noqa: E402

# === Fixtures ===


VALID_SCALES = {
    "ati_s": {"item_1": 5, "item_2": 4, "item_3": 3, "item_4": 6},
    "ptt_a": {"item_1": 4, "item_2": 5, "item_3": 2, "item_4": 7},
    "ki_exp": {"item_1": 6, "item_2": 5, "item_3": 4, "item_4": 3},
}


@contextmanager
def _as_user(db_user):
    """Override require_user with an AuthUser mirroring a seeded DB user row."""
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _aseed_complete_user(db, *, id="complete-user-id"):
    """Async twin of the ``complete_user`` fixture: all mandatory fields set."""
    user = User(
        id=id,
        username="completeuser",
        email="complete@test.com",
        name="Complete User",
        hashed_password=get_password_hash("password123"),
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        legal_expertise_level="law_student",
        german_proficiency="native",
        gender="weiblich",
        age=24,
        subjective_competence_civil=5,
        subjective_competence_public=4,
        subjective_competence_criminal=3,
        grade_zwischenpruefung=2.3,
        grade_vorgeruecktenubung=2.5,
        ati_s_scores=VALID_SCALES["ati_s"],
        ptt_a_scores=VALID_SCALES["ptt_a"],
        ki_experience_scores=VALID_SCALES["ki_exp"],
        mandatory_profile_completed=True,
        profile_confirmed_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _aseed_incomplete_user(db, *, id="incomplete-user-id"):
    """Async twin of the ``incomplete_user`` fixture: missing mandatory fields."""
    user = User(
        id=id,
        username="incompleteuser",
        email="incomplete@test.com",
        name="Incomplete User",
        hashed_password=get_password_hash("password123"),
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        legal_expertise_level="law_student",
        german_proficiency="native",
        mandatory_profile_completed=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _aseed_admin_user(db, *, id="admin-integ-id"):
    """Async twin of the ``admin_user`` fixture: a superadmin."""
    user = User(
        id=id,
        username="admininteg",
        email="admininteg@test.com",
        name="Admin Integration",
        hashed_password=get_password_hash("password123"),
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        mandatory_profile_completed=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
def complete_user(test_db):
    """A user with all mandatory profile fields filled in."""
    user = User(
        id="complete-user-id",
        username="completeuser",
        email="complete@test.com",
        name="Complete User",
        hashed_password=get_password_hash("password123"),
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        legal_expertise_level="law_student",
        german_proficiency="native",
        gender="weiblich",
        age=24,
        subjective_competence_civil=5,
        subjective_competence_public=4,
        subjective_competence_criminal=3,
        grade_zwischenpruefung=2.3,
        grade_vorgeruecktenubung=2.5,
        ati_s_scores=VALID_SCALES["ati_s"],
        ptt_a_scores=VALID_SCALES["ptt_a"],
        ki_experience_scores=VALID_SCALES["ki_exp"],
        mandatory_profile_completed=True,
        profile_confirmed_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    user.token = create_access_token(data={"user_id": user.id})
    return user


@pytest.fixture
def incomplete_user(test_db):
    """A user missing mandatory profile fields."""
    user = User(
        id="incomplete-user-id",
        username="incompleteuser",
        email="incomplete@test.com",
        name="Incomplete User",
        hashed_password=get_password_hash("password123"),
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        legal_expertise_level="law_student",
        german_proficiency="native",
        mandatory_profile_completed=False,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    user.token = create_access_token(data={"user_id": user.id})
    return user


@pytest.fixture
def admin_user(test_db):
    """A superadmin user."""
    user = User(
        id="admin-integ-id",
        username="admininteg",
        email="admininteg@test.com",
        name="Admin Integration",
        hashed_password=get_password_hash("password123"),
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        mandatory_profile_completed=False,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    user.token = create_access_token(data={"user_id": user.id})
    return user


# === Tests for GET /auth/mandatory-profile-status ===


class TestMandatoryProfileStatus:
    """GET /auth/mandatory-profile-status is async — driven via async client."""

    @pytest.mark.asyncio
    async def test_incomplete_user_returns_missing_fields(
        self, async_test_client, async_test_db
    ):
        incomplete_user = await _aseed_incomplete_user(async_test_db)
        with _as_user(incomplete_user):
            response = await async_test_client.get("/api/auth/mandatory-profile-status")
        assert response.status_code == 200
        data = response.json()
        assert data["mandatory_profile_completed"] == False  # noqa: E712
        assert len(data["missing_fields"]) > 0
        assert "gender" in data["missing_fields"]
        assert "age" in data["missing_fields"]

    @pytest.mark.asyncio
    async def test_complete_user_no_missing_fields(self, async_test_client, async_test_db):
        complete_user = await _aseed_complete_user(async_test_db)
        with _as_user(complete_user):
            response = await async_test_client.get("/api/auth/mandatory-profile-status")
        assert response.status_code == 200
        data = response.json()
        assert data["mandatory_profile_completed"] == True  # noqa: E712
        assert data["missing_fields"] == []

    @pytest.mark.asyncio
    async def test_confirmation_due_when_never_confirmed(
        self, async_test_client, async_test_db
    ):
        incomplete_user = await _aseed_incomplete_user(async_test_db)
        with _as_user(incomplete_user):
            response = await async_test_client.get("/api/auth/mandatory-profile-status")
        data = response.json()
        assert data["confirmation_due"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, async_test_client):
        response = await async_test_client.get("/api/auth/mandatory-profile-status")
        assert response.status_code in (401, 403)


# === Tests for POST /auth/confirm-profile ===


class TestConfirmProfile:
    """POST /auth/confirm-profile is async — driven via async client."""

    @pytest.mark.asyncio
    async def test_confirm_complete_profile(self, async_test_client, async_test_db):
        complete_user = await _aseed_complete_user(async_test_db)
        with _as_user(complete_user):
            response = await async_test_client.post("/api/auth/confirm-profile")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True  # noqa: E712
        assert "confirmed_at" in data

    @pytest.mark.asyncio
    async def test_confirm_incomplete_profile_rejected(
        self, async_test_client, async_test_db
    ):
        incomplete_user = await _aseed_incomplete_user(async_test_db)
        with _as_user(incomplete_user):
            response = await async_test_client.post("/api/auth/confirm-profile")
        assert response.status_code == 400
        data = response.json()
        assert "missing fields" in data["detail"].lower() or "missing" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_confirm_creates_history_entry(self, async_test_client, async_test_db):
        complete_user = await _aseed_complete_user(async_test_db)
        with _as_user(complete_user):
            response = await async_test_client.post("/api/auth/confirm-profile")
        assert response.status_code == 200

        entries = (
            await async_test_db.execute(
                select(UserProfileHistory).where(
                    UserProfileHistory.user_id == complete_user.id
                )
            )
        ).scalars().all()
        assert len(entries) >= 1
        confirmation_entry = [e for e in entries if e.change_type == "confirmation"]
        assert len(confirmation_entry) == 1
        assert "profile_confirmed_at" in confirmation_entry[0].changed_fields

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, async_test_client):
        response = await async_test_client.post("/api/auth/confirm-profile")
        assert response.status_code in (401, 403)


# === Tests for GET /auth/profile-history ===


class TestProfileHistory:
    """GET /auth/profile-history is async — driven via async client."""

    @pytest.mark.asyncio
    async def test_empty_history(self, async_test_client, async_test_db):
        complete_user = await _aseed_complete_user(async_test_db)
        with _as_user(complete_user):
            response = await async_test_client.get("/api/auth/profile-history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_history_after_confirmation(self, async_test_client, async_test_db):
        complete_user = await _aseed_complete_user(async_test_db)
        # Confirm profile first
        with _as_user(complete_user):
            await async_test_client.post("/api/auth/confirm-profile")
            response = await async_test_client.get("/api/auth/profile-history")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["change_type"] == "confirmation"

    @pytest.mark.asyncio
    async def test_non_superadmin_cannot_view_others_history(
        self, async_test_client, async_test_db
    ):
        complete_user = await _aseed_complete_user(async_test_db)
        incomplete_user = await _aseed_incomplete_user(async_test_db)
        with _as_user(complete_user):
            response = await async_test_client.get(
                f"/api/auth/profile-history?user_id={incomplete_user.id}"
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_superadmin_can_view_others_history(
        self, async_test_client, async_test_db
    ):
        admin_user = await _aseed_admin_user(async_test_db)
        complete_user = await _aseed_complete_user(async_test_db)
        with _as_user(admin_user):
            response = await async_test_client.get(
                f"/api/auth/profile-history?user_id={complete_user.id}"
            )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_pagination(self, async_test_client, async_test_db):
        complete_user = await _aseed_complete_user(async_test_db)
        # Create multiple history entries
        for i in range(5):
            entry = UserProfileHistory(
                id=f"history-{i}",
                user_id=complete_user.id,
                change_type="update",
                snapshot={"age": 24 + i},
                changed_fields=["age"],
            )
            async_test_db.add(entry)
        await async_test_db.commit()

        with _as_user(complete_user):
            response = await async_test_client.get(
                "/api/auth/profile-history?limit=2&offset=0"
            )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        with _as_user(complete_user):
            response2 = await async_test_client.get(
                "/api/auth/profile-history?limit=2&offset=2"
            )
        data2 = response2.json()
        assert len(data2) == 2

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, async_test_client):
        response = await async_test_client.get("/api/auth/profile-history")
        assert response.status_code in (401, 403)


# === Tests for profile update with history tracking ===


class TestProfileUpdateHistoryTracking:
    def test_profile_update_creates_history_entry(self, client, test_db, complete_user):
        response = client.put(
            "/api/auth/profile",
            json={"age": 30},
            headers={"Authorization": f"Bearer {complete_user.token}"},
        )
        assert response.status_code == 200

        entries = (
            test_db.query(UserProfileHistory)
            .filter(UserProfileHistory.user_id == complete_user.id)
            .filter(UserProfileHistory.change_type == "update")
            .all()
        )
        assert len(entries) >= 1
        latest = entries[-1]
        assert "age" in latest.changed_fields

    def test_profile_update_with_gender(self, client, complete_user):
        response = client.put(
            "/api/auth/profile",
            json={"gender": "divers"},
            headers={"Authorization": f"Bearer {complete_user.token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["gender"] == "divers"

    def test_profile_update_with_invalid_gender_rejected(self, client, complete_user):
        response = client.put(
            "/api/auth/profile",
            json={"gender": "invalid_gender"},
            headers={"Authorization": f"Bearer {complete_user.token}"},
        )
        assert response.status_code == 400

    def test_profile_update_with_psychometric_scales(self, client, complete_user):
        new_ati = {"item_1": 7, "item_2": 6, "item_3": 5, "item_4": 4}
        response = client.put(
            "/api/auth/profile",
            json={"ati_s_scores": new_ati},
            headers={"Authorization": f"Bearer {complete_user.token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ati_s_scores"] == new_ati

    def test_profile_update_invalid_psychometric_rejected(self, client, complete_user):
        bad_scale = {"item_1": 8, "item_2": 4, "item_3": 5, "item_4": 6}
        response = client.put(
            "/api/auth/profile",
            json={"ati_s_scores": bad_scale},
            headers={"Authorization": f"Bearer {complete_user.token}"},
        )
        assert response.status_code == 400

    def test_profile_update_sets_mandatory_completed(self, client, test_db, incomplete_user):
        # Fill in all missing fields for a law_student
        update = {
            "gender": "maennlich",
            "age": 25,
            "subjective_competence_civil": 5,
            "subjective_competence_public": 4,
            "subjective_competence_criminal": 3,
            "grade_zwischenpruefung": 2.3,
            "grade_vorgeruecktenubung": 2.5,
            "ati_s_scores": VALID_SCALES["ati_s"],
            "ptt_a_scores": VALID_SCALES["ptt_a"],
            "ki_experience_scores": VALID_SCALES["ki_exp"],
        }
        response = client.put(
            "/api/auth/profile",
            json=update,
            headers={"Authorization": f"Bearer {incomplete_user.token}"},
        )
        assert response.status_code == 200

        # Check mandatory_profile_completed is now True
        test_db.refresh(incomplete_user)
        assert incomplete_user.mandatory_profile_completed == True  # noqa: E712

    def test_profile_update_with_grades(self, client, complete_user):
        response = client.put(
            "/api/auth/profile",
            json={
                "grade_zwischenpruefung": 1.7,
                "grade_vorgeruecktenubung": 2.0,
            },
            headers={"Authorization": f"Bearer {complete_user.token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["grade_zwischenpruefung"] == 1.7
        assert data["grade_vorgeruecktenubung"] == 2.0

    def test_profile_update_subjective_competence(self, client, complete_user):
        response = client.put(
            "/api/auth/profile",
            json={
                "subjective_competence_civil": 7,
                "subjective_competence_public": 1,
                "subjective_competence_criminal": 4,
            },
            headers={"Authorization": f"Bearer {complete_user.token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["subjective_competence_civil"] == 7
        assert data["subjective_competence_public"] == 1
        assert data["subjective_competence_criminal"] == 4


# === Tests for create_user with mandatory profile fields ===


class TestCreateUserWithProfile:
    def test_create_user_with_all_mandatory_fields(self, test_db):
        from auth_module.user_service import create_user

        user = create_user(
            db=test_db,
            username="newuser",
            email="newuser@test.com",
            name="New User",
            password="securepassword123",
            legal_expertise_level="layperson",
            german_proficiency="native",
            gender="maennlich",
            age=30,
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores=VALID_SCALES["ati_s"],
            ptt_a_scores=VALID_SCALES["ptt_a"],
            ki_experience_scores=VALID_SCALES["ki_exp"],
        )
        assert user.mandatory_profile_completed == True  # noqa: E712
        assert user.profile_confirmed_at != None  # noqa: E711
        assert user.gender == "maennlich"
        assert user.age == 30

    def test_create_user_without_mandatory_fields(self, test_db):
        from auth_module.user_service import create_user

        user = create_user(
            db=test_db,
            username="basicuser2",
            email="basicuser2@test.com",
            name="Basic User",
            password="securepassword123",
        )
        assert user.mandatory_profile_completed == False  # noqa: E712
        assert user.profile_confirmed_at == None  # noqa: E711

    def test_create_user_invalid_gender_rejected(self, test_db):
        from fastapi import HTTPException

        from auth_module.user_service import create_user

        with pytest.raises(HTTPException) as exc_info:
            create_user(
                db=test_db,
                username="badgender",
                email="badgender@test.com",
                name="Bad Gender",
                password="securepassword123",
                gender="invalid",
            )
        assert exc_info.value.status_code == 400
        assert "Invalid gender" in exc_info.value.detail

    def test_create_user_invalid_psychometric_rejected(self, test_db):
        from fastapi import HTTPException

        from auth_module.user_service import create_user

        with pytest.raises(HTTPException) as exc_info:
            create_user(
                db=test_db,
                username="badscale",
                email="badscale@test.com",
                name="Bad Scale",
                password="securepassword123",
                ati_s_scores={"item_1": 10, "item_2": 4, "item_3": 5, "item_4": 6},
            )
        assert exc_info.value.status_code == 400

    def test_create_user_signup_creates_history(self, test_db):
        from auth_module.user_service import create_user

        user = create_user(
            db=test_db,
            username="histuser",
            email="histuser@test.com",
            name="History User",
            password="securepassword123",
            legal_expertise_level="layperson",
            german_proficiency="native",
            gender="divers",
            age=28,
            subjective_competence_civil=4,
            subjective_competence_public=3,
            subjective_competence_criminal=5,
            ati_s_scores=VALID_SCALES["ati_s"],
            ptt_a_scores=VALID_SCALES["ptt_a"],
            ki_experience_scores=VALID_SCALES["ki_exp"],
        )
        entries = (
            test_db.query(UserProfileHistory).filter(UserProfileHistory.user_id == user.id).all()
        )
        assert len(entries) >= 1
        assert entries[0].change_type == "signup"
        assert "all" in entries[0].changed_fields


# === Tests for confirm_profile service function ===


class TestConfirmProfileService:
    def test_confirm_sets_timestamp(self, test_db, complete_user):
        from auth_module.user_service import confirm_profile

        old_confirmed = complete_user.profile_confirmed_at
        updated = confirm_profile(test_db, complete_user.id)
        assert updated is not None
        assert updated.profile_confirmed_at != None  # noqa: E711
        assert updated.profile_confirmed_at > old_confirmed

    def test_confirm_creates_history(self, test_db, complete_user):
        from auth_module.user_service import confirm_profile

        confirm_profile(test_db, complete_user.id)
        entries = (
            test_db.query(UserProfileHistory)
            .filter(UserProfileHistory.user_id == complete_user.id)
            .filter(UserProfileHistory.change_type == "confirmation")
            .all()
        )
        assert len(entries) == 1

    def test_confirm_nonexistent_user_returns_none(self, test_db):
        from auth_module.user_service import confirm_profile

        result = confirm_profile(test_db, "nonexistent-id")
        assert result is None


# === Tests for update_user_profile with Issue #1206 fields ===


class TestUpdateUserProfileService:
    def test_update_gender(self, test_db, complete_user):
        from auth_module.user_service import update_user_profile

        updated = update_user_profile(test_db, complete_user.id, gender="divers")
        assert updated.gender == "divers"

    def test_update_invalid_gender(self, test_db, complete_user):
        from fastapi import HTTPException

        from auth_module.user_service import update_user_profile

        with pytest.raises(HTTPException) as exc_info:
            update_user_profile(test_db, complete_user.id, gender="invalid")
        assert exc_info.value.status_code == 400

    def test_update_competence_scores(self, test_db, complete_user):
        from auth_module.user_service import update_user_profile

        updated = update_user_profile(
            test_db,
            complete_user.id,
            subjective_competence_civil=7,
            subjective_competence_public=1,
            subjective_competence_criminal=4,
        )
        assert updated.subjective_competence_civil == 7
        assert updated.subjective_competence_public == 1
        assert updated.subjective_competence_criminal == 4

    def test_update_grades(self, test_db, complete_user):
        from auth_module.user_service import update_user_profile

        updated = update_user_profile(
            test_db,
            complete_user.id,
            grade_zwischenpruefung=1.0,
            grade_vorgeruecktenubung=1.3,
        )
        assert float(updated.grade_zwischenpruefung) == 1.0
        assert float(updated.grade_vorgeruecktenubung) == 1.3

    def test_update_psychometric_scales(self, test_db, complete_user):
        from auth_module.user_service import update_user_profile

        new_scales = {"item_1": 1, "item_2": 2, "item_3": 3, "item_4": 4}
        updated = update_user_profile(
            test_db,
            complete_user.id,
            ati_s_scores=new_scales,
            ptt_a_scores=new_scales,
            ki_experience_scores=new_scales,
        )
        assert updated.ati_s_scores == new_scales
        assert updated.ptt_a_scores == new_scales
        assert updated.ki_experience_scores == new_scales

    def test_update_invalid_psychometric_rejected(self, test_db, complete_user):
        from fastapi import HTTPException

        from auth_module.user_service import update_user_profile

        with pytest.raises(HTTPException):
            update_user_profile(
                test_db,
                complete_user.id,
                ptt_a_scores={"item_1": 0, "item_2": 4, "item_3": 5, "item_4": 6},
            )

    def test_update_creates_history_with_diff(self, test_db, complete_user):
        from auth_module.user_service import update_user_profile

        update_user_profile(test_db, complete_user.id, age=99)
        entries = (
            test_db.query(UserProfileHistory)
            .filter(UserProfileHistory.user_id == complete_user.id)
            .filter(UserProfileHistory.change_type == "update")
            .all()
        )
        assert len(entries) >= 1
        latest = entries[-1]
        assert "age" in latest.changed_fields
        assert latest.snapshot["age"] == 99

    def test_update_completes_mandatory_profile(self, test_db, incomplete_user):
        from auth_module.user_service import update_user_profile

        update_user_profile(
            test_db,
            incomplete_user.id,
            gender="keine_angabe",
            age=22,
            subjective_competence_civil=4,
            subjective_competence_public=3,
            subjective_competence_criminal=5,
            grade_zwischenpruefung=2.0,
            grade_vorgeruecktenubung=2.3,
            ati_s_scores=VALID_SCALES["ati_s"],
            ptt_a_scores=VALID_SCALES["ptt_a"],
            ki_experience_scores=VALID_SCALES["ki_exp"],
        )
        test_db.refresh(incomplete_user)
        assert incomplete_user.mandatory_profile_completed == True  # noqa: E712

    def test_no_change_no_history(self, test_db, complete_user):
        from auth_module.user_service import update_user_profile

        # Update with same values — no diff should mean no history entry
        update_user_profile(test_db, complete_user.id, age=complete_user.age)
        entries = (
            test_db.query(UserProfileHistory)
            .filter(UserProfileHistory.user_id == complete_user.id)
            .filter(UserProfileHistory.change_type == "update")
            .all()
        )
        assert len(entries) == 0

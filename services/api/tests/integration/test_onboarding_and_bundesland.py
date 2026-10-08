"""PUT /auth/me/onboarding and the exam Bundesland profile field.

- ``PUT /auth/me/onboarding`` deep-merges into users.onboarding_state: each
  writer (setup modal, a tour tier) keeps the other keys; ``reset_tours``
  drops the stored tour versions first; the shape is bounded.
- ``exam_bundesland`` round-trips through PUT/GET /auth/profile, only takes
  the 16 state codes, and shows up on /auth/me so the frontend has it on boot.
"""

import pytest

from tests.integration.test_auth_body_coverage import _as_user, _aseed_user


@pytest.mark.integration
class TestOnboardingState:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_rejected(self, async_test_client):
        resp = await async_test_client.put("/api/auth/me/onboarding", json={})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_fresh_user_has_no_state_on_me(self, async_test_client, async_test_db):
        user = await _aseed_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["onboarding_state"] is None

    @pytest.mark.asyncio
    async def test_writes_merge_and_surface_on_me(self, async_test_client, async_test_db):
        user = await _aseed_user(async_test_db)
        with _as_user(user):
            r1 = await async_test_client.put(
                "/api/auth/me/onboarding",
                json={"setup_completed_at": "2026-10-08T10:00:00+00:00"},
            )
            r2 = await async_test_client.put(
                "/api/auth/me/onboarding", json={"tours": {"student": 1}}
            )
            r3 = await async_test_client.put(
                "/api/auth/me/onboarding", json={"tours": {"contributor": 2}}
            )
            me = await async_test_client.get("/api/auth/me")
        assert r1.status_code == r2.status_code == r3.status_code == 200
        expected = {
            "setup_completed_at": "2026-10-08T10:00:00+00:00",
            "tours": {"student": 1, "contributor": 2},
        }
        assert r3.json()["onboarding_state"] == expected
        assert me.json()["onboarding_state"] == expected

    @pytest.mark.asyncio
    async def test_reset_tours_keeps_setup(self, async_test_client, async_test_db):
        user = await _aseed_user(
            async_test_db,
            onboarding_state={"setup_skipped": True, "tours": {"annotator": 1}},
        )
        with _as_user(user):
            resp = await async_test_client.put(
                "/api/auth/me/onboarding", json={"reset_tours": True}
            )
        assert resp.status_code == 200
        assert resp.json()["onboarding_state"] == {"setup_skipped": True}

    @pytest.mark.asyncio
    async def test_unknown_keys_are_dropped(self, async_test_client, async_test_db):
        user = await _aseed_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.put(
                "/api/auth/me/onboarding",
                json={"setup_skipped": True, "is_superadmin": True},
            )
        assert resp.status_code == 200
        assert resp.json()["onboarding_state"] == {"setup_skipped": True}
        assert resp.json()["is_superadmin"] is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "body",
        [
            {"tours": {"student": "one"}},
            {"tours": {f"tier{i}": 1 for i in range(17)}},
            {"setup_completed_at": "x" * 41},
        ],
    )
    async def test_invalid_shapes_are_422(self, async_test_client, async_test_db, body):
        user = await _aseed_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.put("/api/auth/me/onboarding", json=body)
        assert resp.status_code == 422


@pytest.mark.integration
class TestExamBundesland:
    def test_profile_round_trip(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            "/api/auth/profile",
            json={"exam_bundesland": "NW"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["exam_bundesland"] == "NW"

        # Another profile save without the field keeps it.
        resp = client.put(
            "/api/auth/profile",
            json={"name": "Still NRW"},
            headers=auth_headers["admin"],
        )
        assert resp.json()["exam_bundesland"] == "NW"

    @pytest.mark.parametrize("bad", ["XX", "nw", "Bayern", ""])
    def test_unknown_codes_are_422(self, client, test_db, test_users, auth_headers, bad):
        resp = client.put(
            "/api/auth/profile",
            json={"exam_bundesland": bad},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_surfaces_on_me(self, async_test_client, async_test_db):
        user = await _aseed_user(async_test_db, exam_bundesland="BY")
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me")
        assert resp.json()["exam_bundesland"] == "BY"

"""Branch-coverage integration tests for the notifications router.

Targets the error/edge/filter paths in ``services/api/routers/notifications.py``
that the happy-path suite in ``test_remaining_router_endpoints.py`` does not
exercise:

- ``get_notifications``: ``limit`` clamping (>100 → 100, <1 → 1), the ``offset``
  pagination branch, the ``unread_only`` filter, and the per-user isolation
  (another user's notifications are never returned).
- ``mark_notification_read``: the cross-user access-denied 404 (the row exists
  but belongs to a different user) and the persisted ``is_read`` flip on the
  success path.
- ``mark_all_read``: only the caller's unread rows flip, the count is reported,
  and another user's rows are untouched.
- ``get_notification_preferences`` / ``update_notification_preferences``
  (POST + PUT alias): the per-channel dict shape, the legacy bool shape, the
  invalid-type-skipped branch, and the persisted ``UserNotificationPreference``
  rows.
- ``create_test_notification``: the multi-count loop + the
  ``in_app`` preference suppression branch (a disabled in-app channel means no
  notification row is created).
- ``create_admin_test_notification`` / ``generate_all_test_notifications``: the
  superadmin-only 403 guard.
- bulk mark-read / bulk delete: per-user scoping + persisted state.
- ``get_notification_groups``: the invalid ``group_by`` 400 + a valid grouping.
- ``get_notification_summary``: the ``days`` clamp + the type-count aggregation.

Every test calls the endpoint through the ``client`` fixture, asserts the HTTP
status + response JSON, and verifies persisted DB state via ``test_db``.
"""

import uuid
from typing import List

import pytest
from sqlalchemy.orm import Session

from models import Notification, NotificationType, User, UserNotificationPreference


def _uid() -> str:
    return str(uuid.uuid4())


def _seed_notification(
    test_db: Session,
    user: User,
    *,
    is_read: bool = False,
    ntype: NotificationType = NotificationType.SYSTEM_ALERT,
    title: str = "Test Notification",
    organization_id: str = None,
) -> Notification:
    n = Notification(
        id=_uid(),
        user_id=user.id,
        organization_id=organization_id,
        type=ntype,
        title=title,
        message="This is a test notification",
        data={"test": True},
        is_read=is_read,
    )
    test_db.add(n)
    test_db.commit()
    return n


# ---------------------------------------------------------------------------
# get_notifications — GET /api/notifications/
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetNotifications:
    def test_limit_clamped_above_max(
        self, client, test_db, test_users, auth_headers
    ):
        """limit > 100 is clamped to 100 (no 422); request still succeeds."""
        admin = test_users[0]
        _seed_notification(test_db, admin)
        resp = client.get(
            "/api/notifications/?limit=500",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json(), list)

    def test_limit_clamped_below_min(
        self, client, test_db, test_users, auth_headers
    ):
        """limit < 1 is clamped to 1 → at most one row returned."""
        admin = test_users[0]
        _seed_notification(test_db, admin)
        _seed_notification(test_db, admin)
        resp = client.get(
            "/api/notifications/?limit=0",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) == 1

    def test_offset_paginates(self, client, test_db, test_users, auth_headers):
        """offset skips rows; with 3 rows and offset=2/limit=20 exactly one is
        returned."""
        admin = test_users[0]
        for _ in range(3):
            _seed_notification(test_db, admin)
        resp = client.get(
            "/api/notifications/?offset=2&limit=20",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) == 1

    def test_unread_only_excludes_read(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        _seed_notification(test_db, admin, is_read=False)
        _seed_notification(test_db, admin, is_read=True)
        resp = client.get(
            "/api/notifications/?unread_only=true",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body  # at least the unread one
        assert all(n["is_read"] is False for n in body)

    def test_other_users_notifications_excluded(
        self, client, test_db, test_users, auth_headers
    ):
        """A notification owned by the contributor is never returned to the
        admin (per-user scoping)."""
        admin, contributor = test_users[0], test_users[1]
        own = _seed_notification(test_db, admin, title="admin-own")
        _seed_notification(test_db, contributor, title="contrib-own")
        resp = client.get("/api/notifications/", headers=auth_headers["admin"])
        assert resp.status_code == 200, resp.text
        ids = {n["id"] for n in resp.json()}
        assert own.id in ids
        assert all(n["title"] != "contrib-own" for n in resp.json())


# ---------------------------------------------------------------------------
# mark_notification_read — POST /api/notifications/mark-read/{id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMarkNotificationRead:
    def test_cross_user_notification_returns_404(
        self, client, test_db, test_users, auth_headers
    ):
        """A real notification owned by the contributor cannot be marked read by
        the admin — the service filters by (id, user_id), returns False → 404,
        and the row stays unread."""
        contributor = test_users[1]
        n = _seed_notification(test_db, contributor, is_read=False)
        resp = client.post(
            f"/api/notifications/mark-read/{n.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"].lower()
        test_db.refresh(n)
        assert n.is_read is False

    def test_unknown_notification_returns_404(
        self, client, test_db, test_users, auth_headers
    ):
        resp = client.post(
            f"/api/notifications/mark-read/missing-{_uid()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text

    def test_mark_read_persists_flag(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        n = _seed_notification(test_db, admin, is_read=False)
        resp = client.post(
            f"/api/notifications/mark-read/{n.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert "marked as read" in resp.json()["message"].lower()
        test_db.refresh(n)
        assert n.is_read is True


# ---------------------------------------------------------------------------
# mark_all_read — POST /api/notifications/mark-all-read
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMarkAllRead:
    def test_marks_only_own_unread(
        self, client, test_db, test_users, auth_headers
    ):
        """Two admin unread + one contributor unread → admin's two flip, the
        contributor's stays unread, and the count is 2."""
        admin, contributor = test_users[0], test_users[1]
        a1 = _seed_notification(test_db, admin, is_read=False)
        a2 = _seed_notification(test_db, admin, is_read=False)
        c1 = _seed_notification(test_db, contributor, is_read=False)

        resp = client.post(
            "/api/notifications/mark-all-read",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert "marked 2" in resp.json()["message"].lower()

        for n in (a1, a2):
            test_db.refresh(n)
            assert n.is_read is True
        test_db.refresh(c1)
        assert c1.is_read is False

    def test_mark_all_read_with_nothing_unread(
        self, client, test_db, test_users, auth_headers
    ):
        """No unread rows → count 0, still 200."""
        admin = test_users[0]
        _seed_notification(test_db, admin, is_read=True)
        resp = client.post(
            "/api/notifications/mark-all-read",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert "marked 0" in resp.json()["message"].lower()


# ---------------------------------------------------------------------------
# unread-count — GET /api/notifications/unread-count
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUnreadCount:
    def test_counts_only_own_unread(
        self, client, test_db, test_users, auth_headers
    ):
        admin, contributor = test_users[0], test_users[1]
        _seed_notification(test_db, admin, is_read=False)
        _seed_notification(test_db, admin, is_read=True)
        _seed_notification(test_db, contributor, is_read=False)
        resp = client.get(
            "/api/notifications/unread-count",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["count"] == 1


# ---------------------------------------------------------------------------
# preferences — GET + POST + PUT
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPreferences:
    def test_get_preferences_returns_full_default_map(
        self, client, test_db, test_users, auth_headers
    ):
        """No persisted rows → every NotificationType defaults to in_app on,
        email off."""
        resp = client.get(
            "/api/notifications/preferences",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        prefs = resp.json()["preferences"]
        assert prefs[NotificationType.SYSTEM_ALERT.value] == {
            "enabled": True,
            "in_app": True,
            "email": False,
        }

    def test_update_per_channel_shape_persists(
        self, client, test_db, test_users, auth_headers
    ):
        """Dict-shaped {enabled,in_app,email} value persists a
        UserNotificationPreference row with the matching channel flags."""
        admin = test_users[0]
        resp = client.post(
            "/api/notifications/preferences",
            json={
                "preferences": {
                    NotificationType.SYSTEM_ALERT.value: {
                        "enabled": True,
                        "in_app": False,
                        "email": True,
                    }
                }
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert "updated" in resp.json()["message"].lower()

        pref = (
            test_db.query(UserNotificationPreference)
            .filter(
                UserNotificationPreference.user_id == admin.id,
                UserNotificationPreference.notification_type
                == NotificationType.SYSTEM_ALERT.value,
            )
            .first()
        )
        assert pref is not None
        assert pref.in_app_enabled is False
        assert pref.email_enabled is True

        # And the GET reflects it.
        get_resp = client.get(
            "/api/notifications/preferences",
            headers=auth_headers["admin"],
        )
        prefs = get_resp.json()["preferences"]
        assert prefs[NotificationType.SYSTEM_ALERT.value] == {
            "enabled": True,
            "in_app": False,
            "email": True,
        }

    def test_update_legacy_bool_shape_sets_both_channels(
        self, client, test_db, test_users, auth_headers
    ):
        """Legacy `{type: false}` sets BOTH channels to False on a persisted
        row."""
        admin = test_users[0]
        resp = client.post(
            "/api/notifications/preferences",
            json={"preferences": {NotificationType.SYSTEM_ALERT.value: False}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        pref = (
            test_db.query(UserNotificationPreference)
            .filter(
                UserNotificationPreference.user_id == admin.id,
                UserNotificationPreference.notification_type
                == NotificationType.SYSTEM_ALERT.value,
            )
            .first()
        )
        assert pref is not None
        assert pref.in_app_enabled is False
        assert pref.email_enabled is False

    def test_update_invalid_type_skipped_still_200(
        self, client, test_db, test_users, auth_headers
    ):
        """An unknown notification type is skipped (logged) but the update
        still returns 200 and persists nothing for the bogus key."""
        admin = test_users[0]
        resp = client.post(
            "/api/notifications/preferences",
            json={"preferences": {"totally_not_a_type": True}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        rows = (
            test_db.query(UserNotificationPreference)
            .filter(
                UserNotificationPreference.user_id == admin.id,
                UserNotificationPreference.notification_type == "totally_not_a_type",
            )
            .all()
        )
        assert rows == []

    def test_put_alias_updates_existing_row(
        self, client, test_db, test_users, auth_headers
    ):
        """The PUT alias re-uses the POST handler; updating an existing pref row
        overwrites (does not duplicate) it."""
        admin = test_users[0]
        # Seed an existing row directly.
        test_db.add(UserNotificationPreference(
            id=_uid(),
            user_id=admin.id,
            notification_type=NotificationType.SYSTEM_ALERT.value,
            in_app_enabled=True,
            email_enabled=False,
        ))
        test_db.commit()

        resp = client.put(
            "/api/notifications/preferences",
            json={
                "preferences": {
                    NotificationType.SYSTEM_ALERT.value: {
                        "enabled": True,
                        "in_app": True,
                        "email": True,
                    }
                }
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text

        rows = (
            test_db.query(UserNotificationPreference)
            .filter(
                UserNotificationPreference.user_id == admin.id,
                UserNotificationPreference.notification_type
                == NotificationType.SYSTEM_ALERT.value,
            )
            .all()
        )
        assert len(rows) == 1  # updated in place, not duplicated
        assert rows[0].email_enabled is True


# ---------------------------------------------------------------------------
# create_test_notification — POST /api/notifications/test
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateTestNotification:
    def test_count_creates_multiple_rows(
        self, client, test_db, test_users, auth_headers
    ):
        """count=3 fans out into three persisted notification rows for the
        caller."""
        admin = test_users[0]
        resp = client.post(
            "/api/notifications/test",
            json={"notification_type": "system_alert", "count": 3},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert len(body["notification_ids"]) == 3

        persisted = (
            test_db.query(Notification)
            .filter(Notification.id.in_(body["notification_ids"]))
            .all()
        )
        assert len(persisted) == 3
        assert all(n.user_id == admin.id for n in persisted)

    def test_invalid_type_defaults_to_system_alert(
        self, client, test_db, test_users, auth_headers
    ):
        """An unrecognised notification_type falls back to system_alert."""
        resp = client.post(
            "/api/notifications/test",
            json={"notification_type": "not_a_real_type", "count": 1},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["type"] == NotificationType.SYSTEM_ALERT.value

    def test_in_app_disabled_suppresses_row(
        self, client, test_db, test_users, auth_headers
    ):
        """With in_app disabled for system_alert, create_notification skips the
        user → zero rows created even though the endpoint reports success."""
        admin = test_users[0]
        test_db.add(UserNotificationPreference(
            id=_uid(),
            user_id=admin.id,
            notification_type=NotificationType.SYSTEM_ALERT.value,
            in_app_enabled=False,
            email_enabled=False,
        ))
        test_db.commit()

        resp = client.post(
            "/api/notifications/test",
            json={"notification_type": "system_alert", "count": 2},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Service skipped every recipient → no ids returned.
        assert body["notification_ids"] == []

        count = (
            test_db.query(Notification)
            .filter(
                Notification.user_id == admin.id,
                Notification.type == NotificationType.SYSTEM_ALERT,
            )
            .count()
        )
        assert count == 0


# ---------------------------------------------------------------------------
# admin-only test notification endpoints — 403 guards
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdminTestNotificationGuards:
    def test_create_admin_test_non_superadmin_forbidden(
        self, client, test_db, test_users, auth_headers
    ):
        resp = client.post(
            "/api/notifications/test/create",
            json={"type": "system_alert", "title": "T", "message": "M"},
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403, resp.text
        assert "superadmin" in resp.json()["detail"].lower()

    def test_create_admin_test_superadmin_succeeds(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        resp = client.post(
            "/api/notifications/test/create",
            json={"type": "system_alert", "title": "Hello", "message": "World"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        nid = body["notification_id"]
        assert nid is not None
        n = test_db.query(Notification).filter(Notification.id == nid).first()
        assert n is not None
        assert n.user_id == admin.id
        assert n.title == "Hello"

    def test_generate_all_non_superadmin_forbidden(
        self, client, test_db, test_users, auth_headers
    ):
        resp = client.post(
            "/api/notifications/test/generate-all",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403, resp.text
        assert "superadmin" in resp.json()["detail"].lower()

    def test_generate_all_superadmin_creates_many(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        resp = client.post(
            "/api/notifications/test/generate-all",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["count"] >= 1
        # Several distinct types persisted for the admin.
        persisted = (
            test_db.query(Notification)
            .filter(Notification.user_id == admin.id)
            .count()
        )
        assert persisted >= 1


# ---------------------------------------------------------------------------
# bulk operations — POST /api/notifications/bulk/{mark-read,delete}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBulkOperations:
    def test_bulk_mark_read_scoped_to_owner(
        self, client, test_db, test_users, auth_headers
    ):
        """Only the admin's ids in the request flip; a contributor id passed in
        the same request is ignored (count reflects own rows only)."""
        admin, contributor = test_users[0], test_users[1]
        a1 = _seed_notification(test_db, admin, is_read=False)
        a2 = _seed_notification(test_db, admin, is_read=False)
        c1 = _seed_notification(test_db, contributor, is_read=False)

        resp = client.post(
            "/api/notifications/bulk/mark-read",
            json={"notification_ids": [a1.id, a2.id, c1.id]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["count"] == 2

        for n in (a1, a2):
            test_db.refresh(n)
            assert n.is_read is True
        test_db.refresh(c1)
        assert c1.is_read is False

    def test_bulk_delete_scoped_to_owner(
        self, client, test_db, test_users, auth_headers
    ):
        admin, contributor = test_users[0], test_users[1]
        a1 = _seed_notification(test_db, admin)
        c1 = _seed_notification(test_db, contributor)
        # Capture ids before the delete: a1's row is removed in this same
        # session, so touching a1.id afterwards raises ObjectDeletedError.
        a1_id, c1_id = a1.id, c1.id

        resp = client.post(
            "/api/notifications/bulk/delete",
            json={"notification_ids": [a1_id, c1_id]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["count"] == 1

        # admin's row gone, contributor's untouched.
        assert (
            test_db.query(Notification).filter(Notification.id == a1_id).first()
            is None
        )
        assert (
            test_db.query(Notification).filter(Notification.id == c1_id).first()
            is not None
        )


# ---------------------------------------------------------------------------
# groups — GET /api/notifications/groups
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestNotificationGroups:
    def test_invalid_group_by_returns_400(
        self, client, test_db, test_users, auth_headers
    ):
        resp = client.get(
            "/api/notifications/groups?group_by=bogus",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400, resp.text
        assert "group_by" in resp.json()["detail"]

    def test_group_by_type_buckets_notifications(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        _seed_notification(test_db, admin, ntype=NotificationType.SYSTEM_ALERT)
        _seed_notification(test_db, admin, ntype=NotificationType.SYSTEM_ALERT)
        _seed_notification(test_db, admin, ntype=NotificationType.ERROR_OCCURRED)

        resp = client.get(
            "/api/notifications/groups?group_by=type",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        groups = resp.json()["groups"]
        assert len(groups[NotificationType.SYSTEM_ALERT.value]) == 2
        assert len(groups[NotificationType.ERROR_OCCURRED.value]) == 1


# ---------------------------------------------------------------------------
# summary — GET /api/notifications/summary
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestNotificationSummary:
    def test_days_clamped_above_max(
        self, client, test_db, test_users, auth_headers
    ):
        """days > 90 is clamped to 90 in the response."""
        resp = client.get(
            "/api/notifications/summary?days=365",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["period_days"] == 90

    def test_days_clamped_below_min(
        self, client, test_db, test_users, auth_headers
    ):
        resp = client.get(
            "/api/notifications/summary?days=0",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["period_days"] == 1

    def test_summary_counts_and_type_breakdown(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        _seed_notification(
            test_db, admin, is_read=False, ntype=NotificationType.SYSTEM_ALERT
        )
        _seed_notification(
            test_db, admin, is_read=True, ntype=NotificationType.SYSTEM_ALERT
        )
        _seed_notification(
            test_db, admin, is_read=False, ntype=NotificationType.ERROR_OCCURRED
        )

        resp = client.get(
            "/api/notifications/summary?days=7",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_notifications"] == 3
        assert body["unread_notifications"] == 2
        assert body["read_notifications"] == 1
        assert body["period_days"] == 7
        by_type = body["notifications_by_type"]
        assert by_type[NotificationType.SYSTEM_ALERT.value] == 2
        assert by_type[NotificationType.ERROR_OCCURRED.value] == 1

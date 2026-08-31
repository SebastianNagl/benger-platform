"""Tests for the org storage connections router (cloud imports).

Targets: routers/org_storage_connections.py — the authz matrix (member vs
admin vs outsider), strict secret masking (the secret key never appears in
any response, the access key only as a last-4 hint), endpoint_url
validation, and the server-side browse endpoint with a mocked boto3 client.

Mirrors ``test_org_api_keys_router.py``: async DB lane fixtures
(``async_test_db`` / ``async_test_client``) with seeded identities driven
through ``require_user`` overrides; the S3 layer is patched at the shared
``org_storage_connection_service`` module (which the router imports as a
module, so a patch there is seen by the handler).
"""

import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    OrgStorageConnection,
    User as DBUser,
)

import org_storage_connection_service as storage_conn_service


@contextmanager
def _as_user(db_user):
    """Override require_user with an auth identity built from a seeded DB row."""
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


def _uid():
    return str(uuid.uuid4())


async def _seed_user(db, *, is_superadmin=False):
    u = DBUser(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@e.com",
        name="U",
        hashed_password="x",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_org(db):
    o = Organization(
        id=_uid(),
        name=f"org-{_uid()[:6]}",
        display_name="Org",
        slug=f"org-{_uid()[:8]}",
        is_active=True,
        settings={},
    )
    db.add(o)
    await db.flush()
    return o


async def _seed_member(db, user, org, role):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user.id,
        organization_id=org.id,
        role=role,
        is_active=True,
    )
    db.add(m)
    await db.flush()
    return m


async def _seed_connection(db, org, *, name="Bucket A", prefix="in/", created_by=None):
    conn = OrgStorageConnection(
        id=_uid(),
        organization_id=org.id,
        name=name,
        endpoint_url="https://minio.example.com:9000",
        bucket="customer-bucket",
        prefix=prefix,
        region=None,
        use_ssl=True,
        encrypted_access_key=storage_conn_service.encrypt_secret("AKIAFAKEF4K3"),
        encrypted_secret_key=storage_conn_service.encrypt_secret("very-secret-key"),
        created_by=created_by,
    )
    db.add(conn)
    await db.flush()
    return conn


_CREATE_BODY = {
    "name": "My bucket",
    "endpoint_url": "https://minio.example.com:9000",
    "bucket": "customer-bucket",
    "prefix": "exports/",
    "access_key": "AKIAFAKEF4K3",
    "secret_key": "very-secret-key",
}


def _assert_no_secrets(payload):
    """No response may ever carry the secret key, the full access key, or the
    encrypted blobs — in any key, at any nesting depth."""
    text = str(payload)
    assert "very-secret-key" not in text
    assert "AKIAFAKEF4K3" not in text  # only the last-4 hint is allowed
    assert "encrypted_access_key" not in text
    assert "encrypted_secret_key" not in text
    assert "secret_key" not in text
    assert "gAAAA" not in text  # Fernet ciphertext prefix


class TestAuthzMatrix:
    @pytest.mark.asyncio
    async def test_non_member_cannot_list(self, async_test_client, async_test_db):
        org = await _seed_org(async_test_db)
        outsider = await _seed_user(async_test_db)

        with _as_user(outsider):
            response = await async_test_client.get(
                f"/api/organizations/{org.id}/storage-connections"
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_non_member_cannot_browse(self, async_test_client, async_test_db):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org)
        outsider = await _seed_user(async_test_db)

        with _as_user(outsider):
            response = await async_test_client.get(
                f"/api/organizations/{org.id}/storage-connections/{conn.id}/objects"
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_member_can_list_but_not_mutate(
        self, async_test_client, async_test_db
    ):
        """A plain (annotator) member may list/browse but not create, update,
        delete, or test connections."""
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org)
        member = await _seed_user(async_test_db)
        await _seed_member(async_test_db, member, org, OrganizationRole.ANNOTATOR)

        base = f"/api/organizations/{org.id}/storage-connections"
        with _as_user(member):
            assert (await async_test_client.get(base)).status_code == 200

            assert (
                await async_test_client.post(base, json=dict(_CREATE_BODY))
            ).status_code == status.HTTP_403_FORBIDDEN
            assert (
                await async_test_client.put(
                    f"{base}/{conn.id}", json={"name": "Renamed"}
                )
            ).status_code == status.HTTP_403_FORBIDDEN
            assert (
                await async_test_client.delete(f"{base}/{conn.id}")
            ).status_code == status.HTTP_403_FORBIDDEN
            assert (
                await async_test_client.post(f"{base}/test", json=dict(_CREATE_BODY))
            ).status_code == status.HTTP_403_FORBIDDEN
            assert (
                await async_test_client.post(f"{base}/{conn.id}/test")
            ).status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_org_admin_can_crud(self, async_test_client, async_test_db):
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db)
        await _seed_member(async_test_db, admin, org, OrganizationRole.ORG_ADMIN)

        base = f"/api/organizations/{org.id}/storage-connections"
        with _as_user(admin):
            created = await async_test_client.post(base, json=dict(_CREATE_BODY))
            assert created.status_code == 201
            conn_id = created.json()["id"]

            updated = await async_test_client.put(
                f"{base}/{conn_id}", json={"name": "Renamed"}
            )
            assert updated.status_code == 200
            assert updated.json()["name"] == "Renamed"

            deleted = await async_test_client.delete(f"{base}/{conn_id}")
            assert deleted.status_code == 200

    @pytest.mark.asyncio
    async def test_unknown_org_404(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db, is_superadmin=True)
        with _as_user(admin):
            response = await async_test_client.get(
                f"/api/organizations/{_uid()}/storage-connections"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_connection_of_other_org_404(self, async_test_client, async_test_db):
        """A connection id from another org resolves 404 (no cross-org leak)."""
        org_a = await _seed_org(async_test_db)
        org_b = await _seed_org(async_test_db)
        conn_b = await _seed_connection(async_test_db, org_b)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin):
            response = await async_test_client.delete(
                f"/api/organizations/{org_a.id}/storage-connections/{conn_b.id}"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestSecretMasking:
    @pytest.mark.asyncio
    async def test_create_response_masks_secrets(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/storage-connections",
                json=dict(_CREATE_BODY),
            )
        assert response.status_code == 201
        data = response.json()
        _assert_no_secrets(data)
        assert data["access_key_hint"] == "F4K3"
        assert data["name"] == "My bucket"
        assert data["bucket"] == "customer-bucket"
        assert data["prefix"] == "exports/"

    @pytest.mark.asyncio
    async def test_list_response_masks_secrets(self, async_test_client, async_test_db):
        org = await _seed_org(async_test_db)
        await _seed_connection(async_test_db, org)
        member = await _seed_user(async_test_db)
        await _seed_member(async_test_db, member, org, OrganizationRole.ANNOTATOR)

        with _as_user(member):
            response = await async_test_client.get(
                f"/api/organizations/{org.id}/storage-connections"
            )
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        _assert_no_secrets(rows)
        assert rows[0]["access_key_hint"] == "F4K3"

    @pytest.mark.asyncio
    async def test_update_without_credentials_keeps_stored_ones(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org)
        old_encrypted = conn.encrypted_secret_key
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin):
            response = await async_test_client.put(
                f"/api/organizations/{org.id}/storage-connections/{conn.id}",
                json={"name": "Renamed", "prefix": "other/"},
            )
        assert response.status_code == 200
        _assert_no_secrets(response.json())
        await async_test_db.refresh(conn)
        assert conn.encrypted_secret_key == old_encrypted
        assert conn.name == "Renamed"
        assert conn.prefix == "other/"

    @pytest.mark.asyncio
    async def test_duplicate_name_conflicts(self, async_test_client, async_test_db):
        org = await _seed_org(async_test_db)
        await _seed_connection(async_test_db, org, name="My bucket")
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/storage-connections",
                json=dict(_CREATE_BODY),
            )
        assert response.status_code == status.HTTP_409_CONFLICT


class TestEndpointUrlValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "endpoint_url",
        [
            "ftp://files.example.com",
            "not a url at all ://",
            "https://user:pass@minio.example.com",
            "https://minio.example.com/?x=1",
        ],
    )
    async def test_bad_endpoint_urls_rejected(
        self, async_test_client, async_test_db, endpoint_url
    ):
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        body = dict(_CREATE_BODY, endpoint_url=endpoint_url)
        with _as_user(admin):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/storage-connections", json=body
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_missing_required_fields_rejected(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        body = dict(_CREATE_BODY)
        body.pop("secret_key")
        with _as_user(admin):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/storage-connections", json=body
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_null_endpoint_url_means_aws_default(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        body = dict(_CREATE_BODY)
        body.pop("endpoint_url")
        with _as_user(admin):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/storage-connections", json=body
            )
        assert response.status_code == 201
        assert response.json()["endpoint_url"] is None

    def test_private_endpoint_rejected_only_when_env_falsy(self):
        """Default posture allows private endpoints (self-hosted MinIO); the
        explicit falsy env flips rejection on. Direct service-level check."""
        # Default (unset) → allowed.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORG_STORAGE_ALLOW_PRIVATE_ENDPOINTS", None)
            storage_conn_service.validate_endpoint_url("http://127.0.0.1:9000")

        # Explicitly falsy → loopback rejected.
        with patch.dict(
            os.environ, {"ORG_STORAGE_ALLOW_PRIVATE_ENDPOINTS": "false"}, clear=False
        ):
            with pytest.raises(ValueError):
                storage_conn_service.validate_endpoint_url("http://127.0.0.1:9000")
            with pytest.raises(ValueError):
                storage_conn_service.validate_endpoint_url("http://169.254.169.254/")


class TestBrowseEndpoint:
    @pytest.mark.asyncio
    async def test_member_browse_lists_objects(self, async_test_client, async_test_db):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org, prefix="in/")
        member = await _seed_user(async_test_db)
        await _seed_member(async_test_db, member, org, OrganizationRole.ANNOTATOR)

        s3 = MagicMock()
        s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "in/a.csv",
                    "Size": 42,
                    "LastModified": datetime(2026, 8, 1, tzinfo=timezone.utc),
                },
            ],
            "CommonPrefixes": [{"Prefix": "in/sub/"}],
            "IsTruncated": True,
            "NextContinuationToken": "tok-2",
        }

        with _as_user(member), patch.object(
            storage_conn_service, "build_client", return_value=s3
        ):
            response = await async_test_client.get(
                f"/api/organizations/{org.id}/storage-connections/{conn.id}/objects",
                params={"prefix": "in/", "max_results": 50},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["objects"] == [
            {"key": "in/a.csv", "size": 42, "last_modified": "2026-08-01T00:00:00+00:00"}
        ]
        assert data["prefixes"] == ["in/sub/"]
        assert data["next_token"] == "tok-2"
        # Delimiter-collapsed listing under the requested prefix.
        kwargs = s3.list_objects_v2.call_args.kwargs
        assert kwargs["Bucket"] == "customer-bucket"
        assert kwargs["Prefix"] == "in/"
        assert kwargs["Delimiter"] == "/"
        assert kwargs["MaxKeys"] == 50

    @pytest.mark.asyncio
    async def test_browse_prefix_jail(self, async_test_client, async_test_db):
        """A prefix outside the connection's configured prefix is a 400 — the
        client can never widen the browse scope."""
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org, prefix="in/")
        member = await _seed_user(async_test_db)
        await _seed_member(async_test_db, member, org, OrganizationRole.ANNOTATOR)

        s3 = MagicMock()
        with _as_user(member), patch.object(
            storage_conn_service, "build_client", return_value=s3
        ):
            response = await async_test_client.get(
                f"/api/organizations/{org.id}/storage-connections/{conn.id}/objects",
                params={"prefix": "other/"},
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        s3.list_objects_v2.assert_not_called()

    @pytest.mark.asyncio
    async def test_browse_default_prefix_is_connection_prefix(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org, prefix="jail/")
        member = await _seed_user(async_test_db)
        await _seed_member(async_test_db, member, org, OrganizationRole.ANNOTATOR)

        s3 = MagicMock()
        s3.list_objects_v2.return_value = {"Contents": [], "CommonPrefixes": []}
        with _as_user(member), patch.object(
            storage_conn_service, "build_client", return_value=s3
        ):
            response = await async_test_client.get(
                f"/api/organizations/{org.id}/storage-connections/{conn.id}/objects"
            )
        assert response.status_code == 200
        assert s3.list_objects_v2.call_args.kwargs["Prefix"] == "jail/"

    @pytest.mark.asyncio
    async def test_browse_backend_failure_is_generic_502(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org, prefix="")
        member = await _seed_user(async_test_db)
        await _seed_member(async_test_db, member, org, OrganizationRole.ANNOTATOR)

        s3 = MagicMock()
        s3.list_objects_v2.side_effect = RuntimeError(
            "http://internal-minio.cluster.local:9000 exploded"
        )
        with _as_user(member), patch.object(
            storage_conn_service, "build_client", return_value=s3
        ):
            response = await async_test_client.get(
                f"/api/organizations/{org.id}/storage-connections/{conn.id}/objects"
            )
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        # The internal hostname never leaks into the response.
        assert "internal-minio" not in response.text


class TestConnectionTestEndpoints:
    @pytest.mark.asyncio
    async def test_unsaved_test_uses_request_credentials(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin), patch.object(
            storage_conn_service,
            "test_connection",
            return_value={"ok": True, "message": "Connection successful"},
        ) as mock_test:
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/storage-connections/test",
                json=dict(_CREATE_BODY),
            )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert mock_test.call_args.kwargs["access_key"] == "AKIAFAKEF4K3"
        assert mock_test.call_args.kwargs["secret_key"] == "very-secret-key"

    @pytest.mark.asyncio
    async def test_saved_test_reports_error_status(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin), patch.object(
            storage_conn_service,
            "test_connection",
            return_value={"ok": False, "message": "Bucket not found"},
        ):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/storage-connections/{conn.id}/test"
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        assert body["message"] == "Bucket not found"


class TestServiceListObjects:
    """Direct service-level tests of list_objects with a mocked boto3 client."""

    def _conn(self, prefix="in/"):
        import types

        return types.SimpleNamespace(
            endpoint_url="https://minio.example.com",
            bucket="b",
            prefix=prefix,
            region=None,
            use_ssl=True,
            encrypted_access_key=storage_conn_service.encrypt_secret("ak"),
            encrypted_secret_key=storage_conn_service.encrypt_secret("sk"),
        )

    def test_jail_rejects_outside_prefix(self):
        with pytest.raises(ValueError):
            storage_conn_service.list_objects(self._conn(prefix="in/"), prefix="out/")

    def test_placeholder_key_hidden_and_token_passthrough(self):
        s3 = MagicMock()
        s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "in/", "Size": 0, "LastModified": None},
                {"Key": "in/x.json", "Size": 7, "LastModified": None},
            ],
            "IsTruncated": False,
        }
        with patch.object(storage_conn_service, "build_client", return_value=s3):
            result = storage_conn_service.list_objects(
                self._conn(), continuation_token="tok-1", max_keys=5
            )
        assert [o["key"] for o in result["objects"]] == ["in/x.json"]
        assert result["next_token"] is None
        assert s3.list_objects_v2.call_args.kwargs["ContinuationToken"] == "tok-1"

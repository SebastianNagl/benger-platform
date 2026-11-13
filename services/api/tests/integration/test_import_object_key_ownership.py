"""Import ``object_key`` ownership is an exact check on the minted layout.

The upload-URL endpoints mint ``imports/<yyyy>/<mm>/<owner>/<file name>``
(owner = project id for ``POST /{id}/imports``, user id for
``POST /project-imports``). The job endpoints used to accept any key under
``imports/`` that merely CONTAINED ``/<owner>/``, so a key naming the owner
at another depth, or with a ``..`` segment, passed. Only the exact layout
passes now. Keys minted before this change (no random part, any single-segment
file name) stay importable.

The key minting itself (``ObjectStorageService._get_file_key``) adds a random
component and reduces the client-supplied file name to a safe single segment.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Project


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed(db):
    user = User(
        id=_uid(),
        username=f"ik-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Importer",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    project = Project(
        id=_uid(),
        title="Key ownership",
        created_by=user.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    await db.commit()
    return user, project


def _bad_keys(owner: str):
    other = _uid()
    return [
        # the owner named at the wrong depth
        f"imports/2026/06/{other}/{owner}/20260601_120000_x.json",
        f"imports/{owner}/20260601_120000_x.json",
        # traversal out of another owner's prefix into this one
        f"imports/2026/06/{other}/../{owner}/20260601_120000_x.json",
        f"imports/2026/06/{owner}/../{other}/20260601_120000_x.json",
        f"imports/2026/06/{owner}/..",
        # nested below the owner, or not a date layout
        f"imports/2026/06/{owner}/sub/20260601_120000_x.json",
        f"imports/2026/6/{owner}/20260601_120000_x.json",
        f"imports/2026/06/{owner}/",
        f"/imports/2026/06/{owner}/20260601_120000_x.json",
    ]


def _good_keys(owner: str):
    return [
        # minted before this change: timestamp + raw single-segment name
        f"imports/2026/06/{owner}/20260601_120000_Meine Klausur (1).json",
        # minted now: timestamp + random part + sanitized name
        f"imports/2026/11/{owner}/20261113_120000_9f2c4a1b7d3e5f60_import.json",
    ]


async def _post(client, user, url, key):
    with _as_user(user), patch(
        "routers.projects.import_export.object_storage.get_file_info",
        return_value={"size": 100},
    ), patch(
        "routers.projects.import_export.send_task_safe",
        return_value=MagicMock(id="celery-x"),
    ) as mock_send:
        resp = await client.post(url, json={"object_key": key})
    return resp, mock_send


@pytest.mark.integration
class TestNestedImportKey:
    @pytest.mark.asyncio
    async def test_keys_outside_the_layout_are_rejected(
        self, async_test_client, async_test_db
    ):
        user, project = await _seed(async_test_db)
        url = f"/api/projects/{project.id}/imports"
        for key in _bad_keys(project.id):
            resp, mock_send = await _post(async_test_client, user, url, key)
            assert resp.status_code == 400, key
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_minted_keys_old_and_new_are_accepted(
        self, async_test_client, async_test_db
    ):
        user, project = await _seed(async_test_db)
        url = f"/api/projects/{project.id}/imports"
        for key in _good_keys(project.id):
            resp, _ = await _post(async_test_client, user, url, key)
            assert resp.status_code == 202, (key, resp.text)


@pytest.mark.integration
class TestFullImportKey:
    URL = "/api/projects/project-imports"

    @pytest.mark.asyncio
    async def test_keys_outside_the_layout_are_rejected(
        self, async_test_client, async_test_db
    ):
        user, _project = await _seed(async_test_db)
        for key in _bad_keys(user.id):
            resp, mock_send = await _post(async_test_client, user, self.URL, key)
            assert resp.status_code == 400, key
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_minted_keys_old_and_new_are_accepted(
        self, async_test_client, async_test_db
    ):
        user, _project = await _seed(async_test_db)
        for key in _good_keys(user.id):
            resp, _ = await _post(async_test_client, user, self.URL, key)
            assert resp.status_code == 202, (key, resp.text)


class TestMintedKeys:
    def _key(self, filename, owner="owner-1", file_type="imports"):
        from storage.object_storage import ObjectStorageService

        service = ObjectStorageService.__new__(ObjectStorageService)
        service.PREFIXES = {"imports": "imports/{year}/{month}"}
        return service._get_file_key(file_type, filename, owner)

    def test_key_has_the_owner_prefix_and_one_name_segment(self):
        key = self._key("import.json")
        parts = key.split("/")
        assert parts[0] == "imports" and parts[3] == "owner-1"
        assert len(parts) == 5
        assert parts[4].endswith("_import.json")

    def test_two_keys_for_the_same_file_differ(self):
        assert self._key("import.json") != self._key("import.json")

    @pytest.mark.parametrize(
        "filename",
        ["../../other/x.json", "a/b/c.json", "..\\..\\x.json", "..", ".hidden", ""],
    )
    def test_file_name_is_reduced_to_a_safe_segment(self, filename):
        key = self._key(filename)
        parts = key.split("/")
        assert len(parts) == 5, key
        assert ".." not in parts
        assert "\\" not in key
        name = parts[4]
        assert name and not name.startswith(".")

    def test_unsafe_characters_are_replaced_but_extension_kept(self):
        name = self._key('Klausur "1" <final>.json').split("/")[-1]
        assert name.endswith(".json")
        assert not set('"<>') & set(name)

    def test_long_names_are_capped(self):
        name = self._key("x" * 500 + ".json").split("/")[-1]
        assert len(name) <= 160
        assert name.endswith(".json")

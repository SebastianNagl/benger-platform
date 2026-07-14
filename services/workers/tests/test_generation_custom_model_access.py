"""Worker-side mid-run access guard for custom (BYOM) models.

_check_custom_model_access is the generation worker's re-check that the
invoking user can still use a custom model when a task-cell runs — it
catches share-revocation / privatization that happened AFTER enqueue. It
mirrors the factory-level _user_can_use_custom_model gate; these tests pin
the worker copy so a divergence is caught.
"""

import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
os.environ.setdefault("BENGER_TEST_MODE", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import `tasks` first so the generation module fully initializes through
# its normal entry point — importing generation.llm_generation_service
# directly triggers a circular import (tasks <-> generation) mid-load.
import tasks  # noqa: E402,F401
from generation.llm_generation_service import _check_custom_model_access  # noqa: E402


def _model(**over):
    m = MagicMock()
    m.id = "custom-abc"
    m.is_public = False
    m.created_by = "owner-1"
    for k, v in over.items():
        setattr(m, k, v)
    return m


def test_public_model_allows_any_user():
    assert _check_custom_model_access(MagicMock(), "anyone", _model(is_public=True)) is True


def test_creator_allowed():
    assert _check_custom_model_access(MagicMock(), "owner-1", _model()) is True


def _fake_models(monkeypatch):
    fake = types.ModuleType("models")

    class User:
        id = MagicMock()

    class OrganizationMembership:
        user_id = MagicMock()
        is_active = MagicMock()

    class ModelOrganization:
        model_id = MagicMock()
        organization_id = "ModelOrganization.organization_id"

    fake.User = User
    fake.OrganizationMembership = OrganizationMembership
    fake.ModelOrganization = ModelOrganization
    monkeypatch.setitem(sys.modules, "models", fake)


def _db(*, superadmin=False, model_org_ids=(), member_org_ids=()):
    db = MagicMock()
    user = MagicMock(is_superadmin=superadmin)
    memberships = [MagicMock(organization_id=o) for o in member_org_ids]

    def _query(target):
        name = getattr(target, "__name__", "") or (
            "ModelOrganization" if "organization_id" in str(target) else ""
        )
        q = MagicMock()
        if name == "User":
            q.filter.return_value.first.return_value = user
        elif name == "OrganizationMembership":
            q.filter.return_value.all.return_value = memberships
        else:
            q.filter.return_value.all.return_value = [(o,) for o in model_org_ids]
        return q

    db.query.side_effect = _query
    return db


def test_org_member_allowed(monkeypatch):
    _fake_models(monkeypatch)
    db = _db(model_org_ids=("org-a",), member_org_ids=("org-a", "org-b"))
    assert _check_custom_model_access(db, "user-9", _model(created_by="other")) is True


def test_non_member_denied(monkeypatch):
    _fake_models(monkeypatch)
    db = _db(model_org_ids=("org-a",), member_org_ids=("org-z",))
    assert _check_custom_model_access(db, "user-9", _model(created_by="other")) is False


def test_unshared_private_denied(monkeypatch):
    _fake_models(monkeypatch)
    db = _db(model_org_ids=())
    assert _check_custom_model_access(db, "user-9", _model(created_by="other")) is False


def test_superadmin_allowed(monkeypatch):
    _fake_models(monkeypatch)
    db = _db(superadmin=True)
    assert _check_custom_model_access(db, "user-9", _model(created_by="other")) is True

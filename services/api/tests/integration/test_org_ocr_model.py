"""Organization default model for handwritten uploads (core 2.48).

``PUT /api/organizations/{id}/ocr-model`` stores ``settings.
handwriting_ocr_model`` for org admins and superadmins (merging into the other
settings keys); only active official models that can read images are
accepted, null removes it. ``org_ocr.effective_ocr_model`` resolves a
project's model: off unless the project switch is on, then the project's
override, else the first organization default.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import LLMModel, Organization
from org_ocr import effective_ocr_model, org_ocr_model, with_ocr_model
from tests.integration.test_org_jurisdiction import _as_user, _seed, _stored_settings


def _uid():
    return str(uuid.uuid4())


async def _model(db, *, capabilities, official=True, active=True, provider="Google", model_id=None):
    model_id = model_id or f"ocr-test-{_uid()[:8]}"
    model = LLMModel(
        id=model_id,
        name="OCR test model",
        provider=provider,
        model_type="chat",
        capabilities=capabilities,
        is_active=active,
        is_official=official,
        created_at=datetime.now(timezone.utc),
    )
    if not official:
        model.base_url = "https://llm.example.org/v1"
        model.endpoint_model_name = "vision"
    db.add(model)
    await db.commit()
    return model_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_sets_and_clears_the_default(async_test_client, async_test_db):
    org, users = await _seed(async_test_db)
    model_id = await _model(async_test_db, capabilities=["text-generation", "multimodal"])
    org_id = org.id
    with _as_user(users["ORG_ADMIN"]):
        resp = await async_test_client.put(
            f"/api/organizations/{org_id}/ocr-model", json={"model_id": model_id}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"id": org_id, "model_id": model_id}
        assert await _stored_settings(async_test_db, org_id) == {
            "require_private_keys": False,
            "handwriting_ocr_model": model_id,
        }
        resp = await async_test_client.put(
            f"/api/organizations/{org_id}/ocr-model", json={"model_id": None}
        )
    assert resp.status_code == 200
    assert await _stored_settings(async_test_db, org_id) == {"require_private_keys": False}


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capabilities,official,active,provider,fixed_id",
    [
        (["text-generation"], True, True, "Google", None),
        (["multimodal"], False, True, "Google", None),
        (["multimodal"], True, False, "Google", None),
        (["multimodal"], True, True, "Mistral", None),
        (["multimodal"], True, True, "OpenAI", "gpt-5.9-pro"),
    ],
    ids=["text-only", "custom", "inactive", "provider-without-attachments", "responses-only-pro"],
)
async def test_models_that_cannot_read_images_are_refused(
    async_test_client, async_test_db, capabilities, official, active, provider, fixed_id
):
    org, users = await _seed(async_test_db)
    model_id = await _model(
        async_test_db, capabilities=capabilities, official=official, active=active,
        provider=provider, model_id=fixed_id,
    )
    with _as_user(users["ORG_ADMIN"]):
        resp = await async_test_client.put(
            f"/api/organizations/{org.id}/ocr-model", json={"model_id": model_id}
        )
    assert resp.status_code == 422
    assert "handwriting_ocr_model" not in await _stored_settings(async_test_db, org.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_an_annotator_cannot_set_it(async_test_client, async_test_db):
    org, users = await _seed(async_test_db)
    model_id = await _model(async_test_db, capabilities=["multimodal"])
    with _as_user(users["ANNOTATOR"]):
        resp = await async_test_client.put(
            f"/api/organizations/{org.id}/ocr-model", json={"model_id": model_id}
        )
    assert resp.status_code == 403


def test_settings_helpers():
    assert org_ocr_model(None) is None
    assert org_ocr_model({"handwriting_ocr_model": "  "}) is None
    assert org_ocr_model({"handwriting_ocr_model": " m1 "}) == "m1"
    assert with_ocr_model({"a": 1}, "m1") == {"a": 1, "handwriting_ocr_model": "m1"}
    assert with_ocr_model({"a": 1, "handwriting_ocr_model": "m1"}, "") == {"a": 1}
    with pytest.raises(ValueError):
        with_ocr_model({}, "x" * 300)


@pytest.mark.integration
def test_effective_model_resolution(test_db):
    from models import User
    from project_models import Project, ProjectOrganization

    owner = User(
        id=_uid(), username=f"ocr-{_uid()[:8]}", email=f"{_uid()[:8]}@example.com",
        name="Owner", hashed_password="x",
    )
    test_db.add(owner)
    org = Organization(
        id=_uid(), name="Org", slug=f"org-{_uid()[:8]}", display_name="Org",
        settings={"handwriting_ocr_model": "org-default"},
    )
    test_db.add(org)
    test_db.flush()
    project = Project(id=_uid(), title="p", created_by=owner.id)
    test_db.add(project)
    test_db.flush()
    test_db.add(ProjectOrganization(id=_uid(), project_id=project.id, organization_id=org.id, assigned_by=owner.id))
    test_db.flush()

    assert effective_ocr_model(test_db, project) is None  # switch off
    project.handwriting_ocr_enabled = True
    assert effective_ocr_model(test_db, project) == "org-default"
    project.handwriting_ocr_model = "project-model"
    assert effective_ocr_model(test_db, project) == "project-model"
    project.handwriting_ocr_model = None
    org.settings = {}
    test_db.flush()
    assert effective_ocr_model(test_db, project) is None

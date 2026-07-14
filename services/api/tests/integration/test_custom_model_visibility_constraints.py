"""Integration tests for the three CHECK constraints on the llm_models table
introduced by alembic migration 080 (also mirrored in LLMModel.__table_args__),
plus the uniqueness rules on the two new BYOM tables.

Each test inserts a row that violates one of:
  - ck_llm_models_visibility_exclusive           NOT (is_private AND is_public)
  - ck_llm_models_custom_endpoint_required       is_official OR (base_url AND endpoint_model_name)
  - ck_llm_models_official_no_visibility_flags   NOT is_official OR (flags both false)

or one of:
  - unique_model_organization        (model_id, organization_id) on model_organizations
  - unique_custom_model_credential   (user_id, model_id) on custom_model_credentials

and asserts that PostgreSQL raises IntegrityError.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from models import (
    CustomModelCredential,
    LLMModel,
    ModelOrganization,
    Organization,
    User,
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_constraints():
    """The session-scoped test DB was created by Base.metadata.create_all
    *before* the BYOM columns/CHECK constraints were added to
    LLMModel.__table_args__, so the existing `llm_models` table can be
    missing them on first run. Add any that aren't present, idempotently,
    so this test exercises the same constraints migration 080 applies in
    prod.
    """
    from tests.fixtures.database import _get_engine
    from tests.utils.byom_schema import ensure_byom_llm_schema

    engine, _ = _get_engine()
    ensure_byom_llm_schema(engine)
    yield


@pytest.fixture
def model_creator(test_db):
    """Real user row to satisfy llm_models.created_by / credentials FKs."""
    user = User(
        id=f"mvc-owner-{uuid.uuid4()}",
        username=f"mvc-{uuid.uuid4().hex[:8]}",
        email=f"mvc-{uuid.uuid4().hex[:8]}@test.com",
        name="Model Visibility Constraint Test Owner",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(user)
    test_db.flush()
    return user


@pytest.fixture
def test_organization(test_db):
    """Real organization row to satisfy model_organizations FKs."""
    org = Organization(
        id=f"mvc-org-{uuid.uuid4()}",
        name="mvc-org",
        display_name="Model Constraint Test Org",
        slug=f"mvc-org-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    test_db.add(org)
    test_db.flush()
    return org


def _make_model(**overrides):
    """A valid CUSTOM model row by default; override into other shapes."""
    base = dict(
        id=f"custom-{uuid.uuid4()}",
        name="Constraint test model",
        provider="Custom",
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=False,
        is_private=False,
        is_public=False,
        base_url="http://localhost:11434/v1",
        endpoint_model_name="llama3:8b",
        requires_api_key=True,
    )
    base.update(overrides)
    return LLMModel(**base)


class TestLlmModelVisibilityConstraints:
    def test_private_and_public_cannot_both_be_true(self, test_db):
        test_db.add(_make_model(is_private=True, is_public=True))
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_custom_row_requires_endpoint_fields(self, test_db):
        test_db.add(
            _make_model(base_url=None, endpoint_model_name=None, is_private=True)
        )
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_custom_row_requires_endpoint_model_name_too(self, test_db):
        test_db.add(_make_model(endpoint_model_name=None, is_private=True))
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_official_row_cannot_be_private(self, test_db):
        test_db.add(
            _make_model(
                id=f"official-{uuid.uuid4()}",
                is_official=True,
                base_url=None,
                endpoint_model_name=None,
                is_private=True,
            )
        )
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_official_row_cannot_be_public(self, test_db):
        test_db.add(
            _make_model(
                id=f"official-{uuid.uuid4()}",
                is_official=True,
                base_url=None,
                endpoint_model_name=None,
                is_public=True,
            )
        )
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_valid_official_row_passes(self, test_db):
        test_db.add(
            _make_model(
                id=f"official-{uuid.uuid4()}",
                is_official=True,
                base_url=None,
                endpoint_model_name=None,
            )
        )
        test_db.flush()  # no error

    def test_valid_private_custom_row_passes(self, test_db, model_creator):
        test_db.add(_make_model(is_private=True, created_by=model_creator.id))
        test_db.flush()

    def test_valid_org_scoped_custom_row_passes(self, test_db):
        # Both flags false = org-scoped (shared via model_organizations).
        test_db.add(_make_model())
        test_db.flush()


class TestModelOrganizationUniqueness:
    def test_duplicate_model_org_pair_rejected(
        self, test_db, model_creator, test_organization
    ):
        model = _make_model(is_private=True)
        test_db.add(model)
        test_db.flush()

        test_db.add(
            ModelOrganization(
                id=str(uuid.uuid4()),
                model_id=model.id,
                organization_id=test_organization.id,
                assigned_by=model_creator.id,
            )
        )
        test_db.flush()

        test_db.add(
            ModelOrganization(
                id=str(uuid.uuid4()),
                model_id=model.id,
                organization_id=test_organization.id,
                assigned_by=model_creator.id,
            )
        )
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_same_model_different_org_passes(self, test_db, test_organization):
        model = _make_model(is_private=True)
        other_org = Organization(
            id=f"mvc-org2-{uuid.uuid4()}",
            name="mvc-org2",
            display_name="Second Org",
            slug=f"mvc-org2-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        test_db.add_all([model, other_org])
        test_db.flush()

        test_db.add_all(
            [
                ModelOrganization(
                    id=str(uuid.uuid4()),
                    model_id=model.id,
                    organization_id=test_organization.id,
                ),
                ModelOrganization(
                    id=str(uuid.uuid4()),
                    model_id=model.id,
                    organization_id=other_org.id,
                ),
            ]
        )
        test_db.flush()  # no error


class TestCustomModelCredentialUniqueness:
    def test_duplicate_user_model_pair_rejected(self, test_db, model_creator):
        model = _make_model(is_private=True, created_by=model_creator.id)
        test_db.add(model)
        test_db.flush()

        test_db.add(
            CustomModelCredential(
                id=str(uuid.uuid4()),
                user_id=model_creator.id,
                model_id=model.id,
                encrypted_api_key="ciphertext-1",
            )
        )
        test_db.flush()

        test_db.add(
            CustomModelCredential(
                id=str(uuid.uuid4()),
                user_id=model_creator.id,
                model_id=model.id,
                encrypted_api_key="ciphertext-2",
            )
        )
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_same_user_different_model_passes(self, test_db, model_creator):
        model_a = _make_model(is_private=True)
        model_b = _make_model(is_private=True)
        test_db.add_all([model_a, model_b])
        test_db.flush()

        test_db.add_all(
            [
                CustomModelCredential(
                    id=str(uuid.uuid4()),
                    user_id=model_creator.id,
                    model_id=model_a.id,
                    encrypted_api_key="ciphertext-a",
                ),
                CustomModelCredential(
                    id=str(uuid.uuid4()),
                    user_id=model_creator.id,
                    model_id=model_b.id,
                    encrypted_api_key="ciphertext-b",
                ),
            ]
        )
        test_db.flush()  # no error

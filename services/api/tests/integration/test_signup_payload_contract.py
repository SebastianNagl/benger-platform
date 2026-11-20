"""The signup forms' request bodies are accepted by POST /api/auth/signup.

The fixtures in services/shared/contracts/signup/ are the exact JSON bodies
the frontend's signup modal and register wizard send; the frontend test
services/frontend/src/components/auth/__tests__/signupPayload.contract.test.tsx
keeps them equal to what the forms produce. Here every fixture must validate
against UserCreate and create an account through the real endpoint, so a
form and the schema cannot drift apart unnoticed (a modal that omitted two
then-required fields once made every signup through it fail).
"""

import json
import uuid
from pathlib import Path

import pytest

from auth_module.models import UserCreate
from models import User


def _contract_dir() -> Path:
    """services/shared/contracts/signup in a checkout, /shared/... in the
    Docker test runner (which mounts services/shared at /shared)."""
    parents = Path(__file__).resolve().parents
    candidates = [parents[3] / "shared"] if len(parents) > 3 else []
    candidates.append(Path("/shared"))
    for shared in candidates:
        folder = shared / "contracts" / "signup"
        if folder.is_dir():
            return folder
    raise AssertionError(
        "signup contract fixtures not found: mount services/shared at /shared"
    )


CONTRACT_DIR = _contract_dir()
FIXTURES = sorted(CONTRACT_DIR.glob("*.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _unique(payload: dict) -> dict:
    """The fixture with a fresh username and email, so each case signs up."""
    suffix = uuid.uuid4().hex[:8]
    return {
        **payload,
        "username": f"{payload['username']}_{suffix}",
        "email": f"{suffix}-{payload['email']}",
    }


def test_every_signup_form_has_a_fixture():
    names = {path.name for path in FIXTURES}
    assert {
        "signup_modal.json",
        "signup_modal_research_consent.json",
        "register_minimal.json",
        "register_legal_background.json",
    } <= names


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.stem)
def test_fixture_validates_against_user_create(fixture):
    UserCreate.model_validate(_load(fixture))


@pytest.mark.integration
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.stem)
def test_fixture_signs_up(fixture, client, test_db):
    payload = _unique(_load(fixture))

    resp = client.post("/api/auth/signup", json=payload)

    assert resp.status_code == 200, resp.text
    user = test_db.query(User).filter(User.username == payload["username"]).one()
    # An unanswered legal background is stored as NULL.
    for field in ("legal_expertise_level", "german_proficiency"):
        stored = getattr(user, field)
        assert (stored.value if stored is not None else None) == payload.get(field)

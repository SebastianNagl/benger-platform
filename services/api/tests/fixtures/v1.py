"""Helpers for the /api/v1 integration tests: real key authentication over
the async test session, plus project/task seeding."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Optional

from fastapi import HTTPException, Request

from auth_module.dependencies import require_user
from auth_module.principal import extract_api_key, session_principal
from auth_module.service import db_user_to_user
from main import app
from project_models import Project, ProjectOrganization, Task
from services import api_key_service as svc

LABEL_CONFIG = (
    '<View><Text name="sv" value="$sachverhalt"/>'
    '<TextArea name="antwort" toName="sv"/>'
    '<Choices name="ergebnis" toName="sv"><Choice value="ja"/><Choice value="nein"/></Choices>'
    "</View>"
)


@contextmanager
def v1_auth(db, session_user=None):
    """Replace ``require_user`` with the real access-key check run on the
    async test session (the sync auth path cannot see the test
    transaction). Without a bearer key, ``session_user`` acts as a browser
    session, else 401."""

    async def _require_user(request: Request):
        plain = extract_api_key(request)
        if plain is not None:
            auth = await svc.authenticate_api_key(db, plain, path=request.url.path)
            request.state.principal = auth.principal
            user = await db.run_sync(lambda _s: db_user_to_user(auth.user))
            if user.is_superadmin:
                user = user.model_copy(update={"is_superadmin": False})
            return user
        if session_user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        request.state.principal = session_principal(session_user.id)
        return await db.run_sync(lambda _s: db_user_to_user(session_user))

    app.dependency_overrides[require_user] = _require_user
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_user, None)


def bearer(plain: str) -> dict:
    return {"Authorization": f"Bearer {plain}"}


async def make_project(
    db,
    owner_id: str,
    *,
    org_id: Optional[str] = None,
    group_id: Optional[str] = None,
    title: str = "v1 project",
    **kw,
) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        title=title,
        created_by=owner_id,
        label_config=LABEL_CONFIG,
        **kw,
    )
    db.add(project)
    await db.flush()
    if org_id:
        db.add(
            ProjectOrganization(
                id=str(uuid.uuid4()),
                project_id=project.id,
                organization_id=org_id,
                group_id=group_id,
                assigned_by=owner_id,
            )
        )
        await db.flush()
    return project


async def make_tasks(db, project: Project, count: int, owner_id: str) -> list:
    tasks = []
    for i in range(1, count + 1):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i,
            data={
                "sachverhalt": f"Fall {i}",
                "Musterloesung": f"Lösung {i}",
                "ground_truth": "ja",
            },
            meta={
                "tags": ["zivilrecht"],
                "benchmark": {"rechtsgebiet": "BGB AT", "bewertung": "geheim"},
                "audit_log": [{"by": "editor@example.com", "before": "x"}],
            },
            created_by=owner_id,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        db.add(task)
        tasks.append(task)
    await db.flush()
    return tasks


def ids(items: Iterable[dict]) -> list:
    return [item["id"] for item in items]

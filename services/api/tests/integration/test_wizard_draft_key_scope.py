"""Key scope of creation-wizard drafts (CORE 2.55).

A draft has no organization rows while the wizard runs, so without a rule its
AI work would spend personal keys although the finished exam spends its
organization's (or group's) keys. The rule: for the draft's CREATOR, its
target organization counts as the project's organization in
``org_resolution`` (same membership and ``min_role`` rules), and its target
group is the scope group of ``resolve_project_group_for_org`` while the
creator may create a project there. Both twins (sync and async) and both key
services (api + worker) are pinned.
"""

import uuid

import pytest
from sqlalchemy import select

from models import Organization, OrganizationGroup, OrganizationMembership, OrganizationRole
from project_models import Project, ProjectWizardDraft
from tests.integration.test_group_key_mode import (
    GROUP_A,
    ORG_WIDE,
    PERSONAL,
    _seed_keys,
    _services,
    _set_modes,
)
from tests.integration.test_group_visibility import _world

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _draft(db, creator, org=None, group=None) -> Project:
    project = Project(
        id=str(uuid.uuid4()), title="Entwurf", created_by=creator.id, is_private=True,
        kind="exam", is_wizard_draft=True,
    )
    db.add(project)
    await db.flush()
    db.add(ProjectWizardDraft(
        project_id=project.id, created_by=creator.id, client_key=str(uuid.uuid4()),
        target_organization_id=org.id if org else None,
        target_group_id=group.id if group else None,
    ))
    await db.commit()
    return project


async def _loaded(db, project_id):
    from sqlalchemy.orm import selectinload

    return (
        await db.execute(
            select(Project).options(selectinload(Project.organizations)).where(
                Project.id == project_id
            )
        )
    ).scalar_one()


async def _sync(db, fn, *args, **kwargs):
    return await db.run_sync(lambda s: fn(s, *args, **kwargs))


async def test_target_group_is_the_scope_group_while_the_creator_may_create_there(
    async_test_db,
):
    from org_groups import (
        resolve_project_group_for_org,
        resolve_project_group_for_org_async,
        wizard_draft_target,
        wizard_draft_target_async,
    )

    db = async_test_db
    w = await _world(db)
    draft = await _draft(db, w["contrib_a"], w["org"], w["group_a"])
    expected = (w["contrib_a"].id, w["org"].id, w["group_a"].id)
    assert await wizard_draft_target_async(db, draft.id) == expected
    assert await _sync(db, wizard_draft_target, draft.id) == expected
    assert await resolve_project_group_for_org_async(db, draft.id, w["org"].id) == w["group_a"].id
    assert await _sync(db, resolve_project_group_for_org, draft.id, w["org"].id) == w["group_a"].id
    # Another org is never scoped by the draft's target.
    assert await resolve_project_group_for_org_async(db, draft.id, str(uuid.uuid4())) is None

    # A deactivated group no longer scopes new work for the draft.
    group = await db.get(OrganizationGroup, w["group_a"].id)
    group.is_active = False
    await db.commit()
    assert await resolve_project_group_for_org_async(db, draft.id, w["org"].id) is None
    assert await _sync(db, resolve_project_group_for_org, draft.id, w["org"].id) is None


async def test_an_invalid_target_group_is_ignored(async_test_db):
    """A target group the creator may not create in (written around the
    route's validation, or a membership that ended) never scopes keys."""
    from org_groups import resolve_project_group_for_org, resolve_project_group_for_org_async

    db = async_test_db
    w = await _world(db)
    draft = await _draft(db, w["contrib_a"], w["org"], w["group_b"])
    assert await resolve_project_group_for_org_async(db, draft.id, w["org"].id) is None
    assert await _sync(db, resolve_project_group_for_org, draft.id, w["org"].id) is None


async def test_a_finished_project_follows_its_attachment_only(async_test_db):
    from org_groups import wizard_draft_target_async

    db = async_test_db
    w = await _world(db)
    draft = await _draft(db, w["contrib_a"], w["org"], w["group_a"])
    project = await db.get(Project, draft.id)
    project.is_wizard_draft = False
    await db.commit()
    assert await wizard_draft_target_async(db, draft.id) is None


async def test_target_org_is_the_dispatch_org_for_the_creator_only(async_test_db):
    from org_resolution import (
        billing_org_options,
        billing_org_options_async,
        resolve_dispatch_org_for_project,
        resolve_dispatch_org_for_project_async,
    )

    db = async_test_db
    w = await _world(db)
    await _set_modes(db, w, org=False)
    org_id = w["org"].id
    draft = await _draft(db, w["contrib_a"], w["org"], w["group_a"])
    loaded = await _loaded(db, draft.id)

    creator = w["contrib_a"]
    assert await resolve_dispatch_org_for_project_async(db, creator, draft.id) == org_id
    assert await _sync(db, resolve_dispatch_org_for_project, creator, loaded) == org_id
    assert await resolve_dispatch_org_for_project_async(
        db, creator.id, draft.id, min_role="CONTRIBUTOR"
    ) == org_id
    assert await _sync(
        db, resolve_dispatch_org_for_project, creator.id, loaded, min_role="CONTRIBUTOR"
    ) == org_id
    options = [{"id": org_id, "name": w["org"].display_name}]
    assert await billing_org_options_async(db, creator, draft.id) == options
    assert await _sync(db, billing_org_options, creator, loaded) == options
    assert await resolve_dispatch_org_for_project_async(
        db, creator, draft.id, requested_org_id=org_id
    ) == org_id

    # Anyone else (an org admin of the target, a superadmin) gets no org:
    # the draft is not theirs, so personal keys.
    for other in (w["orgadmin"],):
        assert await resolve_dispatch_org_for_project_async(db, other, draft.id) is None
        assert await _sync(db, resolve_dispatch_org_for_project, other, loaded) is None
        assert await billing_org_options_async(db, other, draft.id) == []

    # A creator who became an annotator of the org loses the hand-started
    # runs (min_role CONTRIBUTOR) but not grading-type dispatches.
    membership = (
        await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == creator.id,
                OrganizationMembership.organization_id == org_id,
            )
        )
    ).scalar_one()
    membership.role = OrganizationRole.ANNOTATOR
    await db.commit()
    # Group A role CONTRIBUTOR still reaches min_role through the group.
    assert await resolve_dispatch_org_for_project_async(
        db, creator, draft.id, min_role="CONTRIBUTOR"
    ) == org_id
    membership.is_active = False
    await db.commit()
    assert await resolve_dispatch_org_for_project_async(db, creator, draft.id) is None
    assert await _sync(db, resolve_dispatch_org_for_project, creator, loaded) is None


async def test_min_role_follows_the_target_group(async_test_db):
    from org_resolution import resolve_dispatch_org_for_project_async

    db = async_test_db
    w = await _world(db)
    # loose: org CONTRIBUTOR without a group. A draft targeting group A was
    # written for them around the validation: group A gives them no role.
    draft = await _draft(db, w["loose"], w["org"], w["group_a"])
    assert await resolve_dispatch_org_for_project_async(
        db, w["loose"], draft.id, min_role="CONTRIBUTOR"
    ) == w["org"].id  # the invalid group is ignored, the org role counts
    draft_b = await _draft(db, w["annot_a"], w["org"], w["group_a"])
    assert await resolve_dispatch_org_for_project_async(
        db, w["annot_a"], draft_b.id, min_role="CONTRIBUTOR"
    ) is None
    assert await resolve_dispatch_org_for_project_async(
        db, w["annot_a"], draft_b.id
    ) == w["org"].id


async def test_a_draft_without_target_stays_personal(async_test_db):
    from org_resolution import resolve_dispatch_org_for_project_async

    db = async_test_db
    w = await _world(db)
    draft = await _draft(db, w["contrib_a"])
    assert await resolve_dispatch_org_for_project_async(db, w["contrib_a"], draft.id) is None


async def test_both_key_services_spend_the_target_scope(async_test_db):
    db = async_test_db
    w = await _world(db)
    await _set_modes(db, w, org=True, group_a=False)
    await _seed_keys(db, w)
    draft = await _draft(db, w["contrib_a"], w["org"], w["group_a"])
    org_wide_draft = await _draft(db, w["loose"], w["org"])

    for svc in _services():
        # Group A pays: its key, as the finished group-A exam would spend.
        key = await db.run_sync(
            lambda s: svc.resolve_api_key(
                s, w["contrib_a"].id, w["org"].id, "openai", project_id=draft.id
            )
        )
        assert key == GROUP_A
        # The org itself has members pay: an org-wide draft spends personal keys.
        key = await db.run_sync(
            lambda s: svc.resolve_api_key(
                s, w["loose"].id, w["org"].id, "openai", project_id=org_wide_draft.id
            )
        )
        assert key == PERSONAL

    org = await db.get(Organization, w["org"].id)
    org.settings = {"require_private_keys": False}
    await db.commit()
    for svc in _services():
        key = await db.run_sync(
            lambda s: svc.resolve_api_key(
                s, w["loose"].id, w["org"].id, "openai", project_id=org_wide_draft.id
            )
        )
        assert key == ORG_WIDE

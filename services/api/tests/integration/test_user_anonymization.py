"""Anonymizing an account against a real database (owner decision D16).

``services/user_anonymization.py``: every identity column and every related
row the design lists is scrubbed or removed, answers and grades stay with the
same account id, the person can no longer sign in or refresh a session, and
refusals change nothing. Also the superadmin endpoints
(``/api/users/{id}/anonymization`` and ``/anonymize``), the reactivation
guard, ``get_current_user`` for inactive accounts and the Redis token
cleanup. The LMS admin endpoints live in
``tests/routers/test_lti_admin_anonymize.py``.
"""

import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

import extensions
from auth_module.dependencies import get_current_user, require_user
from auth_module.service import (
    authenticate_user,
    create_access_token,
    refresh_access_token,
)
from auth_module.user_service import get_password_hash
from models import (
    CustomModelCredential,
    EvaluationJudgeRun,
    EvaluationRun,
    Invitation,
    LLMModel,
    LtiAdminEvent,
    LtiGradeSync,
    LtiResourceLinkUser,
    LtiUserLink,
    MarketplaceOrder,
    Notification,
    NotificationType,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    RefreshToken,
    StudentSubscription,
    TaskEvaluation,
    User,
    UserColumnPreferences,
    UserNotificationPreference,
    UserProfileHistory,
)
from project_models import (
    Annotation,
    MarketplaceEntitlement,
    Project,
    ProjectShareLink,
    Task,
)
from services import user_anonymization as ua
from services.refresh_token_service import create_refresh_token_async
from tests.fixtures.lti_admin_world import (
    FakeExtended,
    add_group_member,
    add_member,
    as_user,
    detail_code,
    make_grade_sync,
    make_group,
    make_org,
    make_participation,
    make_project,
    make_registration,
    make_resource_link,
    make_user,
    make_user_link,
)

PASSWORD = "Secret-Passw0rd!"


@pytest.fixture(autouse=True)
def _community_edition(monkeypatch):
    monkeypatch.setattr(extensions, "_extended", None)


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _fresh(db, model, *conditions):
    stmt = select(model).where(*conditions).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalars().all()


async def _reload_user(db, user_id) -> User:
    return (await _fresh(db, User, User.id == user_id))[0]


async def _student_with_everything(db):
    """An LMS student with a password, tokens, keys, a research profile and
    rows in every table anonymization touches."""
    org = await make_org(db)
    group = await make_group(db, org)
    reg = await make_registration(db, org, group=group)
    teacher = await make_user(db, name="Tanja Teacher")
    exam = await make_project(db, teacher)
    task = (await _fresh(db, Task, Task.project_id == exam.id))[0]
    link = await make_resource_link(db, reg, project=exam)

    student = await make_user(db, name="Erika Musterfrau")
    now = _now()
    student.email = f"erika-{uuid.uuid4().hex[:8]}@uni-example.de"
    student.hashed_password = get_password_hash(PASSWORD)
    student.password_set = True
    student.password_reset_token = "reset-token"
    student.password_reset_expires = now + timedelta(hours=1)
    student.pending_activation_email = "erika.private@example.org"
    student.email_verification_token = "verify-token"
    student.email_verification_sent_at = now
    student.email_verified = True
    student.email_verified_at = now
    student.email_verified_by_id = teacher.id
    student.email_verification_method = "activation"
    student.invitation_token = "invite-token"
    student.invitation_expires_at = now + timedelta(days=1)
    student.encrypted_openai_api_key = "cipher-openai"
    student.encrypted_anthropic_api_key = "cipher-anthropic"
    student.encrypted_google_api_key = "cipher-google"
    student.encrypted_deepinfra_api_key = "cipher-deepinfra"
    student.encrypted_grok_api_key = "cipher-grok"
    student.encrypted_mistral_api_key = "cipher-mistral"
    student.encrypted_cohere_api_key = "cipher-cohere"
    student.timezone = "Europe/Berlin"
    student.age = 23
    student.job = "Studentin"
    student.years_of_experience = 1
    student.legal_expertise_level = "law_student"
    student.german_proficiency = "native"
    student.degree_program_type = "staatsexamen"
    student.current_semester = 5
    student.legal_specializations = ["civil_law"]
    student.german_state_exams_count = 0
    student.german_state_exams_data = []
    student.gender = "female"
    student.subjective_competence_civil = 5
    student.subjective_competence_public = 4
    student.subjective_competence_criminal = 3
    student.grade_zwischenpruefung = Decimal("9.5")
    student.grade_vorgeruecktenubung = Decimal("8.0")
    student.grade_first_staatsexamen = Decimal("7.5")
    student.grade_second_staatsexamen = Decimal("7.0")
    student.ati_s_scores = {"1": 4}
    student.ptt_a_scores = {"1": 5}
    student.ki_experience_scores = {"1": 6}
    student.mandatory_profile_completed = True
    student.profile_confirmed_at = now
    student.research_data_consent_accepted_at = now - timedelta(days=3)
    await db.flush()

    await add_member(db, student, org, OrganizationRole.ANNOTATOR)
    await add_group_member(db, student, group, admin=False)
    user_link = await make_user_link(db, reg, student)
    await make_participation(db, link, student)
    await make_grade_sync(db, link, student)
    await make_grade_sync(db, link, student, kind="ai", status="synced")
    db.add(
        MarketplaceEntitlement(
            id=_uid(), user_id=student.id, project_id=exam.id, source="lti"
        )
    )

    annotation = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=exam.id,
        completed_by=student.id,
        result=[{"from_name": "loesung", "type": "textarea", "value": {"text": ["A"]}}],
        was_cancelled=False,
    )
    db.add(annotation)
    run = EvaluationRun(
        id=_uid(),
        project_id=exam.id,
        model_id="immediate",
        evaluation_type_ids=["llm_judge_falloesung"],
        metrics={},
        status="completed",
        created_by=teacher.id,
    )
    db.add(run)
    await db.flush()
    judge_run = EvaluationJudgeRun(
        id=_uid(), evaluation_id=run.id, run_index=0, status="completed"
    )
    db.add(judge_run)
    await db.flush()
    evaluation = TaskEvaluation(
        id=_uid(),
        evaluation_id=run.id,
        judge_run_id=judge_run.id,
        task_id=task.id,
        annotation_id=annotation.id,
        field_name="loesung",
        answer_type="long_text",
        ground_truth={"value": "M"},
        prediction={"value": "A"},
        metrics={"score": 12},
        passed=True,
    )
    db.add(evaluation)

    # The student's own project with a share link and a colleague's
    # "project created" notice that embeds the student's name.
    own_project = Project(
        id=_uid(), title="Eigene Übung", created_by=student.id, is_private=True
    )
    db.add(own_project)
    await db.flush()
    db.add(
        ProjectShareLink(
            id=_uid(),
            token=uuid.uuid4().hex,
            project_id=own_project.id,
            created_by=student.id,
            password_hash="x",
        )
    )
    foreign_notice = Notification(
        id=_uid(),
        user_id=teacher.id,
        type=NotificationType.PROJECT_CREATED,
        title="Neues Projekt",
        message="Erika Musterfrau created a new project",
        data={"project_id": own_project.id, "creator_name": "Erika Musterfrau"},
    )
    member_notice = Notification(
        id=_uid(),
        user_id=teacher.id,
        type=NotificationType.MEMBER_JOINED,
        title="New member",
        message="Erika joined",
        data={"new_member_email": student.email.upper()},
    )
    unrelated_notice = Notification(
        id=_uid(),
        user_id=teacher.id,
        type=NotificationType.PROJECT_CREATED,
        title="Anderes Projekt",
        message="someone else",
        data={"project_id": exam.id, "creator_name": "Tanja Teacher"},
    )
    # Notices that name the student as the acting account, by id or by name
    # (a provisioned teacher assigns, invites and deletes, too).
    actor_notices = [
        Notification(
            id=_uid(),
            user_id=teacher.id,
            type=NotificationType.TASK_ASSIGNED,
            title="Neue Aufgabe",
            message="Sie haben eine neue Aufgabe",
            data={"project_id": exam.id, "assigned_by": " erika musterfrau "},
        ),
        Notification(
            id=_uid(),
            user_id=teacher.id,
            organization_id=org.id,
            type=NotificationType.ORGANIZATION_INVITATION_SENT,
            title="Einladung",
            message="Erika Musterfrau sent an invitation",
            data={"inviter_name": "Erika Musterfrau", "invitee_email": "x@example.org"},
        ),
        Notification(
            id=_uid(),
            user_id=teacher.id,
            type=NotificationType.PROJECT_DELETED,
            title="Gelöscht",
            message="Ein Projekt wurde gelöscht",
            data={"project_id": exam.id, "deleted_by_user_id": student.id},
        ),
    ]
    # A generic placeholder name never counts as the student's name.
    generic_notice = Notification(
        id=_uid(),
        user_id=teacher.id,
        type=NotificationType.TASK_ASSIGNED,
        title="Neue Aufgabe",
        message="Sie haben eine neue Aufgabe",
        data={"project_id": exam.id, "assigned_by": "LTI Student"},
    )
    db.add_all(actor_notices + [generic_notice])
    own_notice = Notification(
        id=_uid(),
        user_id=student.id,
        type=NotificationType.EVALUATION_RECEIVED_IMMEDIATE,
        title="Bewertet",
        message="Ihre Klausur wurde bewertet",
    )
    db.add_all([foreign_notice, member_notice, unrelated_notice, own_notice])
    db.add(
        UserNotificationPreference(
            id=_uid(), user_id=student.id, notification_type="evaluation_completed"
        )
    )
    db.add(
        UserColumnPreferences(
            id=_uid(), user_id=student.id, task_id=task.id, column_settings={"a": 1}
        )
    )
    db.add(
        UserProfileHistory(
            id=_uid(),
            user_id=student.id,
            change_type="signup",
            snapshot={"age": 23},
            changed_fields=["age"],
        )
    )
    model = LLMModel(
        id=f"anon-test-model-{uuid.uuid4().hex[:8]}",
        name="Anon Test Model",
        provider="openai",
        model_type="chat",
        capabilities=["text_generation"],
        is_official=True,
    )
    db.add(model)
    await db.flush()
    db.add(
        CustomModelCredential(
            id=_uid(),
            user_id=student.id,
            model_id=model.id,
            encrypted_api_key="cipher",
        )
    )
    pending_invite = Invitation(
        id=_uid(),
        organization_id=org.id,
        email=student.email,
        role=OrganizationRole.ANNOTATOR,
        token=uuid.uuid4().hex,
        invited_by=teacher.id,
        expires_at=now + timedelta(days=7),
        pending_user_id=student.id,
    )
    db.add(pending_invite)
    await db.commit()
    refresh_token, _row = await create_refresh_token_async(db, student.id)

    return types.SimpleNamespace(
        org=org,
        group=group,
        reg=reg,
        link=link,
        teacher=teacher,
        exam=exam,
        student=student,
        user_link=user_link,
        annotation=annotation,
        evaluation=evaluation,
        own_project=own_project,
        foreign_notice=foreign_notice,
        member_notice=member_notice,
        unrelated_notice=unrelated_notice,
        actor_notices=actor_notices,
        generic_notice=generic_notice,
        pending_invite=pending_invite,
        old_email=student.email,
        old_username=student.username,
        pseudonym=student.pseudonym,
        refresh_token=refresh_token,
    )


async def _anonymize(db, user_id, **kwargs):
    kwargs.setdefault("actor_id", None)
    kwargs.setdefault("reason", "test")
    result = await ua.anonymize_user(db, user_id, **kwargs)
    await db.commit()
    return result


# --------------------------------------------------------------------------- #
# Scrub
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_anonymize_scrubs_every_identity_field(async_test_db):
    db = async_test_db
    w = await _student_with_everything(db)

    result = await _anonymize(db, w.student.id, actor_id=w.teacher.id)

    user = await _reload_user(db, w.student.id)
    assert user.name == ua.ANONYMIZED_NAME
    assert user.username.startswith("anon-") and user.username != w.old_username
    assert user.email == f"{user.username}@anonymized.invalid"
    assert user.is_active is False
    assert user.anonymized_at is not None
    assert result.anonymized_at == user.anonymized_at
    assert user.use_pseudonym is True
    assert user.password_set is False
    assert user.email_verified is False
    assert user.mandatory_profile_completed is False
    assert user.timezone == "UTC"
    for field in ua._CLEARED_FIELDS + ua.PROFILE_FIELDS:
        assert getattr(user, field) is None, field
    # A fresh pseudonym: staff saw the old one next to the real name.
    assert user.pseudonym.startswith(ua.ANONYMIZED_PSEUDONYM_PREFIX)
    assert user.pseudonym != w.pseudonym
    assert result.pseudonym == user.pseudonym
    # Kept: the research consent.
    assert user.research_data_consent_accepted_at is not None
    assert result.warnings == [ua.WARNING_HAS_PASSWORD]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anonymize_keeps_answers_grades_and_participation(async_test_db):
    db = async_test_db
    w = await _student_with_everything(db)

    result = await _anonymize(db, w.student.id)

    annotation = (await _fresh(db, Annotation, Annotation.id == w.annotation.id))[0]
    assert annotation.completed_by == w.student.id
    evaluation = (
        await _fresh(db, TaskEvaluation, TaskEvaluation.id == w.evaluation.id)
    )[0]
    assert evaluation.annotation_id == w.annotation.id
    participation = await _fresh(
        db, LtiResourceLinkUser, LtiResourceLinkUser.user_id == w.student.id
    )
    assert [row.resource_link_id for row in participation] == [w.link.id]
    assert len(
        await _fresh(
            db, MarketplaceEntitlement, MarketplaceEntitlement.user_id == w.student.id
        )
    ) == 1
    own = (await _fresh(db, Project, Project.id == w.own_project.id))[0]
    assert own.created_by == w.student.id
    assert result.kept == {
        "annotations": 1,
        "task_evaluations": 1,
        "projects_created": 1,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anonymize_removes_links_syncs_sessions_and_personal_rows(
    async_test_db,
):
    db = async_test_db
    w = await _student_with_everything(db)
    uid = w.student.id

    result = await _anonymize(db, uid)

    for model, column in (
        (LtiUserLink, LtiUserLink.user_id),
        (LtiGradeSync, LtiGradeSync.user_id),
        (RefreshToken, RefreshToken.user_id),
        (UserProfileHistory, UserProfileHistory.user_id),
        (Notification, Notification.user_id),
        (UserNotificationPreference, UserNotificationPreference.user_id),
        (UserColumnPreferences, UserColumnPreferences.user_id),
        (CustomModelCredential, CustomModelCredential.user_id),
        (OrganizationGroupMembership, OrganizationGroupMembership.user_id),
    ):
        assert await _fresh(db, model, column == uid) == [], model.__name__
    assert result.removed["lti_user_links"] == 1
    assert result.removed["lti_grade_syncs"] == 2
    assert result.removed["sessions"] == 1
    assert result.removed["group_memberships"] == 1
    assert result.removed["foreign_notifications"] == 5

    # Memberships stay as inactive rows.
    memberships = await _fresh(
        db, OrganizationMembership, OrganizationMembership.user_id == uid
    )
    assert [m.is_active for m in memberships] == [False]
    assert result.removed["memberships"] == 1

    # Other people's notices that embed the name or address are gone; an
    # unrelated notice stays.
    remaining = {
        n.id
        for n in await _fresh(
            db, Notification, Notification.user_id == w.teacher.id
        )
    }
    assert w.foreign_notice.id not in remaining
    assert w.member_notice.id not in remaining
    for notice in w.actor_notices:
        assert notice.id not in remaining, notice.data
    assert w.unrelated_notice.id in remaining
    assert w.generic_notice.id in remaining

    # Share links are revoked, invitations lose the address and the pointer.
    link = (
        await _fresh(db, ProjectShareLink, ProjectShareLink.created_by == uid)
    )[0]
    assert link.revoked_at is not None
    invite = (await _fresh(db, Invitation, Invitation.id == w.pending_invite.id))[0]
    user = await _reload_user(db, uid)
    assert invite.pending_user_id is None
    assert invite.email == user.email
    assert invite.expires_at <= _now()
    assert result.removed["invitations"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_preview_counts_every_session_row_that_anonymizing_deletes(
    async_test_db,
):
    """The preview promised 0 sessions for a person who had signed out
    (revoked tokens), while anonymizing deleted and audited 2 rows. The
    preview now counts every refresh token row, like the delete does."""
    db = async_test_db
    w = await _student_with_everything(db)
    uid = w.student.id
    # A signed-out session and an expired one next to the open session.
    _token, revoked = await create_refresh_token_async(db, uid)
    revoked.is_active = False
    _token, expired = await create_refresh_token_async(db, uid)
    expired.expires_at = _now() - timedelta(days=1)
    await db.commit()

    preview = await ua.anonymization_footprint(db, uid)
    assert preview["removes"]["sessions"] == 3

    result = await _anonymize(db, uid)

    assert result.removed["sessions"] == preview["removes"]["sessions"]
    assert result.removed["lti_user_links"] == preview["removes"]["lti_user_links"]
    assert result.removed["lti_grade_syncs"] == preview["removes"]["lti_grade_syncs"]
    assert result.removed["memberships"] == preview["removes"]["memberships"]
    assert await _fresh(db, RefreshToken, RefreshToken.user_id == uid) == []
    # Nothing is left to count afterwards.
    after = await ua.anonymization_footprint(db, uid)
    assert after["removes"]["sessions"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_preview_counts_signed_out_sessions(async_test_db):
    """Only revoked tokens left: the preview still names them."""
    db = async_test_db
    org = await make_org(db)
    student = await make_user(db, name="Paula Pause")
    await add_member(db, student, org, OrganizationRole.ANNOTATOR)
    await db.commit()
    for _ in range(2):
        _token, row = await create_refresh_token_async(db, student.id)
        row.is_active = False
    await db.commit()

    preview = await ua.anonymization_footprint(db, student.id)

    assert preview["removes"]["sessions"] == 2
    assert preview["removes"]["memberships"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anonymized_account_cannot_sign_in_or_refresh(async_test_db):
    db = async_test_db
    w = await _student_with_everything(db)
    access_token = create_access_token(data={"user_id": w.student.id})

    def _login(session, name):
        return authenticate_user(name, PASSWORD, session)

    def _refresh(session):
        return refresh_access_token(w.refresh_token, session)

    assert await db.run_sync(_login, w.old_username) is not None
    assert (await db.run_sync(_refresh)).access_token

    await _anonymize(db, w.student.id)
    user = await _reload_user(db, w.student.id)

    for name in (w.old_username, w.old_email, user.username, user.email):
        assert await db.run_sync(_login, name) is None, name

    with pytest.raises(HTTPException) as refused:
        await db.run_sync(_refresh)
    assert refused.value.status_code == 401

    request = Request(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {access_token}".encode())],
        }
    )
    assert await db.run_sync(lambda session: get_current_user(request, session)) is None
    with pytest.raises(HTTPException) as rejected:
        await db.run_sync(lambda session: require_user(request, session))
    assert rejected.value.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_current_user_returns_none_for_a_deactivated_account(
    async_test_db,
):
    db = async_test_db
    user = await make_user(db)
    await db.commit()
    token = create_access_token(data={"user_id": user.id})
    request = Request(
        {"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]}
    )

    active = await db.run_sync(lambda session: get_current_user(request, session))
    assert active is not None and active.id == user.id

    user.is_active = False
    await db.commit()
    assert await db.run_sync(lambda session: get_current_user(request, session)) is None


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_refusals_change_nothing(async_test_db):
    db = async_test_db
    admin = await make_user(db, superadmin=True, name="Super Admin")
    person = await make_user(db, name="Paula Person")
    await db.commit()
    admin_id, person_id = admin.id, person.id

    with pytest.raises(ua.AnonymizationRefused) as superadmin:
        await ua.anonymize_user(db, admin_id, actor_id=None, reason="test")
    assert superadmin.value.blockers == [ua.BLOCKER_SUPERADMIN]

    with pytest.raises(ua.AnonymizationRefused) as own:
        await ua.anonymize_user(db, person_id, actor_id=person_id, reason="test")
    assert own.value.blockers == [ua.BLOCKER_SELF]

    with pytest.raises(ua.AnonymizationUserNotFound):
        await ua.anonymize_user(db, "no-such-user", actor_id=None, reason="test")
    await db.rollback()

    assert (await _reload_user(db, person_id)).name == "Paula Person"
    assert (await _reload_user(db, admin_id)).is_active is True

    await _anonymize(db, person_id)
    with pytest.raises(ua.AnonymizationRefused) as again:
        await ua.anonymize_user(db, person_id, actor_id=None, reason="test")
    assert again.value.blockers == [ua.BLOCKER_ALREADY_ANONYMIZED]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("record", ["subscription", "order"])
async def test_payment_records_block(async_test_db, record):
    db = async_test_db
    person = await make_user(db)
    if record == "subscription":
        db.add(
            StudentSubscription(
                id=_uid(),
                user_id=person.id,
                provider_customer_id="cus_123",
                status="canceled",
            )
        )
    else:
        db.add(
            MarketplaceOrder(
                id=_uid(), buyer_user_id=person.id, amount_cents=500, status="paid"
            )
        )
    await db.commit()

    check = await ua.anonymization_check(db, person, actor_id=None)

    assert check.blockers == [ua.BLOCKER_HAS_PAYMENT_RECORDS]
    assert check.eligible is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_subscription_row_without_provider_ids_does_not_block(async_test_db):
    db = async_test_db
    person = await make_user(db)
    db.add(StudentSubscription(id=_uid(), user_id=person.id, status="incomplete"))
    await db.commit()

    check = await ua.anonymization_check(db, person, actor_id=None)

    assert check.eligible is True
    assert check.warnings == []


def test_reserved_username_prefixes():
    assert ua.is_reserved_username("anon-1234")
    assert ua.is_reserved_username(" LTI-abcdef ")
    assert not ua.is_reserved_username("anonymous")
    assert not ua.is_reserved_username("")
    assert not ua.is_reserved_username(None)


# --------------------------------------------------------------------------- #
# Redis token cleanup (extended edition)
# --------------------------------------------------------------------------- #
def test_revoke_lms_link_tokens_is_a_no_op_without_the_extended_edition(
    monkeypatch,
):
    calls = []
    fake = types.ModuleType("benger_extended.lti.identity")
    fake.revoke_link_tokens = lambda uid: calls.append(uid) or 1
    monkeypatch.setitem(sys.modules, "benger_extended.lti.identity", fake)

    assert ua.revoke_lms_link_tokens(["u-1"]) == 0
    assert calls == []


def test_revoke_lms_link_tokens_calls_the_extended_cleanup(monkeypatch):
    calls = []

    def revoke(uid):
        calls.append(uid)
        if uid == "broken":
            raise RuntimeError("redis down")
        return 2

    fake = types.ModuleType("benger_extended.lti.identity")
    fake.revoke_link_tokens = revoke
    monkeypatch.setitem(sys.modules, "benger_extended.lti.identity", fake)
    monkeypatch.setattr(extensions, "_extended", FakeExtended({}))

    assert ua.revoke_lms_link_tokens(["u-1", None, "broken", "u-2"]) == 4
    assert calls == ["u-1", "broken", "u-2"]
    assert ua.revoke_lms_link_tokens([]) == 0


def test_revoke_lms_link_tokens_survives_a_missing_module(monkeypatch):
    monkeypatch.setattr(extensions, "_extended", FakeExtended({}))
    monkeypatch.setitem(sys.modules, "benger_extended.lti.identity", None)

    assert ua.revoke_lms_link_tokens(["u-1"]) == 0


# --------------------------------------------------------------------------- #
# Superadmin user admin
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_superadmin_anonymizes_an_orphaned_account(
    async_test_client, async_test_db, monkeypatch
):
    db = async_test_db
    w = await _student_with_everything(db)
    admin = await make_user(db, superadmin=True)
    # The student also has a live link on a second org's connection: the
    # superadmin path has no organization scope.
    other_org = await make_org(db)
    other_reg = await make_registration(db, other_org)
    await make_user_link(db, other_reg, w.student)
    await db.commit()
    revoked = []
    monkeypatch.setattr(
        "routers.users.revoke_lms_link_tokens", lambda ids: revoked.extend(ids)
    )

    with as_user(admin):
        preview = await async_test_client.get(
            f"/api/users/{w.student.id}/anonymization"
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["eligible"] is True
        assert body["warnings"] == ["has_password"]
        assert body["keeps"]["annotations"] == 1
        assert body["removes"]["lti_user_links"] == 2

        response = await async_test_client.post(
            f"/api/users/{w.student.id}/anonymize"
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["user_id"] == w.student.id
    assert data["anonymized"] is True
    assert data["removed"]["lti_user_links"] == 2
    assert revoked == [w.student.id]
    user = await _reload_user(db, w.student.id)
    assert user.anonymized_at is not None

    events = await _fresh(
        db, LtiAdminEvent, LtiAdminEvent.action == "user_anonymized"
    )
    assert {e.organization_id for e in events} == {w.org.id, other_org.id}
    for event in events:
        assert event.actor_user_id == admin.id
        assert event.changes["user_id"] == w.student.id
        dumped = repr(event.changes)
        assert w.old_email not in dumped and "Erika" not in dumped


@pytest.mark.integration
@pytest.mark.asyncio
async def test_superadmin_endpoint_refusals(async_test_client, async_test_db):
    db = async_test_db
    admin = await make_user(db, superadmin=True)
    other_admin = await make_user(db, superadmin=True)
    person = await make_user(db)
    await db.commit()
    client = async_test_client

    with as_user(person):
        assert (await client.post(f"/api/users/{admin.id}/anonymize")).status_code == 403
        assert (
            await client.get(f"/api/users/{admin.id}/anonymization")
        ).status_code == 403

    with as_user(admin):
        own = await client.post(f"/api/users/{admin.id}/anonymize")
        assert own.status_code == 409
        assert detail_code(own) == "anonymization_blocked"
        assert own.json()["detail"]["blockers"] == ["superadmin", "self"]

        other = await client.post(f"/api/users/{other_admin.id}/anonymize")
        assert other.status_code == 409
        assert other.json()["detail"]["blockers"] == ["superadmin"]

        missing = await client.post("/api/users/no-such-user/anonymize")
        assert missing.status_code == 404
        assert (
            await client.get("/api/users/no-such-user/anonymization")
        ).status_code == 404

        preview = await client.get(f"/api/users/{other_admin.id}/anonymization")
        assert preview.json()["eligible"] is False
        assert preview.json()["blockers"] == ["superadmin"]

    assert (await _reload_user(db, other_admin.id)).anonymized_at is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anonymized_account_cannot_be_reactivated(
    async_test_client, async_test_db
):
    db = async_test_db
    admin = await make_user(db, superadmin=True)
    person = await make_user(db)
    other = await make_user(db)
    other.is_active = False
    await db.commit()
    await _anonymize(db, person.id)

    with as_user(admin):
        refused = await async_test_client.patch(
            f"/api/users/{person.id}/status", json={"is_active": True}
        )
        assert refused.status_code == 400
        assert refused.json()["detail"] == "account_anonymized"

        # Switching it off again is harmless; other accounts are unaffected.
        off = await async_test_client.patch(
            f"/api/users/{person.id}/status", json={"is_active": False}
        )
        assert off.status_code == 200
        on = await async_test_client.patch(
            f"/api/users/{other.id}/status", json={"is_active": True}
        )
        assert on.status_code == 200
        assert on.json()["is_active"] is True

    assert (await _reload_user(db, person.id)).is_active is False


@pytest.mark.integration
@pytest.mark.parametrize("username", ["lti-0123456789abcdef", "Anon-deadbeef"])
def test_signup_refuses_reserved_usernames(client, test_db, username):
    """Only the system hands out ``lti-`` and ``anon-`` logins: a chosen one
    could pass for an LMS or anonymized account."""
    tag = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/auth/signup",
        json={
            "username": username,
            "email": f"reserved-{tag}@example.com",
            "name": "Reserved Name",
            "password": "securepassword123",
            "legal_expertise_level": "layperson",
            "german_proficiency": "native",
        },
    )
    assert response.status_code == 400, response.text
    assert "reserved" in response.json()["detail"]
    assert test_db.query(User).filter(User.email == f"reserved-{tag}@example.com").first() is None



# --------------------------------------------------------------------------- #
# Name matches stay inside the person's organizations and projects
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_same_named_people_elsewhere_keep_their_notices(async_test_db):
    """Names are not unique: a notice naming another "Erika Musterfrau" in
    an org and project the anonymized student never belonged to stays. The
    student's own org and projects are still cleaned, and ids and addresses
    still match everywhere."""
    db = async_test_db
    w = await _student_with_everything(db)
    other_org = await make_org(db)
    namesake = await make_user(db, name="Erika Musterfrau")
    await add_member(db, namesake, other_org, OrganizationRole.CONTRIBUTOR)
    recipient = await make_user(db, name="Empfänger Anderswo")
    other_project = await make_project(db, namesake)
    elsewhere = [
        Notification(
            id=_uid(),
            user_id=recipient.id,
            type=NotificationType.TASK_ASSIGNED,
            title="Neue Aufgabe",
            message="Sie haben eine neue Aufgabe",
            data={"project_id": other_project.id, "assigned_by": "Erika Musterfrau"},
        ),
        Notification(
            id=_uid(),
            user_id=recipient.id,
            organization_id=other_org.id,
            type=NotificationType.ORGANIZATION_INVITATION_SENT,
            title="Einladung",
            message="Erika Musterfrau sent an invitation",
            data={"inviter_name": "erika musterfrau", "invitee_email": "y@example.org"},
        ),
        Notification(
            id=_uid(),
            user_id=recipient.id,
            organization_id=other_org.id,
            type=NotificationType.MEMBER_JOINED,
            title="New member",
            message="Erika joined",
            data={"new_member_name": "Erika Musterfrau"},
        ),
    ]
    # Found anywhere: the student's id and address.
    by_id_or_address = [
        Notification(
            id=_uid(),
            user_id=recipient.id,
            organization_id=other_org.id,
            type=NotificationType.TASK_ASSIGNED,
            title="Neue Aufgabe",
            message="x",
            data={"assigned_by": "E. M.", "assigned_by_user_id": w.student.id},
        ),
        Notification(
            id=_uid(),
            user_id=recipient.id,
            organization_id=other_org.id,
            type=NotificationType.ORGANIZATION_INVITATION_SENT,
            title="Einladung",
            message="x",
            data={"inviter_name": "Jemand", "invitee_email": w.old_email.upper()},
        ),
    ]
    # In the student's org, by name: gone.
    in_scope = Notification(
        id=_uid(),
        user_id=recipient.id,
        organization_id=w.org.id,
        type=NotificationType.MEMBER_JOINED,
        title="New member",
        message="Erika joined",
        data={"new_member_name": " Erika Musterfrau "},
    )
    db.add_all(elsewhere + by_id_or_address + [in_scope])
    await db.commit()

    result = await _anonymize(db, w.student.id)

    remaining = {
        n.id for n in await _fresh(db, Notification, Notification.user_id == recipient.id)
    }
    for notice in elsewhere:
        assert notice.id in remaining, notice.data
    for notice in by_id_or_address + [in_scope]:
        assert notice.id not in remaining, notice.data
    # The five notices of the base world plus the three above.
    assert result.removed["foreign_notifications"] == 8


# --------------------------------------------------------------------------- #
# Many accounts at once
# --------------------------------------------------------------------------- #
async def _plain_students(db, count, *, org, reg, teacher):
    students = []
    for index in range(count):
        student = await make_user(db, name=f"Student Nummer {index}")
        await add_member(db, student, org, OrganizationRole.ANNOTATOR)
        link = await make_user_link(db, reg, student)
        db.add(
            Notification(
                id=_uid(),
                user_id=teacher.id,
                organization_id=org.id,
                type=NotificationType.MEMBER_JOINED,
                title="New member",
                message="joined",
                data={"new_member_name": student.name},
            )
        )
        db.add(
            Invitation(
                id=_uid(),
                organization_id=org.id,
                email=student.email.upper(),
                role=OrganizationRole.ANNOTATOR,
                token=uuid.uuid4().hex,
                invited_by=teacher.id,
                expires_at=_now() + timedelta(days=3),
            )
        )
        await create_refresh_token_async(db, student.id)
        students.append((student, link))
    await db.commit()
    return students


class _StatementLog:
    def __init__(self):
        self.statements = []

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        self.statements.append(" ".join(statement.split()).lower())

    def count(self, prefix, table):
        return sum(
            1
            for stmt in self.statements
            if stmt.startswith(prefix) and f" {table} " in f"{stmt} "
        )

    def writes(self):
        """Writes other than the ORM flush of the user rows (the ORM may
        send one UPDATE per account there)."""
        return [
            stmt
            for stmt in self.statements
            if stmt.startswith(("delete", "update", "insert"))
            and not stmt.startswith("update users ")
        ]


async def _batch_run(db, count):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    org = await make_org(db)
    reg = await make_registration(db, org)
    teacher = await make_user(db, name="Tanja Teacher")
    students = await _plain_students(db, count, org=org, reg=reg, teacher=teacher)
    admin = await make_user(db, name="Org Admin")
    blocked = await make_user(db, superadmin=True, name="Blocked Superadmin")
    blocked_link = await make_user_link(db, reg, blocked)
    await db.commit()

    log = _StatementLog()
    event.listen(Engine, "before_cursor_execute", log)
    try:
        outcomes = await ua.anonymize_users(
            db,
            [(s.id, link.id) for s, link in students]
            + [(blocked.id, blocked_link.id), ("no-such-user", None)],
            actor_id=admin.id,
            reason="registration_deleted",
            scope=ua.AnonymizationScope(organization_id=org.id),
        )
        await db.commit()
    finally:
        event.remove(Engine, "before_cursor_execute", log)
    return students, teacher, outcomes, log


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_anonymizes_with_a_fixed_number_of_writes(async_test_db):
    """Deleting a connection anonymizes its accounts set-based: one scan of
    the notifications and one statement per table, however many accounts."""
    db = async_test_db
    small = await _batch_run(db, 2)
    large = await _batch_run(db, 9)

    for students, teacher, outcomes, log in (small, large):
        assert [o.user_id for o in outcomes[:-2]] == [s.id for s, _ in students]
        assert outcomes[-1].user_id == "no-such-user"
        assert outcomes[-2].result is None
        assert outcomes[-2].blockers == [ua.BLOCKER_SUPERADMIN]
        assert outcomes[-1].not_found is True
        for (student, _link), outcome in zip(students, outcomes):
            assert outcome.result is not None, outcome
            assert outcome.result.removed["foreign_notifications"] == 1
            assert outcome.result.removed["sessions"] == 1
            assert outcome.result.removed["lti_user_links"] == 1
            assert outcome.result.removed["memberships"] == 1
            assert outcome.result.removed["invitations"] == 1
            user = await _reload_user(db, student.id)
            assert user.anonymized_at is not None and user.name == ua.ANONYMIZED_NAME
            invites = await _fresh(db, Invitation, Invitation.email == user.email)
            assert len(invites) == 1
        remaining = await _fresh(db, Notification, Notification.user_id == teacher.id)
        assert remaining == []
        assert log.count("select", "notifications") == 1
        assert log.count("delete from", "notifications") == 2  # others', own

    # The same writes for 2 and for 9 accounts.
    assert len(small[3].writes()) == len(large[3].writes())
    pseudonyms = {o.result.pseudonym for o in large[2] if o.result}
    assert len(pseudonyms) == 9


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_and_single_scrub_the_same(async_test_db):
    db = async_test_db
    single = await _student_with_everything(db)
    batch = await _student_with_everything(db)

    one = await _anonymize(db, single.student.id)
    (outcome,) = await ua.anonymize_users(
        db, [(batch.student.id, None)], actor_id=None, reason="test"
    )
    await db.commit()

    assert outcome.result.removed == one.removed
    assert outcome.result.kept == one.kept
    assert outcome.result.warnings == one.warnings
    a = await _reload_user(db, single.student.id)
    b = await _reload_user(db, batch.student.id)
    for field in ("name", "is_active", "use_pseudonym", "password_set", "timezone"):
        assert getattr(a, field) == getattr(b, field), field
    for field in ua._CLEARED_FIELDS + ua.PROFILE_FIELDS:
        assert getattr(b, field) is None, field


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_refuses_a_repeated_account(async_test_db):
    db = async_test_db
    w = await _student_with_everything(db)

    first, second = await ua.anonymize_users(
        db,
        [(w.student.id, w.user_link.id), (w.student.id, w.user_link.id)],
        actor_id=None,
        reason="test",
    )
    await db.commit()

    assert first.result is not None
    assert second.result is None
    assert ua.BLOCKER_ALREADY_ANONYMIZED in second.blockers

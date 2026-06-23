"""Auth: user info and profile handlers."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_user_primary_role(user: User, db: Session) -> Optional[str]:
    """Get the user's primary organization role.

    Returns:
        The user's organization role (ORG_ADMIN, CONTRIBUTOR, ANNOTATOR) or None if no memberships.
        Does NOT return 'superadmin' - that's tracked separately via is_superadmin flag.
    """
    from models import OrganizationMembership

    # Get active organization memberships for the user
    memberships = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == user.id, OrganizationMembership.is_active == True)  # noqa: E712
        .all()
    )

    if not memberships:
        return None

    # If user has multiple memberships, prioritize by role hierarchy
    # ORG_ADMIN > CONTRIBUTOR > ANNOTATOR
    for role in ['ORG_ADMIN', 'CONTRIBUTOR', 'ANNOTATOR']:
        if any(m.role.value == role for m in memberships):
            return role

    # Fallback to first membership's role
    return memberships[0].role.value if memberships else None


async def get_user_primary_role_async(user: User, db: AsyncSession) -> Optional[str]:
    """Async twin of :func:`get_user_primary_role`."""
    from models import OrganizationMembership

    result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
    )
    memberships = result.scalars().all()

    if not memberships:
        return None

    for role in ['ORG_ADMIN', 'CONTRIBUTOR', 'ANNOTATOR']:
        if any(m.role.value == role for m in memberships):
            return role

    return memberships[0].role.value if memberships else None


def _ensure_dict(value):
    """Convert JSON string to dict if needed. Handles DB columns that may
    store JSON as a string instead of a native dict."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        import json
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _profile_kwargs(db_user, *, role) -> dict:
    """The full UserProfile field mapping from a DB user — the single source of
    truth shared by the sync and async builders (which differ ONLY in how they
    resolve ``role``). Keeping this in one place stops GET (sync/async) and PUT
    /profile from drifting across the ~40 fields.
    """
    return dict(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        role=role,
        is_superadmin=db_user.is_superadmin,
        is_active=db_user.is_active,
        created_at=(db_user.created_at.isoformat() if db_user.created_at else None),
        updated_at=(db_user.updated_at.isoformat() if db_user.updated_at else None),
        # Pseudonymization fields (Issue #790)
        pseudonym=getattr(db_user, "pseudonym", None),
        use_pseudonym=getattr(db_user, "use_pseudonym", True),
        # Demographic fields
        age=getattr(db_user, "age", None),
        job=getattr(db_user, "job", None),
        years_of_experience=getattr(db_user, "years_of_experience", None),
        # Legal expertise fields
        legal_expertise_level=getattr(db_user, "legal_expertise_level", None),
        german_proficiency=getattr(db_user, "german_proficiency", None),
        degree_program_type=getattr(db_user, "degree_program_type", None),
        current_semester=getattr(db_user, "current_semester", None),
        legal_specializations=getattr(db_user, "legal_specializations", None),
        # German state exam fields
        german_state_exams_count=getattr(db_user, "german_state_exams_count", None),
        german_state_exams_data=getattr(db_user, "german_state_exams_data", None),
        # Issue #1206 fields
        gender=getattr(db_user, "gender", None),
        subjective_competence_civil=getattr(db_user, "subjective_competence_civil", None),
        subjective_competence_public=getattr(db_user, "subjective_competence_public", None),
        subjective_competence_criminal=getattr(db_user, "subjective_competence_criminal", None),
        grade_zwischenpruefung=getattr(db_user, "grade_zwischenpruefung", None),
        grade_vorgeruecktenubung=getattr(db_user, "grade_vorgeruecktenubung", None),
        grade_first_staatsexamen=getattr(db_user, "grade_first_staatsexamen", None),
        grade_second_staatsexamen=getattr(db_user, "grade_second_staatsexamen", None),
        ati_s_scores=_ensure_dict(getattr(db_user, "ati_s_scores", None)),
        ptt_a_scores=_ensure_dict(getattr(db_user, "ptt_a_scores", None)),
        ki_experience_scores=_ensure_dict(getattr(db_user, "ki_experience_scores", None)),
        mandatory_profile_completed=getattr(db_user, "mandatory_profile_completed", None),
        profile_confirmed_at=(
            db_user.profile_confirmed_at.isoformat()
            if getattr(db_user, "profile_confirmed_at", None)
            else None
        ),
    )


def _build_user_profile_response(db_user, db: Session) -> UserProfile:
    """Build a UserProfile response from a database user object (sync role lookup).
    The field mapping lives in :func:`_profile_kwargs` so GET and PUT /profile
    can't drift.
    """
    return UserProfile(**_profile_kwargs(db_user, role=get_user_primary_role(db_user, db)))


async def _build_user_profile_response_async(db_user, db: AsyncSession) -> UserProfile:
    """Async twin of :func:`_build_user_profile_response` — same mapping (via
    :func:`_profile_kwargs`), only the role lookup is async, so the large field
    mapping is genuinely shared, not duplicated.
    """
    role = await get_user_primary_role_async(db_user, db)
    return UserProfile(**_profile_kwargs(db_user, role=role))


@router.get("/me")
async def get_current_user(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Get current authenticated user with organization role"""
    user_role = await get_user_primary_role_async(current_user, db)

    user_dict = {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "email_verified": current_user.email_verified,
        "name": current_user.name,
        "is_superadmin": current_user.is_superadmin,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "role": user_role,
    }

    return user_dict


@router.get("/me/contexts")
async def get_user_contexts(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get current user info and organization contexts in a single call.

    Combines GET /auth/me and GET /organizations/ into one response,
    reducing page load from 2 API calls to 1.
    """
    from sqlalchemy import func

    from models import Organization, OrganizationMembership

    # Build user dict (same as /me)
    user_role = await get_user_primary_role_async(current_user, db)
    user_dict = {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "email_verified": current_user.email_verified,
        "name": current_user.name,
        "is_superadmin": current_user.is_superadmin,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "role": user_role,
    }

    # Build organization contexts
    if current_user.is_superadmin:
        organizations = (
            await db.execute(
                select(Organization).where(Organization.is_active == True)  # noqa: E712
            )
        ).scalars().all()

        member_counts = dict(
            (
                await db.execute(
                    select(
                        OrganizationMembership.organization_id,
                        func.count(OrganizationMembership.id),
                    )
                    .where(OrganizationMembership.is_active == True)  # noqa: E712
                    .group_by(OrganizationMembership.organization_id)
                )
            ).all()
        )

        user_roles = dict(
            (
                await db.execute(
                    select(
                        OrganizationMembership.organization_id, OrganizationMembership.role
                    ).where(
                        OrganizationMembership.user_id == current_user.id,
                        OrganizationMembership.is_active == True,  # noqa: E712
                    )
                )
            ).all()
        )

        org_contexts = [
            {
                "id": org.id,
                "name": org.name,
                "display_name": org.display_name,
                "slug": org.slug,
                "description": org.description,
                "is_active": org.is_active,
                "role": user_roles[org.id].value if org.id in user_roles else None,
                "member_count": member_counts.get(org.id, 0),
            }
            for org in organizations
        ]
    else:
        user_orgs_with_roles = (
            await db.execute(
                select(Organization, OrganizationMembership.role)
                .join(
                    OrganizationMembership,
                    Organization.id == OrganizationMembership.organization_id,
                )
                .where(
                    OrganizationMembership.user_id == current_user.id,
                    OrganizationMembership.is_active == True,  # noqa: E712
                    Organization.is_active == True,  # noqa: E712
                )
            )
        ).all()

        org_ids = [org.id for org, _ in user_orgs_with_roles]
        member_counts = {}
        if org_ids:
            member_counts = dict(
                (
                    await db.execute(
                        select(
                            OrganizationMembership.organization_id,
                            func.count(OrganizationMembership.id),
                        )
                        .where(
                            OrganizationMembership.organization_id.in_(org_ids),
                            OrganizationMembership.is_active == True,  # noqa: E712
                        )
                        .group_by(OrganizationMembership.organization_id)
                    )
                ).all()
            )

        org_contexts = [
            {
                "id": org.id,
                "name": org.name,
                "display_name": org.display_name,
                "slug": org.slug,
                "description": org.description,
                "is_active": org.is_active,
                "role": role.value if role else None,
                "member_count": member_counts.get(org.id, 0),
            }
            for org, role in user_orgs_with_roles
        ]

    return {
        "user": user_dict,
        "organizations": org_contexts,
        "private_mode_available": True,
    }


@router.get("/verify")
async def verify_token_endpoint(current_user: User = Depends(require_user)):
    """Verify if token is valid"""
    return {"valid": True, "user": current_user}


@router.get("/profile", response_model=UserProfile)
async def get_user_profile(
    current_user: User = Depends(require_user), db: AsyncSession = Depends(get_async_db)
):
    """Get current user's profile information"""
    try:
        from models import User as DBUser

        user_id = str(current_user.id)
        logger.debug(f"Fetching profile for user ID: {user_id}")

        db_user = (
            await db.execute(select(DBUser).where(DBUser.id == user_id))
        ).scalar_one_or_none()

        if not db_user:
            logger.warning(f"User not found in database: {user_id}")
            user_role = await get_user_primary_role_async(current_user, db)
            return UserProfile(
                id=current_user.id,
                username=current_user.username,
                email=current_user.email,
                name=current_user.name,
                role=user_role,
                is_superadmin=current_user.is_superadmin,
                is_active=current_user.is_active,
                created_at=(
                    current_user.created_at.isoformat()
                    if hasattr(current_user, "created_at") and current_user.created_at
                    else None
                ),
                updated_at=None,
            )

        # Validate that we got the correct user
        if str(db_user.id) != user_id:
            logger.error(f"User ID mismatch! Requested: {user_id}, Got: {db_user.id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: User data mismatch"
            )

        return await _build_user_profile_response_async(db_user, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user profile for {current_user.id}: {e}")
        user_role = await get_user_primary_role_async(current_user, db)
        return UserProfile(
            id=current_user.id,
            username=current_user.username,
            email=current_user.email,
            name=current_user.name,
            role=user_role,
            is_superadmin=current_user.is_superadmin,
            is_active=True,
            created_at=None,
            updated_at=None,
        )


@router.put("/profile", response_model=UserProfile)
async def update_profile(
    profile_data: UserUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Update current user's profile information.

    Stays on the SYNC DB lane: ``update_user_profile`` carries
    profile-history snapshotting / mandatory-field side effects and has no
    async twin (intentionally — converting it is out of scope for this
    migration). The read profile endpoints (/profile GET, /me, /me/contexts,
    history, status, confirm) are on the async lane.
    """
    updated_user = update_user_profile(
        db=db,
        user_id=current_user.id,
        name=profile_data.name,
        email=profile_data.email,
        use_pseudonym=profile_data.use_pseudonym,
        age=profile_data.age,
        job=profile_data.job,
        years_of_experience=profile_data.years_of_experience,
        legal_expertise_level=profile_data.legal_expertise_level,
        german_proficiency=profile_data.german_proficiency,
        degree_program_type=profile_data.degree_program_type,
        current_semester=profile_data.current_semester,
        legal_specializations=profile_data.legal_specializations,
        german_state_exams_count=profile_data.german_state_exams_count,
        german_state_exams_data=profile_data.german_state_exams_data,
        # Issue #1206: Mandatory profile fields
        gender=profile_data.gender,
        subjective_competence_civil=profile_data.subjective_competence_civil,
        subjective_competence_public=profile_data.subjective_competence_public,
        subjective_competence_criminal=profile_data.subjective_competence_criminal,
        grade_zwischenpruefung=profile_data.grade_zwischenpruefung,
        grade_vorgeruecktenubung=profile_data.grade_vorgeruecktenubung,
        grade_first_staatsexamen=profile_data.grade_first_staatsexamen,
        grade_second_staatsexamen=profile_data.grade_second_staatsexamen,
        ati_s_scores=profile_data.ati_s_scores,
        ptt_a_scores=profile_data.ptt_a_scores,
        ki_experience_scores=profile_data.ki_experience_scores,
    )

    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return _build_user_profile_response(updated_user, db)


@router.post("/complete-profile", response_model=ProfileCompletionResponse)
async def complete_profile(
    profile_data: ProfileCompletionRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Complete profile setup for invited users"""
    from auth_module.user_service import get_password_hash, get_user_by_username_async
    from models import User as DBUser

    db_user = (
        await db.execute(select(DBUser).where(DBUser.id == str(current_user.id)))
    ).scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not db_user.created_via_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile completion is only for invited users",
        )

    if db_user.profile_completed:
        return ProfileCompletionResponse(
            success=True,
            message="Profile already completed",
            user_id=str(db_user.id),
            username=db_user.username,
            email=db_user.email,
            profile_completed=True,
            redirect_url="/dashboard",
        )

    existing_user = await get_user_by_username_async(db, profile_data.username)
    if existing_user and existing_user.id != db_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken"
        )

    db_user.username = profile_data.username
    db_user.hashed_password = get_password_hash(profile_data.password)
    if profile_data.name:
        db_user.name = profile_data.name
    db_user.profile_completed = True

    try:
        await db.commit()
        logger.info(f"Profile completed for user {db_user.id} ({db_user.email})")

        return ProfileCompletionResponse(
            success=True,
            message="Profile completed successfully",
            user_id=str(db_user.id),
            username=db_user.username,
            email=db_user.email,
            profile_completed=True,
            redirect_url="/dashboard",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Error completing profile for user {db_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to complete profile"
        )


@router.get("/check-profile-status", response_model=ProfileStatusResponse)
async def check_profile_status(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Check if user needs to complete their profile"""
    from models import User as DBUser

    db_user = (
        await db.execute(select(DBUser).where(DBUser.id == str(current_user.id)))
    ).scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    has_password = bool(db_user.hashed_password)
    needs_completion = db_user.created_via_invitation and not db_user.profile_completed

    return ProfileStatusResponse(
        user_id=str(db_user.id),
        email=db_user.email,
        profile_completed=db_user.profile_completed,
        created_via_invitation=db_user.created_via_invitation,
        has_password=has_password,
        needs_profile_completion=needs_completion,
        message="Profile completion required" if needs_completion else None,
    )


# === Issue #1206: Mandatory profile endpoints ===


@router.get("/mandatory-profile-status", response_model=MandatoryProfileStatusResponse)
async def get_mandatory_profile_status(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Check mandatory profile completion and re-confirmation status"""
    from auth_module.user_service import check_confirmation_due, get_mandatory_profile_fields
    from models import User as DBUser

    db_user = (
        await db.execute(select(DBUser).where(DBUser.id == str(current_user.id)))
    ).scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    missing_fields = get_mandatory_profile_fields(db_user)
    is_due, next_deadline = check_confirmation_due(db_user)

    # Create in-app notification if confirmation is due (deduplicated)
    if is_due:
        try:
            from models import Notification, NotificationType
            existing = (
                await db.execute(
                    select(Notification).where(
                        Notification.user_id == str(current_user.id),
                        Notification.type == NotificationType.PROFILE_CONFIRMATION_DUE,
                        Notification.is_read == False,  # noqa: E712
                    )
                )
            ).scalars().first()  # tolerate duplicate unread rows (matches sync .first())
            if not existing:
                import uuid as _uuid
                deadline_str = next_deadline.strftime("%d.%m.%Y") if next_deadline else ""
                notification = Notification(
                    id=str(_uuid.uuid4()),
                    user_id=str(current_user.id),
                    type=NotificationType.PROFILE_CONFIRMATION_DUE,
                    title="Profile confirmation due",
                    message=f"Please confirm your research profile by {deadline_str}. Visit your profile page to review and confirm your data.",
                    data={"deadline": next_deadline.isoformat() if next_deadline else None},
                )
                db.add(notification)
                await db.commit()
        except Exception:
            await db.rollback()  # Don't break the status check if notification fails

    return MandatoryProfileStatusResponse(
        mandatory_profile_completed=getattr(db_user, "mandatory_profile_completed", False),
        confirmation_due=is_due,
        confirmation_due_date=next_deadline.isoformat() if next_deadline else None,
        missing_fields=missing_fields,
    )


@router.post("/confirm-profile", response_model=ProfileConfirmationResponse)
async def confirm_profile_endpoint(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Confirm that the user's profile data is still up to date (half-yearly re-confirmation)"""
    from auth_module.user_service import confirm_profile_async

    updated_user = await confirm_profile_async(db, str(current_user.id))
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return ProfileConfirmationResponse(
        success=True,
        confirmed_at=updated_user.profile_confirmed_at.isoformat(),
        message="Profile confirmed successfully",
    )


@router.get("/profile-history")
async def get_profile_history(
    user_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Get profile change history for the current user or (superadmin) another user"""
    from models import User as DBUser, UserProfileHistory

    target_user_id = str(current_user.id)

    if user_id and user_id != target_user_id:
        # Only superadmins can view other users' history
        db_current = (
            await db.execute(select(DBUser).where(DBUser.id == target_user_id))
        ).scalar_one_or_none()
        if not db_current or not db_current.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superadmins can view other users' profile history",
            )
        target_user_id = user_id

    entries = (
        await db.execute(
            select(UserProfileHistory)
            .where(UserProfileHistory.user_id == target_user_id)
            .order_by(UserProfileHistory.changed_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    return [
        {
            "id": entry.id,
            "changed_at": entry.changed_at.isoformat() if entry.changed_at else None,
            "change_type": entry.change_type,
            "snapshot": entry.snapshot,
            "changed_fields": entry.changed_fields,
        }
        for entry in entries
    ]

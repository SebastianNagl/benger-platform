"""
Consolidated authentication endpoints.

Merges all auth functionality from both the legacy router and v1 auth router
into a single router (Issue #1207 Phase 3).
"""

import logging
import os
import traceback
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings

from schemas.auth_schemas import (
    EmailVerificationRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordUpdate,
    ResendVerificationRequest,
    UserProfile,
    UserUpdate,
)
from schemas.profile_completion_schemas import (
    EmailVerificationEnhancedResponse,
    MandatoryProfileStatusResponse,
    ProfileCompletionRequest,
    ProfileCompletionResponse,
    ProfileConfirmationResponse,
    ProfileStatusResponse,
)
from auth_module import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    Token,
    User,
    UserCreate,
    UserLogin,
    authenticate_user,
    create_tokens_with_refresh,
    create_user,
    logout_user,
    refresh_access_token,
    require_superadmin,
    revoke_refresh_token,
)
from auth_module.dependencies import require_user
from auth_module.email_verification import email_verification_service
from auth_module.user_service import change_user_password, update_user_profile
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["authentication"], prefix="/api/auth")


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
        .filter(OrganizationMembership.user_id == user.id, OrganizationMembership.is_active == True)
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


def _build_user_profile_response(db_user, db: Session) -> UserProfile:
    """Build a UserProfile response from a database user object.

    Centralizes the mapping from DB model to API response to avoid duplication
    across GET /profile and PUT /profile endpoints.
    """
    user_role = get_user_primary_role(db_user, db)

    return UserProfile(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        role=user_role,
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


# ---------------------------------------------------------------------------
# Authentication endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=Token,
    summary="User Login",
    description="""
    Authenticate a user and return JWT access and refresh tokens.

    **Authentication Flow:**
    1. Validates username/email and password
    2. Returns JWT access token (expires in 30 minutes)
    3. Sets HttpOnly refresh token cookie (expires in 7 days)
    4. Includes user profile and organization information

    **Security Features:**
    - Rate limiting protection
    - Secure HttpOnly cookies for refresh tokens
    - JWT tokens with role-based claims
    """,
    responses={
        200: {
            "description": "Login successful",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                        "user": {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "username": "admin",
                            "email": "admin@benger.dev",
                            "role": "superadmin",
                            "organizations": ["TUM", "Research Lab"],
                        },
                    }
                }
            },
        },
        401: {"description": "Invalid credentials"},
        429: {"description": "Too many login attempts"},
    },
)
async def login(
    login_data: UserLogin,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login endpoint that returns JWT tokens and sets HttpOnly cookies"""
    logger.info(f"Login attempt - Username: {login_data.username}")
    safe_headers = {k: v for k, v in request.headers.items()
                    if k.lower() not in ("cookie", "authorization", "x-api-key")}
    logger.info(f"Request headers: {safe_headers}")
    logger.info(f"Client host: {request.client.host if request.client else 'Unknown'}")
    logger.info(f"Request URL: {request.url}")

    try:
        user = authenticate_user(login_data.username, login_data.password, db)
        if not user:
            logger.info(f"Authentication failed for user: {login_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if email is verified
        if not user.email_verified:
            logger.info(f"Login blocked - unverified email for user: {login_data.username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email verification required. Please check your email for the verification link.",
            )

        logger.info(f"Authentication successful for user: {login_data.username}")

        # Extract request metadata for security tracking
        user_agent = request.headers.get("user-agent")
        ip_address = request.client.host if request.client else None

        # Create both access and refresh tokens
        token_response = create_tokens_with_refresh(
            user=user,
            db=db,
            user_agent=user_agent,
            ip_address=ip_address,
            include_refresh_token=True,
        )

        # Set access token as HttpOnly cookie for security
        _settings = get_settings()
        response.set_cookie(
            key="access_token",
            value=token_response.access_token,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            httponly=True,
            secure=_settings.is_production,
            samesite="lax",
            path="/",
            domain=_settings.cookie_domain,
        )

        # Set refresh token as HttpOnly cookie for security
        if token_response.refresh_token:
            response.set_cookie(
                key="refresh_token",
                value=token_response.refresh_token,
                max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
                httponly=True,
                secure=_settings.is_production,
                samesite="lax",
                path="/",
                domain=_settings.cookie_domain,
            )

        return token_response
    except Exception as e:
        logger.error(f"Login endpoint error: {str(e)}")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


@router.post("/refresh", response_model=Token)
async def refresh_token_endpoint(
    request: Request, response: Response, db: Session = Depends(get_db)
):
    """Refresh access token using refresh token"""
    # Get refresh token from cookie
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract request metadata for security tracking
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    # Refresh the access token (with token rotation)
    token_response = refresh_access_token(
        refresh_token=refresh_token, db=db, user_agent=user_agent, ip_address=ip_address
    )

    _settings = get_settings()
    if not token_response:
        # Clear invalid refresh token cookie
        response.delete_cookie(
            key="refresh_token",
            httponly=True,
            secure=_settings.is_production,
            samesite="lax",
            path="/",
            domain=_settings.cookie_domain,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Set new access token cookie
    response.set_cookie(
        key="access_token",
        value=token_response.access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=_settings.is_production,
        samesite="lax",
        path="/",
        domain=_settings.cookie_domain,
    )

    # Set new refresh token cookie (token rotation)
    if token_response.refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=token_response.refresh_token,
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=_settings.is_production,
            samesite="lax",
            path="/",
            domain=_settings.cookie_domain,
        )

    return token_response


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Logout endpoint that clears cookies and revokes refresh token"""
    # Get refresh token from cookie to revoke it
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        revoke_refresh_token(refresh_token, db)

    # Clear both cookies
    _settings = get_settings()
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=_settings.is_production,
        samesite="lax",
        path="/",
        domain=_settings.cookie_domain,
    )
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=_settings.is_production,
        samesite="lax",
        path="/",
        domain=_settings.cookie_domain,
    )

    return {"message": "Logged out successfully"}


@router.post("/logout-all")
async def logout_all_devices(
    current_user: User = Depends(require_user),
    response: Response = None,
    db: Session = Depends(get_db),
):
    """Logout from all devices by revoking all refresh tokens"""
    from services.refresh_token_service import revoke_user_tokens
    revoked_count = revoke_user_tokens(db, str(current_user.id))

    if response:
        _settings = get_settings()
        response.delete_cookie(
            key="access_token",
            httponly=True,
            secure=_settings.is_production,
            samesite="lax",
            path="/",
            domain=_settings.cookie_domain,
        )
        response.delete_cookie(
            key="refresh_token",
            httponly=True,
            secure=_settings.is_production,
            samesite="lax",
            path="/",
            domain=_settings.cookie_domain,
        )

    return {
        "message": "Logged out from all devices successfully",
        "revoked_sessions": revoked_count,
    }


# ---------------------------------------------------------------------------
# Signup / Registration
# ---------------------------------------------------------------------------


@router.post("/signup", response_model=User)
async def signup(user_data: UserCreate, request: Request, db: Session = Depends(get_db)):
    """Public signup endpoint - new users default to annotator role"""
    from models import Invitation

    try:
        logger.info(f"Signup attempt for username: {user_data.username}, email: {user_data.email}")

        # Check if this is an invitation-based signup
        invitation_token = getattr(user_data, 'invitation_token', None)
        invitation = None

        if invitation_token:
            invitation = (
                db.query(Invitation)
                .filter(
                    Invitation.token == invitation_token,
                    Invitation.email == user_data.email,
                    Invitation.accepted == False,
                )
                .first()
            )

            if not invitation:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid invitation token",
                )

            if invitation.expires_at <= datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invitation has expired",
                )

            logger.info(f"Invitation-based signup for {user_data.email}")

        # Create user with password
        user = create_user(
            db=db,
            username=user_data.username,
            email=user_data.email,
            name=user_data.name,
            password=user_data.password,
            is_superadmin=False,
            legal_expertise_level=getattr(user_data, 'legal_expertise_level', None),
            german_proficiency=getattr(user_data, 'german_proficiency', None),
            degree_program_type=getattr(user_data, 'degree_program_type', None),
            current_semester=getattr(user_data, 'current_semester', None),
            legal_specializations=getattr(user_data, 'legal_specializations', None),
            gender=getattr(user_data, 'gender', None),
            age=getattr(user_data, 'age', None),
            job=getattr(user_data, 'job', None),
            years_of_experience=getattr(user_data, 'years_of_experience', None),
            subjective_competence_civil=getattr(user_data, 'subjective_competence_civil', None),
            subjective_competence_public=getattr(user_data, 'subjective_competence_public', None),
            subjective_competence_criminal=getattr(user_data, 'subjective_competence_criminal', None),
            grade_zwischenpruefung=getattr(user_data, 'grade_zwischenpruefung', None),
            grade_vorgeruecktenubung=getattr(user_data, 'grade_vorgeruecktenubung', None),
            grade_first_staatsexamen=getattr(user_data, 'grade_first_staatsexamen', None),
            grade_second_staatsexamen=getattr(user_data, 'grade_second_staatsexamen', None),
            ati_s_scores=getattr(user_data, 'ati_s_scores', None),
            ptt_a_scores=getattr(user_data, 'ptt_a_scores', None),
            ki_experience_scores=getattr(user_data, 'ki_experience_scores', None),
        )
        logger.info(f"User created successfully: {user.username} ({user.id})")

        # If this was an invitation signup, accept the invitation and add to organization
        if invitation:
            from uuid import uuid4

            from models import OrganizationMembership

            membership = OrganizationMembership(
                id=str(uuid4()),
                user_id=user.id,
                organization_id=invitation.organization_id,
                role=invitation.role,
                is_active=True,
            )

            invitation.accepted = True
            invitation.accepted_at = datetime.now(timezone.utc)
            invitation.pending_user_id = user.id

            db.add(membership)
            db.commit()

            # Mark user as email verified since they came from invitation
            user.email_verified = True
            user.profile_completed = True
            db.commit()

            logger.info(f"User {user.username} added to organization via invitation")

        # Send verification email only for non-invitation signups
        if not invitation:
            try:
                frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
                success = await email_verification_service.send_verification_email(
                    db=db, user=user, base_url=frontend_url, language="en"
                )
                if success:
                    logger.info(f"Verification email sent to new user: {user.email}")
                else:
                    logger.warning(f"Failed to send verification email to new user: {user.email}")
            except Exception as e:
                logger.error(f"Error sending verification email during signup: {e}", exc_info=True)

        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during signup: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during signup. Please try again later.",
        )


@router.post("/register", response_model=User)
async def register(
    user_data: UserCreate,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Register a new user (superadmin only) - allows setting superadmin status"""
    user = create_user(
        db=db,
        username=user_data.username,
        email=user_data.email,
        name=user_data.name,
        password=user_data.password,
        is_superadmin=False,
    )
    return user


# ---------------------------------------------------------------------------
# User info endpoints
# ---------------------------------------------------------------------------


@router.get("/me")
async def get_current_user(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get current authenticated user with organization role"""
    user_role = get_user_primary_role(current_user, db)

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
    db: Session = Depends(get_db),
):
    """
    Get current user info and organization contexts in a single call.

    Combines GET /auth/me and GET /organizations/ into one response,
    reducing page load from 2 API calls to 1.
    """
    from sqlalchemy import func

    from models import Organization, OrganizationMembership

    # Build user dict (same as /me)
    user_role = get_user_primary_role(current_user, db)
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
        organizations = db.query(Organization).filter(Organization.is_active == True).all()

        member_counts = dict(
            db.query(
                OrganizationMembership.organization_id,
                func.count(OrganizationMembership.id),
            )
            .filter(OrganizationMembership.is_active == True)
            .group_by(OrganizationMembership.organization_id)
            .all()
        )

        user_roles = dict(
            db.query(OrganizationMembership.organization_id, OrganizationMembership.role)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.is_active == True,
            )
            .all()
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
            db.query(Organization, OrganizationMembership.role)
            .join(OrganizationMembership, Organization.id == OrganizationMembership.organization_id)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.is_active == True,
                Organization.is_active == True,
            )
            .all()
        )

        org_ids = [org.id for org, _ in user_orgs_with_roles]
        member_counts = {}
        if org_ids:
            member_counts = dict(
                db.query(
                    OrganizationMembership.organization_id,
                    func.count(OrganizationMembership.id),
                )
                .filter(
                    OrganizationMembership.organization_id.in_(org_ids),
                    OrganizationMembership.is_active == True,
                )
                .group_by(OrganizationMembership.organization_id)
                .all()
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


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------


@router.get("/profile", response_model=UserProfile)
async def get_user_profile(
    current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """Get current user's profile information"""
    try:
        from models import User as DBUser

        user_id = str(current_user.id)
        logger.debug(f"Fetching profile for user ID: {user_id}")

        db_user = db.query(DBUser).filter(DBUser.id == user_id).first()

        if not db_user:
            logger.warning(f"User not found in database: {user_id}")
            user_role = get_user_primary_role(current_user, db)
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

        return _build_user_profile_response(db_user, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user profile for {current_user.id}: {e}")
        user_role = get_user_primary_role(current_user, db)
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
    """Update current user's profile information"""
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


# ---------------------------------------------------------------------------
# Password endpoints
# ---------------------------------------------------------------------------


@router.post("/change-password")
async def change_password(
    password_data: PasswordUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Change current user's password"""
    if password_data.new_password != password_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation do not match",
        )

    success = change_user_password(
        db=db,
        user_id=current_user.id,
        current_password=password_data.current_password,
        new_password=password_data.new_password,
    )

    if success:
        return {"message": "Password changed successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password",
        )


@router.post("/request-password-reset")
async def request_password_reset(
    reset_request: PasswordResetRequest,
    db: Session = Depends(get_db),
):
    """Request a password reset email"""
    from app.auth_module.password_reset import password_reset_service
    from models import User as DBUser

    user = db.query(DBUser).filter(DBUser.email == reset_request.email).first()

    # Always return success to prevent email enumeration
    if not user:
        logger.info(f"Password reset requested for non-existent email: {reset_request.email}")
        return {"message": "If the email exists, a password reset link has been sent"}

    try:
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        success = await password_reset_service.send_password_reset_email(
            db=db, user=user, base_url=frontend_url, language=reset_request.language
        )
        if success:
            logger.info(f"Password reset email sent to: {user.email}")
        else:
            logger.warning(f"Failed to send password reset email to: {user.email}")
    except Exception as e:
        logger.error(f"Error sending password reset email: {e}")

    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/reset-password")
async def reset_password(
    reset_confirm: PasswordResetConfirm,
    db: Session = Depends(get_db),
):
    """Reset password using a valid reset token"""
    from app.auth_module.password_reset import password_reset_service

    if reset_confirm.new_password != reset_confirm.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation do not match",
        )

    success = password_reset_service.reset_password(
        db=db, token=reset_confirm.token, new_password=reset_confirm.new_password
    )

    if success:
        logger.info("Password reset successful")
        return {"message": "Password has been reset successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )


# ---------------------------------------------------------------------------
# Email verification endpoints
# ---------------------------------------------------------------------------


@router.post("/verify-email")
async def verify_email(
    verification_request: EmailVerificationRequest,
    db: Session = Depends(get_db),
):
    """Verify email address using verification token (POST with body)"""
    success, message = email_verification_service.verify_email_with_token(
        db=db, token=verification_request.token
    )

    if success:
        logger.info(f"Email verification successful: {message}")
        return {"success": True, "message": message}
    else:
        logger.warning(f"Email verification failed: {message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )


@router.post("/verify-email/{token}")
async def verify_email_with_token(token: str, db: Session = Depends(get_db)):
    """Verify email address using verification token (path parameter)"""
    try:
        success, message = email_verification_service.verify_email_with_token(db, token)

        if success:
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying email with token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify email",
        )


@router.post("/resend-verification")
async def resend_verification_email(
    resend_request: ResendVerificationRequest,
    db: Session = Depends(get_db),
):
    """Resend email verification link"""
    from models import User as DBUser

    user = db.query(DBUser).filter(DBUser.email == resend_request.email).first()

    # Always return success to prevent email enumeration
    if not user:
        logger.info(f"Verification resend requested for non-existent email: {resend_request.email}")
        return {
            "message": "If the email exists and is unverified, a verification link has been sent"
        }

    if user.email_verified:
        logger.info(
            f"Verification resend requested for already verified email: {resend_request.email}"
        )
        return {
            "message": "If the email exists and is unverified, a verification link has been sent"
        }

    try:
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        success = await email_verification_service.send_verification_email(
            db=db, user=user, base_url=frontend_url, language=resend_request.language
        )
        if success:
            logger.info(f"Verification email resent to: {user.email}")
        else:
            logger.warning(f"Failed to resend verification email to: {user.email}")
    except Exception as e:
        logger.error(f"Error resending verification email: {e}")

    return {"message": "If the email exists and is unverified, a verification link has been sent"}


@router.post("/verify-email-enhanced/{token}", response_model=EmailVerificationEnhancedResponse)
async def verify_email_enhanced(
    token: str,
    db: Session = Depends(get_db),
):
    """Enhanced email verification that returns user type info"""
    from models import Invitation
    from models import User as DBUser

    success, message = email_verification_service.verify_email_with_token(db, token)

    if not success:
        return EmailVerificationEnhancedResponse(
            success=False,
            message=message,
            user_type="unknown",
            profile_completed=False,
            redirect_url=None,
        )

    # Get user from token to determine type
    from auth_module.email_verification import email_verification_service as evs

    token_data = evs.validate_verification_token(token)
    if not token_data:
        return EmailVerificationEnhancedResponse(
            success=True,
            message=message,
            user_type="unknown",
            profile_completed=True,
            redirect_url="/login",
        )

    user_id, email = token_data
    db_user = db.query(DBUser).filter(DBUser.id == user_id).first()

    if not db_user:
        return EmailVerificationEnhancedResponse(
            success=True,
            message=message,
            user_type="unknown",
            profile_completed=True,
            redirect_url="/login",
        )

    user_type = "invited" if db_user.created_via_invitation else "self_registered"

    # Check for pending invitations
    invitation_info = None
    if db_user.created_via_invitation and db_user.invitation_token:
        invitation = (
            db.query(Invitation).filter(Invitation.token == db_user.invitation_token).first()
        )
        if invitation:
            invitation_info = {
                "organization_id": invitation.organization_id,
                "role": invitation.role.value,
            }

    # Determine redirect URL
    if db_user.created_via_invitation and not db_user.profile_completed:
        redirect_url = "/complete-profile"
    elif db_user.created_via_invitation:
        redirect_url = (
            f"/organizations/{invitation_info['organization_id']}"
            if invitation_info
            else "/dashboard"
        )
    else:
        redirect_url = "/login"

    return EmailVerificationEnhancedResponse(
        success=True,
        message=message,
        user_type=user_type,
        profile_completed=db_user.profile_completed,
        redirect_url=redirect_url,
        invitation_info=invitation_info,
    )


# ---------------------------------------------------------------------------
# Profile completion endpoints (invitation-based onboarding)
# ---------------------------------------------------------------------------


@router.post("/complete-profile", response_model=ProfileCompletionResponse)
async def complete_profile(
    profile_data: ProfileCompletionRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Complete profile setup for invited users"""
    from auth_module.user_service import get_password_hash, get_user_by_username
    from models import User as DBUser

    db_user = db.query(DBUser).filter(DBUser.id == str(current_user.id)).first()
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

    existing_user = get_user_by_username(db, profile_data.username)
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
        db.commit()
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
        db.rollback()
        logger.error(f"Error completing profile for user {db_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to complete profile"
        )


@router.get("/check-profile-status", response_model=ProfileStatusResponse)
async def check_profile_status(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Check if user needs to complete their profile"""
    from models import User as DBUser

    db_user = db.query(DBUser).filter(DBUser.id == str(current_user.id)).first()
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
    db: Session = Depends(get_db),
):
    """Check mandatory profile completion and re-confirmation status"""
    from auth_module.user_service import check_confirmation_due, get_mandatory_profile_fields
    from models import User as DBUser

    db_user = db.query(DBUser).filter(DBUser.id == str(current_user.id)).first()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    missing_fields = get_mandatory_profile_fields(db_user)
    is_due, next_deadline = check_confirmation_due(db_user)

    # Create in-app notification if confirmation is due (deduplicated)
    if is_due:
        try:
            from models import Notification, NotificationType
            existing = db.query(Notification).filter(
                Notification.user_id == str(current_user.id),
                Notification.type == NotificationType.PROFILE_CONFIRMATION_DUE,
                Notification.is_read == False,  # noqa: E712
            ).first()
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
                db.commit()
        except Exception:
            db.rollback()  # Don't break the status check if notification fails

    return MandatoryProfileStatusResponse(
        mandatory_profile_completed=getattr(db_user, "mandatory_profile_completed", False),
        confirmation_due=is_due,
        confirmation_due_date=next_deadline.isoformat() if next_deadline else None,
        missing_fields=missing_fields,
    )


@router.post("/confirm-profile", response_model=ProfileConfirmationResponse)
async def confirm_profile_endpoint(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Confirm that the user's profile data is still up to date (half-yearly re-confirmation)"""
    from auth_module.user_service import confirm_profile

    updated_user = confirm_profile(db, str(current_user.id))
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
    db: Session = Depends(get_db),
):
    """Get profile change history for the current user or (superadmin) another user"""
    from models import User as DBUser, UserProfileHistory

    target_user_id = str(current_user.id)

    if user_id and user_id != target_user_id:
        # Only superadmins can view other users' history
        db_current = db.query(DBUser).filter(DBUser.id == target_user_id).first()
        if not db_current or not db_current.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superadmins can view other users' profile history",
            )
        target_user_id = user_id

    entries = (
        db.query(UserProfileHistory)
        .filter(UserProfileHistory.user_id == target_user_id)
        .order_by(UserProfileHistory.changed_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

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

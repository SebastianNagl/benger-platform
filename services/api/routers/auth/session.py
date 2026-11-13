"""Auth: login / signup / registration handlers."""
import asyncio

from account_activation import mask_email
from auth_module.auth_cookies import expire_legacy_cookies
from auth_module.models import AccessTokenResponse, SessionResponse
from auth_module.session_origin import clear_session_origin
from sqlalchemy import func

from services import auth_rate_limit
from services.rate_limiter import get_client_ip

from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


def _login_hint(login: str) -> str:
    """Log-safe form of a typed login (username or email) with no account id."""
    if "@" in login:
        return mask_email(login)
    return login[:2] + "…"


def _authenticate_login(login_data: UserLogin, request: Request, db: Session) -> User:
    """The checks every password sign-in passes, for ``/login`` and ``/token``.

    Rate limits, the password, the verified e-mail address and the
    ``after_user_login`` extension hook. Returns the signed-in user.
    """
    # Per-IP soft limit first (counts every attempt), then the account
    # throttle (counts nothing). Both run before the password is checked.
    auth_rate_limit.enforce_ip_limit(request, auth_rate_limit.LOGIN)
    auth_rate_limit.check_login_throttle(login_data.username)

    user = authenticate_user(login_data.username, login_data.password, db)
    if not user:
        logger.info(f"Authentication failed for login: {_login_hint(login_data.username)}")
        auth_rate_limit.record_login_failure(login_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # The password was right: earlier failures no longer count.
    auth_rate_limit.reset_login_failures(login_data.username)

    # Check if email is verified
    if not user.email_verified:
        logger.info(f"Login blocked - unverified email for user: {user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Please check your email for the verification link.",
        )

    logger.info(f"Authentication successful for user: {user.id}")

    # Extension hook: host-aware login onboarding — an EXISTING account's
    # first sign-in on a student-locked host (vertretbar.net) attaches the
    # Vertretbar org membership (the signup hook only covers accounts
    # CREATED there). Runs before token creation so the issued profile
    # already carries the new membership. The context is derived
    # server-side (not a spoofable body field). The hook contract takes
    # the ORM user (it mutates and commits) — authenticate_user returns
    # the Pydantic schema, so re-fetch the row. Never let a hook failure
    # break login.
    try:
        from extensions import after_user_login as _after_user_login_ext
        from models import User as DBUser

        db_user = db.query(DBUser).filter(DBUser.id == str(user.id)).first()
        if db_user is not None:
            login_context = {
                "host": request.headers.get("x-forwarded-host")
                or request.headers.get("host"),
                "origin": request.headers.get("origin")
                or request.headers.get("referer"),
            }
            _after_user_login_ext(db, db_user, login_context)
    except Exception as e:
        logger.error(f"after_user_login hook failed (non-fatal): {e}", exc_info=True)

    return user


_LOGIN_SECURITY_NOTES = """
    - Brute-force limits: after 10 failed attempts for one login (username
      or email as typed, case-insensitive) within a sliding 15 minutes, each
      further attempt within 60 seconds of the last failure is refused
      without checking the password (about one try per minute); a correct
      password after the wait clears the counter. One client IP may try
      1000 times per 15 minutes (`AUTH_IP_LIMIT_LOGIN`).
      Limited requests get 429 with `Retry-After` and
      `detail={"code": "rate_limited", "retry_after": <seconds>}`;
      503 `rate_limiter_unavailable` while Redis is unreachable
"""

_LOGIN_ERROR_RESPONSES = {
    401: {"description": "Invalid credentials"},
    403: {"description": "E-mail address not verified"},
    429: {"description": "Too many login attempts (account throttled or IP limit)"},
    503: {"description": "Rate limiter unavailable (Redis down), login refused"},
}


@router.post(
    "/login",
    response_model=SessionResponse,
    summary="User Login",
    description="""
    Authenticate a user for a browser session.

    **Authentication Flow:**
    1. Validates username/email and password
    2. Sets the HttpOnly `access_token` cookie (a JWT valid for 60 minutes)
    3. Sets the HttpOnly `refresh_token` cookie (valid for 7 days, replaced
       on every `POST /api/auth/refresh`)
    4. Returns the user profile and organization information

    The tokens are never part of the response body, so script on the page
    can not read them. Scripts that need a bearer token use
    `POST /api/auth/token` or an access key.

    **Security Features:**"""
    + _LOGIN_SECURITY_NOTES,
    responses={
        200: {
            "description": "Login successful",
            "content": {
                "application/json": {
                    "example": {
                        "token_type": "bearer",
                        "expires_in": 3600,
                        "user": {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "username": "admin",
                            "email": "admin@benger.dev",
                            "is_superadmin": True,
                        },
                    }
                }
            },
        },
        **_LOGIN_ERROR_RESPONSES,
    },
)
def login(
    login_data: UserLogin,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login endpoint that sets the session tokens as HttpOnly cookies"""
    try:
        user = _authenticate_login(login_data, request, db)

        # Extract request metadata for security tracking
        user_agent = request.headers.get("user-agent")
        ip_address = get_client_ip(request)

        # Create both access and refresh tokens
        token_response = create_tokens_with_refresh(
            user=user,
            db=db,
            user_agent=user_agent,
            ip_address=ip_address,
            include_refresh_token=True,
        )

        # Drop domain-wide cookies of older releases first (before the new
        # host-only ones, see expire_legacy_cookies).
        expire_legacy_cookies(response)

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
            )

        # A password login is a regular session: drop any LMS-launch marker.
        clear_session_origin(response)

        # Shaped by response_model=SessionResponse: no token in the body.
        return {
            "token_type": token_response.token_type,
            "expires_in": token_response.expires_in,
            "user": token_response.user,
        }
    except HTTPException:
        # Expected outcomes (401/403/429/503), not crashes worth a traceback.
        raise
    except Exception as e:
        logger.error(f"Login endpoint error: {str(e)}")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


@router.post(
    "/token",
    response_model=AccessTokenResponse,
    summary="Access token for scripts",
    description="""
    Exchange username/email and password for an access token in the response
    body, to send as `Authorization: Bearer <token>`. Meant for scripts and
    API clients; the browser app uses `POST /api/auth/login`, whose tokens
    stay in HttpOnly cookies.

    Sets no cookie and issues no refresh token: the token is valid for 60
    minutes, after which the script requests a new one. For long-running
    automation prefer an access key (`/api/access-keys`).

    Same checks as login (password, verified e-mail address, limits):"""
    + _LOGIN_SECURITY_NOTES,
    responses=_LOGIN_ERROR_RESPONSES,
)
def issue_access_token(
    login_data: UserLogin,
    request: Request,
    db: Session = Depends(get_db),
):
    """Password grant for API clients: the access token in the body, no cookies"""
    user = _authenticate_login(login_data, request, db)
    token_response = create_tokens_with_refresh(
        user=user, db=db, include_refresh_token=False
    )
    return {
        "access_token": token_response.access_token,
        "token_type": token_response.token_type,
        "expires_in": token_response.expires_in,
        "user": token_response.user,
    }


@router.post("/signup", response_model=User)
async def signup(user_data: UserCreate, request: Request, db: Session = Depends(get_db)):
    """Public signup endpoint - new users default to annotator role"""
    from models import Invitation

    await asyncio.to_thread(auth_rate_limit.enforce_ip_limit, request, auth_rate_limit.SIGNUP)

    try:
        logger.info(f"Signup attempt for email: {mask_email(user_data.email)}")

        # Check if this is an invitation-based signup
        invitation_token = getattr(user_data, 'invitation_token', None)
        invitation = None

        if invitation_token:
            invitation = (
                db.query(Invitation)
                .filter(
                    Invitation.token == invitation_token,
                    func.lower(Invitation.email) == user_data.email.strip().lower(),
                    Invitation.accepted == False,  # noqa: E712
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

            logger.info(f"Invitation-based signup for invitation {invitation.id}")

        # Extension hook: extended edition gates signup on research-data consent.
        # No-op when extended is not loaded.
        from extensions import validate_signup as _validate_signup_ext
        _validate_signup_ext(db, user_data)

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
            research_data_consent_accepted=getattr(user_data, 'research_data_consent_accepted', None),
        )
        logger.info(f"User created successfully: {user.id}")

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

            # Group-scoped invitation: the new user also joins the group with
            # the invitation's group role (same helper as the accept endpoint
            # and email verification - without this, an email
            # invite into a group would land a NEW registrant in the org but
            # outside the group, hiding every group-scoped project).
            from org_groups import ensure_invitation_group_membership

            ensure_invitation_group_membership(db, invitation, user.id)

            db.commit()

            from extensions import after_invitation_accepted

            after_invitation_accepted(db, invitation, user.id)

            # Mark user as email verified since they came from invitation
            user.email_verified = True
            user.profile_completed = True
            db.commit()

            logger.info(f"User {user.id} added to organization via invitation")

        # Extension hook: onboard a student who signed up via a student-locked
        # host (vertretbar.net) — sets preferred_ui_mode + Vertretbar membership.
        # The request origin is derived server-side (not a spoofable body field).
        # No-op when extended is not loaded. Never let a hook failure break signup.
        try:
            from extensions import after_user_signup as _after_user_signup_ext

            signup_context = {
                "host": request.headers.get("x-forwarded-host")
                or request.headers.get("host"),
                "origin": request.headers.get("origin") or request.headers.get("referer"),
            }
            _after_user_signup_ext(db, user, signup_context)
        except Exception as e:
            logger.error(f"after_user_signup hook failed (non-fatal): {e}", exc_info=True)

        # Send verification email only for non-invitation signups
        if not invitation:
            try:
                # Brand the verification email from the signup host (Vertretbar on
                # vertretbar.net, BenGER otherwise) — see resolve_email_brand.
                signup_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
                # No language= → send_verification_email defaults it from the host
                # brand (Vertretbar signups get a German email, benger English).
                success = await email_verification_service.send_verification_email(
                    db=db, user=user, host=signup_host
                )
                if success:
                    logger.info(f"Verification email sent to new user: {user.id}")
                else:
                    logger.warning(f"Failed to send verification email to new user: {user.id}")
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
def register(
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

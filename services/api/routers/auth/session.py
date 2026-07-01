"""Auth: login / signup / registration handlers."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)

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

            logger.info(f"Invitation-based signup for {user_data.email}")

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
                frontend_url = get_settings().frontend_url
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

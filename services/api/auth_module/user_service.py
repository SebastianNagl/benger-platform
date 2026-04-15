"""
User service layer for database operations

Consolidated user management functions for the BenGER authentication system.
"""

import html
import re
import uuid
from typing import List, Optional

import bcrypt
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import User


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        # Handle any encoding issues
        return False


# Common naming aliases for better developer experience
hash_password = get_password_hash  # Alias for common naming convention
check_password = verify_password  # Alias for alternative naming


def sanitize_user_input(input_string: str) -> str:
    """
    Sanitize user input to prevent XSS attacks

    Args:
        input_string: Raw user input

    Returns:
        Sanitized string safe for storage and display
    """
    if not input_string:
        return input_string

    # Remove leading/trailing whitespace
    sanitized = input_string.strip()

    # HTML escape to prevent XSS
    sanitized = html.escape(sanitized)

    # Additional security: block dangerous patterns
    dangerous_patterns = [
        r"<script[^>]*>.*?</script>",
        r"<iframe[^>]*>.*?</iframe>",
        r"<object[^>]*>.*?</object>",
        r"<embed[^>]*>.*?</embed>",
        r"javascript:",
        r"data:",
        r"vbscript:",
    ]

    for pattern in dangerous_patterns:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE | re.DOTALL)

    # Limit length to prevent abuse
    max_length = 100
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].strip()

    return sanitized


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """Get user by ID"""
    try:
        return db.query(User).filter(User.id == user_id).first()
    except Exception as e:
        # Handle database schema issues gracefully (e.g., in tests with old schema)
        if "no such column: users.is_superadmin" in str(e):
            import os

            if os.getenv("TESTING") == "true":
                print(f"Database schema issue in test mode: {e}")
                return None
        # Re-raise other exceptions
        raise


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Get user by username"""
    try:
        return db.query(User).filter(User.username == username).first()
    except Exception as e:
        # Handle database schema issues gracefully (e.g., in tests with old schema)
        if "no such column: users.is_superadmin" in str(e):
            import os

            if os.getenv("TESTING") == "true":
                print(f"Database schema issue in test mode: {e}")
                return None
        raise


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get user by email"""
    try:
        return db.query(User).filter(User.email == email).first()
    except Exception as e:
        # Handle database schema issues gracefully (e.g., in tests with old schema)
        if "no such column: users.is_superadmin" in str(e):
            import os

            if os.getenv("TESTING") == "true":
                print(f"Database schema issue in test mode: {e}")
                return None
        raise


def get_user_by_username_or_email(db: Session, username_or_email: str) -> Optional[User]:
    """Get user by username or email"""
    try:
        return (
            db.query(User)
            .filter(
                or_(
                    User.username == username_or_email,
                    User.email == username_or_email,
                )
            )
            .first()
        )
    except Exception as e:
        # Handle database schema issues gracefully (e.g., in tests with old schema)
        if "no such column: users.is_superadmin" in str(e):
            import os

            if os.getenv("TESTING") == "true":
                print(f"Database schema issue in test mode: {e}")
                return None
        raise


def get_users(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
    """Get all users with pagination"""
    return db.query(User).offset(skip).limit(limit).all()


def authenticate_user(db: Session, username_or_email: str, password: str) -> Optional[User]:
    """Authenticate user with username/email and password"""
    user = get_user_by_username_or_email(db, username_or_email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(
    db: Session,
    username: str,
    email: str,
    name: str,
    password: str,
    is_superadmin: bool = False,
    # Legal expertise fields for human baseline groups
    legal_expertise_level: Optional[str] = None,
    german_proficiency: Optional[str] = None,
    degree_program_type: Optional[str] = None,
    current_semester: Optional[int] = None,
    legal_specializations: Optional[List[str]] = None,
    # Issue #1206: Mandatory profile fields
    gender: Optional[str] = None,
    age: Optional[int] = None,
    subjective_competence_civil: Optional[int] = None,
    subjective_competence_public: Optional[int] = None,
    subjective_competence_criminal: Optional[int] = None,
    grade_zwischenpruefung: Optional[float] = None,
    grade_vorgeruecktenubung: Optional[float] = None,
    grade_first_staatsexamen: Optional[float] = None,
    grade_second_staatsexamen: Optional[float] = None,
    ati_s_scores: Optional[dict] = None,
    ptt_a_scores: Optional[dict] = None,
    ki_experience_scores: Optional[dict] = None,
    job: Optional[str] = None,
    years_of_experience: Optional[int] = None,
) -> User:
    """Create a new user"""
    # Import email validation
    try:
        from email_validation import validate_email_with_details
    except ImportError:
        # Fallback to basic validation if module not available
        def validate_email_with_details(email):
            if "@" not in email or "." not in email:
                return False, "Invalid email format"
            return True, None

    # Validate email format
    is_valid, error_msg = validate_email_with_details(email)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid email address: {error_msg}",
        )

    # Normalize email to lowercase to prevent case-sensitive duplicates
    # RFC 5321 specifies that email addresses should be case-insensitive
    normalized_email = email.lower().strip()

    # Check if username already exists
    if get_user_by_username(db, username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Check if email already exists (using normalized email)
    if get_user_by_email(db, normalized_email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Sanitize user input to prevent XSS attacks
    sanitized_name = sanitize_user_input(name)

    # Generate unique pseudonym for privacy-first leaderboards (Issue #790)
    # Use explicit path import to avoid conflict with tests/utils package
    import importlib.util
    import os

    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pseudonym_module_path = os.path.join(api_dir, "utils", "pseudonym_generator.py")
    spec = importlib.util.spec_from_file_location("pseudonym_generator", pseudonym_module_path)
    pseudonym_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pseudonym_module)
    generate_pseudonym = pseudonym_module.generate_pseudonym

    # Get existing pseudonyms to avoid collisions
    existing_pseudonyms = set(
        p[0] for p in db.query(User.pseudonym).filter(User.pseudonym.isnot(None)).all()
    )
    pseudonym = generate_pseudonym(existing_pseudonyms)

    # Create new user
    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(password)

    # Convert legal expertise enum strings to enum values if provided
    from models import (
        DegreeProgramType,
        GermanProficiency,
        LegalExpertiseLevel,
    )

    legal_level_enum = None
    if legal_expertise_level:
        try:
            legal_level_enum = LegalExpertiseLevel(legal_expertise_level)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid legal expertise level: {legal_expertise_level}",
            )

    german_prof_enum = None
    if german_proficiency:
        try:
            german_prof_enum = GermanProficiency(german_proficiency)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid German proficiency level: {german_proficiency}",
            )

    degree_type_enum = None
    if degree_program_type:
        try:
            degree_type_enum = DegreeProgramType(degree_program_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid degree program type: {degree_program_type}",
            )

    # Validate legal_specializations values
    valid_specializations = None
    if legal_specializations:
        valid_spec_values = [
            "civil_law", "criminal_law", "public_administrative_law",
            "eu_international_law", "tax_law", "labor_law", "ip_law", "other",
        ]
        valid_specializations = [
            spec for spec in legal_specializations if spec in valid_spec_values
        ]

    # Only store semester if user is a law student
    stored_semester = None
    if legal_level_enum == LegalExpertiseLevel.LAW_STUDENT and current_semester:
        stored_semester = current_semester

    db_user = User(
        id=user_id,
        username=username,
        email=normalized_email,  # Store normalized email in database
        email_verified=False,  # New users start with unverified email
        name=sanitized_name,
        hashed_password=hashed_password,
        is_superadmin=is_superadmin,
        is_active=True,
        pseudonym=pseudonym,  # Assign unique pseudonym (GDPR-compliant)
        use_pseudonym=True,  # Default to privacy-first (users can opt-out)
        # Legal expertise fields for research stratification
        legal_expertise_level=legal_level_enum,
        german_proficiency=german_prof_enum,
        degree_program_type=degree_type_enum,
        current_semester=stored_semester,
        legal_specializations=valid_specializations,
    )

    db.add(db_user)

    # Issue #1206: Set mandatory profile fields on the newly created user
    from models import Gender

    if gender is not None:
        valid_genders = [g.value for g in Gender]
        if gender not in valid_genders:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid gender: {gender}. Must be one of: {valid_genders}",
            )
        db_user.gender = gender

    if age is not None:
        db_user.age = age

    # Validate and set psychometric scales
    for field_name, value in [
        ("ati_s_scores", ati_s_scores),
        ("ptt_a_scores", ptt_a_scores),
        ("ki_experience_scores", ki_experience_scores),
    ]:
        if value is not None:
            _validate_psychometric_scale(field_name, value)
            setattr(db_user, field_name, value)

    # Set subjective competence fields
    for field_name, value in [
        ("subjective_competence_civil", subjective_competence_civil),
        ("subjective_competence_public", subjective_competence_public),
        ("subjective_competence_criminal", subjective_competence_criminal),
    ]:
        if value is not None:
            setattr(db_user, field_name, value)

    # Set objective grade fields
    for field_name, value in [
        ("grade_zwischenpruefung", grade_zwischenpruefung),
        ("grade_vorgeruecktenubung", grade_vorgeruecktenubung),
        ("grade_first_staatsexamen", grade_first_staatsexamen),
        ("grade_second_staatsexamen", grade_second_staatsexamen),
    ]:
        if value is not None:
            setattr(db_user, field_name, value)

    if job is not None:
        db_user.job = job
    if years_of_experience is not None:
        db_user.years_of_experience = years_of_experience

    # Check if all mandatory fields are present
    expertise_str = legal_expertise_level
    if _check_mandatory_fields_present(
        legal_expertise_level=expertise_str,
        degree_program_type=degree_program_type,
        gender=gender,
        age=age,
        german_proficiency=german_proficiency,
        subjective_competence_civil=subjective_competence_civil,
        subjective_competence_public=subjective_competence_public,
        subjective_competence_criminal=subjective_competence_criminal,
        ati_s_scores=ati_s_scores,
        ptt_a_scores=ptt_a_scores,
        ki_experience_scores=ki_experience_scores,
        grade_zwischenpruefung=grade_zwischenpruefung,
        grade_vorgeruecktenubung=grade_vorgeruecktenubung,
        grade_first_staatsexamen=grade_first_staatsexamen,
        grade_second_staatsexamen=grade_second_staatsexamen,
        job=job,
        years_of_experience=years_of_experience,
    ):
        from datetime import datetime, timezone
        db_user.mandatory_profile_completed = True
        db_user.profile_confirmed_at = datetime.now(timezone.utc)

    # If any mandatory profile fields were provided, create a signup history entry
    profile_fields_provided = any(v is not None for v in [
        gender, age, subjective_competence_civil, subjective_competence_public,
        subjective_competence_criminal, grade_zwischenpruefung, grade_vorgeruecktenubung,
        grade_first_staatsexamen, grade_second_staatsexamen, ati_s_scores, ptt_a_scores,
        ki_experience_scores, job, years_of_experience,
    ])
    if profile_fields_provided:
        from datetime import datetime, timezone
        from models import UserProfileHistory

        snapshot = create_profile_snapshot(db_user)
        history_entry = UserProfileHistory(
            id=str(uuid.uuid4()),
            user_id=db_user.id,
            changed_at=datetime.now(timezone.utc),
            change_type="signup",
            snapshot=snapshot,
            changed_fields=["all"],
        )
        db.add(history_entry)

    db.commit()
    db.refresh(db_user)
    return db_user


def update_user_superadmin_status(db: Session, user_id: str, is_superadmin: bool) -> Optional[User]:
    """Update user superadmin status"""
    user = get_user_by_id(db, user_id)
    if not user:
        return None

    user.is_superadmin = is_superadmin
    db.commit()
    db.refresh(user)
    return user


def update_user_status(db: Session, user_id: str, is_active: bool) -> Optional[User]:
    """Update user active status"""
    user = get_user_by_id(db, user_id)
    if not user:
        return None

    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: str) -> bool:
    """Delete a user by ID - preserves projects and critical data"""
    from models import (
        FeatureFlag,
        Invitation,
        OrganizationMembership,
        RefreshToken,
        UserNotificationPreference,
    )

    # Find a fallback superadmin for reassigning ownership
    fallback_user = (
        db.query(User).filter(User.username == "pschOrr95", User.is_superadmin == True).first()
    )
    if not fallback_user:
        fallback_user = (
            db.query(User).filter(User.is_superadmin == True, User.id != user_id).first()
        )

    if not fallback_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete user: No other superadmin exists to reassign data to",
        )

    FALLBACK_SUPERADMIN_ID = fallback_user.id

    user = get_user_by_id(db, user_id)
    if not user:
        return False

    if user_id == FALLBACK_SUPERADMIN_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the fallback superadmin user",
        )

    try:
        db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(OrganizationMembership).filter(OrganizationMembership.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(Invitation).filter(Invitation.pending_user_id == user_id).update(
            {"pending_user_id": None}, synchronize_session=False
        )
        db.query(Invitation).filter(Invitation.invited_by == user_id).update(
            {"invited_by": FALLBACK_SUPERADMIN_ID}, synchronize_session=False
        )
        db.flush()  # Ensure invitation FK references are cleared before user delete
        db.query(UserNotificationPreference).filter(
            UserNotificationPreference.user_id == user_id
        ).delete(synchronize_session=False)
        db.query(FeatureFlag).filter(FeatureFlag.created_by == user_id).update(
            {"created_by": FALLBACK_SUPERADMIN_ID}, synchronize_session=False
        )

        try:
            from project_models import (
                Annotation,
                ExportLog,
                GeneratedResult,
                ImportJob,
                Project,
                ProjectCollaborator,
                Task,
                TaskAssignment,
            )

            db.query(Project).filter(Project.created_by == user_id).update(
                {"created_by": FALLBACK_SUPERADMIN_ID}, synchronize_session=False
            )
            db.query(ProjectCollaborator).filter(ProjectCollaborator.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(TaskAssignment).filter(TaskAssignment.assigned_by == user_id).update(
                {"assigned_by": FALLBACK_SUPERADMIN_ID}, synchronize_session=False
            )
            db.query(TaskAssignment).filter(TaskAssignment.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(Task).filter(Task.assigned_to == user_id).update(
                {"assigned_to": None}, synchronize_session=False
            )
            db.query(Task).filter(Task.created_by == user_id).update(
                {"created_by": FALLBACK_SUPERADMIN_ID}, synchronize_session=False
            )
            db.query(Task).filter(Task.updated_by == user_id).update(
                {"updated_by": FALLBACK_SUPERADMIN_ID}, synchronize_session=False
            )
            db.query(Annotation).filter(Annotation.completed_by == user_id).update(
                {"completed_by": FALLBACK_SUPERADMIN_ID}, synchronize_session=False
            )
            db.query(GeneratedResult).filter(GeneratedResult.created_by == user_id).update(
                {"created_by": FALLBACK_SUPERADMIN_ID}, synchronize_session=False
            )
            db.query(ExportLog).filter(ExportLog.exported_by == user_id).update(
                {"exported_by": FALLBACK_SUPERADMIN_ID}, synchronize_session=False
            )
            db.query(ImportJob).filter(ImportJob.imported_by == user_id).update(
                {"imported_by": FALLBACK_SUPERADMIN_ID}, synchronize_session=False
            )
        except ImportError:
            pass

        db.flush()
        db.delete(user)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user: {str(e)}",
        )


def get_all_users(db: Session) -> List[User]:
    """Get all users"""
    return db.query(User).all()


def init_feature_flags(db: Session, created_by_user_id: str):
    """Initialize essential feature flags for the application."""
    import uuid
    from datetime import datetime

    from models import FeatureFlag

    print("Initializing feature flags...")

    feature_flags = [
        {"name": "data", "description": "Enable access to Data Management features and page", "is_enabled": True},
        {"name": "generations", "description": "Enable access to Generation features and page", "is_enabled": True},
        {"name": "evaluations", "description": "Enable access to Evaluation features and page", "is_enabled": True},
        {"name": "reports", "description": "Enable access to Reports page", "is_enabled": True},
        {"name": "how-to", "description": "Enable access to How-To page", "is_enabled": True},
        {"name": "leaderboards", "description": "Enable access to Leaderboards page with pseudonymized annotation rankings (Issue #790)", "is_enabled": True},
    ]

    for flag_data in feature_flags:
        existing_flag = db.query(FeatureFlag).filter(FeatureFlag.name == flag_data["name"]).first()
        if not existing_flag:
            try:
                flag = FeatureFlag(
                    id=str(uuid.uuid4()),
                    name=flag_data["name"],
                    description=flag_data["description"],
                    is_enabled=flag_data["is_enabled"],
                    created_by=created_by_user_id,
                    created_at=datetime.utcnow(),
                )
                db.add(flag)
                db.commit()
                print(f"  Created feature flag: {flag_data['name']}")
            except Exception as e:
                print(f"  Failed to create feature flag {flag_data['name']}: {e}")
                db.rollback()

    print("Feature flags initialization complete!")


def _complete_demo_user_profile(db: Session, user):
    """Fill mandatory profile fields for a demo user if any are missing.

    Uses get_mandatory_profile_fields() to check actual field completeness
    rather than trusting the mandatory_profile_completed boolean flag.
    Only sets fields that are None, so manually changed values are preserved.
    """
    import json
    from datetime import datetime, timezone
    from decimal import Decimal

    missing = get_mandatory_profile_fields(user)
    if not missing:
        return False

    psychometric_scores = {"item_1": 4, "item_2": 4, "item_3": 4, "item_4": 4}

    # Set all defaults where the field is None. We can't rely on only setting
    # fields from `missing` because get_mandatory_profile_fields() returns early
    # when legal_expertise_level is None, omitting expertise-dependent fields
    # like grade_zwischenpruefung that become required once the level is set.
    defaults = {
        "gender": "maennlich",
        "age": 30,
        "german_proficiency": "native",
        "legal_expertise_level": "law_student",
        "subjective_competence_civil": 4,
        "subjective_competence_public": 4,
        "subjective_competence_criminal": 4,
        "grade_zwischenpruefung": Decimal("8.00"),
        "grade_vorgeruecktenubung": Decimal("8.00"),
        "ati_s_scores": psychometric_scores,
        "ptt_a_scores": psychometric_scores,
        "ki_experience_scores": psychometric_scores,
    }

    for field_name, default_value in defaults.items():
        if getattr(user, field_name, None) is None:
            setattr(user, field_name, default_value)

    # Re-check after setting defaults
    still_missing = get_mandatory_profile_fields(user)
    if not still_missing:
        user.mandatory_profile_completed = True
        user.profile_confirmed_at = datetime.now(timezone.utc)

    return True


def init_demo_users(db: Session):
    """Initialize demo users if they don't exist (development only)"""
    import os
    import uuid

    from models import Organization, OrganizationMembership

    environment = os.getenv("ENVIRONMENT", "development").lower()

    if environment not in ("development", "test", "e2e"):
        print(f"Environment '{environment}' is not dev/test - skipping demo user creation for security")
        return

    print("Creating demo users for development environment...")

    default_org = db.query(Organization).filter(Organization.name == "TUM").first()
    if not default_org:
        default_org = Organization(
            id=str(uuid.uuid4()),
            name="TUM",
            display_name="TUM",
            slug="tum",
            description="TUM organization for development testing",
            is_active=True,
        )
        db.add(default_org)
        db.commit()
        print("Created default TUM organization")

    admin_user = get_user_by_email(db, "admin@example.com")
    if not admin_user:
        try:
            admin_user = create_user(
                db=db,
                username="admin",
                email="admin@example.com",
                name="System Administrator",
                password="admin",
                is_superadmin=True,
            )
            admin_user.email_verified = True
            admin_user.email_verification_method = "self"
            db.commit()
            print("Created demo user: admin (superadmin)")

            existing_membership = (
                db.query(OrganizationMembership)
                .filter(
                    OrganizationMembership.user_id == admin_user.id,
                    OrganizationMembership.organization_id == default_org.id,
                )
                .first()
            )
            if not existing_membership:
                membership = OrganizationMembership(
                    id=str(uuid.uuid4()),
                    user_id=admin_user.id,
                    organization_id=default_org.id,
                    role="ORG_ADMIN",
                )
                db.add(membership)
                db.commit()
        except Exception as e:
            print(f"Database initialization error creating admin: {e}")
            return
    else:
        print("Demo user already exists: admin")

    init_feature_flags(db, admin_user.id)

    demo_users = [
        {"username": "org_admin", "email": "org_admin@example.com", "name": "Organization Administrator", "password": "admin", "is_superadmin": False, "org_role": "ORG_ADMIN"},
        {"username": "contributor", "email": "contributor@example.com", "name": "Test Contributor", "password": "admin", "is_superadmin": False, "org_role": "CONTRIBUTOR"},
        {"username": "annotator", "email": "annotator@example.com", "name": "Test Annotator", "password": "admin", "is_superadmin": False, "org_role": "ANNOTATOR"},
        {"username": "annotator2", "email": "annotator2@example.com", "name": "Test Annotator 2", "password": "admin", "is_superadmin": False, "org_role": "ANNOTATOR"},
        {"username": "annotator3", "email": "annotator3@example.com", "name": "Test Annotator 3", "password": "admin", "is_superadmin": False, "org_role": "ANNOTATOR"},
        {"username": "basicuser", "email": "basicuser@example.com", "name": "Basic User", "password": "admin", "is_superadmin": False, "org_role": None},
    ]

    for user_data in demo_users:
        try:
            existing_user = get_user_by_email(db, user_data["email"])
        except Exception as e:
            print(f"Database initialization error: {e}")
            return

        if not existing_user:
            try:
                user = create_user(
                    db=db,
                    username=user_data["username"],
                    email=user_data["email"],
                    name=user_data["name"],
                    password=user_data["password"],
                    is_superadmin=user_data["is_superadmin"],
                )
                user.email_verified = True
                user.email_verification_method = "self"
                db.commit()
                print(f"Created demo user: {user_data['email']}")
                existing_user = user
            except HTTPException:
                pass

        if existing_user and user_data["org_role"] is not None:
            membership = (
                db.query(OrganizationMembership)
                .filter(
                    OrganizationMembership.user_id == existing_user.id,
                    OrganizationMembership.organization_id == default_org.id,
                )
                .first()
            )
            if not membership:
                membership = OrganizationMembership(
                    id=str(uuid.uuid4()),
                    user_id=existing_user.id,
                    organization_id=default_org.id,
                    role=user_data["org_role"],
                    is_active=True,
                )
                db.add(membership)
                db.commit()

    # Complete mandatory profile fields for all demo users
    from models import User

    demo_emails = [
        "admin@example.com", "org_admin@example.com", "contributor@example.com",
        "annotator@example.com", "annotator2@example.com", "annotator3@example.com",
        "basicuser@example.com",
    ]
    completed_count = 0
    for email in demo_emails:
        user = db.query(User).filter(User.email == email).first()
        if user and _complete_demo_user_profile(db, user):
            completed_count += 1
    if completed_count > 0:
        db.commit()
        print(f"Completed mandatory profile fields for {completed_count} demo users")


def update_user_profile(
    db: Session,
    user_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    use_pseudonym: Optional[bool] = None,
    age: Optional[int] = None,
    job: Optional[str] = None,
    years_of_experience: Optional[int] = None,
    # Legal expertise fields (structured enums)
    legal_expertise_level: Optional[str] = None,
    german_proficiency: Optional[str] = None,
    degree_program_type: Optional[str] = None,
    current_semester: Optional[int] = None,
    legal_specializations: Optional[List[str]] = None,
    # German state exam fields
    german_state_exams_count: Optional[int] = None,
    german_state_exams_data: Optional[list] = None,
    # Issue #1206: Mandatory profile fields
    gender: Optional[str] = None,
    subjective_competence_civil: Optional[int] = None,
    subjective_competence_public: Optional[int] = None,
    subjective_competence_criminal: Optional[int] = None,
    grade_zwischenpruefung: Optional[float] = None,
    grade_vorgeruecktenubung: Optional[float] = None,
    grade_first_staatsexamen: Optional[float] = None,
    grade_second_staatsexamen: Optional[float] = None,
    ati_s_scores: Optional[dict] = None,
    ptt_a_scores: Optional[dict] = None,
    ki_experience_scores: Optional[dict] = None,
) -> Optional[User]:
    """Update user profile information"""
    user = get_user_by_id(db, user_id)
    if not user:
        return None

    # Capture old values of profile fields before applying updates (for change tracking)
    _tracked_fields = [
        "name", "email", "use_pseudonym", "age", "job", "years_of_experience",
        "legal_expertise_level", "german_proficiency", "degree_program_type",
        "current_semester", "legal_specializations",
        "german_state_exams_count", "german_state_exams_data",
        "gender", "subjective_competence_civil", "subjective_competence_public",
        "subjective_competence_criminal", "grade_zwischenpruefung",
        "grade_vorgeruecktenubung", "grade_first_staatsexamen",
        "grade_second_staatsexamen", "ati_s_scores", "ptt_a_scores",
        "ki_experience_scores",
    ]
    _old_values = {}
    for _f in _tracked_fields:
        _val = getattr(user, _f, None)
        # Convert enums to their string value for comparison
        if _val is not None and hasattr(_val, 'value'):
            _val = _val.value
        _old_values[_f] = _val

    # Check if new email is provided and validate it
    if email and email != user.email:
        # Import email validation
        try:
            from email_validation import validate_email_with_details
        except ImportError:
            # Fallback to basic validation if module not available
            def validate_email_with_details(email):
                if "@" not in email or "." not in email:
                    return False, "Invalid email format"
                return True, None

        # Validate email format
        is_valid, error_msg = validate_email_with_details(email)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid email address: {error_msg}",
            )

        # Check if email is already taken by another user
        existing_email_user = get_user_by_email(db, email)
        if existing_email_user and existing_email_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered to another user",
            )

    # Update fields if provided
    if name is not None:
        user.name = name
    if email is not None and email != user.email:
        user.email = email
        # Reset email verification when email changes
        if hasattr(user, "email_verified"):
            user.email_verified = False

    # Update pseudonym privacy preference (Issue #790)
    if use_pseudonym is not None:
        user.use_pseudonym = use_pseudonym

    # Update demographic fields
    if age is not None:
        user.age = age
    if job is not None:
        user.job = job
    if years_of_experience is not None:
        user.years_of_experience = years_of_experience

    # Update legal expertise fields (with enum validation)
    from models import (
        DegreeProgramType,
        GermanProficiency,
        LegalExpertiseLevel,
    )

    if legal_expertise_level is not None:
        try:
            user.legal_expertise_level = LegalExpertiseLevel(legal_expertise_level)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid legal expertise level: {legal_expertise_level}",
            )

    if german_proficiency is not None:
        try:
            user.german_proficiency = GermanProficiency(german_proficiency)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid German proficiency level: {german_proficiency}",
            )

    if degree_program_type is not None:
        try:
            user.degree_program_type = DegreeProgramType(degree_program_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid degree program type: {degree_program_type}",
            )

    # Only store semester if user is a law student
    if current_semester is not None:
        if user.legal_expertise_level == LegalExpertiseLevel.LAW_STUDENT:
            user.current_semester = current_semester
        else:
            user.current_semester = None

    if legal_specializations is not None:
        valid_spec_values = [
            "civil_law", "criminal_law", "public_administrative_law",
            "eu_international_law", "tax_law", "labor_law", "ip_law", "other",
        ]
        user.legal_specializations = [
            spec for spec in legal_specializations if spec in valid_spec_values
        ]

    # Update German state exam fields
    if german_state_exams_count is not None:
        user.german_state_exams_count = german_state_exams_count
    if german_state_exams_data is not None:
        user.german_state_exams_data = german_state_exams_data

    # Issue #1206: Gender
    if gender is not None:
        from models import Gender
        valid_genders = [g.value for g in Gender]
        if gender not in valid_genders:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid gender: {gender}. Must be one of: {valid_genders}",
            )
        user.gender = gender

    # Issue #1206: Subjective competence (Likert 1-7)
    for field_name, value in [
        ("subjective_competence_civil", subjective_competence_civil),
        ("subjective_competence_public", subjective_competence_public),
        ("subjective_competence_criminal", subjective_competence_criminal),
    ]:
        if value is not None:
            if not isinstance(value, int) or value < 1 or value > 7:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{field_name} must be an integer between 1 and 7",
                )
            setattr(user, field_name, value)

    # Issue #1206: Objective grades
    for field_name, value in [
        ("grade_zwischenpruefung", grade_zwischenpruefung),
        ("grade_vorgeruecktenubung", grade_vorgeruecktenubung),
        ("grade_first_staatsexamen", grade_first_staatsexamen),
        ("grade_second_staatsexamen", grade_second_staatsexamen),
    ]:
        if value is not None:
            setattr(user, field_name, value)

    # Issue #1206: Psychometric scales
    for field_name, value in [
        ("ati_s_scores", ati_s_scores),
        ("ptt_a_scores", ptt_a_scores),
        ("ki_experience_scores", ki_experience_scores),
    ]:
        if value is not None:
            _validate_psychometric_scale(field_name, value)
            setattr(user, field_name, value)

    # Issue #1206: Check if mandatory profile is now complete
    missing = get_mandatory_profile_fields(user)
    if not missing and not user.mandatory_profile_completed:
        user.mandatory_profile_completed = True

    # Issue #1206: Saving profile counts as confirming it
    from datetime import datetime, timezone as tz
    user.profile_confirmed_at = datetime.now(tz.utc)

    # Issue #1206: Track profile change history
    # Determine which fields actually changed by comparing old vs new values
    _new_values = {}
    for _f in _tracked_fields:
        _val = getattr(user, _f, None)
        if _val is not None and hasattr(_val, 'value'):
            _val = _val.value
        _new_values[_f] = _val

    _changed_fields = [f for f in _tracked_fields if _old_values[f] != _new_values[f]]

    if _changed_fields:
        from datetime import datetime, timezone
        from models import UserProfileHistory

        snapshot = create_profile_snapshot(user)
        history_entry = UserProfileHistory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            changed_at=datetime.now(timezone.utc),
            change_type="update",
            snapshot=snapshot,
            changed_fields=_changed_fields,
        )
        db.add(history_entry)

    db.commit()
    db.refresh(user)
    return user


def change_user_password(
    db: Session, user_id: str, current_password: str, new_password: str
) -> bool:
    """Change user password after verifying current password"""
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Verify current password
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Update password
    user.hashed_password = get_password_hash(new_password)
    db.commit()
    return True


def _validate_psychometric_scale(field_name: str, scale: dict):
    """Validate a psychometric scale (ATI-S, PTT-A, KI-Erfahrung).

    Each scale must be a dict with keys item_1..item_4, each an int 1-7.
    """
    if not isinstance(scale, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be a JSON object with keys item_1..item_4",
        )

    expected_keys = {"item_1", "item_2", "item_3", "item_4"}
    if set(scale.keys()) != expected_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must have exactly keys: {sorted(expected_keys)}",
        )

    for key, value in scale.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name}.{key} must be an integer between 1 and 7",
            )
        if value < 1 or value > 7:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name}.{key} must be between 1 and 7, got {value}",
            )


def get_mandatory_profile_fields(user) -> list:
    """Return list of missing mandatory profile field names for a user.

    Which fields are required depends on the user's legal_expertise_level
    and degree_program_type:
    - All users: gender, age, german_proficiency, subjective_competence_*,
      ati_s_scores, ptt_a_scores, ki_experience_scores, legal_expertise_level
    - law_student+: grade_zwischenpruefung, grade_vorgeruecktenubung
    - referendar+: grade_first_staatsexamen
    - graduated_no_practice+: grade_second_staatsexamen, job, years_of_experience

    LLB/LLM degree programs are exempt from all grade requirements as they
    do not follow the traditional German Staatsexamen grading structure.
    """
    missing = []

    # legal_expertise_level is always required
    expertise = None
    if user.legal_expertise_level is not None:
        expertise = user.legal_expertise_level.value if hasattr(user.legal_expertise_level, 'value') else str(user.legal_expertise_level)
    else:
        missing.append("legal_expertise_level")

    # Base fields required for everyone
    if user.gender is None:
        missing.append("gender")
    if user.age is None:
        missing.append("age")

    if user.german_proficiency is None:
        missing.append("german_proficiency")

    if user.subjective_competence_civil is None:
        missing.append("subjective_competence_civil")
    if user.subjective_competence_public is None:
        missing.append("subjective_competence_public")
    if user.subjective_competence_criminal is None:
        missing.append("subjective_competence_criminal")

    if user.ati_s_scores is None:
        missing.append("ati_s_scores")
    if user.ptt_a_scores is None:
        missing.append("ptt_a_scores")
    if user.ki_experience_scores is None:
        missing.append("ki_experience_scores")

    # Expertise-dependent fields
    if expertise is None:
        return missing

    # LLB/LLM programs don't follow the traditional Staatsexamen grading structure
    degree_type = user.degree_program_type.value if hasattr(user.degree_program_type, 'value') else str(user.degree_program_type) if user.degree_program_type else None
    is_incomparable_grading = degree_type in ("llb", "llm")

    # Levels that require Zwischenpruefung and Vorgeruecktenubung grades
    student_and_above = {"law_student", "referendar", "graduated_no_practice", "practicing_lawyer", "judge_professor"}
    if expertise in student_and_above and not is_incomparable_grading:
        if user.grade_zwischenpruefung is None:
            missing.append("grade_zwischenpruefung")
        if user.grade_vorgeruecktenubung is None:
            missing.append("grade_vorgeruecktenubung")

    # Levels that require 1. Staatsexamen
    referendar_and_above = {"referendar", "graduated_no_practice", "practicing_lawyer", "judge_professor"}
    if expertise in referendar_and_above and not is_incomparable_grading:
        if user.grade_first_staatsexamen is None:
            missing.append("grade_first_staatsexamen")

    # Levels that require 2. Staatsexamen + job info
    graduated_and_above = {"graduated_no_practice", "practicing_lawyer", "judge_professor"}
    if expertise in graduated_and_above:
        if not is_incomparable_grading:
            if user.grade_second_staatsexamen is None:
                missing.append("grade_second_staatsexamen")
        if user.job is None:
            missing.append("job")
        if user.years_of_experience is None:
            missing.append("years_of_experience")

    return missing


def check_confirmation_due(user) -> tuple:
    """Check if the user's profile re-confirmation is due.

    Confirmation deadlines are April 15 and October 15 each year.
    Returns (is_due: bool, next_deadline: datetime).
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    # Determine the most recent past deadline and the next future deadline
    year = now.year
    april_deadline = datetime(year, 4, 15, tzinfo=timezone.utc)
    october_deadline = datetime(year, 10, 15, tzinfo=timezone.utc)

    if now >= october_deadline:
        most_recent_deadline = october_deadline
        next_deadline = datetime(year + 1, 4, 15, tzinfo=timezone.utc)
    elif now >= april_deadline:
        most_recent_deadline = april_deadline
        next_deadline = october_deadline
    else:
        most_recent_deadline = datetime(year - 1, 10, 15, tzinfo=timezone.utc)
        next_deadline = april_deadline

    confirmed_at = user.profile_confirmed_at
    if confirmed_at is None:
        return True, next_deadline

    # Ensure timezone-aware
    if confirmed_at.tzinfo is None:
        confirmed_at = confirmed_at.replace(tzinfo=timezone.utc)

    # If confirmed before the most recent deadline, it's due
    if confirmed_at < most_recent_deadline:
        return True, next_deadline

    return False, next_deadline


def create_profile_snapshot(user) -> dict:
    """Create a JSON-serializable snapshot of the user's profile fields."""
    from decimal import Decimal

    def _get_value(field):
        val = getattr(user, field, None)
        if val is not None and hasattr(val, 'value'):
            return val.value
        if isinstance(val, Decimal):
            return float(val)
        return val

    fields = [
        "legal_expertise_level", "german_proficiency", "degree_program_type",
        "current_semester", "gender", "age", "job", "years_of_experience",
        "subjective_competence_civil", "subjective_competence_public",
        "subjective_competence_criminal", "grade_zwischenpruefung",
        "grade_vorgeruecktenubung", "grade_first_staatsexamen",
        "grade_second_staatsexamen", "ati_s_scores", "ptt_a_scores",
        "ki_experience_scores",
    ]
    return {f: _get_value(f) for f in fields}


def _check_mandatory_fields_present(**kwargs) -> bool:
    """Check if all mandatory fields for a given expertise level are present.

    Used during registration/profile update to determine if mandatory_profile_completed
    should be set to True.
    """
    expertise = kwargs.get("legal_expertise_level")
    if expertise is None:
        return False

    # Base fields required for everyone
    base_fields = ["gender", "age", "german_proficiency",
                   "subjective_competence_civil", "subjective_competence_public",
                   "subjective_competence_criminal",
                   "ati_s_scores", "ptt_a_scores", "ki_experience_scores"]

    for field in base_fields:
        if kwargs.get(field) is None:
            return False

    # LLB/LLM programs don't follow the traditional Staatsexamen grading structure
    degree_type = kwargs.get("degree_program_type")
    is_incomparable_grading = degree_type in ("llb", "llm")

    student_and_above = {"law_student", "referendar", "graduated_no_practice", "practicing_lawyer", "judge_professor"}
    if expertise in student_and_above and not is_incomparable_grading:
        if kwargs.get("grade_zwischenpruefung") is None:
            return False
        if kwargs.get("grade_vorgeruecktenubung") is None:
            return False

    referendar_and_above = {"referendar", "graduated_no_practice", "practicing_lawyer", "judge_professor"}
    if expertise in referendar_and_above and not is_incomparable_grading:
        if kwargs.get("grade_first_staatsexamen") is None:
            return False

    graduated_and_above = {"graduated_no_practice", "practicing_lawyer", "judge_professor"}
    if expertise in graduated_and_above:
        if not is_incomparable_grading:
            if kwargs.get("grade_second_staatsexamen") is None:
                return False
        if kwargs.get("job") is None:
            return False
        if kwargs.get("years_of_experience") is None:
            return False

    return True


def confirm_profile(db: Session, user_id: str):
    """Confirm a user's profile is up to date. Records a snapshot in history."""
    from datetime import datetime, timezone
    from models import UserProfileHistory

    user = get_user_by_id(db, user_id)
    if not user:
        return None

    # Check all mandatory fields are filled
    missing = get_mandatory_profile_fields(user)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot confirm profile with missing fields: {missing}",
        )

    now = datetime.now(timezone.utc)
    snapshot = create_profile_snapshot(user)

    # Record confirmation in history
    history_entry = UserProfileHistory(
        id=str(uuid.uuid4()),
        user_id=user_id,
        changed_at=now,
        change_type="confirmation",
        snapshot=snapshot,
        changed_fields=["profile_confirmed_at"],
    )
    db.add(history_entry)

    user.profile_confirmed_at = now
    user.mandatory_profile_completed = True
    db.commit()
    db.refresh(user)
    return user


def initialize_database(db: Session):
    """Initialize database with demo users"""
    init_demo_users(db)

"""
Token management services

This module contains token-related services including refresh token management
"""

from typing import Optional

from sqlalchemy.orm import Session

import refresh_token_service

from .models import User
from .service import create_tokens_with_refresh


class TokenService:
    """
    Service for handling access tokens
    """

    @staticmethod
    def create_access_token_for_user(
        user: User,
        db: Session,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        include_refresh_token: bool = True,
    ):
        """Create access token for a user"""
        return create_tokens_with_refresh(
            user=user,
            db=db,
            user_agent=user_agent,
            ip_address=ip_address,
            include_refresh_token=include_refresh_token,
        )


class RefreshTokenService:
    """
    Service for handling refresh tokens

    This is a wrapper around the existing refresh_token_service module
    for consistency with the new auth module structure
    """

    @staticmethod
    def create_refresh_token(
        db: Session,
        user_id: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> str:
        """Create a new refresh token"""
        return refresh_token_service.create_refresh_token(
            db=db, user_id=user_id, user_agent=user_agent, ip_address=ip_address
        )

    @staticmethod
    def validate_refresh_token(db: Session, token: str) -> Optional[str]:
        """Validate refresh token and return user ID if valid"""
        return refresh_token_service.validate_refresh_token(db, token)

    @staticmethod
    def revoke_refresh_token(db: Session, token: str) -> bool:
        """Revoke a refresh token"""
        return refresh_token_service.revoke_refresh_token(db, token)

    @staticmethod
    def revoke_all_user_tokens(db: Session, user_id: str) -> bool:
        """Revoke all refresh tokens for a user"""
        return refresh_token_service.revoke_all_user_tokens(db, user_id)

    @staticmethod
    def cleanup_expired_tokens(db: Session) -> int:
        """Clean up expired refresh tokens"""
        return refresh_token_service.cleanup_expired_tokens(db)

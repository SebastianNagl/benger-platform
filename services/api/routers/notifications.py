"""
Notification API endpoints for BenGER

This module provides REST API endpoints for the notification system:
- Get user notifications with pagination
- Mark notifications as read
- Manage user notification preferences
- Server-Sent Events for real-time updates
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from notification_service import NotificationService

# Import email service for testing
try:
    from email_service import email_service

    EMAIL_SERVICE_AVAILABLE = True
except ImportError:
    EMAIL_SERVICE_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# Pydantic models for API
class NotificationResponse(BaseModel):
    id: str
    type: str
    title: str
    message: str
    data: Optional[Dict] = None
    is_read: bool
    created_at: str
    organization_id: Optional[str] = None

    class Config:
        from_attributes = True


class NotificationPreferencesResponse(BaseModel):
    # Per-type per-channel: {type: {enabled, in_app, email}}.
    # Legacy clients that expected `bool` per type still work because the
    # service accepts both shapes on update.
    preferences: Dict[str, Any]


class NotificationPreferencesUpdate(BaseModel):
    preferences: Dict[str, Any] = Field(
        ...,
        description=(
            "Mapping of notification types to either a bool (legacy) or "
            "{enabled, in_app, email} per-channel object."
        ),
    )


class UnreadCountResponse(BaseModel):
    count: int


class BulkOperationRequest(BaseModel):
    notification_ids: List[str] = Field(..., description="List of notification IDs")


class BulkOperationResponse(BaseModel):
    success: bool
    count: int
    message: str


class NotificationGroupsResponse(BaseModel):
    groups: Dict[str, List[NotificationResponse]]


class NotificationSummaryResponse(BaseModel):
    total_notifications: int
    unread_notifications: int
    read_notifications: int
    notifications_by_type: Dict[str, int]
    period_days: int
    summary_generated_at: str


# API Endpoints


@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
    unread_only: bool = False,
):
    """
    Get notifications for the current user with pagination

    Query Parameters:
    - limit: Maximum number of notifications to return (default: 20, max: 100)
    - offset: Pagination offset (default: 0)
    - unread_only: If true, only return unread notifications (default: false)
    """
    # Validate limit
    if limit > 100:
        limit = 100
    if limit < 1:
        limit = 1

    try:
        notifications = NotificationService.get_user_notifications(
            db=db,
            user_id=current_user.id,
            limit=limit,
            offset=offset,
            unread_only=unread_only,
        )

        # Convert to response format
        response_notifications = []
        for notification in notifications:
            response_notifications.append(
                NotificationResponse(
                    id=notification.id,
                    type=notification.type.value,
                    title=notification.title,
                    message=notification.message,
                    data=notification.data,
                    is_read=notification.is_read,
                    created_at=notification.created_at.isoformat(),
                    organization_id=notification.organization_id,
                )
            )

        return response_notifications

    except Exception as e:
        logger.error(f"Error fetching notifications for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching notifications",
        )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """Get the count of unread notifications for the current user"""
    try:
        count = NotificationService.get_unread_count(db=db, user_id=current_user.id)
        return UnreadCountResponse(count=count)
    except Exception as e:
        logger.error(f"Error getting unread count for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting unread count",
        )


@router.post("/mark-read/{notification_id}")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Mark a specific notification as read"""
    try:
        success = NotificationService.mark_notification_read(
            db=db, notification_id=notification_id, user_id=current_user.id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or access denied",
            )

        return {"message": "Notification marked as read"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification {notification_id} as read: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error marking notification as read",
        )


@router.post("/mark-all-read")
async def mark_all_notifications_read(
    current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """Mark all notifications as read for the current user"""
    try:
        count = NotificationService.mark_all_read(db=db, user_id=current_user.id)
        return {"message": f"Marked {count} notifications as read"}
    except Exception as e:
        logger.error(f"Error marking all notifications as read for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error marking notifications as read",
        )


@router.get("/preferences", response_model=NotificationPreferencesResponse)
async def get_notification_preferences(
    current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """Get notification preferences for the current user"""
    try:
        preferences = NotificationService.get_user_preferences(db=db, user_id=current_user.id)
        return NotificationPreferencesResponse(preferences=preferences)
    except Exception as e:
        logger.error(f"Error getting preferences for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting notification preferences",
        )


@router.post("/preferences")
async def update_notification_preferences(
    preferences_update: NotificationPreferencesUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Update notification preferences for the current user"""
    try:
        success = NotificationService.update_user_preferences(
            db=db, user_id=current_user.id, preferences=preferences_update.preferences
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error updating preferences",
            )

        return {"message": "Preferences updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating preferences for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating notification preferences",
        )


# Frontend compatibility alias - PUT endpoint for updating preferences
@router.put("/preferences")
async def update_notification_preferences_put(
    preferences_update: NotificationPreferencesUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Update notification preferences for the current user (PUT alias for frontend compatibility)"""
    return await update_notification_preferences(preferences_update, current_user, db)


# Frontend compatibility alias - digest test endpoint
@router.post("/digest/test")
async def send_test_digest_alias(
    current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """Send a test digest to the current user (alias for frontend compatibility)"""
    from fastapi import HTTPException

    raise HTTPException(status_code=501, detail="Digest feature has been removed")


# Server-Sent Events endpoint for real-time notifications
@router.get("/stream")
async def notification_stream(request: Request, current_user: User = Depends(require_user)):
    """
    Server-Sent Events endpoint for real-time notification updates

    This endpoint maintains a persistent connection and sends new notifications
    as they are created for the authenticated user.
    """

    async def event_generator():
        try:
            # Send initial connection confirmation
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Notification stream connected'})}\n\n"

            # Track last notification timestamp to avoid duplicates
            last_check = None

            # Add counter to prevent infinite loops
            loop_count = 0
            max_loops = 1800  # 1 hour at 2-second intervals

            while loop_count < max_loops:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"Client disconnected from notification stream: {current_user.id}")
                    break

                try:
                    # Create a new database session for each query to avoid holding connections
                    db_session = None
                    try:
                        db_session = next(get_db())
                        # Get recent unread notifications
                        notifications = NotificationService.get_user_notifications(
                            db=db_session,
                            user_id=current_user.id,
                            limit=10,
                            offset=0,
                            unread_only=True,
                        )
                    finally:
                        # Always close the database session
                        if db_session:
                            db_session.close()

                    # Filter new notifications if we have a timestamp
                    new_notifications = []
                    if last_check:
                        new_notifications = [n for n in notifications if n.created_at > last_check]
                    else:
                        # First check - send actual unread count
                        db_session = None
                        try:
                            db_session = next(get_db())
                            actual_unread_count = NotificationService.get_unread_count(
                                db=db_session, user_id=current_user.id
                            )
                            count_data = {
                                "type": "unread_count",
                                "count": actual_unread_count,
                            }
                            yield f"data: {json.dumps(count_data)}\n\n"
                        finally:
                            if db_session:
                                db_session.close()

                    # Send new notifications
                    for notification in new_notifications:
                        notification_data = {
                            "type": "new_notification",
                            "notification": {
                                "id": notification.id,
                                "type": notification.type.value,
                                "title": notification.title,
                                "message": notification.message,
                                "data": notification.data,
                                "is_read": False,
                                "created_at": notification.created_at.isoformat(),
                                "organization_id": notification.organization_id,
                            },
                        }
                        yield f"data: {json.dumps(notification_data)}\n\n"

                    # Update last check timestamp
                    if notifications:
                        last_check = max(n.created_at for n in notifications)

                except Exception as e:
                    logger.error(f"Error in notification stream for user {current_user.id}: {e}")
                    # Send error message but continue stream
                    error_data = {
                        "type": "error",
                        "message": "Error fetching notifications",
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"

                # Wait before next check (reduced interval for better responsiveness)
                await asyncio.sleep(2)
                loop_count += 1

        except Exception as e:
            logger.error(f"Fatal error in notification stream for user {current_user.id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Stream terminated due to error'})}\n\n"
        finally:
            logger.info(f"Notification stream ended for user {current_user.id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        },
    )


# Email testing endpoints


@router.get("/email/status")
async def get_email_status(current_user: User = Depends(require_user)):
    """Get email service status"""
    if not EMAIL_SERVICE_AVAILABLE:
        return {
            "available": False,
            "configured": False,
            "message": "Email service not available",
        }

    try:
        is_configured = email_service.is_available()
        return {
            "available": True,
            "configured": is_configured,
            "message": ("Email service ready" if is_configured else "Email service not configured"),
        }
    except Exception as e:
        logger.warning(f"Error checking email service status: {e}")
        return {
            "available": False,
            "configured": False,
            "message": "Email service not configured",
        }


class TestNotificationRequest(BaseModel):
    """Request model for creating test notifications"""

    notification_type: str = Field(
        default="system_alert", description="Type of notification to create"
    )
    title: Optional[str] = Field(default=None, description="Custom title for the notification")
    message: Optional[str] = Field(default=None, description="Custom message for the notification")
    count: int = Field(
        default=1, min=1, max=10, description="Number of test notifications to create"
    )


class AdminTestNotificationRequest(BaseModel):
    """Request model for admin test notification creation"""

    type: str = Field(..., description="Type of notification")
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message")
    data: Optional[Dict] = Field(default=None, description="Additional data for the notification")


@router.post("/test")
async def create_test_notification(
    request: TestNotificationRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Create test notifications for the current user

    This endpoint is useful for testing the notification system without
    triggering actual events like project creation.
    """
    from models import NotificationType

    try:
        # Validate notification type
        try:
            notification_type = NotificationType(request.notification_type)
        except ValueError:
            # If not a valid enum value, default to system_alert
            notification_type = NotificationType.SYSTEM_ALERT

        # Generate default title and message if not provided
        if not request.title:
            request.title = f"Test {notification_type.value.replace('_', ' ').title()}"
        if not request.message:
            request.message = f"This is a test notification of type: {notification_type.value}"

        # Create the test notifications
        notifications = []
        for i in range(request.count):
            suffix = f" #{i+1}" if request.count > 1 else ""
            result = NotificationService.create_notification(
                db=db,
                user_ids=[current_user.id],
                notification_type=notification_type.value,
                title=request.title + suffix,
                message=request.message + suffix,
                data={"test": True, "index": i + 1},
                organization_id=(
                    current_user.organization_id
                    if hasattr(current_user, "organization_id")
                    else None
                ),
            )
            notifications.extend(result)

        # Commit the transaction
        db.commit()

        return {
            "success": True,
            "message": f"Created {len(notifications)} test notification(s)",
            "notification_ids": [n.id for n in notifications],
            "type": notification_type.value,
        }

    except Exception as e:
        logger.error(f"Error creating test notification: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create test notification: {str(e)}",
        )


@router.post("/test/create")
async def create_admin_test_notification(
    request: AdminTestNotificationRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Create a single test notification (used by admin test page)

    Requires superadmin privileges.
    """
    # Check if user is superadmin
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin privileges required",
        )

    from models import NotificationType

    try:
        # Try to get the notification type from the enum
        try:
            notification_type = NotificationType(request.type)
        except ValueError:
            # If not valid, default to system_alert
            notification_type = NotificationType.SYSTEM_ALERT

        # Create the notification
        result = NotificationService.create_notification(
            db=db,
            user_ids=[current_user.id],
            notification_type=notification_type.value,
            title=request.title,
            message=request.message,
            data=request.data or {"test": True},
            organization_id=(
                current_user.organization_id if hasattr(current_user, "organization_id") else None
            ),
        )

        db.commit()

        return {
            "success": True,
            "message": f"Test notification '{request.title}' created successfully",
            "notification_id": result[0].id if result else None,
        }

    except Exception as e:
        logger.error(f"Error creating admin test notification: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create test notification: {str(e)}",
        )


@router.post("/test/generate-all")
async def generate_all_test_notifications(
    current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """
    Generate one of each type of test notification

    Requires superadmin privileges.
    """
    # Check if user is superadmin
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin privileges required",
        )

    from models import NotificationType

    # Define test notifications for each type
    test_notifications = [
        {
            "type": NotificationType.PROJECT_CREATED,
            "title": "New Project Created",
            "message": "A new project 'Legal Document Analysis' has been created.",
            "data": {"test": True, "category": "Projects"},
        },
        {
            "type": NotificationType.PROJECT_COMPLETED,
            "title": "Project Completed",
            "message": "Project 'Contract Review' has been completed with 42 annotations.",
            "data": {"test": True, "category": "Projects"},
        },
        {
            "type": NotificationType.LLM_GENERATION_COMPLETED,
            "title": "LLM Generation Complete",
            "message": "GPT-4 response generation completed for 'Document Summarization' task.",
            "data": {"test": True, "category": "Generation"},
        },
        {
            "type": NotificationType.EVALUATION_COMPLETED,
            "title": "Evaluation Complete",
            "message": "Evaluation 'BLEU Score Analysis' completed with 95% success rate.",
            "data": {"test": True, "category": "Evaluation"},
        },
        {
            "type": NotificationType.EVALUATION_FAILED,
            "title": "Evaluation Failed",
            "message": "Evaluation 'Model Comparison' failed due to timeout. Please check logs.",
            "data": {"test": True, "category": "Evaluation"},
        },
        {
            "type": NotificationType.ANNOTATION_COMPLETED,
            "title": "Annotation Completed",
            "message": "Annotation for 'Legal Clause Classification' completed by annotator@example.com.",
            "data": {"test": True, "category": "Annotation"},
        },
        {
            "type": NotificationType.MEMBER_JOINED,
            "title": "New Team Member",
            "message": "John Doe (j.doe@example.com) has joined organization 'TUM Research'.",
            "data": {"test": True, "category": "Organization"},
        },
        {
            "type": NotificationType.SYSTEM_ALERT,
            "title": "System Maintenance",
            "message": "Scheduled maintenance will begin at 2:00 AM UTC. Expected downtime: 30 minutes.",
            "data": {"test": True, "category": "System"},
        },
        {
            "type": NotificationType.ERROR_OCCURRED,
            "title": "System Error",
            "message": "Database connection error detected. Please contact system administrator.",
            "data": {"test": True, "category": "System"},
        },
    ]

    created_count = 0
    errors = []

    try:
        for notification_data in test_notifications:
            try:
                result = NotificationService.create_notification(
                    db=db,
                    user_ids=[current_user.id],
                    notification_type=notification_data["type"].value,
                    title=notification_data["title"],
                    message=notification_data["message"],
                    data=notification_data["data"],
                    organization_id=(
                        current_user.organization_id
                        if hasattr(current_user, "organization_id")
                        else None
                    ),
                )
                if result:
                    created_count += 1
            except Exception as e:
                errors.append(f"{notification_data['type'].value}: {str(e)}")
                logger.error(
                    f"Error creating test notification {notification_data['type'].value}: {e}"
                )

        db.commit()

        if errors:
            logger.warning(f"Some test notifications failed: {errors}")

        return {
            "success": created_count > 0,
            "message": f"Generated {created_count} test notifications successfully!",
            "count": created_count,
            "errors": errors if errors else None,
        }

    except Exception as e:
        logger.error(f"Error generating all test notifications: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate test notifications: {str(e)}",
        )


@router.post("/email/test")
async def send_test_email(
    current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """Send test email to current user"""
    if not EMAIL_SERVICE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service not available",
        )

    if not email_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service not configured",
        )

    try:
        success = await email_service.send_test_email(
            user_email=current_user.email, user_name=current_user.name
        )

        if success:
            return {"message": f"Test email sent successfully to {current_user.email}"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send test email",
            )

    except Exception as e:
        logger.error(f"Error sending test email to {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error sending test email",
        )


# Batch operations endpoints


@router.post("/bulk/mark-read", response_model=BulkOperationResponse)
async def mark_notifications_read_bulk(
    request: BulkOperationRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Mark multiple notifications as read in a single operation"""
    try:
        count = NotificationService.mark_notifications_read_bulk(
            db=db, user_id=current_user.id, notification_ids=request.notification_ids
        )

        return BulkOperationResponse(
            success=True, count=count, message=f"Marked {count} notifications as read"
        )

    except Exception as e:
        logger.error(f"Error in bulk mark read for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error marking notifications as read",
        )


@router.post("/bulk/delete", response_model=BulkOperationResponse)
async def delete_notifications_bulk(
    request: BulkOperationRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Delete multiple notifications in a single operation"""
    try:
        count = NotificationService.delete_notifications_bulk(
            db=db, user_id=current_user.id, notification_ids=request.notification_ids
        )

        return BulkOperationResponse(
            success=True, count=count, message=f"Deleted {count} notifications"
        )

    except Exception as e:
        logger.error(f"Error in bulk delete for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting notifications",
        )


# Grouping and analytics endpoints


@router.get("/groups", response_model=NotificationGroupsResponse)
async def get_notification_groups(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
    group_by: str = "type",
    limit: int = 50,
):
    """
    Get notifications grouped by specified criteria

    Query Parameters:
    - group_by: Grouping criteria ("type", "date", "organization")
    - limit: Maximum notifications per group (default: 50)
    """
    if group_by not in ["type", "date", "organization"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid group_by parameter. Must be 'type', 'date', or 'organization'",
        )

    try:
        groups = NotificationService.get_notification_groups(
            db=db, user_id=current_user.id, group_by=group_by, limit=limit
        )

        # Convert to response format
        response_groups = {}
        for key, notifications in groups.items():
            response_groups[key] = [
                NotificationResponse(
                    id=notification.id,
                    type=notification.type.value,
                    title=notification.title,
                    message=notification.message,
                    data=notification.data,
                    is_read=notification.is_read,
                    created_at=notification.created_at.isoformat(),
                    organization_id=notification.organization_id,
                )
                for notification in notifications
            ]

        return NotificationGroupsResponse(groups=response_groups)

    except Exception as e:
        logger.error(f"Error getting notification groups for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting notification groups",
        )


@router.get("/summary", response_model=NotificationSummaryResponse)
async def get_notification_summary(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
    days: int = 7,
):
    """
    Get notification summary and analytics for the current user

    Query Parameters:
    - days: Number of days to analyze (default: 7, max: 90)
    """
    # Validate days parameter
    if days > 90:
        days = 90
    if days < 1:
        days = 1

    try:
        summary = NotificationService.get_notification_summary(
            db=db, user_id=current_user.id, days=days
        )

        return NotificationSummaryResponse(**summary)

    except Exception as e:
        logger.error(f"Error getting notification summary for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting notification summary",
        )

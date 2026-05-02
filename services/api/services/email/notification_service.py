"""
Notification Service for BenGER

This service handles:
1. Creating and managing notifications
2. Role-based notification distribution
3. User preference management
4. Notification cleanup and archival
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import sqlalchemy as sa
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from models import (
    Notification,
    NotificationType,
    OrganizationMembership,
    OrganizationRole,
    User,
    UserNotificationPreference,
)

logger = logging.getLogger(__name__)

# Import email service (with fallback if not available)
try:
    from email_service import send_notification_email

    EMAIL_SERVICE_AVAILABLE = True
except ImportError:
    logger.warning("Email service not available")
    EMAIL_SERVICE_AVAILABLE = False

    async def send_notification_email(*args, **kwargs):
        return False


# Import Project model for project-based notifications
try:
    pass

    PROJECT_MODEL_AVAILABLE = True
except ImportError:
    logger.warning("Project model not available - falling back to Task model")
    PROJECT_MODEL_AVAILABLE = False


class NotificationService:
    """Service for managing notifications and user preferences"""

    @staticmethod
    def create_notification(
        db: Session,
        user_ids: List[str],
        notification_type: Union[NotificationType, str],
        title: str,
        message: str,
        data: Optional[Dict] = None,
        organization_id: Optional[str] = None,
    ) -> List[Notification]:
        """
        Create notifications for specified users

        Args:
            db: Database session
            user_ids: List of user IDs to notify
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            data: Additional context data (task_id, etc.)
            organization_id: Associated organization ID

        Returns:
            List of created notification objects
        """
        # Convert string to enum if needed, and get the string value
        if isinstance(notification_type, str):
            try:
                notification_type_enum = NotificationType(notification_type)
                notification_type_str = notification_type  # Already a string
            except ValueError:
                logger.error(f"❌ Invalid notification type string: {notification_type}")
                return []
        elif isinstance(notification_type, NotificationType):
            notification_type_enum = notification_type
            notification_type_str = notification_type.value
        else:
            logger.error(f"❌ Invalid notification type: {notification_type}")
            return []

        logger.info(f"🔔 CREATE_NOTIFICATION: Starting notification creation")
        logger.info(f"  📝 Type: {notification_type_str} (enum: {notification_type_enum})")
        logger.info(f"  📝 Title: {title}")
        logger.info(f"  👥 User IDs count: {len(user_ids)}")
        logger.info(f"  🏢 Organization: {organization_id}")

        notifications = []

        for user_id in user_ids:
            # In-app channel: only insert a notifications row when in_app is enabled.
            if not NotificationService._user_wants_channel(db, user_id, notification_type_str, "in_app"):
                logger.info(f"  ⏭️ Skipping user {user_id} (in_app disabled)")
                continue

            logger.info(f"  ✅ Creating notification for user {user_id}")
            notification = Notification(
                id=str(uuid.uuid4()),
                user_id=user_id,
                organization_id=organization_id,
                type=notification_type_str,
                title=title,
                message=message,
                data=data or {},
            )

            db.add(notification)
            notifications.append(notification)
            logger.debug(f"    Added notification {notification.id} to session")

        logger.info(f"📊 Prepared {len(notifications)} notifications for commit")

        try:
            logger.info("💾 Committing notifications to database...")
            db.commit()
            logger.info(
                f"✅ Successfully committed {len(notifications)} notifications of type {notification_type}"
            )

            # Extract notification data before detachment to avoid DetachedInstanceError
            notification_data = [
                {
                    "id": n.id,
                    "user_id": n.user_id,
                    "type": n.type,
                    "title": n.title,
                    "message": n.message,
                    "data": n.data,
                }
                for n in notifications
            ]
        except Exception as e:
            logger.error(f"Failed to create notifications: {e}")
            db.rollback()
            # If it's an enum constraint violation, provide a helpful error message
            if "invalid input value for enum" in str(e).lower():
                logger.error(
                    f"Database enum constraint violation for notification type '{notification_type}'. "
                    f"Please ensure the database enum includes this value by running migrations."
                )
            return []

        # Send email notifications asynchronously for users who have email enabled.
        # Schedule on the running event loop when available; in sync test/CLI
        # contexts there is no loop and we silently skip the email side-effect.
        if EMAIL_SERVICE_AVAILABLE and notifications:
            try:
                asyncio.create_task(
                    NotificationService._send_email_notifications(db, notification_data)
                )
            except RuntimeError:
                logger.debug(
                    "No running event loop; skipping async email dispatch"
                )

        return notifications

    @staticmethod
    def get_notification_recipients(
        db: Session, event_type: Union[NotificationType, str], context: Dict
    ) -> List[str]:
        """
        Determine who should receive notifications based on event type and context

        Args:
            db: Database session
            event_type: Type of notification event
            context: Event context (task_id, organization_id, user_id, etc.)

        Returns:
            List of user IDs who should receive the notification
        """
        # Convert string to enum if needed
        if isinstance(event_type, str):
            try:
                event_type_enum = NotificationType(event_type)
            except ValueError:
                logger.error(f"Invalid notification type string: {event_type}")
                return []
        else:
            event_type_enum = event_type

        logger.info(f"📋 GET_RECIPIENTS: Determining recipients for {event_type_enum}")
        logger.info(f"  📝 Context: {context}")

        recipients = []

        if event_type_enum in [
            NotificationType.LLM_GENERATION_COMPLETED,
            NotificationType.ANNOTATION_COMPLETED,
            NotificationType.EVALUATION_COMPLETED,
            NotificationType.EVALUATION_FAILED,
            NotificationType.DATA_UPLOAD_COMPLETED,
        ]:
            # Notify task creator and relevant admins
            if context.get("task_id"):
                task_creator_id = NotificationService._get_task_creator(db, context["task_id"])
                if task_creator_id:
                    recipients.append(task_creator_id)

        elif event_type_enum == NotificationType.MEMBER_JOINED:
            # Notify org admins
            if context.get("organization_id"):
                recipients.extend(
                    NotificationService._get_org_admin_recipients(db, context["organization_id"])
                )

        elif event_type_enum in [
            NotificationType.ORGANIZATION_INVITATION_SENT,
            NotificationType.ORGANIZATION_INVITATION_ACCEPTED,
        ]:
            # Notify org admins
            if context.get("organization_id"):
                recipients.extend(
                    NotificationService._get_org_admin_recipients(db, context["organization_id"])
                )

        elif event_type_enum in [
            NotificationType.SYSTEM_ALERT,
            NotificationType.ERROR_OCCURRED,
        ]:
            # Notify all admins
            recipients.extend(NotificationService._get_admin_recipients(db))

        elif event_type_enum in [
            NotificationType.LLM_GENERATION_FAILED,
            NotificationType.MODEL_API_KEY_INVALID,
            NotificationType.LONG_RUNNING_OPERATION_UPDATE,
            NotificationType.API_QUOTA_WARNING,
        ]:
            # These are typically user-specific notifications - recipients determined by caller
            pass

        elif event_type_enum in [
            NotificationType.SYSTEM_MAINTENANCE,
            NotificationType.PERFORMANCE_ALERT,
        ]:
            # Notify all admins for system-wide issues
            recipients.extend(NotificationService._get_admin_recipients(db))

        elif event_type_enum == NotificationType.SECURITY_ALERT:
            # Security alerts are typically user-specific - recipients determined by caller
            pass

        elif event_type_enum in [
            NotificationType.PROJECT_CREATED,
            NotificationType.PROJECT_COMPLETED,
            NotificationType.PROJECT_DELETED,
            NotificationType.PROJECT_ARCHIVED,
            NotificationType.PROJECT_PUBLISHED,
        ]:
            # Notify organization members when project events occur
            logger.info(f"  📌 Processing {event_type} notification")
            logger.debug(f"Processing {event_type} notification with context: {context}")
            if context.get("organization_id"):
                logger.info(
                    f"  🏢 Looking up organization members for org: {context['organization_id']}"
                )
                # Get all members of the organization
                memberships = (
                    db.query(OrganizationMembership)
                    .filter(OrganizationMembership.organization_id == context["organization_id"])
                    .all()
                )
                org_members = [m.user_id for m in memberships]
                logger.info(f"  👥 Found {len(org_members)} organization members")
                recipients.extend(org_members)
            else:
                logger.warning(f"  ⚠️ No organization_id in context for {event_type}")

            # Also notify all superadmins for project events (they need visibility into all projects)
            # This ensures superadmins are aware of all project activity across the system
            logger.info("  👑 Getting superadmin recipients...")
            superadmins = NotificationService._get_admin_recipients(db)
            logger.info(f"  👑 Found {len(superadmins)} superadmins")
            recipients.extend(superadmins)

        # Remove duplicates and return
        unique_recipients = list(set(recipients))
        logger.info(f"✅ GET_RECIPIENTS: Returning {len(unique_recipients)} unique recipients")
        return unique_recipients

    @staticmethod
    def _get_admin_recipients(db: Session) -> List[str]:
        """Get all system administrators"""
        logger.debug("    Looking up superadmins...")
        admins = db.query(User).filter(User.is_superadmin == True).all()
        admin_ids = [admin.id for admin in admins]
        logger.debug(
            f"    Found {len(admin_ids)} superadmins: {admin_ids[:3]}..."
            if len(admin_ids) > 3
            else f"    Found {len(admin_ids)} superadmins: {admin_ids}"
        )
        return admin_ids

    @staticmethod
    def _get_org_admin_recipients(db: Session, organization_id: str) -> List[str]:
        """Get organization administrators"""
        memberships = (
            db.query(OrganizationMembership)
            .filter(
                and_(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                )
            )
            .all()
        )
        return [membership.user_id for membership in memberships]

    @staticmethod
    def _get_task_creator(db: Session, task_id: str) -> Optional[str]:
        return None  # Cannot get task creator from removed task system

    @staticmethod
    def _user_wants_channel(
        db: Session,
        user_id: str,
        notification_type: Union[NotificationType, str],
        channel: str,
    ) -> bool:
        """Check whether a specific channel ('in_app' or 'email') is enabled
        for the given notification type. Defaults to True when no preference
        is recorded — same as before.
        """
        if isinstance(notification_type, NotificationType):
            type_value = notification_type.value
        elif isinstance(notification_type, str):
            type_value = notification_type
        else:
            return False

        preference = (
            db.query(UserNotificationPreference)
            .filter(
                and_(
                    UserNotificationPreference.user_id == user_id,
                    UserNotificationPreference.notification_type == type_value,
                )
            )
            .first()
        )
        if preference is None:
            return True
        if channel == "in_app":
            return bool(preference.in_app_enabled)
        if channel == "email":
            return bool(preference.email_enabled)
        return False

    @staticmethod
    def _user_wants_notification(
        db: Session, user_id: str, notification_type: Union[NotificationType, str]
    ) -> bool:
        """Back-compat: returns True if EITHER channel is enabled.

        Callers that need per-channel routing should call _user_wants_channel
        directly. This shim keeps existing in-app dispatch sites working.
        """
        return (
            NotificationService._user_wants_channel(db, user_id, notification_type, "in_app")
            or NotificationService._user_wants_channel(db, user_id, notification_type, "email")
        )

    @staticmethod
    def get_user_notifications(
        db: Session,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
    ) -> List[Notification]:
        """
        Get notifications for a user

        Args:
            db: Database session
            user_id: User ID
            limit: Maximum number of notifications to return
            offset: Pagination offset
            unread_only: If True, only return unread notifications

        Returns:
            List of notifications
        """
        query = db.query(Notification).filter(Notification.user_id == user_id)

        if unread_only:
            query = query.filter(Notification.is_read == False)

        notifications = (
            query.order_by(desc(Notification.created_at)).offset(offset).limit(limit).all()
        )
        return notifications

    @staticmethod
    def get_unread_count(db: Session, user_id: str) -> int:
        """Get count of unread notifications for a user"""
        count = (
            db.query(Notification)
            .filter(and_(Notification.user_id == user_id, Notification.is_read == False))
            .count()
        )
        return count

    @staticmethod
    def mark_notification_read(db: Session, notification_id: str, user_id: str) -> bool:
        """
        Mark a notification as read

        Args:
            db: Database session
            notification_id: Notification ID
            user_id: User ID (for security check)

        Returns:
            True if notification was marked as read, False otherwise
        """
        notification = (
            db.query(Notification)
            .filter(and_(Notification.id == notification_id, Notification.user_id == user_id))
            .first()
        )

        if notification:
            notification.is_read = True
            notification.updated_at = datetime.utcnow()
            db.commit()
            return True
        return False

    @staticmethod
    def mark_all_read(db: Session, user_id: str) -> int:
        """
        Mark all notifications as read for a user

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Number of notifications marked as read
        """
        count = (
            db.query(Notification)
            .filter(and_(Notification.user_id == user_id, Notification.is_read == False))
            .update({"is_read": True, "updated_at": datetime.utcnow()})
        )
        db.commit()
        return count

    @staticmethod
    def get_user_preferences(db: Session, user_id: str) -> Dict[str, Dict[str, bool]]:
        """Per-type preferences as `{type: {enabled, in_app, email}}`.

        `enabled` is `True` iff at least one channel is on (back-compat for
        consumers that just want a master toggle). The two channel flags are
        the actual source of truth.
        """
        preferences = (
            db.query(UserNotificationPreference)
            .filter(UserNotificationPreference.user_id == user_id)
            .all()
        )
        # Default every known type to fully on
        pref_map: Dict[str, Dict[str, bool]] = {
            nt.value: {"enabled": True, "in_app": True, "email": True}
            for nt in NotificationType
        }
        for pref in preferences:
            in_app = bool(pref.in_app_enabled)
            email = bool(pref.email_enabled)
            pref_map[pref.notification_type] = {
                "enabled": in_app or email,
                "in_app": in_app,
                "email": email,
            }
        return pref_map

    @staticmethod
    def update_user_preferences(
        db: Session,
        user_id: str,
        preferences: Dict[str, Any],
    ) -> bool:
        """Update preferences. Accepts both the new shape
        `{type: {enabled, in_app, email}}` and the legacy `{type: bool}`.

        Legacy bool means "set both channels to that value" (matches the
        prior behaviour so older callers keep working).
        """
        try:
            for notification_type_str, value in preferences.items():
                try:
                    notification_type = NotificationType(notification_type_str)
                except ValueError:
                    logger.warning(f"Invalid notification type: {notification_type_str}")
                    continue

                if isinstance(value, dict):
                    in_app_enabled = bool(value.get("in_app", value.get("enabled", True)))
                    email_enabled = bool(value.get("email", value.get("enabled", True)))
                else:
                    in_app_enabled = bool(value)
                    email_enabled = bool(value)

                preference = (
                    db.query(UserNotificationPreference)
                    .filter(
                        and_(
                            UserNotificationPreference.user_id == user_id,
                            UserNotificationPreference.notification_type == notification_type.value,
                        )
                    )
                    .first()
                )

                if preference:
                    preference.email_enabled = email_enabled
                    preference.in_app_enabled = in_app_enabled
                    preference.updated_at = datetime.utcnow()
                else:
                    preference = UserNotificationPreference(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        notification_type=notification_type.value,
                        email_enabled=email_enabled,
                        in_app_enabled=in_app_enabled,
                    )
                    db.add(preference)

            db.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating user preferences: {e}")
            db.rollback()
            return False

    @staticmethod
    async def _send_email_notifications(db: Session, notification_data: List[Dict]):
        """Send email notifications for users who have email enabled

        Args:
            db: Database session
            notification_data: List of dictionaries with notification data (to avoid DetachedInstanceError)
        """
        # Import email validation
        try:
            from email_validation import is_valid_email
        except ImportError:
            logger.warning("Email validation module not available")

            # Fallback to basic validation
            def is_valid_email(email):
                return "@" in email and "." in email

        for notif_dict in notification_data:
            try:
                # Get user information
                user = db.query(User).filter(User.id == notif_dict["user_id"]).first()
                if not user or not user.email:
                    continue

                # Validate email address before attempting to send
                if not is_valid_email(user.email):
                    logger.warning(
                        f"Skipping notification for user {user.id} - invalid email: {user.email}"
                    )
                    continue

                # Check if user wants email notifications for this type
                if not NotificationService._user_wants_email_notification(
                    db, user.id, notif_dict["type"]
                ):
                    continue

                # Create a simple object-like structure for the email service
                class NotificationData:
                    def __init__(self, data):
                        self.__dict__.update(data)

                notification_obj = NotificationData(notif_dict)

                # Send email notification
                await send_notification_email(
                    user_email=user.email,
                    notification=notification_obj,
                    context={"user_name": user.name},
                )

            except Exception as e:
                logger.error(
                    f"Failed to send email for notification {notif_dict.get('id', 'unknown')}: {e}"
                )

    @staticmethod
    def _user_wants_email_notification(
        db: Session, user_id: str, notification_type: NotificationType
    ) -> bool:
        """Back-compat shim — defers to the unified per-channel check."""
        return NotificationService._user_wants_channel(
            db, user_id, notification_type, "email"
        )

    @staticmethod
    def cleanup_notifications(db: Session, older_than_days: int = 30) -> int:
        """
        Clean up old notifications

        Args:
            db: Database session
            older_than_days: Delete notifications older than this many days

        Returns:
            Number of notifications deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

        count = db.query(Notification).filter(Notification.created_at < cutoff_date).delete()

        db.commit()
        logger.info(f"Deleted {count} old notifications")
        return count

    @staticmethod
    def mark_notifications_read_bulk(db: Session, user_id: str, notification_ids: List[str]) -> int:
        """
        Mark multiple notifications as read in a single operation

        Args:
            db: Database session
            user_id: User ID (for security check)
            notification_ids: List of notification IDs to mark as read

        Returns:
            Number of notifications marked as read
        """
        count = (
            db.query(Notification)
            .filter(
                and_(
                    Notification.id.in_(notification_ids),
                    Notification.user_id == user_id,
                    Notification.is_read == False,
                )
            )
            .update(
                {"is_read": True, "updated_at": datetime.utcnow()},
                synchronize_session=False,
            )
        )

        db.commit()
        logger.info(f"Marked {count} notifications as read for user {user_id}")
        return count

    @staticmethod
    def delete_notifications_bulk(db: Session, user_id: str, notification_ids: List[str]) -> int:
        """
        Delete multiple notifications in a single operation

        Args:
            db: Database session
            user_id: User ID (for security check)
            notification_ids: List of notification IDs to delete

        Returns:
            Number of notifications deleted
        """
        count = (
            db.query(Notification)
            .filter(
                and_(
                    Notification.id.in_(notification_ids),
                    Notification.user_id == user_id,
                )
            )
            .delete(synchronize_session=False)
        )

        db.commit()
        logger.info(f"Deleted {count} notifications for user {user_id}")
        return count

    @staticmethod
    def get_notification_groups(
        db: Session, user_id: str, group_by: str = "type", limit: int = 50
    ) -> Dict[str, List[Notification]]:
        """
        Get notifications grouped by specified criteria

        Args:
            db: Database session
            user_id: User ID
            group_by: Grouping criteria ("type", "date", "organization")
            limit: Maximum notifications per group

        Returns:
            Dictionary of grouped notifications
        """
        notifications = (
            db.query(Notification)
            .filter(Notification.user_id == user_id)
            .order_by(desc(Notification.created_at))
            .limit(limit * 10)
            .all()
        )

        groups = {}

        for notification in notifications:
            if group_by == "type":
                key = notification.type.value
            elif group_by == "date":
                key = notification.created_at.strftime("%Y-%m-%d")
            elif group_by == "organization":
                key = notification.organization_id or "personal"
            else:
                key = "ungrouped"

            if key not in groups:
                groups[key] = []

            if len(groups[key]) < limit:
                groups[key].append(notification)

        return groups

    @staticmethod
    def get_notification_summary(db: Session, user_id: str, days: int = 7) -> Dict[str, any]:
        """
        Get notification summary for a user over specified days

        Args:
            db: Database session
            user_id: User ID
            days: Number of days to analyze

        Returns:
            Summary statistics
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Total notifications
        total_notifications = (
            db.query(Notification)
            .filter(
                and_(
                    Notification.user_id == user_id,
                    Notification.created_at >= cutoff_date,
                )
            )
            .count()
        )

        # Unread notifications
        unread_notifications = (
            db.query(Notification)
            .filter(
                and_(
                    Notification.user_id == user_id,
                    Notification.created_at >= cutoff_date,
                    Notification.is_read == False,
                )
            )
            .count()
        )

        # Notifications by type
        type_counts = {}
        type_results = (
            db.query(Notification.type, sa.func.count(Notification.id).label("count"))
            .filter(
                and_(
                    Notification.user_id == user_id,
                    Notification.created_at >= cutoff_date,
                )
            )
            .group_by(Notification.type)
            .all()
        )

        for type_result in type_results:
            type_counts[type_result.type.value] = type_result.count

        return {
            "total_notifications": total_notifications,
            "unread_notifications": unread_notifications,
            "read_notifications": total_notifications - unread_notifications,
            "notifications_by_type": type_counts,
            "period_days": days,
            "summary_generated_at": datetime.utcnow().isoformat(),
        }


# Convenience functions for creating specific notification types

# ==============================================
# Project-based notification functions
# ==============================================


def notify_project_created(
    db: Session,
    project_id: str,
    project_title: str,
    creator_name: str,
    organization_id: str,
):
    """Notify about project creation"""
    import logging

    logger = logging.getLogger(__name__)

    logger.info(f"🔔 NOTIFICATION: Starting notify_project_created")
    logger.info(f"  📝 Project ID: {project_id}")
    logger.info(f"  📝 Project Title: {project_title}")
    logger.info(f"  👤 Creator: {creator_name}")
    logger.info(f"  🏢 Organization ID: {organization_id}")

    try:
        # Ensure we're working with a fresh session and primitive values
        # The parameters passed in are already primitive values, not ORM objects
        logger.debug(
            f"notify_project_created called with project_id={project_id}, org_id={organization_id}"
        )

        # Get recipients within the same session
        logger.info("📋 Getting notification recipients...")
        recipients = NotificationService.get_notification_recipients(
            db,
            NotificationType.PROJECT_CREATED.value,
            {"organization_id": organization_id},
        )

        logger.info(
            f"✅ Found {len(recipients) if recipients else 0} recipients for project creation notification"
        )
        if recipients:
            logger.info(
                f"  👥 Recipient IDs: {recipients[:5]}..."
                if len(recipients) > 5
                else f"  👥 Recipient IDs: {recipients}"
            )

        if recipients:
            # All data is already primitive - no ORM objects being passed
            logger.info("📬 Creating notifications in database...")
            result = NotificationService.create_notification(
                db=db,
                user_ids=recipients,
                notification_type=NotificationType.PROJECT_CREATED.value,
                title=f"New Project Created: {project_title}",
                message=f"{creator_name} created a new project '{project_title}'",
                data={
                    "project_id": project_id,
                    "project_title": project_title,
                    "creator_name": creator_name,
                },
                organization_id=organization_id,
            )
            logger.info(
                f"✅ Notification creation result: {len(result) if result else 0} notifications created"
            )
            logger.info(
                f"✅ Project creation notification process completed for project {project_id}"
            )
        else:
            logger.warning(
                f"⚠️ No recipients found for project creation notification - organization_id: {organization_id}"
            )
    except Exception as e:
        logger.error(f"❌ Error in notify_project_created: {str(e)}", exc_info=True)
        # Don't raise - we don't want notification failures to break project creation
        # The caller should handle this gracefully


def notify_project_deleted(
    db: Session,
    project_id: str,
    project_title: str,
    deleted_by_user_id: str,
    deleted_by_username: str,
    organization_id: str,
):
    """Notify about project deletion"""
    recipients = NotificationService.get_notification_recipients(
        db, NotificationType.PROJECT_DELETED, {"organization_id": organization_id}
    )

    if recipients:
        NotificationService.create_notification(
            db=db,
            user_ids=recipients,
            notification_type=NotificationType.PROJECT_DELETED,
            title=f"Project Deleted: {project_title}",
            message=f"{deleted_by_username} deleted project '{project_title}'",
            data={
                "project_id": project_id,
                "project_title": project_title,
                "deleted_by": deleted_by_username,
            },
            organization_id=organization_id,
        )


def notify_project_archived(
    db: Session,
    project_id: str,
    project_title: str,
    archived_by_username: str,
    organization_id: str,
):
    """Notify about project archival"""
    recipients = NotificationService.get_notification_recipients(
        db, NotificationType.PROJECT_ARCHIVED, {"organization_id": organization_id}
    )

    if recipients:
        NotificationService.create_notification(
            db=db,
            user_ids=recipients,
            notification_type=NotificationType.PROJECT_ARCHIVED,
            title=f"Project Archived: {project_title}",
            message=f"{archived_by_username} archived project '{project_title}'",
            data={
                "project_id": project_id,
                "project_title": project_title,
                "archived_by": archived_by_username,
            },
            organization_id=organization_id,
        )


def notify_data_import_success(
    db: Session,
    project_id: str,
    project_title: str,
    imported_by_username: str,
    task_count: int,
    organization_id: str,
):
    """Notify about successful data import"""
    recipients = NotificationService.get_notification_recipients(
        db, NotificationType.DATA_IMPORT_SUCCESS, {"organization_id": organization_id}
    )

    if recipients:
        NotificationService.create_notification(
            db=db,
            user_ids=recipients,
            notification_type=NotificationType.DATA_IMPORT_SUCCESS,
            title=f"Data Import Success: {project_title}",
            message=f"{imported_by_username} imported {task_count} tasks to '{project_title}'",
            data={
                "project_id": project_id,
                "project_title": project_title,
                "imported_by": imported_by_username,
                "task_count": task_count,
            },
            organization_id=organization_id,
        )


def notify_labeling_config_updated(
    db: Session,
    project_id: str,
    project_title: str,
    updated_by_username: str,
    organization_id: str,
):
    """Notify about labeling configuration update"""
    recipients = NotificationService.get_notification_recipients(
        db,
        NotificationType.LABELING_CONFIG_UPDATED,
        {"organization_id": organization_id},
    )

    if recipients:
        NotificationService.create_notification(
            db=db,
            user_ids=recipients,
            notification_type=NotificationType.LABELING_CONFIG_UPDATED,
            title=f"Labeling Config Updated: {project_title}",
            message=f"{updated_by_username} updated the labeling configuration for '{project_title}'",
            data={
                "project_id": project_id,
                "project_title": project_title,
                "updated_by": updated_by_username,
            },
            organization_id=organization_id,
        )


def notify_evaluation_completed(
    db: Session,
    task_id: str,
    task_name: str,
    model_name: str,
    evaluation_id: str,
    success: bool = True,
    error_message: str = None,
    organization_id: Optional[str] = None,
):
    """Notify about evaluation completion"""
    notification_type = (
        NotificationType.EVALUATION_COMPLETED if success else NotificationType.EVALUATION_FAILED
    )

    recipients = []  # Cannot get recipients from removed task system

    if not recipients:
        return

    title = f"Evaluation completed: {task_name}" if success else f"Evaluation failed: {task_name}"

    message = (
        f"Evaluation of model '{model_name}' on task '{task_name}' has completed successfully."
        if success
        else f"Evaluation of model '{model_name}' on task '{task_name}' failed: {error_message or 'Unknown error'}"
    )

    data = {
        "task_id": task_id,
        "task_name": task_name,
        "model_name": model_name,
        "evaluation_id": evaluation_id,
    }

    if error_message:
        data["error_message"] = error_message

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=notification_type,
        title=title,
        message=message,
        data=data,
        organization_id=organization_id,
    )


def notify_data_upload_completed(
    db: Session,
    task_id: str,
    task_name: str,
    uploader_id: str,
    filename: str,
    upload_count: int,
    organization_id: Optional[str] = None,
):
    """Notify about data upload completion"""
    recipients = [uploader_id]

    title = f"Data upload completed: {task_name}"
    message = f"Successfully uploaded {upload_count} items from '{filename}' to task '{task_name}'."

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.DATA_UPLOAD_COMPLETED,
        title=title,
        message=message,
        data={
            "task_id": task_id,
            "task_name": task_name,
            "filename": filename,
            "upload_count": upload_count,
        },
        organization_id=organization_id,
    )


def notify_organization_invitation_sent(
    db: Session,
    organization_id: str,
    organization_name: str,
    invitee_email: str,
    inviter_name: str,
):
    """Notify organization admins about invitation sent"""
    recipients = NotificationService.get_notification_recipients(
        db,
        NotificationType.ORGANIZATION_INVITATION_SENT,
        {"organization_id": organization_id},
    )

    title = f"Invitation sent to {invitee_email}"
    message = f"{inviter_name} sent an invitation to {invitee_email} to join {organization_name}."

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.ORGANIZATION_INVITATION_SENT,
        title=title,
        message=message,
        data={
            "organization_id": organization_id,
            "organization_name": organization_name,
            "invitee_email": invitee_email,
            "inviter_name": inviter_name,
        },
        organization_id=organization_id,
    )


def notify_organization_invitation_accepted(
    db: Session,
    organization_id: str,
    organization_name: str,
    new_member_name: str,
    new_member_email: str,
):
    """Notify organization admins about invitation acceptance"""
    recipients = NotificationService.get_notification_recipients(
        db,
        NotificationType.ORGANIZATION_INVITATION_ACCEPTED,
        {"organization_id": organization_id},
    )

    title = f"{new_member_name} joined {organization_name}"
    message = f"{new_member_name} ({new_member_email}) has accepted the invitation and joined {organization_name}."

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.ORGANIZATION_INVITATION_ACCEPTED,
        title=title,
        message=message,
        data={
            "organization_id": organization_id,
            "organization_name": organization_name,
            "new_member_name": new_member_name,
            "new_member_email": new_member_email,
        },
        organization_id=organization_id,
    )


def notify_member_joined(
    db: Session,
    organization_id: str,
    organization_name: str,
    new_member_name: str,
    new_member_email: str,
):
    """Notify about new organization member"""
    recipients = NotificationService.get_notification_recipients(
        db, NotificationType.MEMBER_JOINED, {"organization_id": organization_id}
    )

    if recipients:
        NotificationService.create_notification(
            db=db,
            user_ids=recipients,
            notification_type=NotificationType.MEMBER_JOINED,
            title=f"New member joined {organization_name}",
            message=f"{new_member_name} ({new_member_email}) has joined your organization",
            data={
                "organization_id": organization_id,
                "organization_name": organization_name,
                "new_member_name": new_member_name,
                "new_member_email": new_member_email,
            },
            organization_id=organization_id,
        )


# Phase 3A: Extended notification helper functions


def notify_llm_generation_failed(
    db: Session,
    task_id: str,
    task_name: str,
    model_name: str,
    user_id: str,
    error_message: str,
    organization_id: Optional[str] = None,
):
    """Notify about LLM generation failure"""
    recipients = [user_id]

    title = f"LLM Generation Failed: {task_name}"
    message = f"LLM generation using '{model_name}' failed for task '{task_name}': {error_message}"

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.LLM_GENERATION_FAILED,
        title=title,
        message=message,
        data={
            "task_id": task_id,
            "task_name": task_name,
            "model_name": model_name,
            "error_message": error_message,
        },
        organization_id=organization_id,
    )


def notify_model_api_key_invalid(
    db: Session,
    user_id: str,
    model_provider: str,
    task_name: Optional[str] = None,
    task_id: Optional[str] = None,
):
    """Notify user about invalid API key"""
    recipients = [user_id]

    title = f"Invalid API Key: {model_provider}"
    message = f"Your {model_provider} API key is invalid or expired. Please update your API key in settings."

    data = {"model_provider": model_provider, "action_required": "update_api_key"}

    if task_name and task_id:
        message += f" This affected the task '{task_name}'."
        data.update({"task_id": task_id, "task_name": task_name})

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.MODEL_API_KEY_INVALID,
        title=title,
        message=message,
        data=data,
    )


def notify_long_running_task_update(
    db: Session,
    task_id: str,
    task_name: str,
    user_id: str,
    operation_type: str,
    progress_message: str,
    progress_percentage: Optional[int] = None,
    organization_id: Optional[str] = None,
):
    """Notify about long-running task progress"""
    recipients = [user_id]

    title = f"Task Progress: {task_name}"
    message = f"{operation_type} for '{task_name}': {progress_message}"

    data = {
        "task_id": task_id,
        "task_name": task_name,
        "operation_type": operation_type,
        "progress_message": progress_message,
    }

    if progress_percentage is not None:
        data["progress_percentage"] = progress_percentage
        message += f" ({progress_percentage}% complete)"

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.LONG_RUNNING_OPERATION_UPDATE,
        title=title,
        message=message,
        data=data,
        organization_id=organization_id,
    )


def notify_system_maintenance(
    db: Session,
    title: str,
    message: str,
    maintenance_start: Optional[str] = None,
    maintenance_end: Optional[str] = None,
    affected_services: Optional[List[str]] = None,
):
    """Notify all active users about system maintenance"""
    # Get all active users
    active_users = db.query(User).filter(User.is_active == True).all()
    recipients = [user.id for user in active_users]

    data = {"maintenance_type": "scheduled", "notification_level": "important"}

    if maintenance_start:
        data["maintenance_start"] = maintenance_start
    if maintenance_end:
        data["maintenance_end"] = maintenance_end
    if affected_services:
        data["affected_services"] = affected_services

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.SYSTEM_MAINTENANCE,
        title=title,
        message=message,
        data=data,
    )


def notify_security_alert(
    db: Session,
    user_id: str,
    alert_type: str,
    alert_message: str,
    severity: str = "medium",
    action_required: Optional[str] = None,
    additional_data: Optional[Dict[str, Any]] = None,
):
    """Notify user about security-related events"""
    recipients = [user_id]

    title = f"Security Alert: {alert_type}"
    message = alert_message

    data = {
        "alert_type": alert_type,
        "severity": severity,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if action_required:
        data["action_required"] = action_required
        message += f" Action required: {action_required}"

    if additional_data:
        data.update(additional_data)

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.SECURITY_ALERT,
        title=title,
        message=message,
        data=data,
    )


def notify_api_quota_warning(
    db: Session,
    user_id: str,
    provider: str,
    usage_percentage: int,
    quota_limit: str,
    current_usage: str,
):
    """Notify user about approaching API quota limits"""
    recipients = [user_id]

    title = f"API Quota Warning: {provider}"
    message = f"Your {provider} API usage is at {usage_percentage}% of your quota limit. Current usage: {current_usage} of {quota_limit}."

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.API_QUOTA_WARNING,
        title=title,
        message=message,
        data={
            "provider": provider,
            "usage_percentage": usage_percentage,
            "quota_limit": quota_limit,
            "current_usage": current_usage,
            "action_required": "monitor_usage",
        },
    )


def notify_performance_alert(
    db: Session,
    alert_message: str,
    affected_service: str,
    severity: str = "medium",
    estimated_resolution: Optional[str] = None,
):
    """Notify administrators about system performance issues"""
    # Get all superadmins
    recipients = NotificationService._get_admin_recipients(db)

    title = f"Performance Alert: {affected_service}"
    message = alert_message

    data = {
        "affected_service": affected_service,
        "severity": severity,
        "alert_type": "performance",
        "timestamp": datetime.utcnow().isoformat(),
    }

    if estimated_resolution:
        data["estimated_resolution"] = estimated_resolution
        message += f" Estimated resolution: {estimated_resolution}"

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.PERFORMANCE_ALERT,
        title=title,
        message=message,
        data=data,
    )


# ==============================================
# PROJECT-BASED NOTIFICATION FUNCTIONS
# ==============================================


def notify_project_completed(
    db: Session,
    project_id: str,
    project_title: str,
    organization_id: str,
):
    """Notify about project completion"""
    recipients = NotificationService.get_notification_recipients(
        db,
        NotificationType.PROJECT_COMPLETED,
        {"organization_id": organization_id, "project_id": project_id},
    )

    title = f"Project Completed: {project_title}"
    message = f"Project '{project_title}' has been completed"

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.PROJECT_COMPLETED,
        title=title,
        message=message,
        data={
            "project_id": project_id,
            "project_title": project_title,
            "organization_id": organization_id,
        },
    )


# Note: The duplicate notify_project_deleted and notify_project_archived functions below were
# kept during migration from task-based to project-based system. Using the ones defined above.


def notify_project_deleted(
    db: Session,
    project_id: str,
    project_title: str,
    deleted_by_user_id: str,
    deleted_by_username: str,
    organization_id: str,
):
    """Notify organization members when a project is deleted"""
    recipients = NotificationService.get_notification_recipients(
        db=db,
        event_type=NotificationType.PROJECT_DELETED,
        context={"organization_id": organization_id, "project_id": project_id},
    )

    # Don't notify the user who deleted the project
    recipients = [r for r in recipients if r != deleted_by_user_id]

    if not recipients:
        return

    title = f"Project Deleted: {project_title}"
    message = f"{deleted_by_username} has deleted project '{project_title}'"

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.PROJECT_DELETED,
        title=title,
        message=message,
        data={
            "project_id": project_id,
            "project_title": project_title,
            "deleted_by_user_id": deleted_by_user_id,
            "deleted_by_username": deleted_by_username,
            "organization_id": organization_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


def notify_project_archived(
    db: Session,
    project_id: str,
    project_title: str,
    archived_by_user_id: str,
    archived_by_username: str,
    organization_id: str,
):
    """Notify organization members when a project is archived"""
    recipients = NotificationService.get_notification_recipients(
        db=db,
        event_type=NotificationType.PROJECT_ARCHIVED,
        context={"organization_id": organization_id, "project_id": project_id},
    )

    # Don't notify the user who archived the project
    recipients = [r for r in recipients if r != archived_by_user_id]

    if not recipients:
        return

    title = f"Project Archived: {project_title}"
    message = f"{archived_by_username} has archived project '{project_title}'"

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.PROJECT_ARCHIVED,
        title=title,
        message=message,
        data={
            "project_id": project_id,
            "project_title": project_title,
            "archived_by_user_id": archived_by_user_id,
            "archived_by_username": archived_by_username,
            "organization_id": organization_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


def notify_data_import_success(
    db: Session,
    project_id: str,
    project_title: str,
    imported_by_user_id: str,
    imported_by_username: str,
    organization_id: str,
    imported_items_count: int,
):
    """Notify organization members when data is successfully imported into a project"""
    recipients = NotificationService.get_notification_recipients(
        db=db,
        event_type=NotificationType.DATA_IMPORT_SUCCESS,
        context={"organization_id": organization_id, "project_id": project_id},
    )

    if not recipients:
        return

    title = f"Data Import Completed: {project_title}"
    message = f"{imported_by_username} has imported {imported_items_count} items into project '{project_title}'"

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.DATA_IMPORT_SUCCESS,
        title=title,
        message=message,
        data={
            "project_id": project_id,
            "project_title": project_title,
            "imported_by_user_id": imported_by_user_id,
            "imported_by_username": imported_by_username,
            "imported_items_count": imported_items_count,
            "organization_id": organization_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


def notify_labeling_config_updated(
    db: Session,
    project_id: str,
    project_title: str,
    updated_by_user_id: str,
    updated_by_username: str,
    organization_id: str,
):
    """Notify project members when labeling configuration is updated"""
    recipients = NotificationService.get_notification_recipients(
        db=db,
        event_type=NotificationType.LABELING_CONFIG_UPDATED,
        context={"organization_id": organization_id, "project_id": project_id},
    )

    # Don't notify the user who updated the config
    recipients = [r for r in recipients if r != updated_by_user_id]

    if not recipients:
        return

    title = f"Labeling Config Updated: {project_title}"
    message = f"{updated_by_username} has updated the labeling configuration for project '{project_title}'"

    NotificationService.create_notification(
        db=db,
        user_ids=recipients,
        notification_type=NotificationType.LABELING_CONFIG_UPDATED,
        title=title,
        message=message,
        data={
            "project_id": project_id,
            "project_title": project_title,
            "updated_by_user_id": updated_by_user_id,
            "updated_by_username": updated_by_username,
            "organization_id": organization_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

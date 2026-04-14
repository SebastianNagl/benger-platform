"""
Notification service for Celery workers
Includes NotificationService class for creating database notifications
"""

import logging
import uuid
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def notify_task_completed(task_id: str, task_name: str, user_id: str, **kwargs):
    """
    Minimal implementation of task completion notification for workers
    This is a simplified version that just logs the notification
    """
    logger.info(f"Task completed: {task_name} (ID: {task_id}) for user {user_id}")


def notify_llm_generation_failed(task_id: str, error_message: str, **kwargs):
    """
    Minimal implementation of LLM generation failure notification for workers
    """
    logger.error(f"LLM generation failed for task {task_id}: {error_message}")


def notify_model_api_key_invalid(model_id: str, user_id: str, **kwargs):
    """
    Minimal implementation of invalid API key notification for workers
    """
    logger.warning(f"Invalid API key for model {model_id} for user {user_id}")


class NotificationService:
    """Service for managing notifications from workers"""

    @staticmethod
    def create_notification(
        db,
        user_ids: List[str],
        notification_type,
        title: str,
        message: str,
        data: Optional[Dict] = None,
        organization_id: Optional[str] = None,
    ) -> List:
        """
        Create notifications for specified users

        Args:
            db: Database session
            user_ids: List of user IDs to notify
            notification_type: Type of notification (enum or string)
            title: Notification title
            message: Notification message
            data: Additional context data
            organization_id: Associated organization ID

        Returns:
            List of created notification objects
        """
        import json

        from sqlalchemy import text

        # Convert to lowercase string value for database storage
        if hasattr(notification_type, 'value'):
            notification_type_str = notification_type.value
        elif isinstance(notification_type, str):
            notification_type_str = notification_type.lower()
        else:
            notification_type_str = str(notification_type).lower()

        logger.info(
            f"Creating notifications for {len(user_ids)} users, type: {notification_type_str}"
        )

        notifications = []

        for user_id in user_ids:
            notification_id = str(uuid.uuid4())

            # Use raw SQL to bypass SQLAlchemy's enum conversion which uses NAME instead of VALUE
            # Use CAST() instead of :: to avoid conflict with SQLAlchemy's :param syntax
            sql = text(
                """
                INSERT INTO notifications (id, user_id, organization_id, type, title, message, data, is_read)
                VALUES (:id, :user_id, :organization_id, CAST(:type AS notificationtype), :title, :message, CAST(:data AS json), false)
            """
            )

            db.execute(
                sql,
                {
                    "id": notification_id,
                    "user_id": user_id,
                    "organization_id": organization_id,
                    "type": notification_type_str,  # lowercase string
                    "title": title,
                    "message": message,
                    "data": json.dumps(data or {}),
                },
            )

            notifications.append({"id": notification_id, "user_id": user_id})
            logger.debug(f"Added notification {notification_id} for user {user_id}")

        try:
            db.commit()
            logger.info(f"Successfully committed {len(notifications)} notifications")
        except Exception as e:
            logger.error(f"Failed to commit notifications: {e}")
            db.rollback()
            return []

        return notifications

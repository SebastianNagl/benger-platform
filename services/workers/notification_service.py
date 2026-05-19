"""
Notification service for Celery workers
Includes NotificationService class for creating database notifications
"""

import json
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

        # Dispatch email sends to the emails-queue worker so users with
        # email notifications enabled actually get an email. Previously this
        # function only committed the in-app row and returned — the bell
        # lit up but no email was sent. Mirrors the API-side dispatch in
        # services/api/services/email/notification_service.py:179-187.
        try:
            from celery import current_app

            notification_data = [
                {
                    "id": n["id"],
                    "user_id": n["user_id"],
                    "type": notification_type_str,
                    "title": title,
                    "message": message,
                    "data": data or {},
                }
                for n in notifications
            ]
            current_app.send_task(
                "emails.send_notification_batch",
                args=[notification_data],
                queue="emails",
            )
        except Exception as e:
            # Never let an email-dispatch failure surface to the caller;
            # the in-app notification already committed above.
            logger.warning(f"Failed to enqueue notification emails: {e}")

        return notifications

"""
Email Digest Service for BenGER

This service handles:
1. Generating periodic email digests of notifications
2. Scheduling and sending digest emails
3. Managing digest preferences
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List

import pytz
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from models import Notification, User

logger = logging.getLogger(__name__)

# Import email service
try:
    from email_service import email_service

    EMAIL_SERVICE_AVAILABLE = True
except ImportError:
    logger.warning("Email service not available for digest")
    EMAIL_SERVICE_AVAILABLE = False


class DigestService:
    """Service for managing notification email digests"""

    @staticmethod
    def should_send_digest(user: User) -> bool:
        """
        Check if a digest should be sent for this user

        Args:
            user: User object with digest preferences

        Returns:
            True if digest should be sent, False otherwise
        """
        if not user.enable_email_digest or not EMAIL_SERVICE_AVAILABLE:
            return False

        if not user.digest_frequency or not user.digest_time:
            return False

        try:
            # Get user's timezone
            user_timezone = user.timezone or "UTC"
            tz = pytz.timezone(user_timezone)
            current_time = datetime.now(tz)

            # Parse digest time
            digest_hour, digest_minute = map(int, user.digest_time.split(":"))

            # Check if we're at or past the digest time today
            digest_time_today = current_time.replace(
                hour=digest_hour, minute=digest_minute, second=0, microsecond=0
            )

            # If current time is before digest time today, don't send yet
            if current_time < digest_time_today:
                return False

            # Check when last digest was sent
            if user.last_digest_sent:
                last_sent = user.last_digest_sent.astimezone(tz)

                if user.digest_frequency == "daily":
                    # Daily: send if last digest was yesterday or earlier
                    cutoff = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
                    return last_sent < cutoff

                elif user.digest_frequency == "weekly":
                    # Weekly: send if it's the right day and last digest was a week ago
                    digest_days = (
                        json.loads(user.digest_days) if user.digest_days else [1]
                    )  # Default to Monday
                    current_weekday = current_time.weekday()  # 0=Monday, 6=Sunday

                    if current_weekday not in digest_days:
                        return False

                    # Check if a week has passed
                    week_ago = current_time - timedelta(days=7)
                    return last_sent < week_ago

                elif user.digest_frequency == "bi-weekly":
                    # Bi-weekly: send every 14 days
                    two_weeks_ago = current_time - timedelta(days=14)
                    return last_sent < two_weeks_ago

            else:
                # No digest has been sent yet, send one
                return True

        except Exception as e:
            logger.error(f"Error checking digest schedule for user {user.id}: {e}")
            return False

        return False

    @staticmethod
    def get_digest_period(user: User) -> Dict[str, datetime]:
        """
        Get the time period for the digest based on user preferences

        Args:
            user: User object with digest preferences

        Returns:
            Dictionary with 'start' and 'end' datetime objects
        """
        try:
            user_timezone = user.timezone or "UTC"
            tz = pytz.timezone(user_timezone)
            current_time = datetime.now(tz)

            if user.digest_frequency == "daily":
                # Yesterday until now
                start_time = current_time - timedelta(days=1)
                end_time = current_time

            elif user.digest_frequency == "weekly":
                # Last 7 days
                start_time = current_time - timedelta(days=7)
                end_time = current_time

            elif user.digest_frequency == "bi-weekly":
                # Last 14 days
                start_time = current_time - timedelta(days=14)
                end_time = current_time

            else:
                # Default to daily
                start_time = current_time - timedelta(days=1)
                end_time = current_time

            return {
                "start": start_time.astimezone(pytz.UTC),
                "end": end_time.astimezone(pytz.UTC),
            }

        except Exception as e:
            logger.error(f"Error calculating digest period for user {user.id}: {e}")
            # Fallback to last 24 hours
            now = datetime.now(pytz.UTC)
            return {"start": now - timedelta(days=1), "end": now}

    @staticmethod
    def get_digest_notifications(
        db: Session, user_id: str, start_time: datetime, end_time: datetime
    ) -> List[Notification]:
        """
        Get notifications for digest within the specified time period

        Args:
            db: Database session
            user_id: User ID
            start_time: Start of digest period
            end_time: End of digest period

        Returns:
            List of notifications
        """
        notifications = (
            db.query(Notification)
            .filter(
                and_(
                    Notification.user_id == user_id,
                    Notification.created_at >= start_time,
                    Notification.created_at <= end_time,
                )
            )
            .order_by(desc(Notification.created_at))
            .all()
        )

        return notifications

    @staticmethod
    def generate_digest_data(notifications: List[Notification]) -> Dict:
        """
        Generate digest data from notifications

        Args:
            notifications: List of notifications

        Returns:
            Dictionary with digest data
        """
        if not notifications:
            return {
                "total_count": 0,
                "by_type": {},
                "recent_notifications": [],
                "summary": "No new notifications",
            }

        # Group by type
        by_type = {}
        for notification in notifications:
            type_name = notification.type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(
                {
                    "id": notification.id,
                    "title": notification.title,
                    "message": notification.message,
                    "created_at": notification.created_at.isoformat(),
                    "is_read": notification.is_read,
                }
            )

        # Get recent notifications (last 10)
        recent_notifications = []
        for notification in notifications[:10]:
            recent_notifications.append(
                {
                    "id": notification.id,
                    "type": notification.type.value,
                    "title": notification.title,
                    "message": notification.message,
                    "created_at": notification.created_at.isoformat(),
                    "is_read": notification.is_read,
                }
            )

        # Generate summary
        total_count = len(notifications)
        unread_count = sum(1 for n in notifications if not n.is_read)
        type_counts = {type_name: len(notifs) for type_name, notifs in by_type.items()}

        # Create readable summary
        if total_count == 1:
            summary = "1 new notification"
        else:
            summary = f"{total_count} new notifications"

        if unread_count > 0:
            summary += f" ({unread_count} unread)"

        return {
            "total_count": total_count,
            "unread_count": unread_count,
            "by_type": by_type,
            "type_counts": type_counts,
            "recent_notifications": recent_notifications,
            "summary": summary,
        }

    @staticmethod
    async def send_digest_email(user: User, digest_data: Dict, period: Dict[str, datetime]) -> bool:
        """
        Send digest email to user

        Args:
            user: User object
            digest_data: Digest data dictionary
            period: Time period dictionary

        Returns:
            True if email was sent successfully
        """
        if not EMAIL_SERVICE_AVAILABLE:
            return False

        try:
            # Prepare context for email template
            context = {
                "user_name": user.name,
                "digest_data": digest_data,
                "period_start": period["start"].strftime("%Y-%m-%d"),
                "period_end": period["end"].strftime("%Y-%m-%d"),
                "frequency": user.digest_frequency,
                "total_count": digest_data["total_count"],
                "unread_count": digest_data["unread_count"],
                "summary": digest_data["summary"],
                "type_counts": digest_data["type_counts"],
                "recent_notifications": digest_data["recent_notifications"],
            }

            # Send email using email service
            success = await email_service.send_digest_email(user_email=user.email, context=context)

            return success

        except Exception as e:
            logger.error(f"Error sending digest email to {user.email}: {e}")
            return False

    @staticmethod
    def update_digest_sent_time(db: Session, user_id: str) -> bool:
        """
        Update the last digest sent timestamp for a user

        Args:
            db: Database session
            user_id: User ID

        Returns:
            True if update was successful
        """
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.last_digest_sent = datetime.utcnow()
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating digest sent time for user {user_id}: {e}")
            db.rollback()
            return False

    @staticmethod
    async def process_digest_for_user(db: Session, user: User) -> bool:
        """
        Process and send digest for a single user

        Args:
            db: Database session
            user: User object

        Returns:
            True if digest was processed successfully
        """
        try:
            # Check if digest should be sent
            if not DigestService.should_send_digest(user):
                return False

            # Get digest period
            period = DigestService.get_digest_period(user)

            # Get notifications for period
            notifications = DigestService.get_digest_notifications(
                db, user.id, period["start"], period["end"]
            )

            # Generate digest data
            digest_data = DigestService.generate_digest_data(notifications)

            # Only send if there are notifications
            if digest_data["total_count"] == 0:
                logger.debug(f"No notifications for digest for user {user.id}")
                return False

            # Send digest email
            success = await DigestService.send_digest_email(user, digest_data, period)

            if success:
                # Update last sent timestamp
                DigestService.update_digest_sent_time(db, user.id)
                logger.info(f"Digest sent successfully to {user.email}")
                return True
            else:
                logger.warning(f"Failed to send digest email to {user.email}")
                return False

        except Exception as e:
            logger.error(f"Error processing digest for user {user.id}: {e}")
            return False

    @staticmethod
    async def process_all_digests(db: Session) -> Dict[str, int]:
        """
        Process digests for all users who have digests enabled

        Args:
            db: Database session

        Returns:
            Dictionary with processing statistics
        """
        stats = {"total_users": 0, "digests_sent": 0, "errors": 0}

        try:
            # Get all users with digest enabled
            users = (
                db.query(User)
                .filter(and_(User.enable_email_digest == True, User.is_active == True))
                .all()
            )

            stats["total_users"] = len(users)

            for user in users:
                try:
                    success = await DigestService.process_digest_for_user(db, user)
                    if success:
                        stats["digests_sent"] += 1
                except Exception as e:
                    logger.error(f"Error processing digest for user {user.id}: {e}")
                    stats["errors"] += 1

            logger.info(f"Digest processing complete: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Error in digest processing: {e}")
            stats["errors"] += 1
            return stats


# Convenience function for scheduled digest processing
async def run_digest_processor(db: Session):
    """Run the digest processor - can be called by a scheduler"""
    logger.info("Starting digest processor")
    stats = await DigestService.process_all_digests(db)
    logger.info(f"Digest processor completed: {stats}")
    return stats

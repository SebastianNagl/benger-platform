"""
System-wide notification helpers for BenGER

This module provides convenience functions for sending system-wide notifications
like maintenance alerts, security notifications, and performance issues.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from notification_service import (
    notify_api_quota_warning,
    notify_performance_alert,
    notify_security_alert,
    notify_system_maintenance,
)

logger = logging.getLogger(__name__)


def send_maintenance_notification(
    db: Session,
    title: str,
    message: str,
    maintenance_start: Optional[str] = None,
    maintenance_end: Optional[str] = None,
    affected_services: Optional[List[str]] = None,
):
    """
    Send system maintenance notification to all active users

    Args:
        db: Database session
        title: Maintenance notification title
        message: Detailed maintenance message
        maintenance_start: Start time (ISO format string)
        maintenance_end: End time (ISO format string)
        affected_services: List of affected service names
    """
    try:
        notify_system_maintenance(
            db=db,
            title=title,
            message=message,
            maintenance_start=maintenance_start,
            maintenance_end=maintenance_end,
            affected_services=affected_services,
        )
        logger.info(f"Sent maintenance notification: {title}")
    except Exception as e:
        logger.error(f"Failed to send maintenance notification: {e}")


def send_performance_alert(
    db: Session,
    service_name: str,
    alert_message: str,
    severity: str = "medium",
    estimated_resolution: Optional[str] = None,
):
    """
    Send performance alert to administrators

    Args:
        db: Database session
        service_name: Name of affected service
        alert_message: Description of the performance issue
        severity: Issue severity (low, medium, high)
        estimated_resolution: When issue is expected to be resolved
    """
    try:
        notify_performance_alert(
            db=db,
            alert_message=alert_message,
            affected_service=service_name,
            severity=severity,
            estimated_resolution=estimated_resolution,
        )
        logger.info(f"Sent performance alert for {service_name}: {severity}")
    except Exception as e:
        logger.error(f"Failed to send performance alert: {e}")


def send_security_alert(
    db: Session,
    user_id: str,
    alert_type: str,
    message: str,
    severity: str = "medium",
    action_required: Optional[str] = None,
    additional_context: Optional[Dict] = None,
):
    """
    Send security alert to specific user

    Args:
        db: Database session
        user_id: User to notify
        alert_type: Type of security alert
        message: Alert message
        severity: Alert severity (low, medium, high)
        action_required: Required action from user
        additional_context: Additional alert data
    """
    try:
        notify_security_alert(
            db=db,
            user_id=user_id,
            alert_type=alert_type,
            alert_message=message,
            severity=severity,
            action_required=action_required,
            additional_data=additional_context,
        )
        logger.info(f"Sent security alert to {user_id}: {alert_type}")
    except Exception as e:
        logger.error(f"Failed to send security alert: {e}")


def send_quota_warning(
    db: Session,
    user_id: str,
    provider: str,
    usage_percentage: int,
    quota_limit: str,
    current_usage: str,
):
    """
    Send API quota warning to user

    Args:
        db: Database session
        user_id: User to notify
        provider: API provider name
        usage_percentage: Current usage percentage
        quota_limit: Total quota limit
        current_usage: Current usage amount
    """
    try:
        notify_api_quota_warning(
            db=db,
            user_id=user_id,
            provider=provider,
            usage_percentage=usage_percentage,
            quota_limit=quota_limit,
            current_usage=current_usage,
        )
        logger.info(f"Sent quota warning to {user_id} for {provider}: {usage_percentage}%")
    except Exception as e:
        logger.error(f"Failed to send quota warning: {e}")


# Common maintenance scenarios
def schedule_system_maintenance(
    db: Session,
    start_time: str,
    end_time: str,
    affected_services: List[str],
    description: str = "Scheduled system maintenance",
):
    """Send scheduled maintenance notification"""
    send_maintenance_notification(
        db=db,
        title="Scheduled System Maintenance",
        message=f"{description}. Some services may be temporarily unavailable during this time.",
        maintenance_start=start_time,
        maintenance_end=end_time,
        affected_services=affected_services,
    )


def emergency_maintenance(
    db: Session,
    reason: str,
    affected_services: List[str],
    estimated_duration: str = "unknown",
):
    """Send emergency maintenance notification"""
    send_maintenance_notification(
        db=db,
        title="Emergency Maintenance in Progress",
        message=f"Emergency maintenance is currently underway due to: {reason}. "
        f"Estimated duration: {estimated_duration}.",
        affected_services=affected_services,
    )


# Common security scenarios
def suspicious_login_attempt(
    db: Session, user_id: str, ip_address: str, location: Optional[str] = None
):
    """Send suspicious login attempt alert"""
    location_info = f" from {location}" if location else ""
    send_security_alert(
        db=db,
        user_id=user_id,
        alert_type="Suspicious Login Attempt",
        message=f"A login attempt was made from IP {ip_address}{location_info}. "
        "If this wasn't you, please secure your account immediately.",
        severity="high",
        action_required="Review account activity and update password if necessary",
        additional_context={"ip_address": ip_address, "location": location},
    )


def password_breach_notification(db: Session, user_id: str, breach_source: str):
    """Send password breach notification"""
    send_security_alert(
        db=db,
        user_id=user_id,
        alert_type="Password Security Alert",
        message=f"Your password may have been compromised in a data breach at {breach_source}. "
        "Please update your password immediately.",
        severity="high",
        action_required="Change your password immediately",
        additional_context={"breach_source": breach_source},
    )


# Common performance scenarios
def database_performance_alert(db: Session, response_time_ms: int, threshold_ms: int = 1000):
    """Send database performance alert"""
    send_performance_alert(
        db=db,
        service_name="Database",
        alert_message=f"Database response time ({response_time_ms}ms) exceeds threshold ({threshold_ms}ms). "
        "This may impact system performance.",
        severity="high" if response_time_ms > threshold_ms * 2 else "medium",
    )


def api_rate_limit_alert(db: Session, service_name: str, current_rate: int, limit: int):
    """Send API rate limit alert"""
    percentage = (current_rate / limit) * 100
    severity = "high" if percentage >= 90 else "medium"

    send_performance_alert(
        db=db,
        service_name=f"{service_name} API",
        alert_message=f"API rate limit approaching: {current_rate}/{limit} requests ({percentage:.1f}%)",
        severity=severity,
    )

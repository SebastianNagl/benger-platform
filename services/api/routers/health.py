"""
Health check and system monitoring endpoints.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth_module import User, require_superadmin, require_user
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/")
async def root():
    """Root-Endpunkt"""
    return {"message": "Willkommen bei der BenGER API"}


@router.get("/healthz")
async def health_check():
    """Health check endpoint for Kubernetes probes"""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}


@router.get("/health")
async def health():
    """Health check endpoint for Docker healthcheck and Kubernetes probes.

    Checks Redis connectivity. Returns 503 if Redis is unreachable so
    Kubernetes removes the pod from the load balancer.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "redis": "unknown",
    }

    try:
        from services.redis_cache import cache

        if cache.is_available and cache.redis_client:
            cache.redis_client.ping()
            health_status["redis"] = "connected"
        else:
            health_status["redis"] = "unavailable"
            health_status["status"] = "degraded"
            return JSONResponse(status_code=503, content=health_status)
    except Exception as e:
        logger.warning(f"Health check: Redis ping failed: {e}")
        health_status["redis"] = f"error"
        health_status["status"] = "degraded"
        return JSONResponse(status_code=503, content=health_status)

    return health_status


@router.get("/health/cors-auth")
async def cors_auth_test(request: Request, current_user: User = Depends(require_user)):
    """Test CORS and authentication flow for development debugging"""
    return {
        "status": "success",
        "message": "CORS and authentication working correctly",
        "user_id": current_user.id,
        "user_username": current_user.username,
        "origin": request.headers.get("origin"),
        "user_agent": request.headers.get("user-agent"),
        "timestamp": datetime.now(timezone.utc),
    }


@router.get("/health/schema")
async def health_check_schema(db: Session = Depends(get_db)):
    """Validate database schema health"""
    try:
        # Test critical table access with key columns that caused issues
        db.execute(text("SELECT id, username, encrypted_openai_api_key FROM users LIMIT 1"))
        db.execute(text("SELECT id, name FROM tasks LIMIT 1"))

        return {
            "status": "healthy",
            "schema": "validated",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Schema health check failed: {str(e)}")
        return {
            "status": "error",
            "schema": "invalid",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@router.get("/health/email")
async def email_health_check(
    test_email: str = None, current_user: User = Depends(require_superadmin)
):
    """
    Email service health check endpoint

    Checks:
    - Mail service configuration status
    - Connection test to mail server
    - Optional test email sending to verify delivery

    Args:
        test_email: Optional email address to send test email to
    """
    try:
        from email_service import email_service

        # Basic configuration check
        health_status = {
            "configured": email_service.mail_enabled,
            "service": "sendgrid",
            "from_email": email_service.from_email,
            "from_name": email_service.from_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Connection test
        try:
            connection_ok = await email_service.test_connection()
            health_status["connection"] = {"success": connection_ok}
        except Exception as e:
            health_status["connection"] = {"success": False, "error": str(e)}

        # Optional test email sending
        if test_email:
            try:
                test_result = await email_service.send_test_email(test_email, "Test User")
                health_status["test_send"] = {
                    "success": test_result,
                    "test_email": test_email,
                }
            except Exception as e:
                health_status["test_send"] = {
                    "success": False,
                    "test_email": test_email,
                    "error": str(e),
                }
        else:
            health_status["test_send"] = {"info": "No test email provided"}

        # Overall health determination
        overall_healthy = health_status["configured"] and health_status["connection"]["success"]

        if test_email:
            overall_healthy = overall_healthy and health_status["test_send"].get("success", False)

        health_status["status"] = "healthy" if overall_healthy else "unhealthy"

        # Return appropriate HTTP status
        if overall_healthy:
            return health_status
        else:
            return JSONResponse(status_code=503, content=health_status)

    except Exception as e:
        logger.error(f"Email health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


@router.get("/performance/stats")
async def get_performance_stats(current_user: User = Depends(require_superadmin)):
    """
    Get system performance statistics for production monitoring

    Returns database and cache performance metrics
    """
    try:
        from rate_limiter import rate_limiter

        stats = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": {},
            "cache": {},
            "rate_limiting": {},
        }

        # Database performance stats
        try:
            from database_optimization import get_query_performance_stats

            stats["database"] = get_query_performance_stats()
        except Exception as e:
            stats["database"] = {"error": str(e)}

        # Cache performance stats
        try:
            from redis_cache import get_cache_performance_stats

            stats["cache"] = get_cache_performance_stats()
        except Exception as e:
            stats["cache"] = {"error": str(e), "available": False}

        # Rate limiting stats
        try:
            stats["rate_limiting"] = {
                "active_clients": len(rate_limiter.clients),
                "cleanup_interval": "30 seconds",
            }
        except Exception as e:
            stats["rate_limiting"] = {"error": str(e)}

        return stats

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving performance stats: {str(e)}",
        )

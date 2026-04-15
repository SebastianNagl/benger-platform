"""
Organization context resolution middleware.

Resolves X-Organization-Slug header to org ID and sets request.state.organization_context.
Downstream auth dependencies (require_org_admin, require_org_contributor) read from
request.state.organization_context, so this middleware integrates transparently.
"""

import logging
import re

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")


class OrgContextMiddleware(BaseHTTPMiddleware):
    """
    Resolves organization context before request processing.

    Priority:
    1. X-Organization-Slug header -> resolve to org ID via cache/DB
    2. X-Organization-Context header -> pass through as-is
    3. Neither -> no org context (private mode)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        slug = request.headers.get("X-Organization-Slug")

        if slug:
            if not SLUG_PATTERN.match(slug):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid organization slug format"},
                )

            org_id = self._resolve_slug(slug)
            if org_id:
                request.state.organization_context = org_id
            else:
                logger.debug(f"Organization slug not found: {slug}")
        else:
            org_context = request.headers.get("X-Organization-Context")
            if org_context:
                request.state.organization_context = org_context

        return await call_next(request)

    def _resolve_slug(self, slug: str) -> str | None:
        """Resolve slug to org ID using Redis cache with DB fallback."""
        from redis_cache import OrgSlugCache

        cached_id = OrgSlugCache.get_org_id(slug)
        if cached_id is not None:
            return cached_id

        try:
            from database import SessionLocal
            from models import Organization

            db = SessionLocal()
            try:
                result = (
                    db.query(Organization.id)
                    .filter(Organization.slug == slug, Organization.is_active == True)
                    .first()
                )
                if result:
                    OrgSlugCache.set_org_id(slug, result.id)
                    return result.id
                return None
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to resolve org slug '{slug}': {e}")
            return None

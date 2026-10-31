"""
Auth cookie scope.

The session cookies (``access_token``, ``refresh_token``) and the readable
``benger_session_origin`` marker are host-only: the API never sends a
``Domain`` attribute, so a browser only returns them to the exact host that
received them and never to sister hosts such as ``storage.`` or
``staging.`` under the same apex.

Older releases scoped these cookies to the whole apex
(``Domain=.what-a-benger.net``). Browsers keep such a cookie next to the new
host-only one until it expires, and keep sending it to every subdomain. While
``LEGACY_COOKIE_DOMAIN`` is set (a comma-separated list of the old domains),
login, refresh and logout responses therefore also send an expiring copy of
each cookie for every legacy domain, which makes the browser drop the old
domain-wide cookie. A browser ignores a legacy domain its current host does
not belong to, so one list can name the domains of every host family the
deployment serves.
"""

from fastapi import Response

from auth_module.session_origin import SESSION_ORIGIN_COOKIE

SESSION_TOKEN_COOKIES = ("access_token", "refresh_token")

# HttpOnly per cookie, as the cookies are set (the marker is readable).
_HTTPONLY = {
    "access_token": True,
    "refresh_token": True,
    SESSION_ORIGIN_COOKIE: False,
}


def legacy_cookie_domains() -> list[str]:
    """The configured legacy cookie domains, in order, without blanks."""
    from app.core.config import get_settings

    raw = get_settings().legacy_cookie_domain or ""
    domains: list[str] = []
    for part in raw.split(","):
        domain = part.strip()
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def expire_legacy_cookies(
    response: Response,
    names: tuple[str, ...] = (*SESSION_TOKEN_COOKIES, SESSION_ORIGIN_COOKIE),
) -> None:
    """Send ``Max-Age=0`` copies of ``names`` for every legacy domain.

    Call it before setting the new host-only cookies on the same response:
    some cookie stores treat a host-only cookie and a domain cookie for the
    same apex as one entry, so an expiring copy sent after the new cookie
    could remove the new one.
    """
    from app.core.config import get_settings

    domains = legacy_cookie_domains()
    if not domains:
        return
    secure = get_settings().is_production
    for domain in domains:
        for name in names:
            response.delete_cookie(
                key=name,
                path="/",
                domain=domain,
                secure=secure,
                httponly=_HTTPONLY.get(name, True),
                samesite="lax",
            )

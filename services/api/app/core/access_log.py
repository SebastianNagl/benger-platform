"""Keep secrets out of uvicorn's access log.

uvicorn logs every request on the ``uvicorn.access`` logger as
``'%s - "%s %s HTTP/%s" %d'``. The third argument is the path together with
its query string. Some LTI calls carry secrets there. The LMS administrator's
browser opens
``/api/lti/register/init?token=<invite>&openid_configuration=<url>&registration_token=<jwt>``
(IMS Dynamic Registration): the one-time invite token and the LMS's
registration JWT would land in the pod log in clear text.

``LtiQueryRedactionFilter`` rewrites the path argument before the record is
formatted:

- ``/api/lti/register/init``: every query value is replaced. The parameter
  names stay, so a log line still shows which parameters arrived.
- any other ``/api/lti/`` path: the values of token-like parameters are
  replaced (see ``_is_secret_name``).
- every other path is left alone.

The filter never drops a record and never raises. If an LTI path cannot be
parsed, its whole query string is replaced.

``install_access_log_redaction`` attaches the filter to the logger. uvicorn
configures logging before it imports ``main`` (also in each ``--workers``
child and under ``--reload``), and ``dictConfig``/``fileConfig`` keep logger
filters, so attaching it at import time of ``main`` is enough.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import unquote_plus

ACCESS_LOGGER_NAME = "uvicorn.access"
REDACTED = "[redacted]"

# ``/api/lti`` as a path segment, also behind a ROOT_PATH prefix. The
# platform's own ``/api/admin/lti`` routes carry no secrets in the query.
_LTI_PATH = re.compile(r"(?:^|/)api/lti(?:/|$)")
_REGISTER_INIT_PATH = re.compile(r"(?:^|/)api/lti/register/init/?$")

_SECRET_NAMES = frozenset(
    {
        "jwt",
        "client_assertion",
        "login_hint",
        "lti_message_hint",
        "state",
        "nonce",
        "code",
    }
)
_SECRET_NAME_PARTS = ("token", "secret", "password")


def _is_secret_name(name: str) -> bool:
    key = unquote_plus(name).strip().lower()
    return key in _SECRET_NAMES or any(part in key for part in _SECRET_NAME_PARTS)


def _redact_pairs(query: str, *, everything: bool) -> str:
    parts = []
    for pair in query.split("&"):
        if not pair:
            parts.append(pair)
            continue
        name, sep, value = pair.partition("=")
        if not sep:
            # A bare value without a name could be the secret itself.
            parts.append(REDACTED if everything else pair)
        elif value and (everything or _is_secret_name(name)):
            parts.append(f"{name}={REDACTED}")
        else:
            parts.append(pair)
    return "&".join(parts)


def redact_lti_query(path_with_query: str) -> str:
    """The access-log path with LTI secrets removed from its query string."""
    path, sep, query = path_with_query.partition("?")
    if not sep or not _LTI_PATH.search(path):
        return path_with_query
    try:
        everything = bool(_REGISTER_INIT_PATH.search(path))
        return f"{path}?{_redact_pairs(query, everything=everything)}"
    except Exception:  # noqa: BLE001  # pragma: no cover - the parser is total
        return f"{path}?{REDACTED}"


class LtiQueryRedactionFilter(logging.Filter):
    """Redacts LTI secrets in the string arguments of an access-log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            args = record.args
            if isinstance(args, tuple) and args:
                redacted = tuple(
                    redact_lti_query(arg) if isinstance(arg, str) else arg
                    for arg in args
                )
                if redacted != args:
                    record.args = redacted
        except Exception:  # noqa: BLE001, S110  # pragma: no cover - never raise
            pass
        return True


def install_access_log_redaction(logger_name: str = ACCESS_LOGGER_NAME) -> None:
    """Attach the filter to the access logger once."""
    logger = logging.getLogger(logger_name)
    if not any(isinstance(f, LtiQueryRedactionFilter) for f in logger.filters):
        logger.addFilter(LtiQueryRedactionFilter())

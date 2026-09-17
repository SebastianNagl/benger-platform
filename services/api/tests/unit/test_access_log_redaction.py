"""The uvicorn access log never shows LTI secrets.

Found on staging: the access log line of the Moodle registration call

    GET /api/lti/register/init?token=<invite>&openid_configuration=<url>&registration_token=<jwt>

carried the one-time invite token and Moodle's registration JWT in clear
text. ``app.core.access_log`` rewrites the path argument of every
``uvicorn.access`` record before it is formatted. These tests feed real
``LogRecord``s through the filter and through uvicorn's own access
formatter, the one the pods use.
"""

import io
import logging

import pytest
from app.core.access_log import (
    ACCESS_LOGGER_NAME,
    REDACTED,
    LtiQueryRedactionFilter,
    install_access_log_redaction,
    redact_lti_query,
)
from uvicorn.logging import AccessFormatter
from uvicorn.protocols.utils import get_path_with_query_string

INVITE = "Zq3xInviteSecret_9f8e7d6c5b4a"
REG_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJtb29kbGUifQ.c2lnbmF0dXJl"
OPENID = "https%3A%2F%2Fmoodle.example.org%2Fmod%2Flti%2Fopenid-configuration.php"
REGISTER_QUERY = (
    f"token={INVITE}&openid_configuration={OPENID}&registration_token={REG_JWT}"
)
UVICORN_ACCESS_MSG = '%s - "%s %s HTTP/%s" %d'


def _record(path_with_query, *, method="GET", status=200, logger=ACCESS_LOGGER_NAME):
    """An access record exactly as uvicorn's h11/httptools protocol emits it."""
    return logging.LogRecord(
        name=logger,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=UVICORN_ACCESS_MSG,
        args=("10.42.0.154:47736", method, path_with_query, "1.1", status),
        exc_info=None,
    )


def _scope_path(path, query):
    """The path argument uvicorn builds from an ASGI scope."""
    scope = {
        "type": "http",
        "path": path,
        "root_path": "",
        "query_string": query.encode("ascii"),
    }
    return get_path_with_query_string(scope)


class TestRegistrationCall:
    def test_the_staging_line_loses_both_tokens(self):
        record = _record(_scope_path("/api/lti/register/init", REGISTER_QUERY))

        assert LtiQueryRedactionFilter().filter(record) is True
        line = record.getMessage()

        assert INVITE not in line
        assert REG_JWT not in line
        assert OPENID not in line
        assert line == (
            '10.42.0.154:47736 - "GET /api/lti/register/init?'
            f"token={REDACTED}&openid_configuration={REDACTED}"
            f'&registration_token={REDACTED} HTTP/1.1" 200'
        )

    def test_uvicorn_access_formatter_prints_the_redacted_request_line(self):
        record = _record(f"/api/lti/register/init?{REGISTER_QUERY}")
        LtiQueryRedactionFilter().filter(record)

        out = AccessFormatter(
            fmt='%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            use_colors=False,
        ).format(record)

        assert INVITE not in out
        assert REG_JWT not in out
        assert "GET /api/lti/register/init?token=[redacted]" in out
        assert "registration_token=[redacted] HTTP/1.1" in out
        assert out.endswith("200 OK")

    @pytest.mark.parametrize(
        "path",
        [
            "/api/lti/register/init/",
            "/backend/api/lti/register/init",
        ],
    )
    def test_trailing_slash_and_root_path_prefix(self, path):
        assert redact_lti_query(f"{path}?token={INVITE}") == f"{path}?token={REDACTED}"

    def test_unknown_and_bare_parameters_are_redacted_too(self):
        assert (
            redact_lti_query(f"/api/lti/register/init?foo=bar&{INVITE}")
            == f"/api/lti/register/init?foo={REDACTED}&{REDACTED}"
        )

    def test_empty_values_and_empty_pairs_stay(self):
        assert (
            redact_lti_query("/api/lti/register/init?token=&&registration_token=")
            == "/api/lti/register/init?token=&&registration_token="
        )

    def test_no_query_is_unchanged(self):
        record = _record("/api/lti/register/init", status=400)
        LtiQueryRedactionFilter().filter(record)
        assert record.getMessage() == (
            '10.42.0.154:47736 - "GET /api/lti/register/init HTTP/1.1" 400'
        )


class TestOtherLtiPaths:
    def test_login_hints_are_redacted_and_routing_values_kept(self):
        path = (
            "/api/lti/login?iss=https%3A%2F%2Filias.example.org"
            "&login_hint=12&lti_message_hint=%7B%22cmid%22%3A4%7D"
            "&client_id=abc123&lti_deployment_id=1"
        )
        assert redact_lti_query(path) == (
            "/api/lti/login?iss=https%3A%2F%2Filias.example.org"
            f"&login_hint={REDACTED}&lti_message_hint={REDACTED}"
            "&client_id=abc123&lti_deployment_id=1"
        )

    @pytest.mark.parametrize(
        "name",
        [
            "token",
            "id_token",
            "ID_TOKEN",
            "registration%5Ftoken",
            "access_token",
            "jwt",
            "client_assertion",
            "state",
            "nonce",
            "code",
            "client_secret",
            "password",
        ],
    )
    def test_token_like_names_are_redacted(self, name):
        assert (
            redact_lti_query(f"/api/lti/pending/identity?{name}=s3cr3t&h=abc")
            == f"/api/lti/pending/identity?{name}={REDACTED}&h=abc"
        )

    def test_public_handles_stay_readable(self):
        path = "/api/lti/pending?h=9Mb-LeIgM6mnnydvXP8JKQ"
        assert redact_lti_query(path) == path


class TestEverythingElseIsUntouched:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/projects?token=abc",
            "/api/admin/lti/registrations?token=abc",
            "/api/ltix/register/init?token=abc",
            "/lti/consent?rl=1&p=2",
            "/api/health",
        ],
    )
    def test_non_lti_api_paths(self, path):
        record = _record(path)
        before = record.getMessage()
        assert LtiQueryRedactionFilter().filter(record) is True
        assert record.getMessage() == before

    def test_records_without_tuple_args(self):
        f = LtiQueryRedactionFilter()
        plain = logging.LogRecord(
            ACCESS_LOGGER_NAME, logging.INFO, __file__, 1, "no args", None, None
        )
        assert f.filter(plain) is True
        assert plain.getMessage() == "no args"

        mapping = logging.LogRecord(
            ACCESS_LOGGER_NAME,
            logging.INFO,
            __file__,
            1,
            "%(path)s",
            ({"path": f"/api/lti/register/init?token={INVITE}"},),
            None,
        )
        assert f.filter(mapping) is True

    def test_non_string_arguments_pass_through(self):
        record = _record(f"/api/lti/register/init?token={INVITE}", status=404)
        LtiQueryRedactionFilter().filter(record)
        assert record.args[4] == 404
        assert record.args[0] == "10.42.0.154:47736"


class TestInstallation:
    def test_install_is_idempotent_and_redacts_the_emitted_line(self):
        name = "test.access_log_redaction.install"
        logger = logging.getLogger(name)
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        logger.setLevel(logging.INFO)
        try:
            install_access_log_redaction(name)
            install_access_log_redaction(name)
            assert (
                sum(isinstance(f, LtiQueryRedactionFilter) for f in logger.filters) == 1
            )

            logger.info(
                UVICORN_ACCESS_MSG,
                "10.0.0.1:1",
                "GET",
                f"/api/lti/register/init?{REGISTER_QUERY}",
                "1.1",
                200,
            )
        finally:
            logger.removeHandler(handler)
            for f in list(logger.filters):
                logger.removeFilter(f)

        written = stream.getvalue()
        assert INVITE not in written
        assert REG_JWT not in written
        assert f"token={REDACTED}" in written

    def test_the_api_app_installs_it_on_uvicorn_access(self):
        import main  # noqa: F401  (importing the app installs the filter)

        filters = logging.getLogger(ACCESS_LOGGER_NAME).filters
        assert any(isinstance(f, LtiQueryRedactionFilter) for f in filters)

    def test_the_filter_survives_a_uvicorn_logging_reconfiguration(self):
        """uvicorn runs dictConfig in each worker; logger filters survive it."""
        import copy
        import logging.config

        from uvicorn.config import LOGGING_CONFIG

        names = ["uvicorn", "uvicorn.error", ACCESS_LOGGER_NAME]
        saved = {
            n: (
                list(logging.getLogger(n).handlers),
                logging.getLogger(n).level,
                logging.getLogger(n).propagate,
                logging.getLogger(n).disabled,
            )
            for n in names
        }
        install_access_log_redaction(ACCESS_LOGGER_NAME)
        try:
            logging.config.dictConfig(copy.deepcopy(LOGGING_CONFIG))
            filters = logging.getLogger(ACCESS_LOGGER_NAME).filters
            assert any(isinstance(f, LtiQueryRedactionFilter) for f in filters)
        finally:
            for n, (handlers, level, propagate, disabled) in saved.items():
                lg = logging.getLogger(n)
                for h in list(lg.handlers):
                    lg.removeHandler(h)
                for h in handlers:
                    lg.addHandler(h)
                lg.setLevel(level)
                lg.propagate = propagate
                lg.disabled = disabled

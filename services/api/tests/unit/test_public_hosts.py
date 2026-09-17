"""Tool host resolution for LMS connections (``shared/public_hosts.py``)."""

import pytest

import public_hosts as ph

pytestmark = pytest.mark.unit


@pytest.fixture
def env(monkeypatch):
    """Start every test with neither host variable set."""
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.delenv("VERTRETBAR_FRONTEND_URL", raising=False)
    return monkeypatch


def test_keys_match_the_schema_constraint():
    import re

    assert ph.TOOL_HOSTS == ("student_locked", "main")
    for key in ph.TOOL_HOSTS:
        assert re.fullmatch(ph.TOOL_HOST_PATTERN, key)
    assert not re.fullmatch(ph.TOOL_HOST_PATTERN, "other")


class TestResolution:
    def test_both_hosts_configured(self, env):
        env.setenv("FRONTEND_URL", "https://what-a-benger.net/")
        env.setenv("VERTRETBAR_FRONTEND_URL", " https://student.example/ ")

        assert ph.tool_base_url("main") == "https://what-a-benger.net"
        assert ph.tool_base_url("student_locked") == "https://student.example"
        assert ph.public_host("main") == "what-a-benger.net"
        assert ph.public_host("student_locked") == "student.example"
        assert ph.default_tool_host() == "student_locked"
        assert [o.as_dict() for o in ph.available_tool_hosts()] == [
            {
                "key": "student_locked",
                "base_url": "https://student.example",
                "host": "student.example",
                "is_default": True,
            },
            {
                "key": "main",
                "base_url": "https://what-a-benger.net",
                "host": "what-a-benger.net",
                "is_default": False,
            },
        ]

    def test_student_host_unset_is_not_offered(self, env):
        env.setenv("FRONTEND_URL", "http://benger.localhost:8080")

        options = ph.available_tool_hosts()

        assert [o.key for o in options] == ["main"]
        assert options[0].is_default is True
        assert options[0].host == "benger.localhost:8080"
        assert ph.default_tool_host() == "main"
        assert ph.is_tool_host_available("student_locked") is False
        with pytest.raises(ph.ToolHostUnavailable) as exc:
            ph.tool_base_url("student_locked")
        assert exc.value.code == "tool_host_unavailable"
        assert exc.value.key == "student_locked"

    def test_blank_student_host_counts_as_unset(self, env):
        env.setenv("VERTRETBAR_FRONTEND_URL", "  /  ")
        assert ph.student_locked_frontend_url() is None
        assert ph.is_tool_host_available("student_locked") is False

    def test_main_host_falls_back_like_the_mail_branding(self, env):
        from mailer.branding import resolve_email_brand

        assert ph.tool_base_url("main") == "http://localhost:3000"
        assert ph.tool_base_url("main") == resolve_email_brand(None).frontend_url

    def test_values_are_read_at_call_time(self, env):
        env.setenv("FRONTEND_URL", "https://one.example")
        assert ph.tool_base_url("main") == "https://one.example"
        env.setenv("FRONTEND_URL", "https://two.example")
        assert ph.tool_base_url("main") == "https://two.example"


class TestValidation:
    def test_valid_keys_pass(self, env):
        env.setenv("VERTRETBAR_FRONTEND_URL", "https://student.example")
        assert ph.validate_tool_host("main") == "main"
        assert ph.validate_tool_host("student_locked") == "student_locked"

    def test_none_selects_the_default(self, env):
        assert ph.validate_tool_host(None) == "main"
        env.setenv("VERTRETBAR_FRONTEND_URL", "https://student.example")
        assert ph.validate_tool_host(None) == "student_locked"

    @pytest.mark.parametrize("key", ["", "MAIN", "student", "platform", 1, "main "])
    def test_unknown_keys_are_rejected(self, env, key):
        with pytest.raises(ph.ToolHostUnavailable):
            ph.validate_tool_host(key)
        with pytest.raises(ph.ToolHostUnavailable):
            ph.tool_base_url(key)
        assert ph.is_tool_host_available(key) is False

    def test_unavailable_error_is_a_value_error(self):
        assert issubclass(ph.ToolHostUnavailable, ValueError)


class TestRequestHostKind:
    def test_student_locked_hosts_map_to_the_student_key(self):
        from mailer.branding import _STUDENT_LOCKED_HOSTS

        for apex in _STUDENT_LOCKED_HOSTS:
            assert ph.tool_host_for_request_host(apex) == "student_locked"
            assert ph.tool_host_for_request_host(f"org.{apex}:443") == "student_locked"

    @pytest.mark.parametrize(
        "host",
        ["what-a-benger.net", "tum.what-a-benger.net", "benger.localhost:3000", None, ""],
    )
    def test_other_hosts_map_to_main(self, host):
        assert ph.tool_host_for_request_host(host) == "main"

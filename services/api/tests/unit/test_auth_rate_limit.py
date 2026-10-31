"""Brute-force limits on the public auth routes (audit S2).

Runs the real limiter against fakeredis with the TESTING bypass switched off:
client-IP extraction, the per-account login lockout and its reset on a
correct password, the per-IP and per-account windows, the 429 shape, and
fail-closed behaviour when Redis is unreachable.
"""

import inspect
from types import SimpleNamespace
from unittest.mock import Mock, patch

import fakeredis
import pytest
from fastapi import HTTPException, Response

from services import auth_rate_limit as arl
from services import rate_limiter as rl


@pytest.fixture
def fake_redis(monkeypatch):
    """The global limiter on fakeredis, TESTING bypass off."""
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    client = fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setattr(rl.rate_limiter, "redis_client", client)
    return client


@pytest.fixture
def no_redis(monkeypatch):
    """Redis down: no client and every reconnect attempt fails."""
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setattr(rl.rate_limiter, "redis_client", None)
    monkeypatch.setattr(rl.rate_limiter, "_memory_store", {})
    monkeypatch.setattr(
        rl.redis, "from_url", Mock(side_effect=ConnectionError("redis down"))
    )


def _request(xff=None, peer="10.0.0.5", headers=None):
    hdrs = dict(headers or {})
    if xff is not None:
        hdrs["X-Forwarded-For"] = xff
    return SimpleNamespace(
        headers=hdrs,
        client=SimpleNamespace(host=peer) if peer else None,
        cookies={},
        state=SimpleNamespace(),
    )


async def _call(handler, **kwargs):
    """Call a route handler that is ``def`` or ``async def`` (the auth
    handlers that take the sync Session are moving to plain ``def``)."""
    result = handler(**kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


def _assert_429(exc: HTTPException, max_retry_after: int):
    assert exc.status_code == 429
    assert exc.detail["code"] == "rate_limited"
    assert 1 <= exc.detail["retry_after"] <= max_retry_after
    assert exc.headers["Retry-After"] == str(exc.detail["retry_after"])


# Client IP --------------------------------------------------------------------


class TestClientIp:
    def test_rightmost_hop_wins_over_client_supplied_left_entries(self, monkeypatch):
        monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
        # The client sent "1.2.3.4"; Traefik appended the real peer.
        assert rl.get_client_ip(_request("1.2.3.4, 198.51.100.7")) == "198.51.100.7"

    def test_single_entry(self, monkeypatch):
        monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
        assert rl.get_client_ip(_request("198.51.100.7")) == "198.51.100.7"

    def test_trusted_hops_skip_proxies_in_front(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
        assert (
            rl.get_client_ip(_request("1.2.3.4, 198.51.100.7, 203.0.113.1"))
            == "198.51.100.7"
        )

    def test_chain_shorter_than_hops_falls_back_to_peer(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
        assert rl.get_client_ip(_request("198.51.100.7")) == "10.0.0.5"

    def test_no_header_uses_peer(self, monkeypatch):
        monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
        assert rl.get_client_ip(_request()) == "10.0.0.5"
        assert rl.get_client_ip(_request(" , ")) == "10.0.0.5"

    def test_no_peer_no_header(self):
        assert rl.get_client_ip(_request(peer=None)) is None

    def test_bad_hops_value_means_zero(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", "many")
        assert rl.get_client_ip(_request("1.2.3.4, 198.51.100.7")) == "198.51.100.7"

    def test_limiter_client_id_uses_the_rightmost_hop(self, monkeypatch):
        monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
        assert (
            rl.rate_limiter._get_client_id(_request("6.6.6.6, 198.51.100.7"))
            == "ip:198.51.100.7"
        )


# Login throttle ---------------------------------------------------------------


def _expire_cooldown(fake_redis, login):
    """Stand in for the 60 s passing."""
    fake_redis.delete(arl._cooldown_key(arl.account_key(login)))


class TestLoginThrottle:
    async def test_tenth_failure_starts_a_one_minute_cooldown(self, fake_redis):
        for _ in range(arl.LOGIN_FREE_FAILURES - 1):
            arl.check_login_throttle("Student@Uni.de")
            arl.record_login_failure("Student@Uni.de")
        arl.check_login_throttle("student@uni.de")  # 9 failures: still open

        arl.record_login_failure("student@uni.de")  # the 10th
        with pytest.raises(HTTPException) as exc:
            # Case-insensitive: the throttle is per submitted login, lowercased.
            arl.check_login_throttle("STUDENT@uni.de")
        _assert_429(exc.value, arl.LOGIN_COOLDOWN_SECONDS)
        assert exc.value.detail["retry_after"] > arl.LOGIN_COOLDOWN_SECONDS - 5

    async def test_after_the_cooldown_one_attempt_per_minute(self, fake_redis):
        for _ in range(arl.LOGIN_FREE_FAILURES):
            arl.record_login_failure("student")
        _expire_cooldown(fake_redis, "student")
        arl.check_login_throttle("student")  # one attempt goes through
        assert arl.record_login_failure("student") == arl.LOGIN_FREE_FAILURES + 1
        with pytest.raises(HTTPException) as exc:
            arl.check_login_throttle("student")  # and the next waits again
        _assert_429(exc.value, arl.LOGIN_COOLDOWN_SECONDS)

    async def test_refused_attempts_do_not_extend_the_cooldown(self, fake_redis):
        for _ in range(arl.LOGIN_FREE_FAILURES):
            arl.record_login_failure("student")
        key = arl._cooldown_key(arl.account_key("student"))
        fake_redis.expire(key, 5)
        for _ in range(20):
            with pytest.raises(HTTPException):
                arl.check_login_throttle("student")
        assert 0 < fake_redis.ttl(key) <= 5

    async def test_correct_password_after_the_cooldown_clears_everything(
        self, fake_redis
    ):
        for _ in range(arl.LOGIN_FREE_FAILURES + 3):
            arl.record_login_failure("student")
        _expire_cooldown(fake_redis, "student")
        arl.check_login_throttle("student")
        arl.reset_login_failures("student")
        # A fresh window: nine more failures do not throttle.
        for _ in range(arl.LOGIN_FREE_FAILURES - 1):
            arl.record_login_failure("student")
        arl.check_login_throttle("student")

    async def test_throttle_is_per_account(self, fake_redis):
        for _ in range(arl.LOGIN_FREE_FAILURES):
            arl.record_login_failure("victim")
        arl.check_login_throttle("someone-else")

    async def test_window_slides(self, fake_redis):
        import time

        key = arl._failures_key(arl.account_key("student"))
        old = time.time() - arl.LOGIN_FAILURE_WINDOW_SECONDS - 1
        fake_redis.zadd(key, {f"old-{i}": old for i in range(arl.LOGIN_FREE_FAILURES)})
        # The stale failures fell out of the window: this is failure number one.
        assert arl.record_login_failure("student") == 1
        arl.check_login_throttle("student")
        assert 0 < fake_redis.ttl(key) <= arl.LOGIN_FAILURE_WINDOW_SECONDS

    async def test_redis_keys_carry_no_address(self, fake_redis):
        for _ in range(arl.LOGIN_FREE_FAILURES):
            arl.record_login_failure("student@uni.de")
        assert not [k for k in fake_redis.keys("*") if "student" in k]


# Windows ------------------------------------------------------------------------


class TestWindows:
    async def test_ip_limit_answers_429_after_the_cap(self, fake_redis):
        request = _request("198.51.100.7")
        for _ in range(3):
            arl.enforce_ip_limit(request, "t_ip", (3, 3600))
        with pytest.raises(HTTPException) as exc:
            arl.enforce_ip_limit(request, "t_ip", (3, 3600))
        _assert_429(exc.value, 3600)
        # Another client is not affected.
        arl.enforce_ip_limit(_request("198.51.100.8"), "t_ip", (3, 3600))

    async def test_spoofed_left_entries_do_not_open_new_buckets(self, fake_redis):
        for i in range(3):
            arl.enforce_ip_limit(
                _request(f"10.9.9.{i}, 198.51.100.7"), "t_spoof", (3, 3600)
            )
        with pytest.raises(HTTPException):
            arl.enforce_ip_limit(
                _request("10.9.9.99, 198.51.100.7"), "t_spoof", (3, 3600)
            )

    async def test_account_limit_is_case_insensitive(self, fake_redis):
        request = _request("198.51.100.7")
        for login in ("A@x.de", "a@x.de", " a@X.de "):
            arl.enforce_account_limit(request, login, "t_acct", arl.MAIL_ACCOUNT_LIMIT)
        with pytest.raises(HTTPException) as exc:
            arl.enforce_account_limit(
                request, "a@x.de", "t_acct", arl.MAIL_ACCOUNT_LIMIT
            )
        _assert_429(exc.value, 3600)

    async def test_no_request_skips_the_ip_bucket(self, fake_redis):
        for _ in range(5):
            arl.enforce_ip_limit(None, "t_none", (1, 3600))

    async def test_testing_bypass(self, fake_redis, monkeypatch):
        monkeypatch.setenv("TESTING", "true")
        for _ in range(5):
            arl.enforce_ip_limit(_request("198.51.100.7"), "t_bypass", (1, 3600))
            arl.record_login_failure("student")
        arl.check_login_throttle("student")


# Fail closed --------------------------------------------------------------------


class TestFailClosed:
    async def test_ip_bucket_refuses_without_redis(self, no_redis):
        with pytest.raises(HTTPException) as exc:
            arl.enforce_ip_limit(_request("198.51.100.7"), "t_down", (300, 900))
        assert exc.value.status_code == 503
        assert exc.value.detail == {"code": "rate_limiter_unavailable"}
        assert exc.value.headers["Retry-After"]

    async def test_login_lock_refuses_without_redis(self, no_redis):
        with pytest.raises(HTTPException) as exc:
            arl.check_login_throttle("student")
        assert exc.value.status_code == 503

    async def test_redis_error_mid_request_refuses(self, fake_redis, monkeypatch):
        broken = Mock()
        broken.pipeline.side_effect = ConnectionError("gone")
        broken.ttl.side_effect = ConnectionError("gone")
        monkeypatch.setattr(rl.rate_limiter, "redis_client", broken)
        with pytest.raises(HTTPException) as exc:
            arl.enforce_account_limit(None, "a@x.de", "t_err", (3, 3600))
        assert exc.value.status_code == 503
        with pytest.raises(HTTPException) as exc:
            arl.check_login_throttle("a@x.de")
        assert exc.value.status_code == 503
        with pytest.raises(HTTPException) as exc:
            arl.record_login_failure("a@x.de")
        assert exc.value.status_code == 503

    async def test_reconnects_when_redis_comes_back(self, monkeypatch):
        monkeypatch.setenv("TESTING", "false")
        monkeypatch.setattr(rl.rate_limiter, "redis_client", None)
        client = fakeredis.FakeRedis(
            server=fakeredis.FakeServer(), decode_responses=True
        )
        monkeypatch.setattr(rl.redis, "from_url", Mock(return_value=client))
        arl.enforce_ip_limit(_request("198.51.100.7"), "t_back", (3, 3600))
        assert rl.rate_limiter.redis_client is client

    async def test_default_callers_stay_fail_open(self, no_redis):
        """custom_models / shares keep the old behaviour: memory fallback."""
        assert (
            await rl.rate_limiter.check_rate_limit(
                _request("198.51.100.7"), "share_password", {"minute": (5, 60)}
            )
            is None
        )

    async def test_fail_open_increment_on_error_still_counts_as_one(self):
        limiter = rl.RateLimiter.__new__(rl.RateLimiter)
        limiter.redis_client = Mock()
        limiter.redis_client.pipeline.side_effect = ConnectionError("gone")
        limiter._memory_store = {}
        assert await limiter._increment_count("k", 60) == 1
        with pytest.raises(rl.RateLimiterUnavailable):
            await limiter._increment_count("k", 60, fail_closed=True)


# Login handler ------------------------------------------------------------------


def _login_request():
    return SimpleNamespace(
        headers={"X-Forwarded-For": "198.51.100.7"},
        client=SimpleNamespace(host="10.0.0.5"),
        cookies={},
        url="http://localhost/api/auth/login",
        state=SimpleNamespace(),
    )


class TestLoginHandler:
    async def test_throttles_after_ten_failures_without_checking_the_password(
        self, fake_redis
    ):
        from auth_module import UserLogin
        from routers.auth import login

        with patch("routers.auth.session.authenticate_user", return_value=None) as auth:
            for _ in range(arl.LOGIN_FREE_FAILURES):
                with pytest.raises(HTTPException) as exc:
                    await _call(
                        login,
                        login_data=UserLogin(username="student", password="guess"),
                        response=Response(),
                        request=_login_request(),
                        db=Mock(),
                    )
                assert exc.value.status_code == 401
            assert auth.call_count == arl.LOGIN_FREE_FAILURES

            with pytest.raises(HTTPException) as exc:
                await _call(
                    login,
                    login_data=UserLogin(username="student", password="right"),
                    response=Response(),
                    request=_login_request(),
                    db=Mock(),
                )
            _assert_429(exc.value, arl.LOGIN_COOLDOWN_SECONDS)
            assert auth.call_count == arl.LOGIN_FREE_FAILURES

    async def test_owner_gets_in_after_a_classmates_burst(self, fake_redis):
        """Ten wrong passwords from someone else cost the owner one minute."""
        from auth_module import UserLogin
        from routers.auth import login

        for _ in range(arl.LOGIN_FREE_FAILURES):
            arl.record_login_failure("student")
        _expire_cooldown(fake_redis, "student")

        unverified = Mock(email_verified=False, id="u1")
        with patch("routers.auth.session.authenticate_user", return_value=unverified):
            with pytest.raises(HTTPException) as exc:
                await _call(
                    login,
                    login_data=UserLogin(username="student", password="right"),
                    response=Response(),
                    request=_login_request(),
                    db=Mock(),
                )
        assert exc.value.status_code == 403  # password accepted, then the email gate
        assert not fake_redis.exists(arl._failures_key(arl.account_key("student")))

    async def test_correct_password_resets_the_counter(self, fake_redis):
        from auth_module import UserLogin
        from routers.auth import login

        for _ in range(arl.LOGIN_FREE_FAILURES - 1):
            arl.record_login_failure("student")

        unverified = Mock(email_verified=False, id="u1")
        with patch("routers.auth.session.authenticate_user", return_value=unverified):
            with pytest.raises(HTTPException) as exc:
                await _call(
                    login,
                    login_data=UserLogin(username="student", password="right"),
                    response=Response(),
                    request=_login_request(),
                    db=Mock(),
                )
        assert exc.value.status_code == 403
        assert not fake_redis.exists(arl._failures_key(arl.account_key("student")))

    async def test_ip_soft_limit(self, fake_redis, monkeypatch):
        from auth_module import UserLogin
        from routers.auth import login

        monkeypatch.setenv("AUTH_IP_LIMIT_LOGIN", "2")
        with patch("routers.auth.session.authenticate_user", return_value=None):
            for name in ("a", "b"):
                with pytest.raises(HTTPException) as exc:
                    await _call(
                        login,
                        login_data=UserLogin(username=name, password="x"),
                        response=Response(),
                        request=_login_request(),
                        db=Mock(),
                    )
                assert exc.value.status_code == 401
            with pytest.raises(HTTPException) as exc:
                await _call(
                    login,
                    login_data=UserLogin(username="c", password="x"),
                    response=Response(),
                    request=_login_request(),
                    db=Mock(),
                )
        _assert_429(exc.value, 900)

    async def test_redis_down_refuses_login(self, no_redis):
        from auth_module import UserLogin
        from routers.auth import login

        with patch("routers.auth.session.authenticate_user") as auth:
            with pytest.raises(HTTPException) as exc:
                await _call(
                    login,
                    login_data=UserLogin(username="student", password="x"),
                    response=Response(),
                    request=_login_request(),
                    db=Mock(),
                )
        assert exc.value.status_code == 503
        auth.assert_not_called()


class TestMailAndTokenRoutes:
    async def test_password_reset_mail_three_per_account(self, fake_redis):
        from routers.auth import request_password_reset
        from schemas.auth_schemas import PasswordResetRequest

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        for _ in range(3):
            await _call(
                request_password_reset,
                reset_request=PasswordResetRequest(email="Nobody@x.de"),
                request=_login_request(),
                db=db,
            )
        with pytest.raises(HTTPException) as exc:
            await _call(
                request_password_reset,
                reset_request=PasswordResetRequest(email="nobody@x.de"),
                request=_login_request(),
                db=db,
            )
        _assert_429(exc.value, 3600)

    async def test_resend_verification_three_per_account(self, fake_redis):
        from routers.auth import resend_verification_email
        from schemas.auth_schemas import ResendVerificationRequest

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        for _ in range(3):
            await _call(
                resend_verification_email,
                resend_request=ResendVerificationRequest(email="a@x.de"),
                request=_login_request(),
                db=db,
            )
        with pytest.raises(HTTPException) as exc:
            await _call(
                resend_verification_email,
                resend_request=ResendVerificationRequest(email="a@x.de"),
                request=_login_request(),
                db=db,
            )
        _assert_429(exc.value, 3600)

    async def test_reset_password_token_submits_per_ip(self, fake_redis, monkeypatch):
        from routers.auth import reset_password
        from schemas.auth_schemas import PasswordResetConfirm

        monkeypatch.setenv("AUTH_IP_LIMIT_RESET_PASSWORD", "2")
        body = PasswordResetConfirm(
            token="t", new_password="a" * 12, confirm_password="b" * 12
        )
        for _ in range(2):
            with pytest.raises(HTTPException) as exc:
                await _call(
                    reset_password,
                    reset_confirm=body,
                    request=_login_request(),
                    db=Mock(),
                )
            assert exc.value.status_code == 400  # mismatch, but counted
        with pytest.raises(HTTPException) as exc:
            await _call(
                reset_password, reset_confirm=body, request=_login_request(), db=Mock()
            )
        _assert_429(exc.value, 3600)

    async def test_activate_account_per_ip(self, fake_redis, monkeypatch):
        from routers.auth import activate_account
        from schemas.auth_schemas import AccountActivateConfirm

        monkeypatch.setenv("AUTH_IP_LIMIT_ACTIVATE", "1")
        body = AccountActivateConfirm(
            token="t", new_password="a" * 12, confirm_password="b" * 12
        )
        with pytest.raises(HTTPException) as exc:
            await _call(
                activate_account, confirm=body, request=_login_request(), db=Mock()
            )
        assert exc.value.status_code == 400
        with pytest.raises(HTTPException) as exc:
            await _call(
                activate_account, confirm=body, request=_login_request(), db=Mock()
            )
        _assert_429(exc.value, 3600)


# Configurable per-IP limits ---------------------------------------------------


class TestIpLimitConfig:
    def test_defaults(self, monkeypatch):
        for env_name, _, _ in arl.IP_LIMITS.values():
            monkeypatch.delenv(env_name, raising=False)
        assert arl.ip_limit(arl.LOGIN) == (1000, 900)
        assert arl.ip_limit(arl.PASSWORD_RESET_MAIL) == (60, 3600)
        assert arl.ip_limit(arl.VERIFICATION_MAIL) == (60, 3600)
        assert arl.ip_limit(arl.PASSWORD_RESET_TOKEN) == (40, 3600)
        assert arl.ip_limit(arl.ACCOUNT_ACTIVATION) == (40, 3600)
        assert arl.ip_limit(arl.SIGNUP) == (40, 3600)

    def test_env_override_and_bad_values(self, monkeypatch):
        monkeypatch.setenv("AUTH_IP_LIMIT_SIGNUP", "250")
        assert arl.ip_limit(arl.SIGNUP) == (250, 3600)
        for bad in ("0", "-3", "lots"):
            monkeypatch.setenv("AUTH_IP_LIMIT_SIGNUP", bad)
            assert arl.ip_limit(arl.SIGNUP) == (40, 3600)

    async def test_signup_route_reads_the_env(self, fake_redis, monkeypatch):
        monkeypatch.setenv("AUTH_IP_LIMIT_SIGNUP", "1")
        request = _request("198.51.100.7")
        arl.enforce_ip_limit(request, arl.SIGNUP)
        with pytest.raises(HTTPException) as exc:
            arl.enforce_ip_limit(request, arl.SIGNUP)
        _assert_429(exc.value, 3600)


# Unknown client address (SNAT, loopback, private) -----------------------------


class TestUnknownClientSkip:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",
            "::1",
            "169.254.10.1",
            "fe80::1",
            "10.42.0.17",
            "172.16.0.1",
            "172.31.255.254",
            "192.168.1.20",
            "fd12:3456::1",
            "::ffff:10.42.0.5",
            None,
        ],
    )
    def test_infrastructure_addresses_are_unknown(self, ip):
        assert arl.client_ip_is_unknown(ip)

    @pytest.mark.parametrize(
        "ip", ["198.51.100.7", "172.32.0.1", "100.64.0.1", "2001:db8::1", "not-an-ip"]
    )
    def test_public_and_unparsable_addresses_are_known(self, ip):
        assert not arl.client_ip_is_unknown(ip)

    async def test_private_client_is_neither_counted_nor_limited(self, fake_redis):
        request = _request("10.42.0.17")  # what svclb SNAT leaves behind
        for _ in range(10):
            arl.enforce_ip_limit(request, "t_snat", (1, 3600))
        assert not [k for k in fake_redis.keys("*") if "t_snat" in k]

    async def test_no_forwarded_header_and_private_peer_skips(self, fake_redis):
        for _ in range(5):
            arl.enforce_ip_limit(_request(peer="10.0.0.5"), "t_peer", (1, 3600))

    async def test_skip_needs_no_redis(self, no_redis):
        arl.enforce_ip_limit(_request("192.168.0.9"), "t_down_private", (1, 3600))

    async def test_account_buckets_still_apply(self, fake_redis):
        request = _request("10.42.0.17")
        for _ in range(3):
            arl.enforce_account_limit(request, "a@x.de", "t_acct_snat", (3, 3600))
        with pytest.raises(HTTPException):
            arl.enforce_account_limit(request, "a@x.de", "t_acct_snat", (3, 3600))

    async def test_debug_logged_once_per_process(self, fake_redis, monkeypatch, caplog):
        import logging

        monkeypatch.setattr(arl, "_unknown_client_logged", False)
        with caplog.at_level(logging.DEBUG, logger=arl.logger.name):
            for _ in range(3):
                arl.enforce_ip_limit(_request("10.42.0.17"), "t_log", (1, 3600))
        notes = [r for r in caplog.records if "client address" in r.getMessage()]
        assert len(notes) == 1
        assert notes[0].levelno == logging.DEBUG

    async def test_login_behind_snat_is_still_throttled_per_account(self, fake_redis):
        from auth_module import UserLogin
        from routers.auth import login

        snat = SimpleNamespace(
            headers={},
            client=SimpleNamespace(host="10.42.0.1"),
            cookies={},
            url="http://localhost/api/auth/login",
            state=SimpleNamespace(),
        )
        with patch("routers.auth.session.authenticate_user", return_value=None):
            for _ in range(arl.LOGIN_FREE_FAILURES):
                with pytest.raises(HTTPException) as exc:
                    await _call(
                        login,
                        login_data=UserLogin(username="student", password="x"),
                        response=Response(),
                        request=snat,
                        db=Mock(),
                    )
                assert exc.value.status_code == 401
            with pytest.raises(HTTPException) as exc:
                await _call(
                    login,
                    login_data=UserLogin(username="student", password="x"),
                    response=Response(),
                    request=snat,
                    db=Mock(),
                )
        _assert_429(exc.value, arl.LOGIN_COOLDOWN_SECONDS)
        assert not [k for k in fake_redis.keys("*") if k.startswith("ratelimit:ip:")]


class TestSyncAndAsyncLimiterShareOneCore:
    async def test_async_and_sync_count_into_the_same_bucket(self, fake_redis):
        limits = {"window": (2, 3600)}
        request = _request("198.51.100.7")
        assert rl.rate_limiter.check_rate_limit_sync(request, "t_twin", limits) is None
        assert await rl.rate_limiter.check_rate_limit(request, "t_twin", limits) is None
        error = rl.rate_limiter.check_rate_limit_sync(request, "t_twin", limits)
        assert error and error["current"] == 3

    async def test_async_fail_closed_raises_like_the_sync_one(self, no_redis):
        with pytest.raises(rl.RateLimiterUnavailable):
            await rl.rate_limiter.check_rate_limit(
                _request("198.51.100.7"),
                "t_twin_down",
                {"w": (1, 60)},
                fail_closed=True,
            )
        with pytest.raises(rl.RateLimiterUnavailable):
            rl.rate_limiter.check_rate_limit_sync(
                _request("198.51.100.7"),
                "t_twin_down",
                {"w": (1, 60)},
                fail_closed=True,
            )

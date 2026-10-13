"""Weak ETags and conditional responses of the v1 task reads."""

from datetime import datetime, timezone
from types import SimpleNamespace

from routers.v1.tasks import conditional_response, etag_matches, weak_etag


def _request(if_none_match=None):
    headers = {"if-none-match": if_none_match} if if_none_match is not None else {}
    return SimpleNamespace(headers=headers)


def test_weak_etag_is_stable_and_sensitive():
    a = weak_etag("tasks", "p", 3, None, True)
    assert a == weak_etag("tasks", "p", 3, None, True)
    assert a.startswith('W/"') and a.endswith('"')
    assert a != weak_etag("tasks", "p", 3, None, False)  # blinding is part of it
    assert a != weak_etag("tasks", "p", 4, None, True)


def test_if_none_match_parsing():
    tag = weak_etag("x")
    assert etag_matches(_request(tag), tag)
    assert etag_matches(_request(tag[2:]), tag)  # strong form of the same tag
    assert etag_matches(_request(f'"other", {tag}'), tag)
    assert etag_matches(_request("*"), tag)
    assert not etag_matches(_request('"other"'), tag)
    assert not etag_matches(_request(), tag)


def test_conditional_response():
    tag = weak_etag("y")
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    r = conditional_response(_request(), {"a": 1}, tag, when)
    assert r.status_code == 200
    assert r.headers["etag"] == tag
    assert r.headers["last-modified"] == "Fri, 02 Jan 2026 03:04:05 GMT"
    r = conditional_response(_request(tag), {"a": 1}, tag, when)
    assert r.status_code == 304 and r.body == b""
    assert r.headers["etag"] == tag

"""Unit tests for the Safe Exam Browser request verifier (/shared/seb.py).

Pure module, no DB. Hash inputs follow SEB's definition:
``hex(sha256(absolute_url_without_fragment + key))``.
"""

import hashlib

import pytest

import seb

CK = "a" * 64
CK2 = "b" * 64
BEK = "c" * 64
BEK_OTHER = "d" * 64


@pytest.fixture(autouse=True)
def _hosts(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://what-a-benger.net")
    monkeypatch.setenv("VERTRETBAR_FRONTEND_URL", "https://vertretbar.net")


def _h(url, key):
    return hashlib.sha256((url + key).encode()).hexdigest()


def _cfg(**extra):
    cfg = {"generated_config_key": CK}
    cfg.update(extra)
    return cfg


PATH = "/api/projects/p1/tasks/t1/draft"
REQ_URL = f"https://what-a-benger.net{PATH}"


class TestPrimitives:
    def test_key_hash_matches_seb_definition_and_drops_fragment(self):
        assert seb.key_hash("https://x.de/a?b=1#frag", CK) == _h("https://x.de/a?b=1", CK)

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("A" * 64, "a" * 64),
            ("  " + "f" * 64 + "\n", "f" * 64),
            ("g" * 64, None),
            ("a" * 63, None),
            (None, None),
            (123, None),
        ],
    )
    def test_normalize_key(self, raw, expected):
        assert seb.normalize_key(raw) == expected

    def test_accepted_keys_merge_generated_and_extra_deduped(self):
        cfg = _cfg(extra_config_keys=[CK.upper(), CK2, "junk"])
        assert seb.accepted_config_keys(cfg) == [CK, CK2]
        assert seb.accepted_config_keys(None) == []
        assert seb.accepted_config_keys({"extra_config_keys": "notalist"}) == []

    def test_accepted_browser_exam_keys_take_dicts_or_strings(self):
        cfg = _cfg(browser_exam_keys=[{"key": BEK, "label": "SEB 3.9"}, BEK_OTHER, {"x": 1}])
        assert seb.accepted_browser_exam_keys(cfg) == [BEK, BEK_OTHER]

    @pytest.mark.parametrize(
        "host,ok",
        [
            ("what-a-benger.net", True),
            ("tum.what-a-benger.net", True),
            ("WHAT-A-BENGER.NET", True),
            ("vertretbar.net", True),
            ("evil-what-a-benger.net", False),
            ("what-a-benger.net.evil.de", False),
            ("", False),
            (None, False),
        ],
    )
    def test_host_allowed(self, host, ok):
        assert seb.host_allowed(host) is ok

    def test_public_request_urls_use_forwarded_host_and_both_schemes(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_URL", "http://benger.localhost")
        urls = seb.public_request_urls(
            {"x-forwarded-host": "benger.localhost, proxy", "x-forwarded-proto": "https"},
            "/api/x",
            "a=1",
        )
        assert urls == ["https://benger.localhost/api/x?a=1", "http://benger.localhost/api/x?a=1"]

    def test_public_request_urls_refuse_foreign_host(self):
        assert seb.public_request_urls({"host": "evil.de"}, "/api/x", "") == []


class TestVerifyNativeHeaders:
    def test_valid_config_key_header_passes(self):
        headers = {"host": "what-a-benger.net", "x-safeexambrowser-configkeyhash": _h(REQ_URL, CK)}
        result = seb.verify_seb_request(headers, PATH, "", _cfg())
        assert result.ok and result.via == seb.VIA_HEADER
        assert not result.browser_exam_key_checked

    def test_extra_config_key_is_accepted(self):
        headers = {"host": "what-a-benger.net", "x-safeexambrowser-configkeyhash": _h(REQ_URL, CK2)}
        assert seb.verify_seb_request(headers, PATH, "", _cfg(extra_config_keys=[CK2])).ok

    def test_hash_for_another_url_is_refused(self):
        other = _h("https://what-a-benger.net/api/projects/p2/tasks/t1/draft", CK)
        headers = {"host": "what-a-benger.net", "x-safeexambrowser-configkeyhash": other}
        result = seb.verify_seb_request(headers, PATH, "", _cfg())
        assert not result.ok and result.code == seb.CODE_SEB_REQUIRED

    def test_query_string_is_part_of_the_hash(self):
        headers = {"host": "what-a-benger.net", "x-safeexambrowser-configkeyhash": _h(REQ_URL, CK)}
        assert not seb.verify_seb_request(headers, PATH, "page=2", _cfg()).ok

    def test_wrong_key_and_missing_proof_are_refused(self):
        wrong = {"host": "what-a-benger.net", "x-safeexambrowser-configkeyhash": _h(REQ_URL, CK2)}
        assert seb.verify_seb_request(wrong, PATH, "", _cfg()).code == seb.CODE_SEB_REQUIRED
        assert seb.verify_seb_request({"host": "what-a-benger.net"}, PATH, "", _cfg()).code == (
            seb.CODE_SEB_REQUIRED
        )

    def test_no_accepted_keys_refuses_everything(self):
        headers = {"host": "what-a-benger.net", "x-safeexambrowser-configkeyhash": _h(REQ_URL, CK)}
        assert not seb.verify_seb_request(headers, PATH, "", {}).ok

    def test_foreign_host_cannot_be_used_as_hash_input(self):
        url = f"https://evil.de{PATH}"
        headers = {"host": "evil.de", "x-safeexambrowser-configkeyhash": _h(url, CK)}
        assert not seb.verify_seb_request(headers, PATH, "", _cfg()).ok

    def test_pinned_browser_exam_key(self):
        cfg = _cfg(browser_exam_keys=[{"key": BEK, "label": "SEB"}])
        base = {"host": "what-a-benger.net", "x-safeexambrowser-configkeyhash": _h(REQ_URL, CK)}
        ok = seb.verify_seb_request(
            {**base, "x-safeexambrowser-requesthash": _h(REQ_URL, BEK)}, PATH, "", cfg
        )
        assert ok.ok and ok.browser_exam_key_checked
        wrong = seb.verify_seb_request(
            {**base, "x-safeexambrowser-requesthash": _h(REQ_URL, BEK_OTHER)}, PATH, "", cfg
        )
        assert wrong.code == seb.CODE_SEB_VERSION_NOT_ALLOWED
        missing = seb.verify_seb_request(base, PATH, "", cfg)
        assert missing.code == seb.CODE_SEB_VERSION_NOT_ALLOWED


class TestVerifyJavaScriptApi:
    PAGE = "https://what-a-benger.net/student/exams/p1?lti_u=u1"

    def test_page_url_hash_passes(self):
        headers = {"x-benger-seb-ck": _h(self.PAGE, CK), "x-benger-seb-url": self.PAGE + "#top"}
        result = seb.verify_seb_request(headers, PATH, "", _cfg())
        assert result.ok and result.via == seb.VIA_JS

    def test_load_url_is_tried_too(self):
        headers = {
            "x-benger-seb-ck": _h(self.PAGE, CK),
            "x-benger-seb-url": "https://what-a-benger.net/student/exams/p1/other",
            "x-benger-seb-load-url": self.PAGE,
        }
        assert seb.verify_seb_request(headers, PATH, "", _cfg()).ok

    def test_page_url_on_foreign_host_is_ignored(self):
        page = "https://evil.de/x"
        headers = {"x-benger-seb-ck": _h(page, CK), "x-benger-seb-url": page}
        assert not seb.verify_seb_request(headers, PATH, "", _cfg()).ok

    def test_page_url_with_other_scheme_is_ignored(self):
        page = "javascript://what-a-benger.net/x"
        headers = {"x-benger-seb-ck": _h(page, CK), "x-benger-seb-url": page}
        assert not seb.verify_seb_request(headers, PATH, "", _cfg()).ok

    def test_pinned_browser_exam_key_via_js(self):
        cfg = _cfg(browser_exam_keys=[BEK])
        headers = {
            "x-benger-seb-ck": _h(self.PAGE, CK),
            "x-benger-seb-bek": _h(self.PAGE, BEK),
            "x-benger-seb-url": self.PAGE,
        }
        assert seb.verify_seb_request(headers, PATH, "", cfg).browser_exam_key_checked
        headers["x-benger-seb-bek"] = _h(self.PAGE, BEK_OTHER)
        assert seb.verify_seb_request(headers, PATH, "", cfg).code == (
            seb.CODE_SEB_VERSION_NOT_ALLOWED
        )

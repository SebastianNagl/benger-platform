"""``app_version.app_version()``: the image tag from ``BENGER_APP_VERSION``."""

from app_version import ENV_VAR, app_version


def test_unset_means_no_version(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert app_version() is None


def test_blank_means_no_version(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "   ")
    assert app_version() is None


def test_returns_the_stripped_tag_and_reads_the_env_on_every_call(monkeypatch):
    monkeypatch.setenv(ENV_VAR, " v2026.11.16-abc1234-def5678 \n")
    assert app_version() == "v2026.11.16-abc1234-def5678"
    monkeypatch.setenv(ENV_VAR, "dev")
    assert app_version() == "dev"

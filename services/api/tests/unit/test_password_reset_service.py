"""
Integration-style tests for PasswordResetService.send_password_reset_email.

These tests intentionally do NOT mock password_reset_service or EmailService —
they exercise the real call chain all the way down to SendGridClient.send_message,
which is the only thing stubbed. This is the test layer that catches:

  * broken module imports inside the service (the bug that black-holed every
    real password reset in prod until 2026-05-14)
  * call-site/method-signature drift between PasswordResetService and EmailService

Coverage that already exists under test_auth_router_coverage.py mocks
`app.auth_module.password_reset.password_reset_service`, so it cannot see
either class of bug.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.email = "user@example.com"
    user.name = "Test User"
    user.username = "test_user"
    user.password_reset_token = None
    user.password_reset_expires = None
    return user


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.commit = MagicMock()
    return db


@pytest.mark.asyncio
async def test_send_password_reset_email_end_to_end(mock_db, mock_user, monkeypatch):
    """Full path: PasswordResetService -> EmailService -> SendGridClient.send_message.

    Asserts the token is persisted on the user row, the link uses FRONTEND_URL,
    and the SendGrid client receives a single message addressed to the user.
    """
    monkeypatch.setenv("FRONTEND_URL", "https://what-a-benger.net")

    with patch("services.email.email_service.SendGridClient") as mock_sg_class, \
         patch("database.SessionLocal"):
        sg_instance = MagicMock()
        sg_instance.send_message = MagicMock(return_value={"status": "success"})
        mock_sg_class.return_value = sg_instance

        from app.auth_module.password_reset import password_reset_service

        ok = await password_reset_service.send_password_reset_email(
            db=mock_db,
            user=mock_user,
            base_url="https://fallback.example",
            language="de",
        )

    assert ok is True
    assert mock_user.password_reset_token != None  # noqa: E711
    assert mock_user.password_reset_expires != None  # noqa: E711
    mock_db.commit.assert_called_once()

    sg_instance.send_message.assert_called_once()
    call_kwargs = sg_instance.send_message.call_args[1]
    assert call_kwargs["to"] == ["user@example.com"]
    assert "Passwort" in call_kwargs["subject"]
    assert "https://what-a-benger.net/reset-password/" in call_kwargs["html_body"]
    assert mock_user.password_reset_token in call_kwargs["html_body"]
    # Template-declared duration must match PasswordResetService.TOKEN_EXPIRY_HOURS,
    # otherwise users assume the link is dead before it actually expires.
    assert "24 Stunden" in call_kwargs["html_body"]


@pytest.mark.asyncio
async def test_send_password_reset_email_propagates_sendgrid_failure(
    mock_db, mock_user, monkeypatch
):
    """If SendGrid reports failure the service returns False, but the token
    is still persisted (so admin diagnostics can find it and the email can
    be re-issued without rotating the row)."""
    monkeypatch.setenv("FRONTEND_URL", "https://what-a-benger.net")

    with patch("services.email.email_service.SendGridClient") as mock_sg_class, \
         patch("database.SessionLocal"):
        sg_instance = MagicMock()
        sg_instance.send_message = MagicMock(
            return_value={"status": "error", "error": "boom"}
        )
        mock_sg_class.return_value = sg_instance

        from app.auth_module.password_reset import password_reset_service

        ok = await password_reset_service.send_password_reset_email(
            db=mock_db, user=mock_user, base_url="https://fallback.example", language="en"
        )

    assert ok is False
    assert mock_user.password_reset_token != None  # noqa: E711


@pytest.mark.asyncio
async def test_send_password_reset_email_uses_username_when_name_missing(
    mock_db, mock_user, monkeypatch
):
    monkeypatch.setenv("FRONTEND_URL", "https://what-a-benger.net")
    mock_user.name = None

    with patch("services.email.email_service.SendGridClient") as mock_sg_class, \
         patch("database.SessionLocal"):
        sg_instance = MagicMock()
        sg_instance.send_message = MagicMock(return_value={"status": "success"})
        mock_sg_class.return_value = sg_instance

        from app.auth_module.password_reset import password_reset_service

        ok = await password_reset_service.send_password_reset_email(
            db=mock_db, user=mock_user, base_url="https://fallback.example", language="en"
        )

    assert ok is True
    sent_html = sg_instance.send_message.call_args[1]["html_body"]
    assert "test_user" in sent_html
    assert "24 hours" in sent_html


@pytest.mark.asyncio
async def test_send_password_reset_email_falls_back_to_base_url(
    mock_db, mock_user, monkeypatch
):
    """When FRONTEND_URL is unset the caller-supplied base_url is used."""
    monkeypatch.delenv("FRONTEND_URL", raising=False)

    with patch("services.email.email_service.SendGridClient") as mock_sg_class, \
         patch("database.SessionLocal"):
        sg_instance = MagicMock()
        sg_instance.send_message = MagicMock(return_value={"status": "success"})
        mock_sg_class.return_value = sg_instance

        from app.auth_module.password_reset import password_reset_service

        await password_reset_service.send_password_reset_email(
            db=mock_db, user=mock_user, base_url="https://fallback.example", language="en"
        )

    sent_html = sg_instance.send_message.call_args[1]["html_body"]
    assert "https://fallback.example/reset-password/" in sent_html

"""The async EmailService senders run the sync mail client off the event loop.

``mail_client.send_message`` is a blocking ``requests.post`` to the mail
provider. The coroutines the API handlers await (password reset, verification,
test mail) hand it to a worker thread, so a slow provider cannot stall other
requests on the same event loop.
"""

import asyncio
import threading
import time
from unittest.mock import patch

import pytest

from email_service import EmailService


class _RecordingClient:
    """Stands in for the provider client: records the thread, sleeps like a slow send."""

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.threads = []

    def send_message(self, **kwargs):
        self.threads.append(threading.get_ident())
        if self.delay:
            time.sleep(self.delay)
        return {"status": "success"}


@pytest.fixture
def service():
    with patch("mailer.email_service.SendGridClient"), patch("database.SessionLocal"):
        svc = EmailService()
    svc.mail_client = _RecordingClient()
    return svc


SENDERS = {
    "password_reset": lambda s: s.send_password_reset_email(
        "user@example.com", "User", "https://example.com/reset"
    ),
    "verification": lambda s: s.send_verification_email(
        "user@example.com", "User", "https://example.com/verify"
    ),
    "test_email": lambda s: s.send_test_email("user@example.com"),
}


@pytest.mark.parametrize("name", sorted(SENDERS))
async def test_send_runs_off_the_loop_thread(service, name):
    loop_thread = threading.get_ident()

    assert await SENDERS[name](service) is True

    assert len(service.mail_client.threads) == 1
    assert service.mail_client.threads[0] != loop_thread


async def test_slow_send_does_not_block_a_concurrent_coroutine(service):
    service.mail_client = _RecordingClient(delay=0.5)
    done_at = {}

    async def send():
        result = await SENDERS["password_reset"](service)
        done_at["send"] = time.monotonic()
        return result

    async def ticker():
        for _ in range(5):
            await asyncio.sleep(0.02)
        done_at["ticker"] = time.monotonic()

    sent, _ = await asyncio.gather(send(), ticker())

    assert sent is True
    # A send on the loop thread would hold the loop for the whole 0.5 s, so the
    # ticker could only finish after it; off the loop it finishes during the send.
    assert done_at["ticker"] < done_at["send"]

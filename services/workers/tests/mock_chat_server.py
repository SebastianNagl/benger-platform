"""A local OpenAI-compatible chat-completions server for tests.

It records the raw body of every request and answers from a queue of
scripted replies, so a test can compare what a provider client recorded as
sent (``ai_services.request_capture``) with the bytes the server received.
"""

from __future__ import annotations

import http.server
import json
import threading
from contextlib import contextmanager
from typing import Iterator, List, Optional


class MockChatServer:
    def __init__(self) -> None:
        self.bodies: List[bytes] = []
        self.paths: List[str] = []
        self.replies: List[dict] = []
        self._server: Optional[http.server.HTTPServer] = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def reply(
        self,
        content: str,
        *,
        finish_reason: str = "stop",
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
        reasoning: Optional[str] = None,
    ) -> None:
        message = {"role": "assistant", "content": content}
        if reasoning is not None:
            message["reasoning_content"] = reasoning
        self.replies.append(
            {
                "id": f"chatcmpl-{len(self.replies)}",
                "object": "chat.completion",
                "created": 0,
                "model": "mock",
                "choices": [
                    {"index": 0, "message": message, "finish_reason": finish_reason}
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
        )

    def json_bodies(self) -> List[dict]:
        return [json.loads(body) for body in self.bodies]

    def _handler(self):
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 (http.server API)
                length = int(self.headers.get("Content-Length") or 0)
                server.bodies.append(self.rfile.read(length))
                server.paths.append(self.path)
                reply = (
                    server.replies.pop(0)
                    if server.replies
                    else {
                        "choices": [
                            {"message": {"content": ""}, "finish_reason": "stop"}
                        ],
                        "usage": {},
                    }
                )
                payload = json.dumps(reply).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):  # quiet
                pass

        return Handler

    def start(self) -> "MockChatServer":
        self._server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), self._handler()
        )
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()


@contextmanager
def mock_chat_server() -> Iterator[MockChatServer]:
    server = MockChatServer().start()
    try:
        yield server
    finally:
        server.stop()

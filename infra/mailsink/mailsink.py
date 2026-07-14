"""Tiny SendGrid-API mail catcher for local dev.

Accepts POST /v3/mail/send (the SendGrid contract), stores messages in
memory, and serves a web view at / with the extracted verification/reset
links made clickable. No auth, no real delivery — dev only.
"""
import json, re, html
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MSGS = []  # newest first
LINK_RE = re.compile(r'https?://[^\s"\'<>]+/(?:verify-email|reset-password|accept-invitation)[^\s"\'<>]*')


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        if self.path.rstrip("/") == "/v3/mail/send":
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n).decode("utf-8", "replace")
            try:
                p = json.loads(raw)
            except Exception:
                p = {"_parse_error": raw[:500]}
            to = ", ".join(
                t.get("email", "") for pers in p.get("personalizations", [{}])
                for t in pers.get("to", [])
            )
            subject = p.get("subject") or (p.get("personalizations", [{}])[0].get("subject", ""))
            contents = p.get("content", [])
            body_html = next((c.get("value", "") for c in contents if c.get("type") == "text/html"), "")
            body_txt = next((c.get("value", "") for c in contents if c.get("type") == "text/plain"), "")
            links = sorted(set(LINK_RE.findall(body_html + " " + body_txt)))
            MSGS.insert(0, {
                "at": datetime.now().strftime("%H:%M:%S"),
                "to": to, "subject": subject,
                "html": body_html, "txt": body_txt, "links": links,
            })
            del MSGS[50:]
            # SendGrid returns 202 Accepted with an X-Message-Id header.
            self.send_response(202)
            self.send_header("X-Message-Id", "mailsink-local")
            self.end_headers()
            return
        self._send(404, "not found")

    def do_GET(self):
        if self.path.startswith("/json"):
            return self._send(200, json.dumps(MSGS, ensure_ascii=False), "application/json")
        rows = []
        for m in MSGS:
            links = "".join(
                f'<div><a href="{html.escape(l)}" target="_blank">{html.escape(l)}</a></div>' for l in m["links"]
            ) or '<em>(no verify/reset link found)</em>'
            rows.append(
                f'<div style="border:1px solid #ddd;border-radius:8px;padding:12px;margin:10px 0">'
                f'<div style="color:#666;font-size:12px">{m["at"]} → {html.escape(m["to"])}</div>'
                f'<div style="font-weight:600;margin:4px 0">{html.escape(m["subject"])}</div>'
                f'<div style="margin:8px 0">{links}</div>'
                f'<details><summary style="cursor:pointer;color:#059669">HTML anzeigen</summary>'
                f'<div style="border-top:1px solid #eee;margin-top:8px;padding-top:8px">{m["html"]}</div></details>'
                f'</div>'
            )
        page = (
            '<html><head><meta charset="utf-8"><title>BenGER Mail Sink</title>'
            '<meta http-equiv="refresh" content="5">'
            '<style>body{font-family:system-ui;max-width:760px;margin:24px auto;padding:0 16px}</style></head>'
            f'<body><h2>📬 BenGER Mail Sink <span style="color:#666;font-size:14px">({len(MSGS)} captured, auto-refresh 5s)</span></h2>'
            + ("".join(rows) or "<p>No emails yet. Sign up to trigger one.</p>")
            + "</body></html>"
        )
        self._send(200, page)


if __name__ == "__main__":
    print("mailsink on :8025 (POST /v3/mail/send, view /)")
    ThreadingHTTPServer(("0.0.0.0", 8025), H).serve_forever()

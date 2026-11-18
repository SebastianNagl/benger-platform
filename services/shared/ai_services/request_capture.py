"""The exact requests a provider client sends, for the generation record.

Every provider service calls :func:`record_request` immediately before it
hands a request to the network (the JSON body of an HTTP POST) or to a
provider SDK (the keyword arguments of the SDK call). The generation worker
opens a :func:`capture_requests` scope around each provider call and stores
what was captured as ``generations.request_record``, so the stored record is
what the client actually sent: the rendered messages including every block a
service added on its own (an appended answer-format instruction, a
structured-output schema in the system prompt, ``response_format``), and the
sampling parameters after every clamp and drop.

``capture`` names how close the record is to the wire:

* ``http_body``: the JSON body on the wire. For the aiohttp clients
  (DeepInfra, xAI, custom OpenAI-compatible endpoints) it is the dict passed
  as ``json=``; for the SDK clients (OpenAI, Anthropic, Google, Mistral,
  Cohere, all on httpx) it is read from the request the SDK hands to
  httpx, inside the capture scope, so it holds what the SDK added
  (``"stream": false``, ``extra_body`` merged in, Gemini's REST field
  names). ``path`` is then the request path.
* ``sdk_kwargs``: the keyword arguments of the SDK call, kept when the SDK
  sent nothing through httpx (a replaced client in a test).

Outside a capture scope :func:`record_request` does nothing, so callers that
do not ask (judges, scripts) pay nothing.
"""

from __future__ import annotations

import contextvars
import copy
import hashlib
import json
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

#: Version of the ``request_record`` document. Bump on a shape change.
REQUEST_RECORD_VERSION = 1

_capture_ctx: contextvars.ContextVar = contextvars.ContextVar(
    "ai_service_request_capture", default=None
)


@contextmanager
def capture_requests() -> Iterator[List[Dict[str, Any]]]:
    """Collect every request the provider clients send inside the block.

    Yields the list the entries land in. Nested scopes are independent: the
    inner one sees only its own requests.
    """
    captured: List[Dict[str, Any]] = []
    token = _capture_ctx.set(captured)
    try:
        yield captured
    finally:
        try:
            _capture_ctx.reset(token)
        except ValueError:
            # Reset from another Context (SDKs hop threads on error paths):
            # clearing is equivalent here.
            _capture_ctx.set(None)


def _jsonable(value: Any) -> Any:
    """A JSON-safe copy of an SDK argument (pydantic models, enums, types)."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    for dump in ("model_dump", "to_dict", "dict"):
        method = getattr(value, dump, None)
        if callable(method):
            try:
                dumped = method(exclude_none=True) if dump == "model_dump" else method()
            except TypeError:
                dumped = method()
            return _jsonable(dumped)
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int, float)):
        return enum_value
    return str(value)


def record_request(
    provider: str,
    api: str,
    body: Dict[str, Any],
    *,
    capture: str = "http_body",
) -> None:
    """Record one outgoing request if a capture scope is open.

    Call it right before the send. A transport retry (HTTP 429/5xx) re-sends
    the same body; it is counted on the previous entry (``sends``) instead of
    being listed twice.
    """
    captured = _capture_ctx.get()
    if captured is None:
        return
    if capture == "http_body":
        # The HTTP client serialises this very dict; a JSON round trip gives
        # an independent copy with the same content.
        snapshot = json.loads(json.dumps(body, ensure_ascii=False))
    else:
        snapshot = _jsonable(copy.copy(body))
    if (
        captured
        and captured[-1]["api"] == api
        and captured[-1]["provider"] == provider
        and captured[-1]["body"] == snapshot
    ):
        captured[-1]["sends"] += 1
        return
    captured.append(
        {
            "provider": provider,
            "api": api,
            "capture": capture,
            "body": snapshot,
            "sends": 1,
        }
    )


def _record_wire(request: Any) -> None:
    """httpx send hook: replace the pending ``sdk_kwargs`` entry of the scope
    with the JSON body the SDK actually sends."""
    captured = _capture_ctx.get()
    if not captured:
        return
    pending = captured[-1]
    try:
        body = json.loads(request.content or b"null")
    except (ValueError, TypeError, UnicodeDecodeError, RuntimeError):
        return
    if not isinstance(body, dict):
        return
    if pending.get("capture") == "http_body" and pending.get("body") == body:
        # The SDK's own retry of the same request.
        pending["sends"] += 1
        return
    if pending.get("capture") != "sdk_kwargs":
        return
    pending["body"] = body
    pending["capture"] = "http_body"
    pending["path"] = request.url.path
    if (
        len(captured) > 1
        and captured[-2].get("capture") == "http_body"
        and captured[-2]["api"] == pending["api"]
        and captured[-2]["body"] == body
    ):
        # A service-level retry re-sent the previous request unchanged.
        captured.pop()
        captured[-1]["sends"] += 1


def _install_httpx_hook() -> None:
    """Wrap ``Client.send`` / ``AsyncClient.send`` of httpx (and of
    ``httpx2``, the copy some SDKs ship on) once, so a request an SDK sends
    inside a capture scope is recorded as sent. Outside a scope the wrapper
    only checks the context variable."""
    import importlib

    for module_name in ("httpx", "httpx2"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for cls_name, is_async in (("Client", False), ("AsyncClient", True)):
            cls = getattr(module, cls_name, None)
            original = getattr(cls, "send", None)
            if original is None or getattr(original, "_benger_request_capture", False):
                continue
            if is_async:

                async def wrapped(self, request, *args, _original=original, **kwargs):
                    _record_wire(request)
                    return await _original(self, request, *args, **kwargs)

            else:

                def wrapped(self, request, *args, _original=original, **kwargs):
                    _record_wire(request)
                    return _original(self, request, *args, **kwargs)

            wrapped._benger_request_capture = True
            cls.send = wrapped


_install_httpx_hook()


def canonical_json(value: Any) -> str:
    """Stable serialisation for hashing (sorted keys, no whitespace)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_of(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Normalised view: messages, response format, parameters, model id
# --------------------------------------------------------------------------

_CHAT_APIS = {"chat.completions", "mistral.chat", "cohere.chat"}


def normalized_view(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Provider-neutral view of one captured request.

    ``messages`` is a list of ``{"role", "content"}`` in conversation order
    with the system prompt first (where the provider takes it apart, as
    Anthropic and Google do, it is put back in front); ``response_format``
    is whatever constrains the answer format (``response_format``, a tool
    schema, a response schema), or None; ``parameters`` is the rest of the
    request; ``model`` the provider's model id.
    """
    api = entry.get("api")
    body = dict(entry.get("body") or {})
    model = body.pop("model", None)
    messages: List[Dict[str, Any]] = []
    response_format: Any = None

    if api in _CHAT_APIS:
        messages = list(body.pop("messages", []) or [])
        response_format = body.pop("response_format", None)
    elif api == "openai.responses":
        instructions = body.pop("instructions", None)
        if instructions:
            messages.append({"role": "system", "content": instructions})
        inp = body.pop("input", None)
        if isinstance(inp, list):
            messages.extend(inp)
        elif inp is not None:
            messages.append({"role": "user", "content": inp})
        response_format = body.pop("text", None)
    elif api == "anthropic.messages":
        system = body.pop("system", None)
        if system:
            messages.append({"role": "system", "content": system})
        messages.extend(body.pop("messages", []) or [])
        tools = body.pop("tools", None)
        tool_choice = body.pop("tool_choice", None)
        if tools or tool_choice:
            response_format = {"tools": tools, "tool_choice": tool_choice}
    elif api == "google.generate_content":
        # SDK kwargs (config.system_instruction) or the REST body on the
        # wire (systemInstruction, generationConfig).
        config = dict(body.pop("config", None) or body.pop("generationConfig", None) or {})
        system = config.pop("system_instruction", None) or body.pop("systemInstruction", None)
        if isinstance(system, dict):
            texts = [p.get("text") for p in system.get("parts") or [] if isinstance(p, dict)]
            system = "".join(t for t in texts if isinstance(t, str))
        if system:
            messages.append({"role": "system", "content": system})
        contents = body.pop("contents", None)
        if isinstance(contents, list):
            for item in contents:
                if isinstance(item, dict) and "role" in item:
                    role = "assistant" if item.get("role") == "model" else item.get("role")
                    parts = item.get("parts") or []
                    texts = [p.get("text") for p in parts if isinstance(p, dict) and "text" in p]
                    content: Any = texts[0] if len(texts) == 1 and len(parts) == 1 else parts
                    messages.append({"role": role, "content": content})
                else:
                    messages.append({"role": "user", "content": item})
        elif contents is not None:
            messages.append({"role": "user", "content": contents})
        schema = (
            config.pop("response_schema", None)
            or config.pop("response_json_schema", None)
            or config.pop("responseSchema", None)
            or config.pop("responseJsonSchema", None)
        )
        mime = config.pop("response_mime_type", None) or config.pop("responseMimeType", None)
        if schema is not None or mime == "application/json":
            response_format = {"response_mime_type": mime, "response_schema": schema}
        elif mime is not None:
            config["response_mime_type"] = mime
        if config:
            body["config"] = config
    else:
        # "worker_call" and any OpenAI-shaped body.
        messages = list(body.pop("messages", []) or [])
        response_format = body.pop("response_format", None)

    return {
        "model": model,
        # Role and content only: wire details of a message (Mistral's
        # ``prefix: false`` on assistant turns) stay in ``requests[].body``.
        "messages": [
            {"role": m.get("role"), "content": m.get("content")} if isinstance(m, dict) else m
            for m in messages
        ],
        "response_format": response_format,
        "parameters": body,
    }


def build_request_record(
    captured: List[Dict[str, Any]],
    *,
    fallback: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """The ``generations.request_record`` document for one generation.

    ``captured`` holds every request the provider clients sent for the
    generation in order (the first request, then a format retry, if any).
    The top-level ``model``, ``messages``, ``response_format`` and
    ``parameters`` describe the first request: that is the designed prompt a
    re-run must reproduce, and ``request_sha256`` hashes it. ``requests``
    keeps every request verbatim.

    ``fallback`` is used when the client reported nothing (an E2E mock or a
    test double that does not send): it is the call the worker made, marked
    ``capture: "worker_call"`` so a reader can tell it apart from a captured
    request.
    """
    if captured:
        requests = [dict(entry) for entry in captured]
    elif fallback is not None:
        requests = [dict(fallback, capture="worker_call", sends=0)]
    else:
        return None
    first = normalized_view(requests[0])
    return {
        "version": REQUEST_RECORD_VERSION,
        "provider": requests[0].get("provider"),
        "api": requests[0].get("api"),
        "capture": requests[0].get("capture"),
        **first,
        "requests": requests,
    }


def request_sha256(record: Optional[Dict[str, Any]]) -> Optional[str]:
    """Hash of the first request's body (canonical JSON), or None."""
    if not record or not record.get("requests"):
        return None
    return sha256_of(record["requests"][0].get("body"))

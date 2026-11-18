"""ai_services.request_capture: what a provider client sent, recorded as sent."""

import json

from ai_services.request_capture import (
    REQUEST_RECORD_VERSION,
    build_request_record,
    capture_requests,
    normalized_view,
    record_request,
    request_sha256,
    sha256_of,
)

BODY = {
    "model": "acme/model-1",
    "messages": [
        {"role": "system", "content": "Du bist Schlichter für Mietsachen."},
        {"role": "user", "content": "Akte S-12/26 \u2013 Mieterin gegen Vermieter, § 535 BGB."},
    ],
    "temperature": 0.7,
    "max_tokens": 600,
    "stream": False,
}


def test_outside_a_scope_nothing_is_recorded():
    record_request("DeepInfra", "chat.completions", BODY)
    with capture_requests() as captured:
        pass
    assert captured == []


def test_records_an_independent_copy_and_counts_resends():
    body = json.loads(json.dumps(BODY))
    with capture_requests() as captured:
        record_request("DeepInfra", "chat.completions", body)
        body["messages"][1]["content"] = "changed after the send"
        # A transport retry re-sends the original body: counted, not listed.
        record_request("DeepInfra", "chat.completions", BODY)
        record_request("DeepInfra", "chat.completions", body)
    assert [entry["sends"] for entry in captured] == [2, 1]
    assert captured[0]["body"] == BODY
    assert captured[0]["capture"] == "http_body"


def test_nested_scopes_are_independent():
    with capture_requests() as outer:
        record_request("A", "chat.completions", {"model": "a"})
        with capture_requests() as inner:
            record_request("B", "chat.completions", {"model": "b"})
        record_request("C", "chat.completions", {"model": "c"})
    assert [e["provider"] for e in outer] == ["A", "C"]
    assert [e["provider"] for e in inner] == ["B"]


def test_sdk_kwargs_are_made_json_safe():
    class _Config:
        def model_dump(self, exclude_none=False):
            return {"temperature": 0.0, "system_instruction": "Sys", "skip": None} if not exclude_none else {"temperature": 0.0, "system_instruction": "Sys"}

    with capture_requests() as captured:
        record_request(
            "Google", "google.generate_content",
            {"model": "g", "contents": "Frage", "config": _Config()},
            capture="sdk_kwargs",
        )
    assert captured[0]["body"]["config"] == {"temperature": 0.0, "system_instruction": "Sys"}
    json.dumps(captured[0]["body"])


def test_build_record_describes_the_first_request():
    retry = dict(BODY, messages=BODY["messages"] + [
        {"role": "assistant", "content": "kein JSON"},
        {"role": "user", "content": "Bitte nur den JSON-Block."},
    ])
    with capture_requests() as captured:
        record_request("DeepInfra", "chat.completions", BODY)
        record_request("DeepInfra", "chat.completions", retry)
    record = build_request_record(captured)
    assert record["version"] == REQUEST_RECORD_VERSION
    assert record["model"] == "acme/model-1"
    assert record["messages"] == BODY["messages"]
    assert record["response_format"] is None
    assert record["parameters"] == {"temperature": 0.7, "max_tokens": 600, "stream": False}
    assert [r["body"] for r in record["requests"]] == [BODY, retry]
    # The hash identifies the designed (first) request, independent of key order.
    reordered = dict(reversed(list(BODY.items())))
    assert request_sha256(record) == sha256_of(reordered)


def test_no_request_gives_no_record():
    assert build_request_record([]) is None
    assert request_sha256(None) is None


def test_normalized_views_put_the_system_prompt_first():
    anthropic = normalized_view({"api": "anthropic.messages", "body": {
        "model": "c", "system": "Sys", "max_tokens": 5,
        "messages": [{"role": "user", "content": "U"}],
    }})
    assert anthropic["messages"] == [
        {"role": "system", "content": "Sys"}, {"role": "user", "content": "U"},
    ]
    assert anthropic["parameters"] == {"max_tokens": 5}

    google = normalized_view({"api": "google.generate_content", "body": {
        "model": "g",
        "contents": [
            {"role": "user", "parts": [{"text": "U"}]},
            {"role": "model", "parts": [{"text": "A"}]},
        ],
        "config": {"system_instruction": "Sys", "response_mime_type": "application/json",
                   "temperature": 0.0},
    }})
    assert google["messages"] == [
        {"role": "system", "content": "Sys"},
        {"role": "user", "content": "U"},
        {"role": "assistant", "content": "A"},
    ]
    assert google["response_format"]["response_mime_type"] == "application/json"
    assert google["parameters"] == {"config": {"temperature": 0.0}}

    responses = normalized_view({"api": "openai.responses", "body": {
        "model": "o", "instructions": "Sys", "input": "U", "max_output_tokens": 9,
    }})
    assert responses["messages"] == [
        {"role": "system", "content": "Sys"}, {"role": "user", "content": "U"},
    ]

    chat = normalized_view({"api": "chat.completions", "body": {
        "model": "m", "messages": [], "response_format": {"type": "json_object"},
    }})
    assert chat["response_format"] == {"type": "json_object"}

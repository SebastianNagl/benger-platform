"""Binary attachments (page images, PDFs) on provider calls (CORE 2.48).

Pins the content shapes each provider sends and that every other provider is
refused up front: a text-only model that silently dropped the pages would
answer without seeing them, which for OCR means an invented transcript.
"""

import types
from unittest.mock import MagicMock

import pytest

from ai_services.anthropic_service import AnthropicService
from ai_services.attachments import (
    Attachment,
    UnsupportedAttachmentError,
    generate_with_attachments,
    service_supports_attachments,
)
from ai_services.google_service import GoogleService
from ai_services.mistral_service import MistralService
from ai_services.openai_service import OpenAIService

JPEG = Attachment("image/jpeg", b"\xff\xd8\xffjpegbytes", "page1.jpg")
PDF = Attachment("application/pdf", b"%PDF-1.7 bytes", "scan.pdf")


def test_attachment_rejects_unknown_types_and_empty_data():
    with pytest.raises(UnsupportedAttachmentError):
        Attachment("image/tiff", b"x")
    with pytest.raises(UnsupportedAttachmentError):
        Attachment("image/png", b"")


def test_anthropic_sends_image_and_document_blocks_before_the_text():
    svc = AnthropicService(api_key="sk-ant-test")
    svc.client = MagicMock()
    svc.client.messages.create.return_value = types.SimpleNamespace(
        content=[types.SimpleNamespace(text="Transkript")],
        stop_reason="end_turn",
        usage=types.SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    result = generate_with_attachments(
        svc, "Bitte transkribieren", [JPEG, PDF], model_name="claude-sonnet-4-6"
    )
    assert result["content"] == "Transkript"
    content = svc.client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "document", "text"]
    assert content[0]["source"]["media_type"] == "image/jpeg"
    assert content[1]["source"]["media_type"] == "application/pdf"
    assert content[2]["text"] == "Bitte transkribieren"


def test_anthropic_without_attachments_still_sends_a_plain_string():
    svc = AnthropicService(api_key="sk-ant-test")
    svc.client = MagicMock()
    svc.client.messages.create.return_value = types.SimpleNamespace(
        content=[types.SimpleNamespace(text="ok")],
        stop_reason="end_turn",
        usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    svc.generate(prompt="hi", model_name="claude-sonnet-4-6")
    assert svc.client.messages.create.call_args.kwargs["messages"][0]["content"] == "hi"


def test_openai_chat_sends_data_url_parts():
    svc = OpenAIService(api_key="sk-test")
    svc.client = MagicMock()
    choice = types.SimpleNamespace(
        message=types.SimpleNamespace(content="Transkript", refusal=None),
        finish_reason="stop",
    )
    svc.client.chat.completions.create.return_value = types.SimpleNamespace(
        choices=[choice],
        usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        system_fingerprint=None,
    )
    generate_with_attachments(svc, "Bitte transkribieren", [JPEG, PDF], model_name="gpt-4.1")
    messages = svc.client.chat.completions.create.call_args.kwargs["messages"]
    parts = messages[1]["content"]
    assert parts[0] == {"type": "text", "text": "Bitte transkribieren"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert parts[2]["type"] == "file"
    assert parts[2]["file"]["file_data"].startswith("data:application/pdf;base64,")


def test_openai_responses_only_models_are_refused():
    svc = OpenAIService(api_key="sk-test")
    pro = next(
        m for m in ("gpt-5-pro", "o3-pro", "gpt-5.4-pro")
        if OpenAIService._is_responses_api_only_model(m)
    )
    assert service_supports_attachments(svc, pro) is False
    with pytest.raises(UnsupportedAttachmentError):
        generate_with_attachments(svc, "p", [JPEG], model_name=pro)


def test_google_sends_parts_then_text():
    svc = GoogleService(api_key="g-test")
    svc.client = MagicMock()
    generate_with_attachments(svc, "Bitte transkribieren", [JPEG], model_name="gemini-2.0-flash")
    contents = svc.client.models.generate_content.call_args.kwargs["contents"]
    assert contents[-1] == "Bitte transkribieren"
    assert len(contents) == 2


def test_text_only_providers_are_refused_before_any_call():
    svc = MistralService(api_key="m-test")
    svc.client = MagicMock()
    assert service_supports_attachments(svc) is False
    with pytest.raises(UnsupportedAttachmentError):
        generate_with_attachments(svc, "p", [JPEG], model_name="mistral-large-latest")
    svc.client.assert_not_called()


def test_no_attachments_is_an_error():
    with pytest.raises(UnsupportedAttachmentError):
        generate_with_attachments(AnthropicService(api_key="k"), "p", [], model_name="m")


def test_catalog_rule_for_models_that_read_pages():
    from ai_services.attachments import catalog_model_reads_attachments

    assert catalog_model_reads_attachments("OpenAI", "gpt-5.4", ["multimodal"])
    assert catalog_model_reads_attachments("Google", "gemini-2.5-pro", ["multimodal"])
    assert catalog_model_reads_attachments("anthropic", "claude-sonnet-4-6", ["multimodal"])
    # Responses-API-only tiers, providers without attachments, text models.
    assert not catalog_model_reads_attachments("OpenAI", "gpt-5.4-pro", ["multimodal"])
    assert not catalog_model_reads_attachments("Mistral", "pixtral", ["multimodal"])
    assert not catalog_model_reads_attachments("OpenAI", "gpt-5.4", ["text-generation"])
    assert not catalog_model_reads_attachments(None, "x", None)

"""Binary attachments (page images, PDFs) for provider calls.

Only providers whose service class sets ``SUPPORTS_ATTACHMENTS = True``
accept them (Anthropic, OpenAI chat completions, Google). Every caller goes
through :func:`generate_with_attachments`, which refuses up front on any other
provider: a text-only provider that silently dropped the images would answer
the prompt without ever seeing them, which for OCR means an invented
transcript.

Each provider builds its own content shape from the same ``Attachment`` list
via the ``*_content`` helpers below.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
PDF_MIME_TYPE = "application/pdf"
SUPPORTED_MIME_TYPES = IMAGE_MIME_TYPES | {PDF_MIME_TYPE}


class UnsupportedAttachmentError(ValueError):
    """The provider/model cannot take binary attachments, or the type is unknown."""


@dataclass(frozen=True)
class Attachment:
    mime_type: str
    data: bytes
    filename: str = "attachment"

    def __post_init__(self) -> None:
        if self.mime_type not in SUPPORTED_MIME_TYPES:
            raise UnsupportedAttachmentError(
                f"unsupported attachment type {self.mime_type!r}"
            )
        if not self.data:
            raise UnsupportedAttachmentError("empty attachment")

    @property
    def b64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    @property
    def is_pdf(self) -> bool:
        return self.mime_type == PDF_MIME_TYPE


def anthropic_content(prompt: str, attachments: Sequence[Attachment]) -> List[Dict[str, Any]]:
    """Anthropic Messages content blocks: attachments first, then the text."""
    blocks: List[Dict[str, Any]] = []
    for att in attachments:
        blocks.append({
            "type": "document" if att.is_pdf else "image",
            "source": {"type": "base64", "media_type": att.mime_type, "data": att.b64},
        })
    blocks.append({"type": "text", "text": prompt})
    return blocks


def openai_chat_content(prompt: str, attachments: Sequence[Attachment]) -> List[Dict[str, Any]]:
    """OpenAI Chat Completions content parts (image_url / file data URLs)."""
    parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for att in attachments:
        data_url = f"data:{att.mime_type};base64,{att.b64}"
        if att.is_pdf:
            parts.append({
                "type": "file",
                "file": {"filename": att.filename or "document.pdf", "file_data": data_url},
            })
        else:
            parts.append({"type": "image_url", "image_url": {"url": data_url, "detail": "high"}})
    return parts


def google_contents(prompt: str, attachments: Sequence[Attachment]) -> List[Any]:
    """google.genai ``contents``: one Part per attachment, then the text."""
    from google.genai import types  # local: only the workers/api images that call Google need it

    contents: List[Any] = [
        types.Part.from_bytes(data=att.data, mime_type=att.mime_type) for att in attachments
    ]
    contents.append(prompt)
    return contents


#: Providers whose services send attachments (``SUPPORTS_ATTACHMENTS``).
ATTACHMENT_PROVIDERS = frozenset({"openai", "anthropic", "google"})


def catalog_model_reads_attachments(provider: Optional[str], model_id: str, capabilities) -> bool:
    """Whether a catalog model can take page images/PDFs here: a provider
    with attachment support, the ``multimodal`` capability, and not one of
    OpenAI's responses-API-only ``*-pro`` tiers (attachments are wired for
    chat completions only). The frontend model picker mirrors this rule."""
    if (provider or "").lower() not in ATTACHMENT_PROVIDERS:
        return False
    if "multimodal" not in (capabilities or []):
        return False
    if (provider or "").lower() == "openai":
        from .openai_service import OpenAIService

        return not OpenAIService._is_responses_api_only_model(model_id)
    return True


def service_supports_attachments(service: Any, model_name: Optional[str] = None) -> bool:
    if not getattr(service, "SUPPORTS_ATTACHMENTS", False):
        return False
    check = getattr(service, "model_supports_attachments", None)
    if model_name and callable(check):
        return bool(check(model_name))
    return True


def generate_with_attachments(
    service: Any,
    prompt: str,
    attachments: Sequence[Attachment],
    *,
    model_name: str,
    system_prompt: str = "",
    max_tokens: int = 4000,
    temperature: float = 0.0,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Call ``service.generate`` with attachments, refusing unsupported providers.

    Returns the provider's normal response dict (``content``, ``usage``,
    ``metadata.cost_usd``, ``success``/``error``).
    """
    if not attachments:
        raise UnsupportedAttachmentError("no attachments given")
    if not service_supports_attachments(service, model_name):
        raise UnsupportedAttachmentError(
            f"{service.__class__.__name__} / {model_name} cannot read images or PDFs"
        )
    return service.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        model_name=model_name,
        max_tokens=max_tokens,
        temperature=temperature,
        attachments=list(attachments),
        **kwargs,
    )

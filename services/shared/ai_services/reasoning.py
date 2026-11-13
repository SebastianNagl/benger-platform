"""Reasoning text that providers return next to the answer.

Reasoning models hand back their reasoning (a raw trace or a provider-side
summary of it) in a different place per provider. These helpers read it
out of each response shape so a provider service can store it as
``response["reasoning"]``, a field of its own beside ``response["content"]``.
The answer text is never touched here: reasoning is research data kept
next to the answer, never fed into answer parsing, scoring or judges.

Shapes covered (each helper returns ``None`` when the response carries no
reasoning text):

* OpenAI-compatible chat completions (vLLM, SGLang, DeepSeek, DeepInfra,
  xAI): ``choices[0].message.reasoning_content`` or
  ``choices[0].message.reasoning`` (a plain string).
* Anthropic Messages: ``thinking`` content blocks (``block.thinking``).
  ``redacted_thinking`` blocks are encrypted and carry no readable text.
* Google Gemini: content parts flagged ``thought=True`` (thought summaries,
  only returned with ``ThinkingConfig(include_thoughts=True)``).
* OpenAI Responses API: ``reasoning`` output items, their ``summary`` texts
  and, where a model exposes it, their ``content`` reasoning texts.
* Mistral Magistral: ``thinking`` chunks in a list-valued message content.
* Cohere v2: ``thinking`` content blocks (``block.thinking``).
"""

from typing import Any, Iterable, Optional, Tuple

# Separator between several reasoning blocks of one response (Anthropic
# interleaves several thinking blocks, Gemini returns several thought parts).
_BLOCK_SEPARATOR = "\n\n"


def _field(obj: Any, name: str) -> Any:
    """Read ``name`` from a dict or an SDK object alike."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    value = getattr(obj, name, None)
    if value is None:
        # Pydantic SDK models keep undeclared response fields (e.g. the
        # non-standard ``reasoning_content`` on an OpenAI ChatCompletion
        # message) in ``model_extra`` rather than as attributes.
        extra = getattr(obj, "model_extra", None)
        if isinstance(extra, dict):
            value = extra.get(name)
    return value


def join_reasoning(parts: Iterable[Optional[str]]) -> Optional[str]:
    """Join reasoning fragments; ``None`` when nothing readable is left.

    NUL characters are dropped: PostgreSQL text columns reject them, and a
    stray NUL in a reasoning trace must not fail the whole generation write.
    """
    texts = []
    for part in parts:
        if not isinstance(part, str):
            continue
        text = part.replace("\x00", "")
        if text.strip():
            texts.append(text.strip())
    if not texts:
        return None
    return _BLOCK_SEPARATOR.join(texts)


def chat_message_reasoning(message: Any) -> Optional[str]:
    """Reasoning of an OpenAI-compatible chat-completion message.

    ``reasoning_content`` is the DeepSeek/vLLM/xAI name, ``reasoning`` the
    newer vLLM/OpenRouter name; servers that send both send the same text,
    so the first non-empty one wins. Non-string values (e.g. an OpenRouter
    ``reasoning_details`` list) are ignored.
    """
    for name in ("reasoning_content", "reasoning"):
        text = join_reasoning([_field(message, name)])
        if text is not None:
            return text
    return None


def chat_completion_reasoning(result: Any) -> Optional[str]:
    """Reasoning of the first choice of a chat-completion body (dict or SDK)."""
    choices = _field(result, "choices")
    if not choices:
        return None
    return chat_message_reasoning(_field(choices[0], "message"))


def thinking_blocks(content_blocks: Any) -> Optional[str]:
    """Text of the ``thinking`` blocks of an Anthropic Messages or Cohere v2 chat response."""
    if not content_blocks:
        return None
    return join_reasoning(
        _field(block, "thinking")
        for block in content_blocks
        if _field(block, "type") == "thinking"
    )


def google_thoughts(parts: Any) -> Optional[str]:
    """Text of the Gemini content parts flagged as thoughts."""
    if not parts:
        return None
    return join_reasoning(
        _field(part, "text") for part in parts if _field(part, "thought") is True
    )


def responses_api_reasoning(output_items: Any) -> Optional[str]:
    """Reasoning of an OpenAI Responses-API response's ``output`` items.

    Reasoning items carry ``summary`` entries (when a summary was requested)
    and, for models that expose their raw trace, ``content`` entries of type
    ``reasoning_text``. Summaries come first, then raw text.
    """
    if not output_items:
        return None
    parts = []
    for item in output_items:
        if _field(item, "type") != "reasoning":
            continue
        for entry in _field(item, "summary") or []:
            parts.append(_field(entry, "text"))
        for entry in _field(item, "content") or []:
            parts.append(_field(entry, "text"))
    return join_reasoning(parts)


def mistral_content(content: Any) -> Tuple[str, Optional[str]]:
    """Split a Mistral message content into ``(answer, reasoning)``.

    Plain models return a string. Magistral reasoning models return a list
    of chunks: ``text`` chunks make up the answer, ``thinking`` chunks hold
    a list of text chunks with the reasoning.
    """
    if content is None:
        return "", None
    if isinstance(content, str):
        return content, None
    answer_parts = []
    reasoning_parts = []
    for chunk in content:
        if isinstance(chunk, str):
            answer_parts.append(chunk)
            continue
        chunk_type = _field(chunk, "type")
        if chunk_type == "thinking":
            for inner in _field(chunk, "thinking") or []:
                reasoning_parts.append(
                    inner if isinstance(inner, str) else _field(inner, "text")
                )
        elif chunk_type in (None, "text"):
            text = _field(chunk, "text")
            if isinstance(text, str):
                answer_parts.append(text)
    return "".join(answer_parts), join_reasoning(reasoning_parts)

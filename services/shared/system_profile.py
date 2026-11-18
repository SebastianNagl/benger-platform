"""System identity of a generation: model id plus parameter profile.

A system under test is not just a model. The same model with thinking on
and with thinking off answers differently enough to be two systems (a
reasoning arm), and so does the same model at another temperature or
output budget. Every generation therefore records

* ``parameter_profile``: the generation parameters that define the system,
  as they were sent (temperature, max_tokens, top_p and the reasoning knob),
  never the per-trial ones (seed, run index);
* ``parameter_profile_sha256``: SHA-256 of the profile's canonical JSON
  (sorted keys, no whitespace, numbers normalised so ``1`` and ``1.0`` hash
  alike for float parameters);
* ``system_key``: ``"<model_id>@<first 12 hex digits of the hash>"``.

Analysis groups answers by ``system_key``, so a reasoning arm of a model is a
system of its own while its repeats (seeds, runs) stay one system. External
submissions later put their system id in the same place.

The module also owns the reasoning knobs of OpenAI-compatible hosts that are
declared per catalog model (``default_config.reasoning_config``):

* ``reasoning_effort`` (gpt-oss and similar): sent as the top-level
  ``reasoning_effort`` field.
* ``enable_thinking`` (Qwen, Gemma, Nemotron chat templates): stored as
  ``"on"`` / ``"off"`` (the select values the model picker offers) and sent
  as ``chat_template_kwargs: {"enable_thinking": true|false}``.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Mapping, Optional

#: Knobs that change which system answers. Seed and run index are left out
#: on purpose: they vary per trial of one system.
FLOAT_PARAMS = ("temperature", "top_p")
INT_PARAMS = ("max_tokens",)
REASONING_PARAMS = (
    "reasoning_effort",
    "thinking_budget",
    "thinking_token_budget",
    "prompt_mode",
    "enable_thinking",
)
PROFILE_PARAMS = FLOAT_PARAMS + INT_PARAMS + REASONING_PARAMS

#: Length of the hash prefix in a system key. 48 bits keep collisions
#: between the handful of profiles of one model out of reach.
SYSTEM_KEY_HASH_CHARS = 12

#: Reasoning knobs an OpenAI-compatible host (DeepInfra) receives when the
#: catalog model declares them.
OPENAI_COMPATIBLE_REASONING_PARAMS = frozenset({"reasoning_effort", "enable_thinking"})

_THINKING_ON = {"on", "true", "1", "yes"}
_THINKING_OFF = {"off", "false", "0", "no"}


def thinking_flag(value: Any) -> Optional[bool]:
    """``enable_thinking`` value as a bool; None when it is not one."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _THINKING_ON:
            return True
        if v in _THINKING_OFF:
            return False
    return None


def _normalise(key: str, value: Any) -> Any:
    if isinstance(value, bool):
        if key == "enable_thinking":
            return "on" if value else "off"
        return value
    if key in FLOAT_PARAMS and isinstance(value, (int, float)):
        f = float(value)
        if math.isfinite(f):
            return f
        return str(f)
    if key in INT_PARAMS and isinstance(value, float) and value.is_integer():
        return int(value)
    if key == "enable_thinking":
        flag = thinking_flag(value)
        if flag is not None:
            return "on" if flag else "off"
    return value


def parameter_profile(params: Mapping[str, Any]) -> Dict[str, Any]:
    """The system-defining subset of ``params``, normalised.

    Keys outside ``PROFILE_PARAMS`` (seed, provenance, run bookkeeping) and
    keys whose value is None are dropped.
    """
    profile: Dict[str, Any] = {}
    for key in PROFILE_PARAMS:
        if key not in params:
            continue
        value = params[key]
        if value is None:
            continue
        profile[key] = _normalise(key, value)
    return profile


def canonical_json(profile: Mapping[str, Any]) -> str:
    return json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def parameter_profile_sha256(profile: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(profile).encode("utf-8")).hexdigest()


def system_key(model_id: str, profile: Mapping[str, Any]) -> str:
    """``"<model_id>@<hash prefix>"`` for a model and its parameter profile."""
    digest = parameter_profile_sha256(profile)
    return f"{model_id}@{digest[:SYSTEM_KEY_HASH_CHARS]}"


def system_record(
    model_id: str,
    params: Mapping[str, Any],
    *,
    provider: Optional[str] = None,
    provider_model_id: Optional[str] = None,
    response_model: Optional[str] = None,
) -> Dict[str, Any]:
    """The ``system`` block stored with a generation.

    ``provider_model_id`` is the model string sent to the provider (the
    endpoint name for custom models), ``response_model`` the model string the
    provider reported back, when it reports one.
    """
    profile = parameter_profile(params)
    digest = parameter_profile_sha256(profile)
    return {
        "key": f"{model_id}@{digest[:SYSTEM_KEY_HASH_CHARS]}",
        "model_id": model_id,
        "provider": provider,
        "provider_model_id": provider_model_id,
        "response_model": response_model,
        "parameter_profile": profile,
        "parameter_profile_sha256": digest,
    }


def declared_reasoning_config(default_config: Any) -> Optional[Dict[str, Any]]:
    """A model row's ``default_config.reasoning_config`` when well formed."""
    if not isinstance(default_config, dict):
        return None
    rc = default_config.get("reasoning_config")
    if not isinstance(rc, dict) or not isinstance(rc.get("parameter"), str):
        return None
    return rc


def openai_compatible_reasoning_payload(
    reasoning_config: Optional[Mapping[str, Any]], params: Mapping[str, Any]
) -> Dict[str, Any]:
    """Request fields for the model's declared reasoning knob.

    Only the knob the catalog declares for the model is sent, with the run's
    value or, when the run carries none, the declared default, so the value
    the model picker shows is the value the model receives. An undeclared
    knob, a value outside the declared ``values`` or a model without a
    declaration sends nothing.
    """
    if not reasoning_config:
        return {}
    param = reasoning_config.get("parameter")
    if param not in OPENAI_COMPATIBLE_REASONING_PARAMS:
        return {}
    value = params.get(param)
    if value is None:
        value = reasoning_config.get("default")
    if value is None:
        return {}
    if param == "enable_thinking":
        flag = thinking_flag(value)
        if flag is None:
            return {}
        return {"chat_template_kwargs": {"enable_thinking": flag}}
    allowed = reasoning_config.get("values")
    if isinstance(allowed, list) and allowed and value not in allowed:
        return {}
    return {"reasoning_effort": value}


def reasoning_params_sent(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """The reasoning knobs of a request payload, in profile form."""
    sent: Dict[str, Any] = {}
    if "reasoning_effort" in payload:
        sent["reasoning_effort"] = payload["reasoning_effort"]
    ctk = payload.get("chat_template_kwargs")
    if isinstance(ctk, dict) and "enable_thinking" in ctk:
        sent["enable_thinking"] = "on" if ctk["enable_thinking"] else "off"
    return sent

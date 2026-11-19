"""Catalog entries that belong to a feature flag (core 2.75).

``llm_models.yaml`` marks a model with ``default_config.feature_flag`` (the
whole model belongs to the flag: the open-weight experiment panel) and a
reasoning knob with ``default_config.reasoning_config.feature_flag`` (only
the knob does: the ``enable_thinking`` switch of three existing models). The
marks are stored with the row's ``default_config``, so every reader of a
catalog row can apply them without the YAML.

With the flag off for the caller a marked model is not offered and not
generated with, and a marked knob is neither shown nor sent: the catalog
looks and behaves as it did before the entries existed.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

#: The key naming the flag inside ``default_config`` and its ``reasoning_config``.
CATALOG_FLAG_KEY = "feature_flag"


def model_flag(default_config: Any) -> Optional[str]:
    """The flag the whole model belongs to, or None."""
    if isinstance(default_config, Mapping):
        name = default_config.get(CATALOG_FLAG_KEY)
        if isinstance(name, str) and name:
            return name
    return None


def reasoning_flag(default_config: Any) -> Optional[str]:
    """The flag the model's reasoning knob belongs to, or None."""
    if isinstance(default_config, Mapping):
        return model_flag(default_config.get("reasoning_config"))
    return None


def model_offered(default_config: Any, is_on: Callable[[str], bool]) -> bool:
    """Whether the model is offered to a caller for whom ``is_on`` answers."""
    flag = model_flag(default_config)
    return flag is None or bool(is_on(flag))


def reasoning_config_for(reasoning_config: Any, is_on: Callable[[str], bool]) -> Any:
    """``reasoning_config`` as it applies to the caller: None when it
    belongs to a flag that is off."""
    flag = model_flag(reasoning_config)
    if flag is not None and not is_on(flag):
        return None
    return reasoning_config


def served_default_config(default_config: Any, is_on: Callable[[str], bool]) -> Any:
    """``default_config`` as the API serves it: without a reasoning knob
    whose flag is off (the marks themselves stay, they mean nothing to a
    client)."""
    if not isinstance(default_config, Mapping):
        return default_config
    if reasoning_config_for(default_config.get("reasoning_config"), is_on) is None and (
        default_config.get("reasoning_config") is not None
    ):
        served = dict(default_config)
        served.pop("reasoning_config", None)
        return served
    return default_config

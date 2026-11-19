"""Per-structure answer-format options of a prompt structure.

A prompt structure (``generation_config.prompt_structures[key]``) decides
what a generation sends and how its answer is read. Beyond the two prompts
it can carry these options, all optional, with defaults that keep the
behaviour of a structure that does not set them:

``append_schema_instruction`` (default ``true``)
    Append :func:`schema_instruction` (the answer fields of the label config
    as a JSON skeleton) to the user prompt. Off, the user prompt is sent as
    the structure renders it, which a re-run of a fixed prompt design needs.

``structured_output`` (``"auto"`` or ``"off"``, default ``"auto"``)
    ``auto`` asks the provider for structured output with a JSON schema
    derived from the label config when it has answer fields. ``off`` sends
    a plain text request and parses the free-text answer.

``format_retry`` (``{"message": str}``, default none)
    When an answer does not parse, ask once again in the same conversation
    (the first answer as the assistant turn, then ``message`` as the user
    turn). The generation keeps the first answer (``first_response_content``)
    and is marked ``retried``.

``answer_schema`` (default none)
    ``{"fields": {<control name>: {"key": <template>, "values": {<template>:
    <stored value>}}}}``. The answer key (and the choice values) a prompt
    asks for may depend on the task, for example a key named after a party
    of the case. ``{{path}}`` in a template is the task data value at
    ``path`` (dot notation; ``{{path|lower}}`` and ``{{path|upper}}`` change
    the case). The parser reads the rendered key as the control name and
    maps a rendered value onto the stored value; the appended instruction
    and the structured-output schema use the rendered keys too.

``refusal_heuristic`` (``{"pattern": regex, "flags": "i", "window": int}``,
default none)
    Flags a generation as a refusal when the pattern matches the first
    ``window`` characters of the answer (or of the first answer of a format
    retry). The provider's own refusal signal still counts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

#: Upper bound of ``runs_per_task`` for generation. Repeated runs of one
#: task stay one task with many runs; variant designs need dozens of them.
MAX_GENERATION_RUNS_PER_TASK = 100

#: Default and upper bound of ``refusal_heuristic.window`` (characters).
DEFAULT_REFUSAL_WINDOW = 1500
MAX_REFUSAL_WINDOW = 100_000

STRUCTURED_OUTPUT_MODES = ("auto", "off")
_REGEX_FLAGS = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL}

# {{path}} or {{path|filter}}; the path is the dot notation of task data.
_KEY_TEMPLATE = re.compile(
    r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*(?:\|\s*(lower|upper)\s*)?\}\}"
)


@dataclass(frozen=True)
class FormatRetry:
    message: str


@dataclass(frozen=True)
class RefusalHeuristic:
    pattern: str
    flags: str = "i"
    window: int = DEFAULT_REFUSAL_WINDOW

    def compiled(self) -> "re.Pattern[str]":
        value = 0
        for flag in self.flags or "":
            value |= _REGEX_FLAGS[flag]
        return re.compile(self.pattern, value)


@dataclass(frozen=True)
class AnswerFormat:
    append_schema_instruction: bool = True
    structured_output: str = "auto"
    format_retry: Optional[FormatRetry] = None
    refusal_heuristic: Optional[RefusalHeuristic] = None
    answer_schema: Optional[Dict[str, Any]] = None

    def as_record(self) -> Dict[str, Any]:
        """The effective options, for the generation's metadata."""
        return {
            "append_schema_instruction": self.append_schema_instruction,
            "structured_output": self.structured_output,
            "format_retry": (
                {"message": self.format_retry.message} if self.format_retry else None
            ),
            "refusal_heuristic": (
                {
                    "pattern": self.refusal_heuristic.pattern,
                    "flags": self.refusal_heuristic.flags,
                    "window": self.refusal_heuristic.window,
                }
                if self.refusal_heuristic
                else None
            ),
            "answer_schema": self.answer_schema,
        }


# --------------------------------------------------------------------------
# Validation (API write path) and tolerant reading (worker)
# --------------------------------------------------------------------------


def validate_format_retry(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("format_retry must be an object with 'message'")
    unknown = set(value) - {"message"}
    if unknown:
        raise ValueError(f"format_retry has unknown keys: {sorted(unknown)}")
    message = value.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("format_retry.message must be a non-empty string")
    return {"message": message}


def validate_refusal_heuristic(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("refusal_heuristic must be an object with 'pattern'")
    unknown = set(value) - {"pattern", "flags", "window"}
    if unknown:
        raise ValueError(f"refusal_heuristic has unknown keys: {sorted(unknown)}")
    pattern = value.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        raise ValueError(
            "refusal_heuristic.pattern must be a non-empty regular expression"
        )
    flags = value.get("flags", "i")
    if not isinstance(flags, str) or any(f not in _REGEX_FLAGS for f in flags):
        raise ValueError("refusal_heuristic.flags may only contain i, m and s")
    window = value.get("window", DEFAULT_REFUSAL_WINDOW)
    if (
        not isinstance(window, int)
        or isinstance(window, bool)
        or not 1 <= window <= MAX_REFUSAL_WINDOW
    ):
        raise ValueError(
            f"refusal_heuristic.window must be an integer between 1 and {MAX_REFUSAL_WINDOW}"
        )
    heuristic = RefusalHeuristic(pattern=pattern, flags=flags, window=window)
    try:
        heuristic.compiled()
    except re.error as e:
        raise ValueError(
            f"refusal_heuristic.pattern is not a valid regular expression: {e}"
        )
    return {"pattern": pattern, "flags": flags, "window": window}


def validate_answer_schema(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"fields"}:
        raise ValueError("answer_schema must be an object with only 'fields'")
    fields = value.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise ValueError("answer_schema.fields must be a non-empty object")
    for name, spec in fields.items():
        if not isinstance(spec, dict) or set(spec) - {"key", "values"}:
            raise ValueError(
                f"answer_schema.fields.{name} may only have 'key' and 'values'"
            )
        key = spec.get("key")
        if key is not None and (not isinstance(key, str) or not key.strip()):
            raise ValueError(
                f"answer_schema.fields.{name}.key must be a non-empty string"
            )
        values = spec.get("values")
        if values is not None:
            if not isinstance(values, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in values.items()
            ):
                raise ValueError(
                    f"answer_schema.fields.{name}.values must map answer values to stored values"
                )
        if key is None and not values:
            raise ValueError(f"answer_schema.fields.{name} needs a 'key' or 'values'")
    return value


def answer_format(structure: Any) -> AnswerFormat:
    """The answer-format options of a stored structure.

    Tolerant: a structure written before these options existed, or an option
    that does not validate (an imported project), falls back to the default
    of that option instead of failing the generation.
    """
    if not isinstance(structure, dict):
        return AnswerFormat()
    append = structure.get("append_schema_instruction", True)
    mode = structure.get("structured_output", "auto")
    retry = refusal = schema = None
    stored_retry = structure.get("format_retry")
    if isinstance(stored_retry, dict):
        stored_retry = {k: v for k, v in stored_retry.items() if k != "max"}
    try:
        raw = validate_format_retry(stored_retry)
        retry = FormatRetry(**raw) if raw else None
    except ValueError:
        retry = None
    try:
        raw = validate_refusal_heuristic(structure.get("refusal_heuristic"))
        refusal = RefusalHeuristic(**raw) if raw else None
    except ValueError:
        refusal = None
    try:
        schema = validate_answer_schema(structure.get("answer_schema"))
    except ValueError:
        schema = None
    return AnswerFormat(
        append_schema_instruction=append if isinstance(append, bool) else True,
        structured_output=mode if mode in STRUCTURED_OUTPUT_MODES else "auto",
        format_retry=retry,
        refusal_heuristic=refusal,
        answer_schema=schema,
    )


# --------------------------------------------------------------------------
# The appended instruction
# --------------------------------------------------------------------------


#: Label-config control tags whose names the appended instruction lists.
INSTRUCTION_FIELD_TAGS = ("TextArea", "Choices", "Rating", "Number")


def label_config_answer_fields(label_config: Optional[str]) -> List[str]:
    """The answer field names of a label config, in document order: the
    names :func:`schema_instruction` lists (annotation controls only, not
    display tags such as Header or Text). Controls inside a ``<Repeater>``
    are left out: they answer as a list of objects under the block's own
    key (:func:`answer_skeleton`). Empty for a config that does not parse."""
    if not label_config:
        return []
    from xml.etree import ElementTree

    try:
        root = ElementTree.fromstring(label_config)
    except ElementTree.ParseError:
        return []
    repeated = {
        id(child)
        for repeater in root.iter("Repeater")
        for child in repeater.iter()
        if child is not repeater
    }
    return [
        elem.get("name")
        for elem in root.iter()
        if id(elem) not in repeated
        and elem.tag in INSTRUCTION_FIELD_TAGS
        and elem.get("name")
    ]


def answer_skeleton(
    label_config: Optional[str],
    task_data: Any = None,
    answer_keys: Optional[AnswerKeys] = None,
) -> Dict[str, Any]:
    """The JSON skeleton :func:`schema_instruction` shows: each answer field
    of the label config (named by its rendered answer key when the
    structure has an ``answer_schema``) with ``"<your response>"``, and each
    ``<Repeater>`` block as one example object per item of ``task_data``
    (one object when no task is given)."""
    from label_config_repeater import repeater_answer_example, repeater_blocks

    skeleton: Dict[str, Any] = {}
    for name in label_config_answer_fields(label_config):
        key = answer_keys.answer_key(name) if answer_keys is not None else name
        skeleton[key] = "<your response>"
    if label_config:
        for block in repeater_blocks(label_config):
            if block.controls:
                skeleton[block.answer_property] = repeater_answer_example(
                    block, task_data
                )
    return skeleton


def schema_instruction_preview(
    structure: Any, label_config: Optional[str]
) -> Optional[str]:
    """The text a generation with ``structure`` appends to the user prompt,
    or None when it appends nothing. Answer keys of an ``answer_schema`` are
    rendered per task and a ``<Repeater>`` block lists one object per item
    of the task; the preview names the label-config fields and shows one
    item."""
    if not answer_format(structure).append_schema_instruction:
        return None
    skeleton = answer_skeleton(label_config)
    return schema_instruction(skeleton) if skeleton else None


def schema_instruction(output_schema: Union[Dict[str, Any], List[str]]) -> str:
    """The block appended to the user prompt when
    ``append_schema_instruction`` is on and the label config has answer
    fields: ``output_schema`` (:func:`answer_skeleton`, or a list of field
    names, each shown as ``"<your response>"``) as JSON. The project page
    previews this exact text."""
    if not isinstance(output_schema, dict):
        output_schema = {name: "<your response>" for name in output_schema}
    return (
        "\n\n---\n"
        "IMPORTANT: Respond ONLY with valid JSON using these exact field names:\n"
        f"```json\n{json.dumps(output_schema, indent=2)}\n```"
    )


# --------------------------------------------------------------------------
# Answer keys from task data
# --------------------------------------------------------------------------


def _lookup(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def render_key_template(
    template: str,
    task_data: Dict[str, Any],
    is_sensitive: Optional[Callable[[str], bool]] = None,
) -> str:
    """Fill ``{{path}}`` placeholders from task data.

    Raises ValueError for a missing value or a sensitive path, so a key that
    cannot be built fails the trial instead of asking for a wrong key.
    """

    def _replace(match: "re.Match[str]") -> str:
        path, case = match.group(1), match.group(2)
        if is_sensitive is not None and is_sensitive(path):
            raise ValueError(
                f"answer_schema may not reference the sensitive field '{path}'"
            )
        value = _lookup(task_data, path)
        if value is None or isinstance(value, (dict, list)):
            raise ValueError(
                f"answer_schema references '{path}', which the task does not hold"
            )
        text = str(value)
        if case == "lower":
            text = text.lower()
        elif case == "upper":
            text = text.upper()
        return text

    return _KEY_TEMPLATE.sub(_replace, template)


@dataclass
class AnswerKeys:
    """An ``answer_schema`` rendered for one task."""

    #: answer key -> control name
    key_to_field: Dict[str, str] = field(default_factory=dict)
    #: control name -> {answer value -> stored value}
    value_maps: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def answer_key(self, control: str) -> str:
        for key, target in self.key_to_field.items():
            if target == control:
                return key
        return control

    def map_answer(
        self, parsed: Any
    ) -> Tuple[Any, Dict[str, str], Dict[str, Dict[str, Any]]]:
        """Rename rendered keys to control names and map rendered values.

        Returns ``(data, mapped_keys, mapped_values)``; a control name the
        answer already uses exactly keeps its value.
        """
        if not isinstance(parsed, dict):
            return parsed, {}, {}
        result: Dict[str, Any] = {}
        mapped_keys: Dict[str, str] = {}
        taken = {
            k
            for k in parsed
            if k in self.key_to_field.values() and k not in self.key_to_field
        }
        for key, value in parsed.items():
            target = self.key_to_field.get(key) if isinstance(key, str) else None
            if target is not None and target != key and target not in taken:
                taken.add(target)
                result[target] = value
                mapped_keys[key] = target
            else:
                result[key] = value
        mapped_values: Dict[str, Dict[str, Any]] = {}
        for control, value_map in self.value_maps.items():
            value = result.get(control)
            if not isinstance(value, str):
                continue
            new = value_map.get(value)
            if new is None:
                folded = {k.strip().casefold(): v for k, v in value_map.items()}
                new = folded.get(value.strip().casefold())
            if new is not None and new != value:
                result[control] = new
                mapped_values[control] = {value: new}
        return result, mapped_keys, mapped_values

    def rename_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """A JSON schema over control names, re-keyed to the answer keys
        (and choice enums to the answer values) the prompt asks for."""
        if not isinstance(schema, dict) or not isinstance(
            schema.get("properties"), dict
        ):
            return schema
        renamed = dict(schema)
        properties: Dict[str, Any] = {}
        for control, prop in schema["properties"].items():
            prop = dict(prop) if isinstance(prop, dict) else prop
            value_map = self.value_maps.get(control)
            if (
                value_map
                and isinstance(prop, dict)
                and isinstance(prop.get("enum"), list)
            ):
                targeted = set(value_map.values())
                prop["enum"] = list(value_map.keys()) + [
                    v for v in prop["enum"] if v not in targeted and v not in value_map
                ]
            properties[self.answer_key(control)] = prop
        renamed["properties"] = properties
        if isinstance(schema.get("required"), list):
            renamed["required"] = [self.answer_key(c) for c in schema["required"]]
        return renamed


def render_answer_schema(
    answer_schema: Optional[Dict[str, Any]],
    task_data: Dict[str, Any],
    is_sensitive: Optional[Callable[[str], bool]] = None,
) -> Optional[AnswerKeys]:
    """Render an ``answer_schema`` for one task; None when there is none."""
    if not answer_schema:
        return None
    keys = AnswerKeys()
    for control, spec in (answer_schema.get("fields") or {}).items():
        if spec.get("key"):
            rendered = render_key_template(spec["key"], task_data, is_sensitive)
            if rendered in keys.key_to_field:
                raise ValueError(
                    f"answer_schema renders the key '{rendered}' for two fields of this task"
                )
            keys.key_to_field[rendered] = control
        if spec.get("values"):
            keys.value_maps[control] = {
                render_key_template(answer, task_data, is_sensitive): stored
                for answer, stored in spec["values"].items()
            }
    return keys


# --------------------------------------------------------------------------
# Refusal heuristic
# --------------------------------------------------------------------------


def refusal_matches(
    heuristic: Optional[RefusalHeuristic], *texts: Optional[str]
) -> bool:
    """Whether the heuristic matches the opening of any of ``texts``."""
    if heuristic is None:
        return False
    pattern = heuristic.compiled()
    return any(bool(pattern.search(text[: heuristic.window])) for text in texts if text)

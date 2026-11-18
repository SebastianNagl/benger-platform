"""Per-slot label configs: Label Studio ``<Repeater>`` sugar, indexed slot
names and array answers.

A task often asks for the same set of answers once per item: per case of a
docket, per person in a judgment, per claim of a pleading. Label Studio's
results carry one result per control name, so per-item answers are stored
under flat *indexed* control names (``risk_0``, ``risk_1``, ... or hand-written
``credibility_1``, ``credibility_2``). Label Studio offers ``<Repeater>`` to
write such a block once::

    <Repeater on="$cases" indexFlag="{{idx}}" mode="pagination">
      <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
      <Number name="risk_{{idx}}" toName="case_{{idx}}" min="0" max="100"/>
    </Repeater>

Label Studio expands the tag while parsing the config against a task
(``web/libs/editor/src/core/Tree.tsx``): its children are repeated once per
element of the array the ``on`` binding names, the index flag (default
``{{idx}}``) is replaced by the 0-based element index in every attribute of
every repeated element, and the Repeater itself becomes a ``<View>``. Results
are ordinary results under the expanded names. This module reproduces that
expansion exactly, so BenGER and Label Studio store the same results.

Label Studio marks the tag as due for deprecation and has removed it from its
docs, so BenGER treats it as authoring sugar only: the stored results and the
config offered for export to Label Studio use the expanded, plain indexed
names, which every Label Studio version reads.

On top of the expansion this module provides what generation needs:

- :func:`repeater_blocks` describes each Repeater: the array it iterates, its
  controls and the key each control takes inside one answer object.
- :func:`repeater_answer_schema` is the JSON schema of the array answer a
  Repeater block asks for (one object per item), used for structured output.
- :func:`map_array_answers` maps such an array answer onto the indexed control
  names, by an item key the answer names (``answerKey``) or by position.
- :func:`derive_slot_map` maps each slot index to its control names, from the
  Repeater or from declared name patterns for hand-written indexed names.

Two attributes on ``<Repeater>`` are BenGER extensions; Label Studio ignores
unknown attributes, and the expanded export drops them:

- ``answerKey``: the key in each answer object that identifies its item
  (for example ``case`` when the prompt numbers the items "Case 1", "Case 2").
  Without it, answer objects map to items by position.
- ``answerKeyStart``: the ``answerKey`` value of the first item (default 1,
  since prompts number items from 1 while Label Studio indexes from 0).

Rules the validator enforces (:func:`repeater_errors`): ``on`` must be a
``$`` binding; Repeaters do not nest; every named control inside a Repeater
carries the index flag in its name, exactly once per attribute (Label Studio
replaces only the first occurrence); no expanded name can equal another
control's name or another template's expansion; and the answer keys of one
block are unique and differ from ``answerKey``.

Pure module (``xml.etree``, ``re``, ``copy`` only): the API, the workers and
the schema generator import it.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

REPEATER_TAG = "Repeater"
DEFAULT_INDEX_FLAG = "{{idx}}"
DEFAULT_ANSWER_KEY_START = 1

# Attributes the Repeater itself understands; the expanded <View> keeps the
# others (style, className, ...), as Label Studio's expanded view does.
_REPEATER_ATTRIBUTES = {"on", "indexflag", "mode", "answerkey", "answerkeystart"}

# Control tags whose results carry an answer, in the response parser's sense.
ANSWER_CONTROL_TAGS = (
    "Choices",
    "TextArea",
    "Rating",
    "Number",
    "Labels",
    "Gliederung",
    "Loesung",
)

# The placeholder of a hand-written slot-name pattern (``credibility_{idx}``).
PATTERN_INDEX_PLACEHOLDER = "{idx}"

_SEPARATORS = "_-."


# --------------------------------------------------------------------------
# Data paths (``$cases``, ``$doc.cases``, ``$cases[0].text``)
# --------------------------------------------------------------------------


def _path_segments(path: str) -> List[str]:
    """``doc.cases[2].text`` -> ``["doc", "cases", "2", "text"]``."""
    normalised = re.sub(r"\[([^\]]*)\]", r".\1", path)
    return [part for part in normalised.split(".") if part != ""]


def resolve_data_path(task_data: Any, binding: Optional[str]) -> Any:
    """The value a ``$`` binding names in ``task_data``, or None.

    Follows dots and ``[n]`` indexes like the lodash ``get`` Label Studio uses
    (``parseValue`` in ``web/libs/editor/src/utils/data.js``).
    """
    if not binding or not isinstance(binding, str) or not binding.startswith("$"):
        return None
    current = task_data
    for part in _path_segments(binding[1:]):
        if isinstance(current, Mapping):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
            except ValueError:
                return None
            if not 0 <= index < len(current):
                return None
            current = current[index]
        else:
            return None
    return current


# --------------------------------------------------------------------------
# Block description
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RepeaterControl:
    """One answer control inside a Repeater."""

    template: str  # name with the index flag, e.g. "risk_{{idx}}"
    tag: str  # "Number", "Choices", ...
    item_key: str  # key inside one answer object, e.g. "risk"
    element: ET.Element = field(compare=False, repr=False)

    def name_for(self, index: int, index_flag: str) -> str:
        return self.template.replace(index_flag, str(index))


@dataclass(frozen=True)
class RepeaterBlock:
    """A ``<Repeater>`` of a label config."""

    on: str  # "$cases"
    index_flag: str
    mode: Optional[str]
    answer_key: Optional[str]
    answer_key_start: int
    controls: Tuple[RepeaterControl, ...]

    @property
    def data_path(self) -> str:
        """``$doc.cases`` -> ``doc.cases``."""
        return self.on[1:] if self.on.startswith("$") else self.on

    @property
    def answer_property(self) -> str:
        """The key of this block's array in an answer object: the last segment
        of the ``on`` path (``$doc.cases`` -> ``cases``)."""
        segments = _path_segments(self.data_path)
        return segments[-1] if segments else self.data_path

    def items(self, task_data: Any) -> List[Any]:
        """The array this block repeats over in ``task_data`` (empty when the
        binding names no list, as Label Studio repeats nothing then)."""
        value = resolve_data_path(task_data, self.on)
        return list(value) if isinstance(value, list) else []

    def item_count(self, task_data: Any) -> int:
        return len(self.items(task_data))


def item_key_for(template: str, index_flag: str) -> str:
    """The answer key of a control template: its name without the index flag
    and one separator next to it.

    ``risk_{{idx}}`` -> ``risk``; ``{{idx}}_risk`` -> ``risk``;
    ``person_{{idx}}_credibility`` -> ``person_credibility``;
    ``risk{{idx}}`` -> ``risk``.
    """
    position = template.find(index_flag)
    if position < 0:
        return template
    before = template[:position]
    after = template[position + len(index_flag):]
    if before and before[-1] in _SEPARATORS:
        before = before[:-1]
    elif after and after[0] in _SEPARATORS:
        after = after[1:]
    return before + after


def _parse(label_config: Optional[str]) -> Optional[ET.Element]:
    if not label_config or not isinstance(label_config, str):
        return None
    try:
        return ET.fromstring(label_config)
    except ET.ParseError:
        return None


def has_repeater(label_config: Optional[str]) -> bool:
    """Whether the config contains a ``<Repeater>`` (cheap pre-check first)."""
    if not label_config or REPEATER_TAG not in label_config:
        return False
    root = _parse(label_config)
    return root is not None and any(elem.tag == REPEATER_TAG for elem in root.iter())


def repeater_attribute(element: ET.Element, name: str) -> Optional[str]:
    """A Repeater attribute, matched case-insensitively: Label Studio
    lower-cases attribute names before reading them (``attrsToProps``)."""
    if name in element.attrib:
        return element.attrib[name]
    lowered = name.lower()
    for key, value in element.attrib.items():
        if key.lower() == lowered:
            return value
    return None


def index_flag_of(element: ET.Element) -> str:
    """The index flag of a ``<Repeater>`` element (``{{idx}}`` by default)."""
    return repeater_attribute(element, "indexFlag") or DEFAULT_INDEX_FLAG


def _answer_key_start(element: ET.Element) -> int:
    raw = repeater_attribute(element, "answerKeyStart")
    if raw is None or raw.strip() == "":
        return DEFAULT_ANSWER_KEY_START
    return int(raw)


def _block_of(element: ET.Element) -> RepeaterBlock:
    index_flag = index_flag_of(element)
    controls = []
    for child in element.iter():
        if child is element or child.tag not in ANSWER_CONTROL_TAGS:
            continue
        name = child.get("name")
        if not name:
            continue
        controls.append(
            RepeaterControl(
                template=name,
                tag=child.tag,
                item_key=item_key_for(name, index_flag),
                element=child,
            )
        )
    try:
        start = _answer_key_start(element)
    except ValueError:
        start = DEFAULT_ANSWER_KEY_START
    return RepeaterBlock(
        on=repeater_attribute(element, "on") or "",
        index_flag=index_flag,
        mode=repeater_attribute(element, "mode"),
        answer_key=repeater_attribute(element, "answerKey") or None,
        answer_key_start=start,
        controls=tuple(controls),
    )


def repeater_blocks(label_config: Optional[str]) -> List[RepeaterBlock]:
    """Every ``<Repeater>`` of the config, in document order."""
    if not label_config or REPEATER_TAG not in label_config:
        return []
    root = _parse(label_config)
    if root is None:
        return []
    return [_block_of(elem) for elem in root.iter() if elem.tag == REPEATER_TAG]


def repeater_control_names(label_config: Optional[str]) -> set:
    """The (template) names of every control inside a Repeater."""
    names = set()
    root = _parse(label_config) if label_config and REPEATER_TAG in label_config else None
    if root is None:
        return names
    for elem in root.iter():
        if elem.tag != REPEATER_TAG:
            continue
        for child in elem.iter():
            if child is not elem and child.get("name"):
                names.add(child.get("name"))
    return names


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def repeater_errors(root: ET.Element) -> List[str]:
    """Structural errors of every Repeater under ``root`` (empty when fine)."""
    errors: List[str] = []
    for element in root.iter():
        if element.tag != REPEATER_TAG:
            continue
        on = repeater_attribute(element, "on")
        if not on or not on.startswith("$") or len(on) < 2:
            errors.append(
                "<Repeater> requires an 'on' attribute binding a task data array, "
                "e.g. on=\"$items\""
            )
        index_flag = index_flag_of(element)
        if not index_flag.strip():
            errors.append("<Repeater> indexFlag cannot be empty")
            continue
        if element.get("name"):
            errors.append(
                "<Repeater> takes no 'name' attribute; name the controls inside it"
            )
        if repeater_attribute(element, "answerKeyStart") is not None:
            try:
                _answer_key_start(element)
            except ValueError:
                errors.append(
                    f"<Repeater> answerKeyStart must be an integer, got "
                    f"'{repeater_attribute(element, 'answerKeyStart')}'"
                )
        answer_key = repeater_attribute(element, "answerKey")
        if answer_key is not None and not answer_key.strip():
            errors.append("<Repeater> answerKey cannot be empty")

        item_keys: Dict[str, str] = {}
        for child in element.iter():
            if child is element:
                continue
            if child.tag == REPEATER_TAG:
                errors.append("Nested <Repeater> tags are not supported")
                continue
            for attr_name, attr_value in child.attrib.items():
                if attr_value.count(index_flag) > 1:
                    errors.append(
                        f"Attribute '{attr_name}' of <{child.tag}> inside a <Repeater> "
                        f"uses the index flag '{index_flag}' more than once"
                    )
            name = child.get("name")
            if name and index_flag not in name:
                errors.append(
                    f"Control '{name}' inside a <Repeater> must contain the index flag "
                    f"'{index_flag}' in its name, or its expanded names collide"
                )
                continue
            if name and child.tag in ANSWER_CONTROL_TAGS:
                key = item_key_for(name, index_flag)
                if not key:
                    errors.append(
                        f"Control '{name}' inside a <Repeater> needs a name besides "
                        f"the index flag"
                    )
                elif key in item_keys:
                    errors.append(
                        f"Controls '{item_keys[key]}' and '{name}' inside a <Repeater> "
                        f"take the same answer key '{key}'"
                    )
                elif answer_key and key == answer_key:
                    errors.append(
                        f"Control '{name}' takes the answer key '{key}', which the "
                        f"<Repeater> uses as its answerKey"
                    )
                else:
                    item_keys[key] = name

    # Each block's array answer sits under the last segment of its binding;
    # it must not clash with another block or with a control outside blocks.
    repeaters = list(root.iter(REPEATER_TAG))
    if repeaters:
        inside = {id(c) for r in repeaters for c in r.iter() if c is not r}
        flat_names = {
            elem.get("name")
            for elem in root.iter()
            if id(elem) not in inside and elem.tag in ANSWER_CONTROL_TAGS and elem.get("name")
        }
        seen_properties: set = set()
        for repeater in repeaters:
            on = repeater_attribute(repeater, "on") or ""
            segments = _path_segments(on[1:]) if on.startswith("$") else []
            if not segments:
                continue
            prop = segments[-1]
            if prop in flat_names:
                errors.append(
                    f"The <Repeater> on '{on}' answers under '{prop}', which is also "
                    f"the name of a control"
                )
            if prop in seen_properties:
                errors.append(f"Two <Repeater> blocks answer under the same key '{prop}'")
            seen_properties.add(prop)
        errors.extend(_expanded_name_collisions(root, repeaters, inside))
    return errors


_DIGITS = "0123456789"


def _templates_collide(first: Tuple[str, str], second: Tuple[str, str]) -> bool:
    """Whether two control templates (``(name, index flag)``) expand to a
    common name for some pair of 0-based indexes."""
    (name_a, flag_a), (name_b, flag_b) = first, second
    before_a, after_a = name_a.split(flag_a, 1)
    before_b, after_b = name_b.split(flag_b, 1)
    for width_a in range(1, len(name_a) + len(name_b) + 3):
        total = len(before_a) + width_a + len(after_a)
        width_b = total - len(before_b) - len(after_b)
        if width_b < 1:
            continue
        side_a = list(before_a) + [None] * width_a + list(after_a)
        side_b = list(before_b) + [None] * width_b + list(after_b)
        chars: List[Optional[str]] = []
        for char_a, char_b in zip(side_a, side_b):
            if char_a is None and char_b is None:
                chars.append(None)
            elif char_a is None or char_b is None:
                literal = char_a if char_b is None else char_b
                if literal not in _DIGITS:
                    break
                chars.append(literal)
            elif char_a != char_b:
                break
            else:
                chars.append(char_a)
        else:
            # An index has no leading zero: a free digit can always be 1.
            if not any(
                width > 1 and chars[start] == "0"
                for start, width in ((len(before_a), width_a), (len(before_b), width_b))
            ):
                return True
    return False


def _template_matches(template: Tuple[str, str], name: str) -> bool:
    """Whether a control template expands to ``name`` for some index."""
    before, after = template[0].split(template[1], 1)
    pattern = re.escape(before) + "(0|[1-9][0-9]*)" + re.escape(after)
    return re.fullmatch(pattern, name) is not None


def _expanded_name_collisions(
    root: ET.Element, repeaters: List[ET.Element], inside: set
) -> List[str]:
    """Names that only collide once the Repeaters are expanded: a template
    against a name outside every Repeater, or two templates against each
    other (identical templates are left to the duplicate-name check)."""
    errors: List[str] = []
    flat_names = [
        elem.get("name") for elem in root.iter() if id(elem) not in inside and elem.get("name")
    ]
    templates: List[Tuple[str, str]] = []
    for repeater in repeaters:
        index_flag = index_flag_of(repeater)
        if not index_flag.strip():
            continue
        for child in repeater.iter():
            name = child.get("name")
            if child is not repeater and name and name.count(index_flag) == 1:
                templates.append((name, index_flag))
    for template in templates:
        for name in flat_names:
            if _template_matches(template, name):
                errors.append(
                    f"Control '{template[0]}' inside a <Repeater> expands to '{name}', "
                    f"which is also the name of a control outside it"
                )
    for position, first in enumerate(templates):
        for second in templates[position + 1:]:
            if first[0] != second[0] and _templates_collide(first, second):
                errors.append(
                    f"Controls '{first[0]}' and '{second[0]}' inside <Repeater> blocks "
                    f"can expand to the same name"
                )
    return errors


def substitute_index_flag(value: str, index_flag: str, index: Any) -> str:
    """``value`` with the index flag replaced by ``index`` (validation of a
    template name uses index 0)."""
    return value.replace(index_flag, str(index))


# --------------------------------------------------------------------------
# Expansion (Label Studio's Tree.tsx semantics)
# --------------------------------------------------------------------------


def _substitute_attributes(element: ET.Element, index_flag: str, index: int) -> None:
    for node in element.iter():
        for attr_name, attr_value in list(node.attrib.items()):
            if index_flag in attr_value:
                node.set(attr_name, attr_value.replace(index_flag, str(index)))


def _expand_element(element: ET.Element, count_for) -> None:
    for position, child in enumerate(list(element)):
        if child.tag != REPEATER_TAG:
            _expand_element(child, count_for)
            continue
        block = _block_of(child)
        view = ET.Element(
            "View",
            {k: v for k, v in child.attrib.items() if k.lower() not in _REPEATER_ATTRIBUTES},
        )
        view.text = child.text
        view.tail = child.tail
        for index in range(count_for(block)):
            item_view = ET.SubElement(view, "View")
            item_view.text = child.text
            for grandchild in child:
                clone = copy.deepcopy(grandchild)
                _substitute_attributes(clone, block.index_flag, index)
                item_view.append(clone)
        element.remove(child)
        element.insert(position, view)


def _expand(label_config: str, count_for) -> str:
    if not has_repeater(label_config):
        return label_config
    root = ET.fromstring(label_config)
    if root.tag == REPEATER_TAG:
        wrapper = ET.Element("View")
        wrapper.append(root)
        _expand_element(wrapper, count_for)
        root = wrapper[0]
    else:
        _expand_element(root, count_for)
    return ET.tostring(root, encoding="unicode")


def expand_repeaters(label_config: Optional[str], task_data: Any) -> Optional[str]:
    """The config as Label Studio renders it for ``task_data``.

    Each ``<Repeater>`` becomes a ``<View>`` holding one ``<View>`` per element
    of its array, with the index flag replaced by the 0-based element index in
    every attribute. A config without a Repeater is returned unchanged (same
    string), so existing configs never change.
    """
    if label_config is None:
        return None
    return _expand(label_config, lambda block: block.item_count(task_data))


def expand_repeaters_with_counts(
    label_config: Optional[str], counts: Mapping[str, int]
) -> Optional[str]:
    """The config with each Repeater expanded to ``counts[on]`` items (0 when
    its binding is missing), for counts computed elsewhere, e.g. in SQL."""
    if label_config is None:
        return None
    return _expand(label_config, lambda block: max(int(counts.get(block.on, 0) or 0), 0))


def data_path_segments(binding: str) -> List[str]:
    """The path segments of a ``$`` binding (``$doc.cases`` -> ``["doc", "cases"]``)."""
    return _path_segments(binding[1:] if binding.startswith("$") else binding)


# --------------------------------------------------------------------------
# Array answers
# --------------------------------------------------------------------------


class ArrayAnswerError(ValueError):
    """An array answer that does not fit its Repeater block."""


def _as_item_number(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"\s*-?\d+\s*", value):
        return int(value)
    return None


def map_array_answers(
    answer: Any, blocks: Sequence[RepeaterBlock], task_data: Any
) -> Any:
    """Map array answers onto the indexed control names of their blocks.

    ``answer`` is the decoded JSON answer. A top-level list is read as the
    array of the config's only Repeater block. In an object, each block's
    array sits under its :attr:`RepeaterBlock.answer_property`; it is replaced
    by flat ``{expanded control name: value}`` entries, and every other key
    is kept as it is (so flat indexed names keep working too).

    Raises :class:`ArrayAnswerError` when an array does not fit: not a list of
    objects, a different number of objects than the task has items, or an
    ``answerKey`` value that is not an item number of this task or repeats.
    """
    if not blocks:
        return answer
    if isinstance(answer, list):
        if len(blocks) != 1:
            raise ArrayAnswerError(
                "A top-level JSON list is ambiguous for a label config with "
                f"{len(blocks)} Repeater blocks; answer with an object keyed by "
                + ", ".join(f"'{b.answer_property}'" for b in blocks)
            )
        answer = {blocks[0].answer_property: answer}
    if not isinstance(answer, dict):
        return answer

    result = dict(answer)
    for block in blocks:
        if block.answer_property not in result:
            continue
        items = result.pop(block.answer_property)
        if not isinstance(items, list):
            raise ArrayAnswerError(
                f"'{block.answer_property}' must be a JSON list with one object per item"
            )
        # Without the task's data the item count is the answer's own.
        count = block.item_count(task_data) if task_data is not None else len(items)
        if len(items) != count:
            raise ArrayAnswerError(
                f"'{block.answer_property}' has {len(items)} objects, the task has "
                f"{count} items"
            )
        seen: Dict[int, int] = {}
        for position, item in enumerate(items):
            if not isinstance(item, dict):
                raise ArrayAnswerError(
                    f"'{block.answer_property}' item {position + 1} is not a JSON object"
                )
            index = position
            if block.answer_key and block.answer_key in item:
                number = _as_item_number(item[block.answer_key])
                index = -1 if number is None else number - block.answer_key_start
                if not 0 <= index < count:
                    raise ArrayAnswerError(
                        f"'{block.answer_property}' item {position + 1}: "
                        f"'{block.answer_key}' is {item[block.answer_key]!r}, expected "
                        f"{block.answer_key_start} to {block.answer_key_start + count - 1}"
                    )
            if index in seen:
                raise ArrayAnswerError(
                    f"'{block.answer_property}' items {seen[index] + 1} and {position + 1} "
                    f"answer the same item"
                )
            seen[index] = position
            for control in block.controls:
                if control.item_key in item:
                    result[control.name_for(index, block.index_flag)] = item[control.item_key]
    return result


def repeater_answer_schema(
    block: RepeaterBlock,
    control_schema,
    task_data: Any = None,
    strict_mode: bool = True,
) -> Dict[str, Any]:
    """The JSON schema of one block's array answer.

    ``control_schema(element)`` returns ``(schema, required)`` for a control
    element, or None for one without an answer schema, so each caller keeps
    its own type mapping. With ``task_data`` the array length is pinned to the
    task's item count.
    """
    properties: Dict[str, Any] = {}
    required: List[str] = []
    count = block.item_count(task_data) if task_data is not None else None
    if block.answer_key:
        key_schema: Dict[str, Any] = {
            "type": "integer",
            "description": f"Item number (first item: {block.answer_key_start})",
        }
        if count:
            key_schema["minimum"] = block.answer_key_start
            key_schema["maximum"] = block.answer_key_start + count - 1
        properties[block.answer_key] = key_schema
        required.append(block.answer_key)
    for control in block.controls:
        described = control_schema(control.element)
        if described is None:
            continue
        schema, is_required = described
        properties[control.item_key] = schema
        if is_required or strict_mode:
            required.append(control.item_key)
    item_schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if strict_mode:
        item_schema["required"] = list(properties)
        item_schema["additionalProperties"] = False
    elif required:
        item_schema["required"] = required
    array_schema: Dict[str, Any] = {"type": "array", "items": item_schema}
    if count is not None:
        array_schema["minItems"] = count
        array_schema["maxItems"] = count
    return array_schema


def repeater_answer_example(block: RepeaterBlock, task_data: Any = None) -> List[Dict[str, Any]]:
    """An example array answer for prompt instructions: one object per item
    of the task (one object when the item count is unknown)."""
    count = block.item_count(task_data) if task_data is not None else 1
    example = []
    for position in range(max(count, 1)):
        item: Dict[str, Any] = {}
        if block.answer_key:
            item[block.answer_key] = block.answer_key_start + position
        for control in block.controls:
            item[control.item_key] = "<your response>"
        example.append(item)
    return example


# --------------------------------------------------------------------------
# Slot maps
# --------------------------------------------------------------------------


def _pattern_regex(pattern: str) -> Tuple[re.Pattern, str]:
    if pattern.count(PATTERN_INDEX_PLACEHOLDER) != 1:
        raise ValueError(
            f"Slot name pattern '{pattern}' must contain '{PATTERN_INDEX_PLACEHOLDER}' exactly once"
        )
    before, after = pattern.split(PATTERN_INDEX_PLACEHOLDER)
    regex = re.compile(re.escape(before) + r"(\d+)" + re.escape(after) + r"\Z")
    return regex, item_key_for(pattern, PATTERN_INDEX_PLACEHOLDER)


def _answer_control_names(label_config: Optional[str]) -> List[str]:
    root = _parse(label_config)
    if root is None:
        return []
    return [
        elem.get("name")
        for elem in root.iter()
        if elem.tag in ANSWER_CONTROL_TAGS and elem.get("name")
    ]


def derive_slot_map(
    label_config: Optional[str],
    task_data: Any = None,
    patterns: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Map each slot index to the control names that hold its answers.

    Returns one group per Repeater block and, when ``patterns`` are given,
    one group for the hand-written names they match::

        [{"source": "repeater", "on": "$cases", "index_base": 0,
          "slots": [{"index": 0, "controls": {"risk": "risk_0", ...}}, ...]},
         {"source": "pattern", "patterns": ["credibility_{idx}"], "index_base": None,
          "slots": [{"index": 1, "controls": {"credibility": "credibility_1"}}, ...]}]

    A Repeater group needs ``task_data`` for its item count (without it the
    group has no slots). Its ``index`` is Label Studio's 0-based index; the
    item number an answer uses is ``index + answer_key_start``. A pattern
    group's ``index`` is the number in the control name, as written.
    """
    groups: List[Dict[str, Any]] = []
    for block in repeater_blocks(label_config):
        count = block.item_count(task_data) if task_data is not None else 0
        groups.append(
            {
                "source": "repeater",
                "on": block.on,
                "index_flag": block.index_flag,
                "index_base": 0,
                "answer_key": block.answer_key,
                "answer_key_start": block.answer_key_start,
                "slots": [
                    {
                        "index": index,
                        "controls": {
                            control.item_key: control.name_for(index, block.index_flag)
                            for control in block.controls
                        },
                    }
                    for index in range(count)
                ],
            }
        )
    if patterns:
        compiled = [_pattern_regex(pattern) for pattern in patterns]
        expanded = (
            expand_repeaters(label_config, task_data) if task_data is not None else label_config
        )
        slots: Dict[int, Dict[str, str]] = {}
        for name in _answer_control_names(expanded):
            for regex, key in compiled:
                match = regex.match(name)
                if match:
                    slots.setdefault(int(match.group(1)), {})[key] = name
                    break
        groups.append(
            {
                "source": "pattern",
                "patterns": list(patterns),
                "index_base": None,
                "slots": [
                    {"index": index, "controls": slots[index]} for index in sorted(slots)
                ],
            }
        )
    return groups


# --------------------------------------------------------------------------
# Result targets
# --------------------------------------------------------------------------


def control_targets(label_config: Optional[str]) -> Tuple[Dict[str, str], set]:
    """``({control name: its toName}, {object names})`` of a config.

    Label Studio attaches a result to its object through ``to_name``; a result
    without one does not render. Expand a Repeater config first so the names
    are the task's indexed ones.
    """
    root = _parse(label_config)
    if root is None:
        return {}, set()
    targets: Dict[str, str] = {}
    objects: set = set()
    for elem in root.iter():
        name = elem.get("name")
        if not name:
            continue
        to_name = elem.get("toName")
        if to_name:
            targets[name] = to_name
        else:
            objects.add(name)
    return targets, objects


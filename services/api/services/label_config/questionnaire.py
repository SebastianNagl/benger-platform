"""Post-annotation questionnaire configs (Issue #1208).

A questionnaire is written in the label-config XML the annotation interface
uses and rendered by the same component, so it is validated by
``LabelConfigValidator``. This module adds what only a questionnaire needs:
a check on save that it asks at least one question, the ``required="true"``
check of a submitted response, and the hash that ties each response to the
exact config it answered.
"""

import hashlib
import re
from typing import Any, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET

from services.label_config.validator import LabelConfigValidator

# Tags that take an answer: the controls the questionnaire modal renders,
# which must match the 'control' category of the frontend tag registry
# (frontend/src/lib/labelConfig/registry.ts). A tag outside it shows no
# field, so it neither counts as a question nor can be required.
# ``required="true"`` on any other tag (an object tag such as
# <Text value="$x" required="true"/>) marks a task data field as required,
# not a question, and is left to the label-config data checks.
ANSWER_TAGS = frozenset({'Choices', 'TextArea', 'Rating', 'Likert', 'Number', 'Labels'})


def _parse(config: str) -> Optional[ET.Element]:
    try:
        return ET.fromstring(re.sub(r'<\?xml[^>]+\?>', '', config).strip())
    except ET.ParseError:
        return None


def _answer_elements(root: ET.Element) -> Iterable[ET.Element]:
    for element in root.iter():
        if element.tag in ANSWER_TAGS and element.get('name'):
            yield element


def validate_questionnaire_config(config: str) -> Tuple[bool, List[str]]:
    """Validate a questionnaire config before it is saved.

    The label-config rules apply as they are, plus one of the questionnaire's
    own: it must ask at least one question, else annotators would face a
    modal they cannot answer or close.
    """
    is_valid, errors = LabelConfigValidator.validate(config)
    if not is_valid:
        return False, errors
    root = _parse(config)
    if root is None or not any(True for _ in _answer_elements(root)):
        return False, [
            "The questionnaire has no question: add at least one answer field "
            f"({', '.join(sorted(ANSWER_TAGS))}) with a 'name'"
        ]
    return True, []


def required_questions(config: Optional[str]) -> List[Tuple[str, str]]:
    """``(name, label)`` of every question marked ``required="true"``, in
    config order. The label is what the annotator sees (``label``, else the
    name)."""
    if not config:
        return []
    root = _parse(config)
    if root is None:
        return []
    return [
        (element.get('name'), element.get('label') or element.get('name'))
        for element in _answer_elements(root)
        if (element.get('required') or '').strip().lower() == 'true'
    ]


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return any(_has_content(item) for item in value)
    if isinstance(value, dict):
        return any(_has_content(item) for item in value.values())
    return True


def _is_answered(entry: dict) -> bool:
    value = entry.get('value')
    # A star rating cleared by clicking the chosen star again is sent as 0:
    # ratings start at 1, so 0 means no answer.
    if str(entry.get('type', '')).lower() == 'rating':
        rating = value.get('rating') if isinstance(value, dict) else value
        return isinstance(rating, (int, float)) and not isinstance(rating, bool) and rating > 0
    return _has_content(value)


def missing_required_answers(config: Optional[str], result: List[dict]) -> List[str]:
    """Labels of the required questions the ``result`` leaves unanswered."""
    answered = {
        entry.get('from_name')
        for entry in result or []
        if isinstance(entry, dict) and _is_answered(entry)
    }
    return [label for name, label in required_questions(config) if name not in answered]


def questionnaire_config_hash(config: Optional[str]) -> Optional[str]:
    """SHA-256 of the config text a response answered, so an analysis can
    tell which version of the questionnaire each response belongs to after
    the config was edited."""
    if not config:
        return None
    return hashlib.sha256(config.encode('utf-8')).hexdigest()

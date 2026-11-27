"""Every label config already in the repo parses exactly as it did before
Repeater support was added.

``tests/fixtures/label_config/corpus.json`` holds the label configs found in
the repo's code, tests and templates (every balanced ``<View>`` literal that
parses as XML) together with what the parser, validator, response parser and
structured-output schema generator returned for each of them on ``dev``
before the Repeater work. The test recomputes those outputs with the current
code, with and without task data, and requires them to be identical.

One deliberate exception: the schema generator used to ask a
``<Choices choice="multiple">`` field for a single string, so a model could
pick only one option. It now asks for a list of the choice values, and the
seven multi-choice entries were regenerated for that change alone: entry 6
(``api/init_complete.py``), 92 (``api/tests/unit/test_evaluation_config.py``),
184 (``api/tests/unit/test_pure_functions_coverage.py``), 210
(``frontend/e2e/helpers/test-fixtures.ts``), 227 and 240
(``frontend/e2e/user-workflows/label-config-updates.spec.ts``) and 290
(``frontend/src/lib/labelConfig/__tests__/parser.test.ts``). Only their
``generation_schema``, ``generation_schema_loose`` and
``format_instructions`` changed; their parse, field and validator outputs are
the ones from before the Repeater work.

A second one: ``<Likert>`` (rendered by the frontend's LikertInput) became a
supported tag of the validator. Entry 250 (the questionnaire templates of
``frontend/src/components/projects/AdvancedSettingsCard.tsx``) had only its
``validator`` output changed, from ten "Unsupported field type: 'Likert'"
errors to valid.

Regenerate the golden outputs only for a deliberate behaviour change:
``python tests/unit/test_label_config_corpus_unchanged.py --write`` from
``services/api`` (with ``services/api`` and ``services/shared`` on
``PYTHONPATH``).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from typing import Any, Dict

import pytest

_API_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHARED = os.path.join(os.path.dirname(_API_ROOT), "shared")
for _path in (_API_ROOT, _SHARED):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from label_config_repeater import expand_repeaters  # noqa: E402
from response_parser import ResponseParser  # noqa: E402
from services.label_config.parser import LabelConfigParser  # noqa: E402
from services.label_config.validator import LabelConfigValidator  # noqa: E402

# The schema generator is file-imported: the ``ai_services`` package import
# pulls every provider SDK.
_spec = importlib.util.spec_from_file_location(
    "_corpus_schema_generator", os.path.join(_SHARED, "ai_services", "schema_generator.py")
)
_schema_generator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_schema_generator)

CORPUS_PATH = os.path.join(_API_ROOT, "tests", "fixtures", "label_config", "corpus.json")

# Task data handed to the task-aware entry points: unrelated to any config, so
# a config without a Repeater must not change at all when it is given.
_TASK_DATA = {"text": "Ein Sachverhalt.", "items": [{"x": 1}, {"x": 2}]}


def _sample_value(config: Dict[str, Any]) -> Any:
    kind = config.get("type")
    if kind == "Choices":
        return (config.get("choices") or ["A"])[0]
    if kind in ("Number", "Rating"):
        return 3
    if kind == "Labels":
        return [{"start": 0, "end": 3, "text": "Ein", "type": (config.get("labels") or ["X"])[0]}]
    return "Antwort"


def _strip_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_ids(v) for k, v in value.items() if k != "id"}
    if isinstance(value, list):
        return [_strip_ids(v) for v in value]
    return value


def snapshot(label_config: str, task_data: Any = None) -> Dict[str, Any]:
    """The observable outputs of every label-config consumer for one config."""
    kwargs = {} if task_data is None else {"task_data": task_data}
    expanded = label_config if task_data is None else expand_repeaters(label_config, task_data)
    parser = ResponseParser({}, label_config)
    answer = {name: _sample_value(cfg) for name, cfg in parser.label_config_map.items()}
    parsed = parser.parse(json.dumps(answer, ensure_ascii=False), **kwargs)
    valid, errors = LabelConfigValidator.validate(label_config)
    summary = LabelConfigParser.validate_config(label_config)
    if isinstance(summary.get("field_types"), list):
        # Built from a set: its order changes with string hashing per run.
        summary["field_types"] = sorted(summary["field_types"])
    return {
        "fields": LabelConfigParser.extract_fields(expanded),
        "fields_raw": LabelConfigParser.extract_fields(expanded, sanitize=False),
        "bound": sorted(LabelConfigParser.bound_data_fields(label_config)),
        "validate_config": summary,
        "validator": [valid, errors],
        "label_config_map": parser.label_config_map,
        "json_schema": parser.json_schema,
        "parse": [parsed.status, parsed.error, _strip_ids(parsed.parsed_annotation)],
        "field_values": _strip_ids(parsed.field_values),
        "generation_schema": _schema_generator.generate_json_schema_from_label_config(
            label_config, **kwargs
        ),
        "generation_schema_loose": _schema_generator.generate_json_schema_from_label_config(
            label_config, strict_mode=False, **kwargs
        ),
        "format_instructions": _schema_generator.generate_format_instructions(label_config),
    }


def _normalise(value: Any) -> Any:
    """JSON round trip, so tuples and lists compare like the stored fixture."""
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _load_corpus():
    with open(CORPUS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


_CORPUS = _load_corpus() if os.path.exists(CORPUS_PATH) else []


def test_corpus_is_substantial():
    # The corpus was collected from the whole repo; a silently emptied
    # fixture would make the parametrised test below pass vacuously.
    assert len(_CORPUS) >= 400


@pytest.mark.parametrize(
    "entry", _CORPUS, ids=[f"{i}-{e['source']}" for i, e in enumerate(_CORPUS)]
)
def test_existing_label_config_parses_unchanged(entry):
    expected = entry["expected"]
    assert _normalise(snapshot(entry["label_config"])) == expected
    # Passing a task's data to the task-aware entry points changes nothing
    # for a config without a Repeater.
    assert _normalise(snapshot(entry["label_config"], _TASK_DATA)) == expected


if __name__ == "__main__":  # pragma: no cover - fixture regeneration
    if "--write" not in sys.argv:
        raise SystemExit("pass --write to regenerate the golden outputs")
    corpus = _load_corpus()
    for item in corpus:
        item["expected"] = _normalise(snapshot(item["label_config"]))
    with open(CORPUS_PATH, "w", encoding="utf-8") as handle:
        # One entry per line keeps a regenerated fixture's diff readable.
        handle.write("[\n")
        handle.write(
            ",\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in corpus)
        )
        handle.write("\n]\n")
    print(f"wrote {len(corpus)} entries to {CORPUS_PATH}")

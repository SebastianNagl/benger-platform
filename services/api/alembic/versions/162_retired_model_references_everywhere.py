"""Point every saved model reference from retired models to their replacements.

Migration 161 rewrote a fixed set of keys (the generation config's model
list and per-model settings, the project's model id list, the evaluation
config's judges, the OCR model). Saved evaluation configs name models under
further keys, which 161 left alone, for example the generator of a sheet
judge (``metric_parameters.rubric_generator_model_id`` and
``metric_parameters.rubric_generator_selection.model_id``); a judge saved
again after 161 ran also kept its retired id. Those projects stop working
once the provider switches the model off.

This migration walks every JSON value of the saved configs instead of a key
list, with 161's ``REPLACEMENTS`` mapping (loaded from 161, not copied):

* every JSON column of ``projects`` (``generation_config``,
  ``llm_model_ids``, ``evaluation_config``, ``korrektur_config``,
  ``exam_tools`` and whatever else the table holds, except the
  ``label_config_history`` record), ``organizations.settings`` and the
  unfinished wizard drafts (``project_wizard_drafts.state``, which become
  projects), plus ``projects.handwriting_ocr_model``;
* a string is a model reference when its key is a model key: ``model``,
  ``models``, ``model_id``, ``model_ids`` or a key ending in ``_model``,
  ``_models``, ``_model_id`` or ``_model_ids`` (``judge_model``,
  ``rubric_generator_model_id``, ``llm_model_ids``), camelCase keys of the
  wizard state included (``selectedModelIds``); a string in a list under
  such a key is one too, and so is a key of a per-model settings dict
  (``model_configs``, ``modelConfigs``), whose settings move to the
  replacement unless the replacement has its own;
* a list of model ids keeps the first of two entries that now name the same
  model, and so does a ``judges`` list by ``judge_model_id``;
* a ``display_name`` next to a rewritten reference names the replacement
  wherever the retired id stands as a whole id, as in 161;
* a string under any other key stays, even when it equals a retired id
  (a label "o3", a prompt text naming "gpt-5").

Records of the past are not touched: ``rubric_selector`` picks the sheets a
generator produced, so its ``generator_model_id`` must keep naming the model
that produced them, and a ``skipped`` list records which models a selection
passed over. A future retirement adds its ids to a mapping and calls
:func:`rewrite_model_references` with it.

Counts per column, per retired id and per key path are printed. Idempotent:
a second run finds no retired id. Downgrade is a no-op, since the retired
models no longer run.

Revision ID: 162_retired_model_references_everywhere
Revises: 161_retired_model_references
Create Date: 2026-11-27
"""

import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "162_retired_model_references_everywhere"
down_revision = "161_retired_model_references"
branch_labels = None
depends_on = None


def _load_161():
    path = Path(__file__).with_name("161_retired_model_references.py")
    spec = importlib.util.spec_from_file_location("_migration_161_retired_model_references", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Retired id -> replacement: migration 161's mapping, shared rather than copied.
REPLACEMENTS = dict(_load_161().REPLACEMENTS)

_MODEL_KEYS = {"model", "models", "model_id", "model_ids"}
_MODEL_KEY_SUFFIXES = ("_model", "_models", "_model_id", "_model_ids")
#: Keys whose dict is keyed by model id (per-model settings).
_MODEL_DICT_SUFFIX = "model_configs"
#: Subtrees that record the past rather than name a model to run.
_RECORD_KEYS = {"rubric_selector", "skipped"}
#: Columns that are history, not configuration.
_SKIPPED_COLUMNS = {("projects", "label_config_history")}


def _snake(key):
    """``selectedModelIds`` -> ``selected_model_ids``; snake keys unchanged."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", key).lower()


def is_model_key(key):
    if not isinstance(key, str):
        return False
    key = _snake(key)
    return key in _MODEL_KEYS or key.endswith(_MODEL_KEY_SUFFIXES)


def _is_model_dict_key(key):
    return isinstance(key, str) and _snake(key).endswith(_MODEL_DICT_SUFFIX)


def _rename_in_label(label, retired_ids, replacements):
    """``label`` with each retired id replaced where it stands as a whole id
    ("Notenpunkte (gpt-5-mini)"), never inside a longer one ("gpt-5" in
    "gpt-5.4-mini"). Same rule as 161."""
    for retired in sorted(retired_ids, key=len, reverse=True):
        label = re.sub(
            r"(?<![\w.\-/])" + re.escape(retired) + r"(?![\w.\-/])",
            replacements[retired],
            label,
        )
    return label


class _Walk:
    """One rewrite of one JSON value: what changed, by retired id and path."""

    def __init__(self, replacements):
        self.replacements = replacements
        self.hits = []  # retired ids in walk order, one per rewritten reference
        self.paths = Counter()

    @property
    def retired(self):
        return set(self.hits)

    def _hit(self, retired, path):
        self.hits.append(retired)
        self.paths[path] += 1

    def model_value(self, value, path):
        """A value under a model key: a string, or a list of strings."""
        if isinstance(value, str):
            if value in self.replacements:
                self._hit(value, path)
                return self.replacements[value]
            return value
        if isinstance(value, list):
            out = []
            changed = False
            for item in value:
                if isinstance(item, str) and item in self.replacements:
                    self._hit(item, f"{path}[]")
                    item = self.replacements[item]
                    changed = True
                if isinstance(item, (dict, list)):
                    item = self.node(item, f"{path}[]")
                if changed and isinstance(item, str) and item in out:
                    continue
                out.append(item)
            return out
        return self.node(value, path)

    def model_dict(self, value, path):
        """A per-model settings dict: retired keys move to the replacement
        unless the replacement has its own settings (161's rule)."""
        if not isinstance(value, dict):
            return self.node(value, path)
        retired = [k for k in value if k in self.replacements]
        for key in retired:
            self._hit(key, f"{path}{{}}")
        out = {}
        for key, settings in value.items():
            if key not in self.replacements:
                out[key] = self.node(settings, f"{path}.<model>")
        for key, settings in value.items():
            target = self.replacements.get(key)
            if target is not None and target not in out:
                out[target] = self.node(settings, f"{path}.<model>")
        return out

    def node(self, value, path):
        if isinstance(value, list):
            return [self.node(item, f"{path}[]") for item in value]
        if not isinstance(value, dict):
            return value
        first_hit = len(self.hits)
        out = {}
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if isinstance(key, str) and _snake(key) in _RECORD_KEYS:
                out[key] = child
            elif is_model_key(key):
                out[key] = self.model_value(child, child_path)
            elif _is_model_dict_key(key):
                out[key] = self.model_dict(child, child_path)
            else:
                out[key] = self.node(child, child_path)
        replaced_here = set(self.hits[first_hit:])
        if replaced_here:
            judges = out.get("judges")
            if isinstance(judges, list):
                seen = set()
                deduped = []
                for entry in judges:
                    judge = entry.get("judge_model_id") if isinstance(entry, dict) else None
                    if judge is not None and judge in seen:
                        continue
                    if judge is not None:
                        seen.add(judge)
                    deduped.append(entry)
                out["judges"] = deduped
            for label_key in ("display_name", "displayName"):
                label = out.get(label_key)
                if isinstance(label, str):
                    new_label = _rename_in_label(label, replaced_here, self.replacements)
                    if new_label != label:
                        out[label_key] = new_label
                        self.paths[f"{path}.{label_key}" if path else label_key] += 1
        return out


def rewrite_model_references(value, key, replacements=None):
    """(``value``, saved under ``key``, with every retired model reference
    replaced; the retired ids replaced; a Counter of rewritten references per
    key path, starting at ``key``). (None, empty set, empty Counter) when
    nothing changed. ``key`` is the column name, so a column that is itself a
    model key (``llm_model_ids``) is a list of model ids, while a list in any
    other column (``korrektur_config``) is only walked."""
    walk = _Walk(REPLACEMENTS if replacements is None else replacements)
    out = walk.node({key: value}, "")[key]
    if out == value:
        return None, set(), Counter()
    return out, walk.retired, walk.paths


def _json_columns(conn, table):
    """{column: "jsonb" | "json"} of the table's JSON columns."""
    columns = {}
    for column in inspect(conn).get_columns(table):
        kind = str(column["type"]).upper()
        if "JSON" in kind and (table, column["name"]) not in _SKIPPED_COLUMNS:
            columns[column["name"]] = "jsonb" if "JSONB" in kind else "json"
    return columns


def _key_column(conn, table):
    pk = inspect(conn).get_pk_constraint(table).get("constrained_columns") or []
    return pk[0] if len(pk) == 1 else None


def _load(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _like_any(column, replacements):
    """A cheap SQL prefilter: the column's text mentions some retired id."""
    ids = list(replacements)
    clauses = " OR ".join(f"{column}::text LIKE :p{i}" for i in range(len(ids)))
    params = {f"p{i}": f'%"{rid}"%' for i, rid in enumerate(ids)}
    return clauses, params


def _rewrite_table(conn, table, per_id, per_path, counts, replacements):
    if not inspect(conn).has_table(table):
        return
    key = _key_column(conn, table)
    if key is None:
        return
    for column, cast in sorted(_json_columns(conn, table).items()):
        where, params = _like_any(column, replacements)
        rows = conn.execute(
            sa.text(f"SELECT {key}, {column} FROM {table} WHERE {where}"), params
        ).fetchall()
        updated = 0
        for row_key, value in rows:
            new_value, retired, paths = rewrite_model_references(
                _load(value), column, replacements
            )
            if new_value is None:
                continue
            per_id.update(retired)
            for path, n in paths.items():
                per_path[f"{table}.{path}"] += n
            conn.execute(
                sa.text(
                    f"UPDATE {table} SET {column} = CAST(:v AS {cast}) WHERE {key} = :k"
                ),
                {"v": json.dumps(new_value), "k": row_key},
            )
            updated += 1
        counts[f"{table}.{column}"] = updated


def upgrade(replacements=None) -> None:
    replacements = REPLACEMENTS if replacements is None else replacements
    conn = op.get_bind()
    per_id = Counter()
    per_path = Counter()
    counts = {}
    for table in ("projects", "organizations", "project_wizard_drafts"):
        _rewrite_table(conn, table, per_id, per_path, counts, replacements)
    ocr = 0
    if "handwriting_ocr_model" in {c["name"] for c in inspect(conn).get_columns("projects")}:
        for retired, replacement in replacements.items():
            n = conn.execute(
                sa.text(
                    "UPDATE projects SET handwriting_ocr_model = :new "
                    "WHERE handwriting_ocr_model = :old"
                ),
                {"new": replacement, "old": retired},
            ).rowcount
            ocr += n
            if n:
                per_id[retired] += n
                per_path["projects.handwriting_ocr_model"] += n
    counts["projects.handwriting_ocr_model"] = ocr
    summary = ", ".join(f"{name}={n}" for name, n in sorted(counts.items()))
    print(f"162: rewrote retired model references: {summary}")
    by_id = ", ".join(f"{rid}={n}" for rid, n in sorted(per_id.items())) or "none"
    print(f"162: rewritten rows per retired id: {by_id}")
    by_path = ", ".join(f"{p}={n}" for p, n in sorted(per_path.items())) or "none"
    print(f"162: rewritten references per key path: {by_path}")


def downgrade() -> None:
    # Nothing to restore: the retired models no longer run, so pointing the
    # configs back at them would only make every job fail again.
    pass

"""Point saved configs from retired catalog models to their replacements.

The 2026-11 catalog refresh switches off twelve official models that their
provider retires, reroutes or no longer serves (``llm_models.yaml``):
Claude Sonnet 4.5 (retired 2026-11-30), Gemini 3.5 Flash and 3.7 Flash
(answered by other models since 2026-10-08), Gemini 2.5 Pro and 2.5 Flash
(rerouted from 2026-12-01), the two DeepInfra Qwen3-Max rows (no longer
served) and gpt-5, gpt-5-mini, gpt-5-nano, o3 and o3-pro (shut down
2026-12-11). About forty more official rows were switched off by earlier
refreshes (older OpenAI, Anthropic, Google, xAI, Mistral and DeepInfra
models such as o4-mini, claude-sonnet-4-20250514 or grok-3), yet saved
configs naming them kept running. Switching a row off only hides it from
the pickers, and the platform now refuses an inactive official model at
generation and evaluation start, so a saved config that still names one of
either group would stop working. This rewrites the saved references to the
replacement each provider names:

* ``projects.generation_config``: ``selected_configuration.models`` and the
  keys of ``selected_configuration.model_configs`` (a retired model's
  per-model settings move to its replacement unless the replacement has its
  own; the provider services drop reasoning settings a model does not take);
* ``projects.llm_model_ids``;
* ``projects.evaluation_config``: every ``judge_model`` and
  ``judge_model_id`` value, at any depth (``evaluation_configs``,
  ``multi_field_evaluations``, legacy ``selected_methods``; a ``judges``
  list that then names a model twice keeps its first entry), and the
  retired id in the ``display_name`` of an entry whose judge moved
  ("Notenpunkte (gpt-5-mini)" becomes "Notenpunkte (gpt-6.1-terra)");
* ``projects.handwriting_ocr_model`` and the ``handwriting_ocr_model`` key
  of ``organizations.settings``.

Past results keep the model id they were produced with (generations,
evaluation rows, judge runs, rubric records and their
``rubric_selector.generator_model_id`` lookups are not touched), so the
record stays truthful. Three inactive rows have no replacement in the
catalog (Qwen/QwQ-32B, Qwen/Qwen2.5-Coder-32B-Instruct and
magistral-small-latest): their references stay, and generation or
evaluation start refuses them with a message asking for another model in
the project settings. Counts per column and per retired id are printed.
Idempotent: a second run finds no retired id. Downgrade is a no-op, since
the retired models no longer run.

Revision ID: 161_retired_model_references
Revises: 160_bug_reports
Create Date: 2026-11-26
"""

import json
import re
from collections import Counter

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "161_retired_model_references"
down_revision = "160_bug_reports"
branch_labels = None
depends_on = None

#: Retired id -> the replacement its provider names (deprecation pages and
#: DeepInfra ``replaced_by``, 2026-11-26). o3-pro's named replacement is
#: gpt-6.1-sol in "pro" reasoning mode, which the platform does not send;
#: plain gpt-6.1-sol it is. The first group is retired by this refresh, the
#: second was switched off earlier; an earlier row still served under an
#: alias maps to the current catalog equivalent.
REPLACEMENTS = {
    "claude-sonnet-4-5-20250929": "claude-sonnet-5-5",
    "gemini-3.5-flash": "gemini-3.6-flash",
    "gemini-3.7-flash": "gemini-3.8-flash",
    "gemini-2.5-pro": "gemini-3.8-flash",
    "gemini-2.5-flash": "gemini-3.5-flash-lite",
    "Qwen/Qwen3-Max": "Qwen/Qwen3.8-Max",
    "Qwen/Qwen3-Max-Thinking": "Qwen/Qwen3.8-Max",
    "gpt-5": "gpt-6.1-sol",
    "gpt-5-mini": "gpt-6.1-terra",
    "gpt-5-nano": "gpt-6-luna",
    "o3": "gpt-6.1-sol",
    "o3-pro": "gpt-6.1-sol",
    "gpt-4.1-nano": "gpt-5.6-luna",
    "o4-mini": "gpt-5.6-terra",
    "o3-mini": "gpt-5.6-sol",
    "o1": "gpt-5.6-sol",
    "gpt-3.5-turbo": "gpt-5.6-terra",
    "claude-opus-4-1-20250805": "claude-opus-4-8",
    "claude-opus-4-20250514": "claude-opus-4-8",
    "claude-sonnet-4-20250514": "claude-sonnet-5-5",
    "claude-3-5-haiku-20241022": "claude-haiku-4-5-20251001",
    "claude-3-opus-20240229": "claude-opus-4-8",
    "claude-3-sonnet-20240229": "claude-sonnet-5-5",
    "claude-3-haiku-20240307": "claude-haiku-4-5-20251001",
    "gemini-2.0-flash": "gemini-3.6-flash",
    "gemini-3.1-flash-lite-preview": "gemini-3.1-flash-lite",
    "grok-4": "grok-4.3",
    "grok-4-1-fast": "grok-4.3",
    "grok-3": "grok-4.3",
    "grok-3-mini": "grok-4.3",
    "grok-3-beta": "grok-4.3",
    "grok-3-mini-beta": "grok-4.3",
    "mistral-large-latest": "mistral-large-4",
    "devstral-latest": "mistral-medium-latest",
    "magistral-medium-latest": "mistral-medium-latest",
    "deepseek-ai/DeepSeek-R1-Distill-Llama-70B": "deepseek-ai/DeepSeek-R1-0528",
    "Qwen/Qwen3.5-122B-A10B": "Qwen/Qwen3.5-397B-A17B",
    "Qwen/Qwen3-235B-A22B-Thinking-2507": "Qwen/Qwen3.6-35B-A3B",
    "meta-llama/Meta-Llama-3.1-70B-Instruct": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "meta-llama/Meta-Llama-3.1-8B-Instruct": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8": "google/gemma-4-31B-it-turbo",
    "moonshotai/Kimi-K2-Instruct-0905": "moonshotai/Kimi-K2.6",
    "Qwen/Qwen3-Coder-480B-A35B-Instruct": "Qwen/Qwen3-Coder-480B-A35B-Instruct-Turbo",
    "MiniMaxAI/MiniMax-M2.5": "MiniMaxAI/MiniMax-M3",
    "MiniMaxAI/MiniMax-M2.7": "MiniMaxAI/MiniMax-M3",
    "MiniMaxAI/MiniMax-M2.7-Turbo": "MiniMaxAI/MiniMax-M3",
    "moonshotai/Kimi-K2.7-Code": "moonshotai/Kimi-K3",
    "moonshotai/Kimi-K2.5": "moonshotai/Kimi-K2.6",
    "zai-org/GLM-5.1": "zai-org/GLM-5.3",
    "zai-org/GLM-5": "zai-org/GLM-5.2",
    "zai-org/GLM-4.7-Flash": "zai-org/GLM-5.3-Flash",
    "stepfun-ai/Step-3.5-Flash": "XiaomiMiMo/MiMo-V2.6-Flash",
    "stepfun-ai/Step-3.7-Flash": "XiaomiMiMo/MiMo-V2.6-Flash",
    "nvidia/Nemotron-3-Nano-30B-A3B": "nvidia/NVIDIA-Nemotron-3.5-Lightning",
}

_JUDGE_KEYS = ("judge_model", "judge_model_id")
_OCR_KEY = "handwriting_ocr_model"


def _replace_list(ids):
    """(model id list with retired ids replaced, duplicates dropped with the
    first occurrence winning; the retired ids replaced). (None, empty set)
    when nothing changed."""
    if not isinstance(ids, list):
        return None, set()
    replaced = {m for m in ids if isinstance(m, str) and m in REPLACEMENTS}
    if not replaced:
        return None, set()
    out = []
    for m in ids:
        m = REPLACEMENTS.get(m, m) if isinstance(m, str) else m
        if m not in out:
            out.append(m)
    return out, replaced


def rewrite_generation_config(config):
    """(``generation_config`` with retired ids replaced, the retired ids
    replaced); (None, empty set) when unchanged."""
    if not isinstance(config, dict):
        return None, set()
    selected = config.get("selected_configuration")
    if not isinstance(selected, dict):
        return None, set()
    new_selected = dict(selected)
    models, replaced = _replace_list(selected.get("models"))
    if models is not None:
        new_selected["models"] = models
    model_configs = selected.get("model_configs")
    retired_keys = (
        {k for k in model_configs if k in REPLACEMENTS}
        if isinstance(model_configs, dict)
        else set()
    )
    if retired_keys:
        moved = {}
        for key, value in model_configs.items():
            if key not in REPLACEMENTS:
                moved[key] = value
        for key, value in model_configs.items():
            target = REPLACEMENTS.get(key)
            if target is not None and target not in moved:
                moved[target] = value
        new_selected["model_configs"] = moved
        replaced = replaced | retired_keys
    if not replaced:
        return None, set()
    return {**config, "selected_configuration": new_selected}, replaced


def _rename_in_label(label, retired_ids):
    """``label`` with each of ``retired_ids`` replaced where it stands as a
    whole id ("Notenpunkte (gpt-5-mini)"), never inside a longer one
    ("gpt-5" in "gpt-5.4-mini")."""
    for retired in sorted(retired_ids, key=len, reverse=True):
        label = re.sub(
            r"(?<![\w.\-/])" + re.escape(retired) + r"(?![\w.\-/])",
            REPLACEMENTS[retired],
            label,
        )
    return label


def _rewrite_judges(node):
    """``node`` with judge ids replaced at any depth; (node, retired ids
    replaced in it). A ``display_name`` beside them names the replacement
    too, so the label matches the judge that runs."""
    if isinstance(node, dict):
        replaced = set()
        out = {}
        for key, value in node.items():
            if key in _JUDGE_KEYS and isinstance(value, str) and value in REPLACEMENTS:
                out[key] = REPLACEMENTS[value]
                replaced.add(value)
                continue
            new_value, sub_replaced = _rewrite_judges(value)
            out[key] = new_value
            replaced |= sub_replaced
        judges = out.get("judges")
        if replaced and isinstance(judges, list):
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
        label = out.get("display_name")
        if replaced and isinstance(label, str):
            out["display_name"] = _rename_in_label(label, replaced)
        return out, replaced
    if isinstance(node, list):
        replaced = set()
        out = []
        for item in node:
            new_item, sub_replaced = _rewrite_judges(item)
            out.append(new_item)
            replaced |= sub_replaced
        return out, replaced
    return node, set()


def rewrite_evaluation_config(config):
    """(``evaluation_config`` with retired judge ids replaced, the retired ids
    replaced); (None, empty set) when unchanged."""
    if not isinstance(config, dict):
        return None, set()
    out, replaced = _rewrite_judges(config)
    return (out, replaced) if replaced else (None, set())


def rewrite_org_settings(settings):
    """(``organizations.settings`` with a retired OCR model replaced, the
    retired id replaced); (None, empty set) when unchanged."""
    if not isinstance(settings, dict):
        return None, set()
    value = settings.get(_OCR_KEY)
    if not isinstance(value, str) or value.strip() not in REPLACEMENTS:
        return None, set()
    return {**settings, _OCR_KEY: REPLACEMENTS[value.strip()]}, {value.strip()}


def _column_types(conn, table):
    return {c["name"]: str(c["type"]).upper() for c in inspect(conn).get_columns(table)}


def _cast(column_type):
    return "jsonb" if "JSONB" in column_type else "json"


def _load(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _like_any(column):
    """A cheap SQL prefilter: the column's text mentions some retired id."""
    clauses = " OR ".join(f"{column}::text LIKE :p{i}" for i in range(len(REPLACEMENTS)))
    params = {f"p{i}": f'%"{rid}"%' for i, rid in enumerate(REPLACEMENTS)}
    return clauses, params


def _rewrite_json_column(conn, table, column, rewrite, per_id):
    types = _column_types(conn, table)
    if column not in types:
        return 0
    where, params = _like_any(column)
    rows = conn.execute(
        sa.text(f"SELECT id, {column} FROM {table} WHERE {where}"), params
    ).fetchall()
    updated = 0
    for row_id, value in rows:
        new_value, replaced = rewrite(_load(value))
        if new_value is None:
            continue
        per_id.update(replaced)
        conn.execute(
            sa.text(
                f"UPDATE {table} SET {column} = CAST(:v AS {_cast(types[column])}) "
                "WHERE id = :id"
            ),
            {"v": json.dumps(new_value), "id": row_id},
        )
        updated += 1
    return updated


def upgrade() -> None:
    conn = op.get_bind()
    per_id = Counter()
    counts = {
        "projects.generation_config": _rewrite_json_column(
            conn, "projects", "generation_config", rewrite_generation_config, per_id
        ),
        "projects.llm_model_ids": _rewrite_json_column(
            conn, "projects", "llm_model_ids", _replace_list, per_id
        ),
        "projects.evaluation_config": _rewrite_json_column(
            conn, "projects", "evaluation_config", rewrite_evaluation_config, per_id
        ),
        "organizations.settings": _rewrite_json_column(
            conn, "organizations", "settings", rewrite_org_settings, per_id
        ),
    }
    ocr = 0
    if "handwriting_ocr_model" in _column_types(conn, "projects"):
        for retired, replacement in REPLACEMENTS.items():
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
    counts["projects.handwriting_ocr_model"] = ocr
    summary = ", ".join(f"{name}={n}" for name, n in counts.items())
    print(f"161: rewrote retired model references: {summary}")
    by_id = ", ".join(f"{rid}={n}" for rid, n in sorted(per_id.items())) or "none"
    print(f"161: rewritten references per retired id: {by_id}")


def downgrade() -> None:
    # Nothing to restore: the retired models no longer run, so pointing the
    # configs back at them would only make every job fail again.
    pass

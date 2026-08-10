"""Drop superseded generation attempts inside one task's generation list.

Two superseded-attempt families exist in the raw task exports; both follow
the same platform pattern (a task was re-generated for the same system and
the earlier attempt was never deleted, so exports carry both rows):

- ZJS: the 2026-05-13 campaign ran with max_tokens=8000; generations that
  hit the cap (``response_metadata.truncated``) were re-generated on
  2026-05-14 at 20,000 tokens. 1,072 (task, system) pairs carry both rows.
- Benchathon: a partial April 2026 pre-finalisation round (no logged
  system/instruction prompts, temperature 0.0, no token budget, partially
  different model set) was superseded by the finalized 2026-05-08 campaign.
  gpt-5.4 (15) and Qwen3-235B-Thinking (13) carry both rows.

Counting both inflates per-system n inconsistently and mixes experimental
conditions, so every leaderboard-scoped derive script must count only the
replacement. Rule: within one task, a generation is dropped iff a strictly
later generation of the same ``model_id`` exists on the same task (the
newest generation per (task, system) is the canonical one). Grundprinzipien
has no multi-generation groups; the rule is a verified no-op there.

Pick-level analyses (the 45 human-graded validation picks, judge swap,
judge repeats) intentionally do NOT dedup: one graded LLM pick is an April
Benchathon generation, and human grades exist for exactly that text. The
superseded generations' judge/metric rows are exported separately
(``benchathon_superseded_*.json``) so those joins stay complete.
"""

from __future__ import annotations

from collections import Counter

_MIN_KEY = ("", "")


def _sort_key(gen: dict) -> tuple[str, str]:
    return (str(gen.get("created_at") or ""), str(gen.get("id") or ""))


def dedup_superseded(gens: list, dropped: Counter | None = None,
                     removed: list | None = None) -> list:
    """Return ``gens`` minus attempts a later same-model gen supersedes.

    Order-preserving. ``gens`` is one task's generation list from a task
    export. Pass a ``Counter`` as ``dropped`` to accumulate per-model_id
    drop counts across tasks; pass a list as ``removed`` to collect the
    dropped generation dicts themselves.
    """
    if not gens or len(gens) < 2:
        return list(gens or [])
    latest: dict[str, tuple[str, str]] = {}
    for g in gens:
        mid = g.get("model_id")
        if not mid:
            continue
        key = _sort_key(g)
        if key > latest.get(mid, _MIN_KEY):
            latest[mid] = key
    kept = []
    for g in gens:
        mid = g.get("model_id")
        if mid and _sort_key(g) < latest.get(mid, _MIN_KEY):
            if dropped is not None:
                dropped[mid] += 1
            if removed is not None:
                removed.append(g)
            continue
        kept.append(g)
    return kept


def dedup_export_view(export: dict, dropped: Counter | None = None,
                      removed_by_task: dict | None = None) -> dict:
    """Deduped copy of a ``{"tasks": [...]}`` export (tasks shallow-copied).

    The input export is left untouched so pick-level derivations can keep
    walking the full generation set. ``removed_by_task`` (task_id -> [gen])
    collects the dropped generations for the superseded side-exports.
    """
    tasks = []
    for task in export.get("tasks") or []:
        removed: list = []
        kept = dedup_superseded(task.get("generations") or [], dropped, removed)
        if removed and removed_by_task is not None:
            removed_by_task.setdefault(task.get("id"), []).extend(removed)
        t = dict(task)
        t["generations"] = kept
        tasks.append(t)
    view = dict(export)
    view["tasks"] = tasks
    return view

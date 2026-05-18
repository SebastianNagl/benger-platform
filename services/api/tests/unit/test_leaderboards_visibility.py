"""Issue #30 PR 5: regression test for the LLM leaderboard's default
visibility filter.

When a leaderboard endpoint is called without an explicit `project_ids`
list, only PUBLIC projects (Project.is_public=True) should contribute to
the aggregation. The pre-fix default mixed scores from private projects
(e.g. ZJS Fälle on prod — BLEU-only on 34k+ task_evaluations) into the
global per-model averages, silently skewing them.

We don't have the platform Postgres harness here; cover the contract via
static-analysis on the router source.
"""

from __future__ import annotations

import os
import re


REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ROUTER = os.path.join(REPO, "api", "routers", "leaderboards.py")


def _src() -> str:
    with open(ROUTER) as f:
        return f.read()


def test_apply_default_visibility_filter_helper_exists():
    src = _src()
    assert "def _apply_default_visibility_filter(" in src, (
        "Helper missing — the default-public filter is the contract of PR 5"
    )


def test_helper_falls_back_to_is_public_when_no_project_ids():
    """The helper's else-branch must add `Project.is_public.is_(True)` so
    private projects (ZJS-style) drop out of the default aggregation."""
    src = _src()
    m = re.search(
        r"def _apply_default_visibility_filter\([^)]*\):.+?(?=\ndef |\nclass )",
        src,
        re.DOTALL,
    )
    assert m, "_apply_default_visibility_filter body not found"
    body = m.group(0)
    assert "Project.is_public" in body, (
        "Default branch must filter by Project.is_public — otherwise the "
        "regression PR 5 closes (ZJS-in-global-leaderboard) reopens"
    )
    assert "EvaluationRun.project_id" in body
    # Explicit project_ids list must still bypass the public filter
    assert "if project_ids:" in body


def test_all_evaluation_endpoints_use_the_helper():
    """The four `_filter_accessible_project_ids` callsites that query
    EvaluationRun must all go through the helper — otherwise one endpoint
    leaks private projects while siblings hide them. The annotation-stats
    endpoint at line ~219 is intentionally NOT in this set (Annotation
    table, separate decision)."""
    src = _src()
    # Count callsites that use the helper
    callsite_count = src.count("_apply_default_visibility_filter(query, project_ids)")
    assert callsite_count >= 3, (
        f"Expected ≥3 helper callsites on EvaluationRun queries, found "
        f"{callsite_count} — likely an endpoint was missed"
    )


def test_helper_only_joins_project_when_filter_is_needed():
    """When the caller already supplied project_ids, we should NOT add an
    extra Project join — saves a query plan node. The helper's true-branch
    must use the existing in_-filter, not the join."""
    src = _src()
    m = re.search(
        r"def _apply_default_visibility_filter\([^)]*\):.+?(?=\ndef |\nclass )",
        src,
        re.DOTALL,
    )
    body = m.group(0)
    # The if-truthy branch should use .filter(...) with in_(project_ids), no .join
    if_branch_end = body.find("return query.join")
    if_branch_text = body[: if_branch_end] if if_branch_end > 0 else body
    assert ".filter(EvaluationRun.project_id.in_(" in if_branch_text

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


# tests live at services/api/tests/unit/ on the host, or /app/tests/unit/ in
# the container. Both resolve to "two levels up" pointing at the services/api
# root (host) or /app (container).
_API_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROUTER = os.path.join(_API_ROOT, "routers", "leaderboards.py")


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


def test_default_scope_falls_back_to_public_for_non_superadmin():
    """After the precomputed-summary refactor (migration 051), visibility
    is enforced at the scope-key level rather than via .filter() calls on
    EvaluationRun. The contract is the same: a non-superadmin user with
    no `project_ids` filter must read from the 'public' scope (which the
    worker precomputes from `Project.is_public=True` only), NOT from 'all'.

    Closes the same regression as PR 5 (ZJS Fälle bleeding into the
    global per-model averages).
    """
    src = _src()
    m = re.search(
        # Multi-line signature with return-type annotation: capture from
        # `def _project_scope_key_for_request(` through the next top-level
        # `def`/`class`/decorator.
        r"def _project_scope_key_for_request\(.*?\).*?:.+?(?=\ndef |\nclass |\n@)",
        src,
        re.DOTALL,
    )
    assert m, "_project_scope_key_for_request helper missing — refactor reverted?"
    body = m.group(0)
    # Default branch (no project_ids) must select 'public' unless superadmin.
    assert "is_superadmin" in body, (
        "Scope selector must branch on is_superadmin so non-superadmins land "
        "on the 'public' scope by default"
    )
    assert "'public'" in body or '"public"' in body, (
        "Default scope key for non-superadmin without project_ids must be "
        "'public' — otherwise private projects leak into the leaderboard"
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

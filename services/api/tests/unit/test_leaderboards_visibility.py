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


def test_default_scope_splits_by_authentication():
    """Visibility contract for the precomputed leaderboard:

    * **Anonymous visitors** (no auth cookie / no token) → 'public' scope.
      Private project rankings must NOT leak to the open internet via
      the unauthenticated /leaderboards endpoint.
    * **Any authenticated user** (superadmin or not) → 'all' scope. Logged-in
      users see aggregate scores from every project. Aggregates are not
      row-level data; the private-project signal is the whole point of
      the leaderboard for evaluators.

    Replaces the older non-superadmin → 'public' rule. The original
    motivation (ZJS Fälle on a 34k-row BLEU project skewing the global
    average) is preserved for anonymous visitors; the change only opens
    the inside view to authenticated users.
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
    # Authenticated branch must exist and return 'all'.
    assert "current_user is not None" in body, (
        "Scope selector must branch on whether the user is authenticated "
        "(current_user is not None) so logged-in users land on 'all'"
    )
    assert "'all'" in body or '"all"' in body, (
        "Authenticated default must be 'all' — otherwise SebaN-style users "
        "can't see private-project leaderboard data"
    )
    # Anonymous fallback must still be 'public'.
    assert "'public'" in body or '"public"' in body, (
        "Anonymous fallback must be 'public' — otherwise private project "
        "rankings leak to the open internet via /leaderboards"
    )


def test_strict_filter_rejects_unknown_project_ids():
    """PR #116: when the leaderboard endpoint is called with
    `project_ids=<unknown-or-inaccessible>` and the filter strips every
    id, we MUST raise HTTP 400 instead of silently re-defaulting to the
    no-filter scope. The silent fallback hid project_id typos and let the
    caller think they were looking at a scoped leaderboard.

    `_filter_accessible_project_ids(strict=True)` is the path the
    leaderboard list endpoint opts into.
    """
    src = _src()
    m = re.search(
        r"def _filter_accessible_project_ids\([^)]*\)[^:]*:.+?(?=\ndef |\nclass )",
        src,
        re.DOTALL,
    )
    assert m, "_filter_accessible_project_ids helper missing — refactor reverted?"
    body = m.group(0)
    assert "strict" in body, "helper must accept a strict kwarg so callers can opt in"
    assert "HTTPException" in body, (
        "strict mode must raise HTTPException(400), not silently re-default"
    )

    # The list endpoint must call with strict=True so unknown project_ids
    # produce a 400 there. Other endpoints (single-model, compare) keep
    # the lenient default for backward compatibility.
    list_endpoint_call = re.search(
        r"async def get_llm_leaderboard\b.+?_filter_accessible_project_ids\([^)]*\)",
        src,
        re.DOTALL,
    )
    assert list_endpoint_call, "get_llm_leaderboard endpoint missing or no project_ids call"
    assert "strict=True" in list_endpoint_call.group(0), (
        "get_llm_leaderboard must call _filter_accessible_project_ids(strict=True) "
        "so unknown project_ids surface as 400 rather than a silently-broader leaderboard"
    )


def test_llm_leaderboard_trust_scope_intersect_helper_exists_and_is_wired():
    """PR #116 temp tweak: the LLM leaderboard is scoped to an
    allowlisted set of organisation IDs (currently TUM only) so untrusted
    eval data from other orgs doesn't surface on the public ranking.

    Contract:
      - `_intersect_with_allowlisted_org_projects` helper exists
      - `_LLM_LEADERBOARD_ALLOWLISTED_ORG_IDS` constant defines the gate
      - `get_llm_leaderboard` calls the helper before scope-key mapping
    """
    src = _src()
    assert "_LLM_LEADERBOARD_ALLOWLISTED_ORG_IDS" in src, (
        "trust-scope constant missing — the LLM leaderboard would surface "
        "untrusted org data"
    )
    assert "def _intersect_with_allowlisted_org_projects(" in src, (
        "trust-scope helper missing"
    )
    # The list endpoint must call the helper. Capture the function body and
    # assert the call appears (order matters: after accessibility check).
    list_fn = re.search(
        r"async def get_llm_leaderboard\b.+?(?=\nasync def |\ndef |\nclass )",
        src,
        re.DOTALL,
    )
    assert list_fn, "get_llm_leaderboard endpoint missing"
    body = list_fn.group(0)
    assert "_intersect_with_allowlisted_org_projects" in body, (
        "get_llm_leaderboard must call _intersect_with_allowlisted_org_projects "
        "so non-allowlisted projects are excluded from rankings"
    )


def test_llm_leaderboard_default_request_uses_tum_precomputed_scope():
    """PR after #118: the leaderboard's hot-path default (no project_ids,
    no eval_types filter, threshold ON, no search) must serve from the
    'tum' precomputed scope rather than live-aggregating on every page
    load — that was a 5+ second tax per request.

    The endpoint detects "caller didn't supply project_ids" and skips
    `_project_scope_key_for_request`'s multi-project-→-None mapping in
    favour of `scope_key = "tum"` directly. Lock the wiring in so a
    future refactor doesn't quietly bypass the precomputed read.
    """
    src = _src()
    list_fn = re.search(
        r"async def get_llm_leaderboard\b.+?(?=\nasync def |\ndef |\nclass )",
        src,
        re.DOTALL,
    )
    assert list_fn, "get_llm_leaderboard endpoint missing"
    body = list_fn.group(0)
    assert "caller_supplied_project_ids" in body, (
        "endpoint must track whether the caller supplied project_ids "
        "so the default request can pick scope='tum' over live aggregation"
    )
    assert '"tum"' in body or "'tum'" in body, (
        "endpoint must map the no-filter default to scope='tum'"
    )


def test_llm_leaderboard_min_samples_threshold_params_exist():
    """PR #116 default-on min-samples toggle: the list endpoint must
    accept `min_generation_count` and `min_samples_evaluated` query
    params with sensible defaults so noisy low-sample models don't
    pollute the ranking by default.
    """
    src = _src()
    assert "min_generation_count" in src, (
        "min_generation_count param missing — threshold filter not wired"
    )
    assert "min_samples_evaluated" in src, (
        "min_samples_evaluated param missing — threshold filter not wired"
    )
    # The frontend toggle defaults ON and sends 50/50; the API defaults
    # match so raw curl gets the same view. Drop these constants and the
    # filter when lifting the gate.
    assert "_LLM_LEADERBOARD_DEFAULT_MIN_GENERATIONS" in src
    assert "_LLM_LEADERBOARD_DEFAULT_MIN_SAMPLES" in src


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

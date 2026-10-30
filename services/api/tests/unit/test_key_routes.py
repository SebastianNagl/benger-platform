"""The access-key rule table of the full API (``app/core/key_routes.py``).

On a snapshot failure run ``make generate-public-api-docs`` and review the
diff in docs/full-api-routes.md: every opened route and every scope change
is a security decision."""

from pathlib import Path

import pytest

from app.core import key_routes as kr
from app.core.scopes import get_scope
from main import app
from middleware.key_gate import get_index
from routers.v1.reference import build_reference_openapi, routes_markdown


def _rule(method, path):
    entry, params = kr.match(get_index(app), method, path)
    assert entry is not None, f"{method} {path} matches no route"
    return entry.rule, params


def test_every_platform_route_has_a_rule():
    assert kr.uncovered_routes(app) == []
    kr.assert_key_routes_covered(app)


def test_rules_name_known_scopes_and_bindings():
    for rule in kr.PLATFORM_RULES:
        for scope in rule.scopes or ():
            assert get_scope(scope) is not None, f"{rule.pattern}: unknown scope {scope}"
        for spec in rule.bind:
            source, _, name = spec.partition(":")
            assert source in ("query", "body") and name, f"{rule.pattern}: bad bind {spec}"


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/refresh"),
        ("POST", "/api/auth/logout"),
        ("POST", "/api/auth/change-password"),
        ("POST", "/api/auth/reset-password"),
        ("POST", "/api/auth/register"),
        ("PUT", "/api/auth/profile"),
        ("POST", "/api/invitations/accept/abc"),
        ("POST", "/api/test/seed/annotations"),
        ("GET", "/api/debug/status"),
        ("POST", "/api/notifications/email/test"),
    ],
)
def test_credential_and_test_routes_stay_closed(method, path):
    rule, _ = _rule(method, path)
    assert not rule.allowed


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/projects/p1/tasks"),
        ("GET", "/api/projects/tasks/t1"),
        ("GET", "/api/projects/p1/next"),
        ("GET", "/api/projects/p1/my-tasks"),
        ("GET", "/api/projects/p1/task-rubrics"),
        ("POST", "/api/projects/p1/exports"),
        ("POST", "/api/projects/bulk-export"),
        ("GET", "/api/evaluations/e1/samples"),
        ("GET", "/api/data/"),
    ],
)
def test_task_content_needs_read_reference(method, path):
    """The full API does not blind reference solutions, so every route that
    returns task content needs tasks:read_reference (v1 stays the blinded
    path for ANNOTATOR keys)."""
    rule, _ = _rule(method, path)
    assert "tasks:read_reference" in rule.scopes


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/users"),
        ("PATCH", "/api/users/u1/role"),
        ("GET", "/api/feature-flags"),
        ("PUT", "/api/feature-flags/x"),
        ("POST", "/api/admin/llm-models/reseed"),
        ("GET", "/api/organizations/manage/users"),
    ],
)
def test_superadmin_routes_need_admin_platform(method, path):
    rule, _ = _rule(method, path)
    assert "admin:platform" in rule.scopes


def test_research_workflow_is_open():
    """Register a model, configure and start generation, evaluate, read results."""
    expectations = [
        ("POST", "/api/custom-models/", "models:manage"),
        ("POST", "/api/projects/", "projects:write"),
        ("PUT", "/api/projects/p1/generation-config", "runs:write"),
        ("POST", "/api/generation-tasks/projects/p1/generate", "runs:write"),
        ("GET", "/api/projects/p1/generation-status", "runs:read"),
        ("PUT", "/api/evaluations/projects/p1/evaluation-config", "evaluations:run"),
        ("POST", "/api/evaluations/run", "evaluations:run"),
        ("GET", "/api/evaluations/run/results/project/p1", "results:read"),
        ("POST", "/api/projects/p1/imports", "tasks:write"),
    ]
    for method, path, scope in expectations:
        rule, _ = _rule(method, path)
        assert rule.allowed and scope in rule.scopes, (method, path, rule)


def test_match_returns_template_and_params():
    entry, params = kr.match(get_index(app), "GET", "/api/projects/abc/tasks")
    assert entry.template == "/api/projects/{project_id}/tasks"
    assert params == {"project_id": "abc"}
    assert kr.match(get_index(app), "GET", "/api/no-such-route") == (None, None)


def test_v1_routes_are_not_indexed():
    assert all(not e.template.startswith("/api/v1") for e in get_index(app))


def test_overlay_rules_apply_to_overlay_routes_only():
    kr.register_overlay_rules(
        "pkg", [{"pattern": "/api/x*", "scopes": ["projects:read"], "methods": "read"}]
    )
    try:
        assert kr.resolve_rule("pkg", "GET", "/api/x/1").scopes == ("projects:read",)
        assert kr.resolve_rule("pkg", "POST", "/api/x/1") is None
        assert kr.resolve_rule(kr.PLATFORM_OWNER, "GET", "/api/x/1") is None
    finally:
        kr.unregister_overlay_rules("pkg")
    with pytest.raises(ValueError):
        kr.register_overlay_rules("pkg", [{"pattern": "/api/x"}])


def test_reference_spec_lists_scopes_and_omits_closed_routes():
    spec = build_reference_openapi(app, platform_only=True)
    paths = spec["paths"]
    assert "/api/auth/login" not in paths
    assert not any(p.startswith("/api/v1") for p in paths)
    op = paths["/api/projects/{project_id}"]["get"]
    assert op["x-benger-scopes"] == ["projects:read"]
    assert op["x-benger-stability"] == "unversioned"
    assert op["x-benger-project-bound"] is True
    assert "x-benger-project-bound" not in paths["/api/custom-models/"]["get"]


def _docs_dir():
    parents = Path(__file__).resolve().parents
    repo_docs = [parents[4] / "docs"] if len(parents) > 4 else []
    for candidate in (*repo_docs, Path("/docs")):
        if (candidate / "api-docs").is_dir():
            return candidate
    return None


DOCS = _docs_dir()


@pytest.mark.skipif(DOCS is None, reason="repository docs/ folder not mounted")
def test_committed_route_table_matches_rules():
    committed = (DOCS / "full-api-routes.md").read_text(encoding="utf-8")
    assert committed == routes_markdown(app), "run `make generate-public-api-docs`"

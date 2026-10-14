"""Scope vocabulary: implications, grant rules, overlay registration."""

import pytest
from fastapi import HTTPException

from app.core import scopes as sc


def test_expand_follows_implications_transitively():
    sc.register_scopes(
        {
            "ext:c": {"description": "c", "implies": []},
            "ext:b": {"description": "b", "implies": ["ext:c"]},
            "ext:a": {"description": "a", "implies": ["ext:b"]},
        }
    )
    try:
        assert sc.expand(["ext:a"]) == frozenset({"ext:a", "ext:b", "ext:c"})
    finally:
        sc.unregister_scopes(["ext:a", "ext:b", "ext:c"])


def test_builtin_implications():
    assert "tasks:read" in sc.expand(["tasks:read_reference"])
    assert "submissions:read" in sc.expand(["submissions:write"])
    assert "systems:read" in sc.expand(["systems:manage"])
    assert sc.expand(["tasks:read"]) == frozenset({"tasks:read"})


def test_scopes_satisfied():
    assert sc.scopes_satisfied(["submissions:write"], ["submissions:read"])
    assert not sc.scopes_satisfied(["submissions:read"], ["submissions:write"])
    assert sc.scopes_satisfied([], [])
    assert sc.scopes_satisfied(sc.SESSION_SCOPES, ["anything:at_all"])


def test_session_scopes_sentinel_contains_everything():
    assert "x:y" in sc.SESSION_SCOPES
    assert bool(sc.SESSION_SCOPES)
    assert sc.expand(sc.SESSION_SCOPES) is sc.SESSION_SCOPES


def test_unknown_scope_is_422():
    with pytest.raises(HTTPException) as ei:
        sc.validate_scopes_for_grant(sc.GrantContext(), "user", None, ["nope:nope"])
    assert ei.value.status_code == 422
    assert ei.value.detail["code"] == "unknown_scope"


def test_validate_returns_sorted_unique():
    out = sc.validate_scopes_for_grant(
        sc.GrantContext(), "user", None, ["tasks:read", "projects:read", "tasks:read"]
    )
    assert out == ["projects:read", "tasks:read"]


@pytest.mark.parametrize(
    "owner_type,role,ok",
    [
        ("user", None, True),
        ("org", "CONTRIBUTOR", True),
        ("org", "ANNOTATOR", False),
    ],
)
def test_reference_scope_needs_full_data_role(owner_type, role, ok):
    call = lambda: sc.validate_scopes_for_grant(  # noqa: E731
        sc.GrantContext(is_org_admin=True), owner_type, role, ["tasks:read_reference"]
    )
    if ok:
        assert call() == ["tasks:read_reference"]
    else:
        with pytest.raises(HTTPException) as ei:
            call()
        assert ei.value.status_code == 400
        assert ei.value.detail["code"] == "scope_not_grantable"


def test_keys_manage_is_personal_only():
    assert sc.validate_scopes_for_grant(sc.GrantContext(), "user", None, ["keys:manage"])
    with pytest.raises(HTTPException) as ei:
        sc.validate_scopes_for_grant(
            sc.GrantContext(is_org_admin=True), "org", "CONTRIBUTOR", ["keys:manage"]
        )
    assert ei.value.detail["code"] == "scope_not_grantable"


def test_org_admin_scope_needs_org_wide_admin():
    sc.register_scopes(
        {"ext:admin": {"description": "x", "implies": [], "grantable": "org_admin"}}
    )
    try:
        assert sc.validate_scopes_for_grant(
            sc.GrantContext(is_org_admin=True), "org", "ANNOTATOR", ["ext:admin"]
        )
        with pytest.raises(HTTPException):
            sc.validate_scopes_for_grant(
                sc.GrantContext(is_org_admin=False), "org", "ANNOTATOR", ["ext:admin"]
            )
        with pytest.raises(HTTPException):
            sc.validate_scopes_for_grant(
                sc.GrantContext(is_org_admin=True), "user", None, ["ext:admin"]
            )
    finally:
        sc.unregister_scopes(["ext:admin"])


def test_register_overlay_shape_of_benger_compliance():
    overlay = {
        "compliance:read": {"description": "Read assessments", "implies": []},
        "compliance:write": {
            "description": "Create and run assessments",
            "implies": ["compliance:read"],
        },
    }
    sc.register_scopes(overlay, source="benger_compliance")
    try:
        names = {s.name for s in sc.all_scopes()}
        assert {"compliance:read", "compliance:write"} <= names
        assert sc.expand(["compliance:write"]) == frozenset(
            {"compliance:write", "compliance:read"}
        )
        d = sc.get_scope("compliance:write").to_dict()
        assert d["description_de"] == d["description_en"] == "Create and run assessments"
        assert d["source"] == "benger_compliance"
        assert sc.validate_scopes_for_grant(
            sc.GrantContext(), "org", "ANNOTATOR", ["compliance:write"]
        )
    finally:
        sc.unregister_scopes(["compliance:read", "compliance:write"])
    assert sc.get_scope("compliance:read") is None


def test_builtin_cannot_be_overridden_and_names_are_checked():
    with pytest.raises(ValueError):
        sc.register_scopes({"tasks:read": {"description": "evil"}})
    with pytest.raises(ValueError):
        sc.register_scopes({"noscope": {"description": "x"}})
    with pytest.raises(ValueError):
        sc.register_scopes({"x:y": {"description": "x", "grantable": "everyone"}})


def test_presets_only_name_known_scopes():
    known = {s.name for s in sc.all_scopes()}
    for name, scopes in sc.SCOPE_PRESETS.items():
        assert scopes, name
        assert set(scopes) <= known, name
    catalog = sc.scope_catalog()
    assert set(catalog["presets"]) == {"benchmark_read", "benchmark_submit", "org_full"}
    assert any(s["name"] == "keys:manage" for s in catalog["scopes"])


def test_org_full_preset_is_grantable_to_contributor_org_key():
    assert sc.validate_scopes_for_grant(
        sc.GrantContext(is_org_admin=True), "org", "CONTRIBUTOR", sc.SCOPE_PRESETS["org_full"]
    )

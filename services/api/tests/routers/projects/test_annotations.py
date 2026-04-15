"""Tests for annotations router."""

import inspect


def test_annotations_router_exists():
    """Test that annotations router is importable."""
    from routers.projects.annotations import router

    assert router is not None


def test_create_annotation_route_defined():
    """Test that create annotation route exists."""
    from routers.projects.annotations import router

    routes = [r.path for r in router.routes]
    assert "/tasks/{task_id}/annotations" in routes


def test_list_annotations_route_defined():
    """Test that list annotations route exists."""
    from routers.projects.annotations import router

    # Should have both POST and GET routes for /tasks/{task_id}/annotations
    routes_with_methods = [(r.path, r.methods) for r in router.routes]
    task_annotation_routes = [
        (path, methods)
        for path, methods in routes_with_methods
        if path == "/tasks/{task_id}/annotations"
    ]

    assert len(task_annotation_routes) >= 2
    methods_list = [m for _, methods in task_annotation_routes for m in methods]
    assert "POST" in methods_list
    assert "GET" in methods_list


def test_update_annotation_route_defined():
    """Test that update annotation route exists."""
    from routers.projects.annotations import router

    routes = [r.path for r in router.routes]
    assert "/annotations/{annotation_id}" in routes


def test_update_annotation_route_method():
    """Test that update annotation route accepts PATCH."""
    from routers.projects.annotations import router

    route = next(r for r in router.routes if r.path == "/annotations/{annotation_id}")
    assert "PATCH" in route.methods


def test_list_annotations_filters_by_user():
    """Guard: endpoint must have completed_by filter and all_users parameter.

    The actual query behavior is tested in tests/container/test_annotation_isolation.py
    against a real Postgres database. This test guards against accidental removal
    of the filter from the source code.
    """
    from routers.projects.annotations import list_task_annotations

    source = inspect.getsource(list_task_annotations)

    assert "completed_by" in source, (
        "list_task_annotations must filter by completed_by to prevent data leakage"
    )

    sig = inspect.signature(list_task_annotations)
    assert "all_users" in sig.parameters, (
        "list_task_annotations must have all_users parameter"
    )
    assert sig.parameters["all_users"].default is False, (
        "all_users must default to False (user-scoped by default)"
    )

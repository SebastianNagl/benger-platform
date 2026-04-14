"""Tests for assignments router."""


def test_assignments_router_exists():
    """Test that assignments router is importable."""
    from routers.projects.assignments import router

    assert router is not None


def test_assignments_routes_defined():
    """Test that all assignment routes exist."""
    from routers.projects.assignments import router

    routes = [r.path for r in router.routes]

    assert "/{project_id}/tasks/assign" in routes
    assert "/{project_id}/tasks/{task_id}/assignments" in routes
    assert "/{project_id}/tasks/{task_id}/assignments/{assignment_id}" in routes
    assert "/{project_id}/workload" in routes
    assert "/{project_id}/my-tasks" in routes


def test_assignments_route_methods():
    """Test HTTP methods for each route."""
    from routers.projects.assignments import router

    route_methods = {}
    for route in router.routes:
        route_methods[route.path] = route.methods

    assert 'POST' in route_methods["/{project_id}/tasks/assign"]
    assert 'GET' in route_methods["/{project_id}/tasks/{task_id}/assignments"]
    assert 'DELETE' in route_methods["/{project_id}/tasks/{task_id}/assignments/{assignment_id}"]
    assert 'GET' in route_methods["/{project_id}/workload"]
    assert 'GET' in route_methods["/{project_id}/my-tasks"]

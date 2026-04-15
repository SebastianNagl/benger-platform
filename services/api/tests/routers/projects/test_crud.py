"""Tests for CRUD router."""


def test_crud_router_exists():
    """Test that CRUD router is importable."""
    from routers.projects.crud import router

    assert router is not None


def test_crud_routes_defined():
    """Test that all CRUD routes exist."""
    from routers.projects.crud import router

    routes = [r.path for r in router.routes]

    assert "/" in routes
    assert "/{project_id}" in routes
    assert "/{project_id}/recalculate-stats" in routes


def test_crud_route_methods():
    """Test HTTP methods for each route."""
    from routers.projects.crud import router

    # Collect all methods for each path (FastAPI creates separate route objects for each method)
    route_methods = {}
    for route in router.routes:
        if route.path not in route_methods:
            route_methods[route.path] = set()
        route_methods[route.path].update(route.methods)

    assert "GET" in route_methods["/"]
    assert "POST" in route_methods["/"]
    assert "GET" in route_methods["/{project_id}"]
    assert "PATCH" in route_methods["/{project_id}"]
    assert "DELETE" in route_methods["/{project_id}"]
    assert "POST" in route_methods["/{project_id}/recalculate-stats"]

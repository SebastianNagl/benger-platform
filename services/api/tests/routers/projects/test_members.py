"""Tests for members router."""


def test_members_router_exists():
    """Test that members router is importable."""
    from routers.projects.members import router

    assert router is not None


def test_members_routes_defined():
    """Test that all member routes exist."""
    from routers.projects.members import router

    routes = [r.path for r in router.routes]
    assert "/{project_id}/members" in routes
    assert "/{project_id}/members/{user_id}" in routes


def test_members_route_methods():
    """Test HTTP methods for each route."""
    from routers.projects.members import router

    # Collect all methods for each path
    route_methods = {}
    for route in router.routes:
        if route.path not in route_methods:
            route_methods[route.path] = set()
        route_methods[route.path].update(route.methods)

    assert 'GET' in route_methods["/{project_id}/members"]
    assert 'POST' in route_methods["/{project_id}/members/{user_id}"]
    assert 'DELETE' in route_methods["/{project_id}/members/{user_id}"]

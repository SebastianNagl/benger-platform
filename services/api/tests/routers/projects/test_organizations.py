"""Tests for organizations router."""


def test_organizations_router_exists():
    """Test that organizations router is importable."""
    from routers.projects.organizations import router

    assert router is not None


def test_organizations_routes_defined():
    """Test that all organization routes exist."""
    from routers.projects.organizations import router

    routes = [r.path for r in router.routes]
    assert "/{project_id}/organizations" in routes
    assert "/{project_id}/organizations/{organization_id}" in routes


def test_organizations_route_methods():
    """Test HTTP methods for each route."""
    from routers.projects.organizations import router

    # Collect all methods for each path (FastAPI creates separate route objects for each method)
    route_methods = {}
    for route in router.routes:
        if route.path not in route_methods:
            route_methods[route.path] = set()
        route_methods[route.path].update(route.methods)

    assert 'GET' in route_methods["/{project_id}/organizations"]
    assert 'POST' in route_methods["/{project_id}/organizations/{organization_id}"]
    assert 'DELETE' in route_methods["/{project_id}/organizations/{organization_id}"]

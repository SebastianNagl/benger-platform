"""Tests for bulk operations router."""


def test_bulk_router_exists():
    """Test that bulk router is importable."""
    from routers.projects.bulk import router

    assert router is not None


def test_bulk_delete_route_defined():
    """Test that bulk-delete route exists."""
    from routers.projects.bulk import router

    routes = [r.path for r in router.routes]
    assert "/bulk-delete" in routes


def test_bulk_delete_route_method():
    """Test that bulk-delete route accepts POST."""
    from routers.projects.bulk import router

    route = next(r for r in router.routes if r.path == "/bulk-delete")
    assert "POST" in route.methods


def test_bulk_archive_route_defined():
    """Test that bulk-archive route exists."""
    from routers.projects.bulk import router

    routes = [r.path for r in router.routes]
    assert "/bulk-archive" in routes


def test_bulk_archive_route_method():
    """Test that bulk-archive route accepts POST."""
    from routers.projects.bulk import router

    route = next(r for r in router.routes if r.path == "/bulk-archive")
    assert "POST" in route.methods


def test_bulk_unarchive_route_defined():
    """Test that bulk-unarchive route exists."""
    from routers.projects.bulk import router

    routes = [r.path for r in router.routes]
    assert "/bulk-unarchive" in routes


def test_bulk_unarchive_route_method():
    """Test that bulk-unarchive route accepts POST."""
    from routers.projects.bulk import router

    route = next(r for r in router.routes if r.path == "/bulk-unarchive")
    assert "POST" in route.methods

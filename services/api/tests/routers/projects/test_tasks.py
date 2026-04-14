"""Tests for tasks router."""


def test_tasks_router_exists():
    """Test that tasks router is importable."""
    from routers.projects.tasks import router

    assert router is not None


def test_tasks_routes_defined():
    """Test that all task routes exist."""
    from routers.projects.tasks import router

    routes = [r.path for r in router.routes]

    # Core task routes
    assert "/{project_id}/tasks" in routes
    assert "/{project_id}/next" in routes
    assert "/tasks/{task_id}" in routes
    assert "/{project_id}/tasks/{task_id}" in routes

    # Metadata routes
    assert "/tasks/{task_id}/metadata" in routes
    assert "/tasks/bulk-metadata" in routes

    # Bulk operations
    assert "/{project_id}/tasks/bulk-delete" in routes
    assert "/{project_id}/tasks/bulk-export" in routes
    assert "/{project_id}/tasks/bulk-archive" in routes


def test_tasks_route_methods():
    """Test HTTP methods for each route."""
    from routers.projects.tasks import router

    route_methods = {}
    for route in router.routes:
        route_methods[route.path] = route.methods

    # GET routes
    assert "GET" in route_methods["/{project_id}/tasks"]
    assert "GET" in route_methods["/{project_id}/next"]
    assert "GET" in route_methods["/tasks/{task_id}"]

    # UPDATE routes
    assert "PUT" in route_methods["/{project_id}/tasks/{task_id}"]
    assert "PATCH" in route_methods["/tasks/{task_id}/metadata"]
    assert "PATCH" in route_methods["/tasks/bulk-metadata"]

    # POST routes (bulk operations)
    assert "POST" in route_methods["/{project_id}/tasks/bulk-delete"]
    assert "POST" in route_methods["/{project_id}/tasks/bulk-export"]
    assert "POST" in route_methods["/{project_id}/tasks/bulk-archive"]


def test_tasks_route_count():
    """Test that we have exactly 11 routes."""
    from routers.projects.tasks import router

    # 11 routes total:
    # 1. GET /{project_id}/tasks
    # 2. GET /{project_id}/next
    # 3. GET /tasks/{task_id}
    # 4. PUT /{project_id}/tasks/{task_id}
    # 5. PATCH /tasks/{task_id}/metadata
    # 6. PATCH /tasks/bulk-metadata
    # 7. POST /{project_id}/tasks/bulk-delete
    # 8. POST /{project_id}/tasks/bulk-export
    # 9. POST /{project_id}/tasks/bulk-archive
    # 10. POST /{project_id}/tasks/{task_id}/skip
    # 11. GET /{project_id}/task-fields
    assert len(router.routes) == 11


def test_tasks_route_names():
    """Test that route functions have correct names."""
    from routers.projects.tasks import router

    route_names = [r.name for r in router.routes]

    assert "list_project_tasks" in route_names
    assert "get_next_task" in route_names
    assert "get_task" in route_names
    assert "update_task_data" in route_names
    assert "update_task_metadata" in route_names
    assert "bulk_update_task_metadata" in route_names
    assert "bulk_delete_tasks" in route_names
    assert "bulk_export_tasks" in route_names
    assert "bulk_archive_tasks" in route_names

"""
Performance tests for project API endpoints

These tests verify that optimized query patterns are used to avoid N+1 problems.
"""


import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine


class QueryCounter:
    """Helper class to count SQL queries executed"""

    def __init__(self):
        self.count = 0
        self.queries = []

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        self.count += 1
        self.queries.append(statement)


@pytest.mark.integration
def test_list_projects_query_count(client, test_db, auth_headers, test_users):
    """Verify list_projects uses optimized queries (not N+1)"""

    import uuid

    from project_models import Annotation, Project, Task

    # Use first test user
    test_user = test_users[0]

    # Create 10 test projects with varying stats
    projects = []
    for i in range(10):
        project = Project(
            id=str(uuid.uuid4()),
            title=f"Test Project {i}",
            description=f"Project {i} description",
            created_by=test_user.id,
        )
        test_db.add(project)
        projects.append(project)

        # Add varying number of tasks to each project
        for j in range(i + 1):
            task = Task(
                id=str(uuid.uuid4()),
                project_id=project.id,
                inner_id=j + 1,
                data={"text": f"Task {j}"},
                is_labeled=(j % 2 == 0),  # Half completed
            )
            test_db.add(task)

            # Add annotation to some tasks
            if j % 3 == 0:
                annotation = Annotation(
                    id=str(uuid.uuid4()),
                    project_id=project.id,
                    task_id=task.id,
                    completed_by=test_user.id,
                    result=[],
                    was_cancelled=False,
                )
                test_db.add(annotation)

    test_db.commit()

    # Set up query counter
    counter = QueryCounter()
    event.listen(Engine, "before_cursor_execute", counter)

    try:
        # Make request to list projects with admin headers
        admin_headers = auth_headers["admin"]
        response = client.get("/api/projects?page=1&page_size=100", headers=admin_headers)
        assert response.status_code == 200

        # Verify query count
        # Expected queries:
        # 1. Count query for pagination
        # 2. Main project query with joinedloads
        # 3. Task stats batch query
        # 4. Annotation stats batch query
        # 5-6. Possible additional queries for organizations/memberships
        #
        # Should be <= 10 queries (not 1 + 10*3 = 31 queries)
        assert counter.count <= 10, (
            f"Too many queries: {counter.count}. "
            f"Expected <= 10, got {counter.count}. "
            f"This indicates N+1 query problem."
        )

        # Verify response contains at least our test projects
        data = response.json()
        created_ids = {p.id for p in projects}
        returned_ids = {item["id"] for item in data["items"]}
        assert created_ids.issubset(returned_ids), (
            f"Missing test projects in response. "
            f"Expected {len(created_ids)} test projects, found {len(created_ids & returned_ids)}"
        )

        # Verify stats are populated correctly
        for item in data["items"]:
            assert "task_count" in item
            assert "annotation_count" in item
            assert "completed_tasks_count" in item
            assert item["task_count"] >= 0
            assert item["annotation_count"] >= 0
            assert item["completed_tasks_count"] >= 0

    finally:
        # Clean up event listener
        event.remove(Engine, "before_cursor_execute", counter)


@pytest.mark.integration
def test_list_projects_with_zero_stats(client, test_db, auth_headers, test_users):
    """Verify projects with no tasks/annotations show 0, not NULL"""

    import uuid

    from project_models import Project

    test_user = test_users[0]

    # Create project with no tasks
    project = Project(
        id=str(uuid.uuid4()),
        title="Empty Project",
        description="Project with no tasks",
        created_by=test_user.id,
    )
    test_db.add(project)
    test_db.commit()

    # Fetch project list
    admin_headers = auth_headers["admin"]
    response = client.get("/api/projects?page=1&page_size=100", headers=admin_headers)
    assert response.status_code == 200

    data = response.json()
    empty_project = next((p for p in data["items"] if p["title"] == "Empty Project"), None)

    assert empty_project is not None
    assert empty_project["task_count"] == 0
    assert empty_project["annotation_count"] == 0
    assert empty_project["completed_tasks_count"] == 0
    assert empty_project["progress_percentage"] == 0.0


@pytest.mark.integration
def test_list_projects_progress_calculation(client, test_db, auth_headers, test_users):
    """Verify progress percentage is calculated correctly"""

    import uuid

    from project_models import Project, Task

    test_user = test_users[0]

    # Create project with 10 tasks, 3 completed
    project = Project(
        id=str(uuid.uuid4()),
        title="Progress Test Project",
        description="Testing progress calculation",
        created_by=test_user.id,
    )
    test_db.add(project)

    for i in range(10):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"Task {i}"},
            is_labeled=(i < 3),  # First 3 are completed
        )
        test_db.add(task)

    test_db.commit()

    # Fetch project list
    admin_headers = auth_headers["admin"]
    response = client.get("/api/projects?page=1&page_size=100", headers=admin_headers)
    assert response.status_code == 200

    data = response.json()
    test_project = next((p for p in data["items"] if p["title"] == "Progress Test Project"), None)

    assert test_project is not None
    assert test_project["task_count"] == 10
    assert test_project["completed_tasks_count"] == 3
    assert test_project["progress_percentage"] == 30.0


@pytest.mark.integration
def test_batch_stats_function_directly(test_db, test_users):
    """Test the batch stats calculation function directly"""

    import uuid

    from project_models import Project, Task
    from projects_api import calculate_project_stats_batch

    test_user = test_users[0]

    # Create 5 projects
    project_ids = []
    for i in range(5):
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            title=f"Batch Test Project {i}",
            description=f"Project {i}",
            created_by=test_user.id,
        )
        test_db.add(project)
        project_ids.append(project_id)

        # Add tasks
        for j in range(i + 1):
            task = Task(
                id=str(uuid.uuid4()),
                project_id=project_id,
                inner_id=j + 1,
                data={"text": f"Task {j}"},
                is_labeled=(j == 0),  # Only first task is completed
            )
            test_db.add(task)

    test_db.commit()

    # Call batch stats function
    stats_map = calculate_project_stats_batch(test_db, project_ids)

    # Verify results
    assert len(stats_map) == 5

    for i, project_id in enumerate(project_ids):
        assert project_id in stats_map
        stats = stats_map[project_id]
        assert stats["task_count"] == i + 1
        assert stats["completed_tasks_count"] == 1  # Only first task is completed
        assert stats["annotation_count"] == 0  # No annotations


@pytest.mark.integration
def test_batch_stats_empty_list(test_db):
    """Test batch stats with empty project list"""

    from projects_api import calculate_project_stats_batch

    stats_map = calculate_project_stats_batch(test_db, [])
    assert stats_map == {}


@pytest.mark.integration
def test_batch_stats_with_annotations(test_db, test_users):
    """Test batch stats includes annotation counts"""

    import uuid

    from project_models import Annotation, Project, Task
    from projects_api import calculate_project_stats_batch

    test_user = test_users[0]

    # Create project
    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        title="Annotation Test Project",
        description="Testing annotation stats",
        created_by=test_user.id,
    )
    test_db.add(project)

    # Add tasks with annotations
    for i in range(5):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project_id,
            inner_id=i + 1,
            data={"text": f"Task {i}"},
            is_labeled=True,
        )
        test_db.add(task)

        # Add 2 annotations per task, 1 cancelled
        for j in range(2):
            annotation = Annotation(
                id=str(uuid.uuid4()),
                project_id=project_id,
                task_id=task.id,
                completed_by=test_user.id,
                result=[{"from_name": "label", "to_name": "text", "type": "choices", "value": {"choices": ["positive"]}}],
                was_cancelled=(j == 1),  # Second annotation is cancelled
            )
            test_db.add(annotation)

    test_db.commit()

    # Call batch stats function
    stats_map = calculate_project_stats_batch(test_db, [project_id])

    # Verify results
    assert project_id in stats_map
    stats = stats_map[project_id]
    assert stats["task_count"] == 5
    assert stats["completed_tasks_count"] == 5
    assert stats["annotation_count"] == 5  # Only non-cancelled annotations

"""Tests for project helpers module."""

from unittest.mock import Mock

from routers.projects.helpers import (
    calculate_generation_stats,
    calculate_project_stats,
    calculate_project_stats_batch,
    get_project_organizations,
    get_user_with_memberships,
)


def test_calculate_project_stats_batch_with_projects():
    """Test batch stats calculation returns correct structure."""
    # Mock database session
    db = Mock()

    # Mock query results
    task_stats = [
        Mock(project_id='p1', task_count=10, completed_tasks_count=5),
        Mock(project_id='p2', task_count=20, completed_tasks_count=15),
    ]

    annotation_stats = [
        Mock(project_id='p1', annotation_count=8),
        Mock(project_id='p2', annotation_count=18),
    ]

    # Setup mock query chain for task stats
    task_query_mock = Mock()
    task_query_mock.filter.return_value.group_by.return_value.all.return_value = task_stats

    # Setup mock query chain for annotation stats
    annotation_query_mock = Mock()
    annotation_query_mock.filter.return_value.group_by.return_value.all.return_value = (
        annotation_stats
    )

    # Setup db.query to return different mocks on consecutive calls
    db.query.side_effect = [task_query_mock, annotation_query_mock]

    # Call function
    result = calculate_project_stats_batch(db, ['p1', 'p2'])

    # Assertions
    assert 'p1' in result
    assert 'p2' in result
    assert result['p1']['task_count'] == 10
    assert result['p1']['completed_tasks_count'] == 5
    assert result['p1']['annotation_count'] == 8
    assert result['p2']['task_count'] == 20
    assert result['p2']['completed_tasks_count'] == 15
    assert result['p2']['annotation_count'] == 18


def test_calculate_project_stats_batch_empty_list():
    """Test batch stats with empty project list."""
    db = Mock()
    result = calculate_project_stats_batch(db, [])
    assert result == {}


def test_calculate_project_stats_batch_missing_annotations():
    """Test batch stats when some projects have no annotations."""
    db = Mock()

    # Only p1 has task stats, only p2 has annotation stats
    task_stats = [Mock(project_id='p1', task_count=10, completed_tasks_count=5)]
    annotation_stats = [Mock(project_id='p2', annotation_count=18)]

    task_query_mock = Mock()
    task_query_mock.filter.return_value.group_by.return_value.all.return_value = task_stats

    annotation_query_mock = Mock()
    annotation_query_mock.filter.return_value.group_by.return_value.all.return_value = (
        annotation_stats
    )

    db.query.side_effect = [task_query_mock, annotation_query_mock]

    result = calculate_project_stats_batch(db, ['p1', 'p2'])

    # p1 should have task stats but zero annotations
    assert result['p1']['task_count'] == 10
    assert result['p1']['completed_tasks_count'] == 5
    assert result['p1']['annotation_count'] == 0

    # p2 should have annotation stats but zero task stats
    assert result['p2']['task_count'] == 0
    assert result['p2']['completed_tasks_count'] == 0
    assert result['p2']['annotation_count'] == 18


def test_calculate_project_stats():
    """Test single project stats calculation."""
    db = Mock()
    response = Mock()

    # Setup task count query
    task_count_query = Mock()
    task_count_query.filter.return_value.count.return_value = 10

    # Setup annotation count query
    annotation_count_query = Mock()
    annotation_count_query.filter.return_value.count.return_value = 8

    # Setup completed tasks query
    completed_tasks_query = Mock()
    completed_tasks_query.filter.return_value.count.return_value = 5

    # db.query returns different mocks for each model
    db.query.side_effect = [task_count_query, annotation_count_query, completed_tasks_query]

    calculate_project_stats(db, 'project-1', response)

    # Verify response was populated
    assert response.task_count == 10
    assert response.annotation_count == 8
    assert response.completed_tasks_count == 5
    assert response.progress_percentage == 50.0


def test_calculate_project_stats_zero_tasks():
    """Test stats calculation when project has no tasks."""
    db = Mock()
    response = Mock()

    # All counts are zero
    db.query.return_value.filter.return_value.count.return_value = 0

    calculate_project_stats(db, 'empty-project', response)

    assert response.task_count == 0
    assert response.progress_percentage == 0.0


def test_get_user_with_memberships():
    """Test fetching user with memberships."""
    db = Mock()
    mock_user = Mock()

    query_mock = Mock()
    query_mock.options.return_value.filter.return_value.first.return_value = mock_user
    db.query.return_value = query_mock

    result = get_user_with_memberships(db, 'user-1')

    assert result == mock_user
    # Verify joinedload was used for eager loading
    db.query.assert_called_once()


def test_get_project_organizations():
    """Test fetching project organizations."""
    db = Mock()

    # Mock organization objects
    org1 = Mock()
    org1.id = 'org-1'
    org1.name = 'Organization 1'

    org2 = Mock()
    org2.id = 'org-2'
    org2.name = 'Organization 2'

    # Mock project organization objects
    po1 = Mock()
    po1.organization = org1

    po2 = Mock()
    po2.organization = org2

    query_mock = Mock()
    query_mock.options.return_value.filter.return_value.all.return_value = [po1, po2]
    db.query.return_value = query_mock

    result = get_project_organizations(db, 'project-1')

    assert len(result) == 2
    assert result[0]['id'] == 'org-1'
    assert result[0]['name'] == 'Organization 1'
    assert result[1]['id'] == 'org-2'
    assert result[1]['name'] == 'Organization 2'


def test_get_project_organizations_filters_missing():
    """Test that organizations with missing references are filtered out."""
    db = Mock()

    org1 = Mock()
    org1.id = 'org-1'
    org1.name = 'Organization 1'

    po1 = Mock()
    po1.organization = org1

    po2 = Mock()
    po2.organization = None  # Missing organization reference

    query_mock = Mock()
    query_mock.options.return_value.filter.return_value.all.return_value = [po1, po2]
    db.query.return_value = query_mock

    result = get_project_organizations(db, 'project-1')

    # Should only include po1, not po2 with missing organization
    assert len(result) == 1
    assert result[0]['id'] == 'org-1'


def test_calculate_generation_stats():
    """Test generation stats calculation."""
    db = Mock()
    project = Mock()
    response = Mock()

    # Setup project with generation config
    project.id = 'project-1'
    project.generation_config = {
        'prompt_structures': {'structure1': {}},
        'selected_configuration': {'models': ['model1', 'model2']},
    }

    # Mock generation_count query (new in Statistiken tile)
    generation_count_query = Mock()
    generation_count_query.join.return_value.filter.return_value.scalar.return_value = 0

    # Mock task IDs query
    task_id_mock1 = Mock()
    task_id_mock1.id = 'task-1'
    task_id_mock2 = Mock()
    task_id_mock2.id = 'task-2'

    task_query = Mock()
    task_query.filter.return_value.all.return_value = [task_id_mock1, task_id_mock2]

    # Mock generation count query
    gen_query = Mock()
    gen_query.filter.return_value.count.return_value = 4  # 2 tasks * 2 models

    db.query.side_effect = [generation_count_query, task_query, gen_query]

    # Set task_count on response (this would be set by calculate_project_stats)
    response.task_count = 2

    calculate_generation_stats(db, project, response)

    assert response.generation_config_ready == True
    assert response.generation_prompts_ready == True
    assert response.generation_models_count == 2
    assert response.generation_completed == True


def test_calculate_generation_stats_incomplete():
    """Test generation stats when generation is not complete."""
    db = Mock()
    project = Mock()
    response = Mock()

    project.id = 'project-1'
    project.generation_config = {
        'prompt_structures': {'structure1': {}},
        'selected_configuration': {'models': ['model1', 'model2']},
    }

    generation_count_query = Mock()
    generation_count_query.join.return_value.filter.return_value.scalar.return_value = 0

    task_id_mock = Mock()
    task_id_mock.id = 'task-1'

    task_query = Mock()
    task_query.filter.return_value.all.return_value = [task_id_mock]

    # Only 1 generation complete, but 2 expected (1 task * 2 models)
    gen_query = Mock()
    gen_query.filter.return_value.count.return_value = 1

    db.query.side_effect = [generation_count_query, task_query, gen_query]
    response.task_count = 1

    calculate_generation_stats(db, project, response)

    assert response.generation_models_count == 2
    assert response.generation_completed == False

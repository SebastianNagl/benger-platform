"""
Shared fixtures and configuration for integration tests
"""

import asyncio
import os
import pytest
import redis
import requests
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Generator

# Import from services for testing
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../services/api'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../services/workers'))

# Use conditional imports for when modules are available
try:
    from database import Base, get_db
    from auth_module import create_access_token, create_user
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    Base = None
    get_db = None
    create_access_token = None
    create_user = None


class IntegrationTestConfig:
    """Configuration for integration tests"""
    
    def __init__(self):
        self.api_url = os.getenv('API_URL', 'http://localhost:8000')
        self.frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        self.postgres_url = os.getenv('POSTGRES_URL', 'postgresql://postgres:postgres@localhost:5432/benger')
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.test_environment = os.getenv('TEST_ENVIRONMENT', 'local')


@pytest.fixture(scope="session")
def config():
    """Test configuration fixture"""
    return IntegrationTestConfig()


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def db_engine(config):
    """Create database engine for integration tests"""
    if not DB_AVAILABLE:
        pytest.fail("Database modules not available - ensure API dependencies are installed")
    engine = create_engine(config.postgres_url)
    # Ensure tables exist
    if Base:
        Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create database session for each test"""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="session")
def redis_client(config):
    """Create Redis client for integration tests"""
    client = redis.from_url(config.redis_url)
    
    # Test connection
    try:
        client.ping()
    except redis.ConnectionError:
        pytest.fail("Redis not available - ensure Redis is running at " + config.redis_url)
    
    yield client
    
    # Cleanup test keys
    for key in client.scan_iter(match="test:*"):
        client.delete(key)


@pytest.fixture
def api_client(config):
    """HTTP client for API testing"""
    class APIClient:
        def __init__(self, base_url: str):
            self.base_url = base_url
            self.session = requests.Session()
            self.auth_token = None
        
        def set_auth_token(self, token: str):
            """Set authentication token for requests"""
            self.auth_token = token
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        def clear_auth(self):
            """Clear authentication"""
            self.auth_token = None
            if "Authorization" in self.session.headers:
                del self.session.headers["Authorization"]
        
        def get(self, endpoint: str, **kwargs):
            return self.session.get(f"{self.base_url}{endpoint}", **kwargs)
        
        def post(self, endpoint: str, **kwargs):
            return self.session.post(f"{self.base_url}{endpoint}", **kwargs)
        
        def put(self, endpoint: str, **kwargs):
            return self.session.put(f"{self.base_url}{endpoint}", **kwargs)
        
        def delete(self, endpoint: str, **kwargs):
            return self.session.delete(f"{self.base_url}{endpoint}", **kwargs)
        
        def login(self, username: str, password: str):
            """Login and set auth token"""
            response = self.post("/auth/login", json={
                "username": username,
                "password": password
            })
            response.raise_for_status()
            data = response.json()
            self.set_auth_token(data["access_token"])
            return data
        
        def wait_for_health(self, timeout: int = 30):
            """Wait for API to be healthy"""
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = self.get("/health")
                    if response.status_code == 200:
                        return True
                except requests.ConnectionError:
                    pass
                time.sleep(1)
            return False
    
    client = APIClient(config.api_url)

    # Wait for API to be ready
    if not client.wait_for_health():
        pytest.fail("API not available at " + config.api_url + " - ensure E2E stack is running")

    yield client


@pytest.fixture
def frontend_client(config):
    """HTTP client for frontend testing"""
    class FrontendClient:
        def __init__(self, base_url: str):
            self.base_url = base_url
            self.session = requests.Session()
        
        def get(self, path: str = "/", **kwargs):
            return self.session.get(f"{self.base_url}{path}", **kwargs)
        
        def wait_for_health(self, timeout: int = 30):
            """Wait for frontend to be ready"""
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = self.get("/")
                    if response.status_code == 200:
                        return True
                except requests.ConnectionError:
                    pass
                time.sleep(1)
            return False
    
    client = FrontendClient(config.frontend_url)

    # Wait for frontend to be ready
    if not client.wait_for_health():
        pytest.fail("Frontend not available at " + config.frontend_url + " - ensure E2E stack is running")

    yield client


@pytest.fixture
def test_user(db_session):
    """Create a test user for integration tests"""
    if not create_user:
        pytest.skip("create_user not available - API modules not installed")

    user = create_user(
        db=db_session,
        username="integration_test_user",
        email="integration_test@example.com",
        name="Integration Test User",
        password="test_password_123",
        is_superadmin=False
    )
    db_session.commit()

    yield user

    # Cleanup
    db_session.delete(user)
    db_session.commit()


@pytest.fixture
def test_admin_user(db_session):
    """Create a test admin user for integration tests"""
    if not create_user:
        pytest.skip("create_user not available - API modules not installed")

    user = create_user(
        db=db_session,
        username="integration_test_admin",
        email="integration_test_admin@example.com",
        name="Integration Test Admin",
        password="test_admin_password_123",
        is_superadmin=True
    )
    db_session.commit()

    yield user

    # Cleanup
    db_session.delete(user)
    db_session.commit()


@pytest.fixture
def authenticated_api_client(api_client, test_user):
    """API client authenticated as test user"""
    api_client.login(test_user.username, "test_password_123")
    yield api_client
    api_client.clear_auth()


@pytest.fixture
def authenticated_admin_client(api_client, test_admin_user):
    """API client authenticated as admin user"""
    api_client.login(test_admin_user.username, "test_admin_password_123")
    yield api_client
    api_client.clear_auth()


@pytest.fixture
def sample_project(db_session, test_user):
    """Create a sample project for testing"""
    from models import Project
    
    project = Project(
        id="integration-test-project",
        name="Integration Test Project",
        description="Project for integration testing",
        created_by=test_user.id
    )
    
    db_session.add(project)
    db_session.commit()
    
    yield project
    
    # Cleanup
    db_session.delete(project)
    db_session.commit()


@pytest.fixture
def sample_task(db_session, test_user, sample_project):
    """Create a sample task for testing"""
    from models import OldTask
    
    task = OldTask(
        id="integration-test-task",
        name="Integration Test Task",
        description="Task for integration testing",
        task_type_id="qa",
        data={
            "question": "What is the capital of France?",
            "reference_answers": ["Paris"]
        },
        created_by=test_user.id,
        project_id=sample_project.id,
        organization_ids=["tum"],
        visibility="private"
    )
    
    db_session.add(task)
    db_session.commit()
    
    yield task
    
    # Cleanup
    db_session.delete(task)
    db_session.commit()


# Pytest markers for different test categories
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "frontend_api: mark test as frontend-API integration test"
    )
    config.addinivalue_line(
        "markers", "api_database: mark test as API-database integration test"
    )
    config.addinivalue_line(
        "markers", "api_workers: mark test as API-workers integration test"
    )
    config.addinivalue_line(
        "markers", "websocket: mark test as WebSocket integration test"
    )
    config.addinivalue_line(
        "markers", "cross_service: mark test as cross-service integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
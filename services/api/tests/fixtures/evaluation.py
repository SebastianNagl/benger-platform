"""Evaluation and organization fixtures for BenGER API tests.

Provides test evaluation types, organizations, and test data helpers.
"""

import uuid
from datetime import datetime
from typing import Dict, List

import pytest
from sqlalchemy.orm import Session

from models import EvaluationType, Organization, OrganizationMembership, User


@pytest.fixture(scope="function")
def test_evaluation_types(test_db: Session) -> List[EvaluationType]:
    """Create test evaluation types in the database."""
    eval_types_data = [
        {
            "id": "accuracy",
            "name": "Accuracy",
            "description": "Classification accuracy",
            "category": "classification",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["test_classification", "text_classification"],
            "is_active": True,
        },
        {
            "id": "f1",
            "name": "F1 Score",
            "description": "F1 score",
            "category": "classification",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": [
                "test_classification",
                "test_qa",
                "text_classification",
                "qa_reasoning",
            ],
            "is_active": True,
        },
        {
            "id": "exact_match",
            "name": "Exact Match",
            "description": "Exact match accuracy",
            "category": "qa",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["test_qa", "qa_reasoning"],
            "is_active": True,
        },
        {
            "id": "token_f1",
            "name": "Token F1",
            "description": "Token-level F1 score",
            "category": "qa",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["qa_reasoning"],
            "is_active": True,
        },
        {
            "id": "precision",
            "name": "Precision",
            "description": "Classification precision",
            "category": "classification",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["text_classification"],
            "is_active": True,
        },
        {
            "id": "recall",
            "name": "Recall",
            "description": "Classification recall",
            "category": "classification",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["text_classification"],
            "is_active": True,
        },
    ]

    eval_types = []
    for eval_type_data in eval_types_data:
        eval_type = EvaluationType(**eval_type_data)
        test_db.add(eval_type)
        eval_types.append(eval_type)

    test_db.commit()
    return eval_types


@pytest.fixture(scope="function")
def test_org(test_db: Session, test_users) -> Organization:
    """Create a test organization with all required fields."""
    org = Organization(
        id=str(uuid.uuid4()),
        name="Test Organization",
        slug="test-organization",
        display_name="Test Organization Display",
        description="A test organization for testing",
        created_at=datetime.utcnow(),
    )
    test_db.add(org)
    test_db.commit()

    # Create organization memberships for all 4 test users
    # [0] admin (superadmin) = ORG_ADMIN, [1] contributor = CONTRIBUTOR,
    # [2] annotator = ANNOTATOR, [3] org_admin (non-superadmin) = ORG_ADMIN
    roles = ["ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR", "ORG_ADMIN"]
    for i, user in enumerate(test_users[:4]):
        membership = OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role=roles[i],
            joined_at=datetime.utcnow(),
        )
        test_db.add(membership)
    test_db.commit()

    return org


@pytest.fixture(scope="function")
def test_org_with_members(test_db: Session, test_users: List[User]) -> Organization:
    """Create a test organization with members."""
    org = Organization(
        id=str(uuid.uuid4()),
        name="Test Org With Members",
        slug="test-org-members",
        display_name="Test Org Members Display",
        description="A test organization with members",
        created_by=test_users[0].id,
        created_at=datetime.utcnow(),
    )
    test_db.add(org)
    test_db.commit()

    # Add members with different roles (use correct uppercase enum values)
    roles = ["ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR", "ORG_ADMIN"]
    for i, user in enumerate(test_users[:4]):
        membership = OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role=roles[i % len(roles)],
            joined_at=datetime.utcnow(),
        )
        test_db.add(membership)

    test_db.commit()
    return org


@pytest.fixture(scope="function")
def sample_evaluation_data() -> Dict:
    """Sample evaluation data for testing."""
    return {
        "task_id": "test-task-id",
        "model_name": "test-model",
        "evaluation_type": "accuracy",
        "config": {"batch_size": 32},
    }


@pytest.fixture(scope="function")
def security_test_data() -> Dict:
    """Security test data for testing various attack vectors."""
    return {
        "sql_injection_payloads": [
            "' OR '1'='1",
            "'; DROP TABLE users;--",
            "' UNION SELECT * FROM users--",
            "admin'--",
            "' OR 1=1#",
            "'; INSERT INTO users VALUES ('hacker', 'password');--",
        ],
        "xss_payloads": [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<svg onload=alert('XSS')>",
            "';alert('XSS');//",
            "<iframe src='javascript:alert(\"XSS\")'></iframe>",
        ],
        "invalid_tokens": [
            "invalid_token",
            "",
            "Bearer invalid",
            "malformed.jwt.token",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature",
            "not.a.jwt",
            "null",
            "undefined",
        ],
    }


@pytest.fixture(scope="function")
def performance_config() -> Dict:
    """Performance test configuration."""
    return {
        "max_response_time": 2.0,  # seconds
        "concurrent_users": 5,
        "max_tasks_per_batch": 100,
        "timeout_limit": 30.0,  # seconds
        "memory_limit_mb": 512,
    }

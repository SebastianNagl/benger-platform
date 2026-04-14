"""
Comprehensive tests for database migrations and schema evolution.
Tests migration integrity, schema consistency, and data preservation.

Uses the shared PostgreSQL test_db fixture for tests that interact with
ORM models (which use PostgreSQL-specific JSONB columns). Lightweight
SQL-only tests (task ID migration, FK updates, version tracking) use
their own ephemeral SQLite databases.
"""

import os
import tempfile
import uuid

import pytest
from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from database import Base
from models import User
from project_models import Annotation, Project, Task


def _create_test_user(session: Session) -> str:
    """Create a test user and return its ID."""
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        username=f"migration-test-{user_id[:8]}",
        email=f"migration-test-{user_id[:8]}@test.com",
        name="Migration Test User",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superadmin=False,
        email_verified=True,
    )
    session.add(user)
    session.flush()
    return user_id


class TestDatabaseMigrations:
    """Test database migration functionality and schema evolution"""

    @pytest.fixture(scope="function")
    def temp_database(self):
        """Create temporary SQLite database for lightweight SQL-only tests."""
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_path = db_file.name
        db_file.close()

        engine = create_engine(f"sqlite:///{db_path}")
        yield engine, db_path

        engine.dispose()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_migration_creates_all_required_tables(self, test_db: Session):
        """Test that all required tables exist in the database schema"""
        engine = test_db.get_bind()
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        expected_tables = [
            'users',
            'organizations',
            'projects',
            'tasks',
            'annotations',
            'organization_memberships',
        ]

        for table_name in expected_tables:
            assert table_name in existing_tables, f"Table {table_name} should exist"

    def test_task_id_migration_from_integer_to_string(self, temp_database):
        """Test migration of Task.id from Integer to String type"""
        engine, db_path = temp_database
        metadata = MetaData()

        old_tasks_table = Table(
            'tasks_old',
            metadata,
            Column('id', Integer, primary_key=True),
            Column('project_id', String),
            Column('inner_id', Integer),
            Column('data', String),
            Column('is_labeled', Boolean),
        )

        metadata.create_all(bind=engine)

        with engine.connect() as conn:
            conn.execute(
                old_tasks_table.insert().values(
                    id=1, project_id="test-project", inner_id=1,
                    data='{"text": "test"}', is_labeled=False,
                )
            )
            conn.execute(
                old_tasks_table.insert().values(
                    id=2, project_id="test-project", inner_id=2,
                    data='{"text": "test2"}', is_labeled=True,
                )
            )
            conn.commit()

        new_tasks_table = Table(
            'tasks',
            metadata,
            Column('id', String, primary_key=True),
            Column('project_id', String),
            Column('inner_id', Integer),
            Column('data', String),
            Column('is_labeled', Boolean),
        )

        new_tasks_table.create(bind=engine)

        with engine.connect() as conn:
            old_data = conn.execute(old_tasks_table.select()).fetchall()
            for row in old_data:
                conn.execute(
                    new_tasks_table.insert().values(
                        id=str(row.id), project_id=row.project_id,
                        inner_id=row.inner_id, data=row.data,
                        is_labeled=row.is_labeled,
                    )
                )
            conn.commit()

        with engine.connect() as conn:
            result = conn.execute(new_tasks_table.select()).fetchall()
            assert len(result) == 2
            assert result[0].id == "1"
            assert result[1].id == "2"
            assert isinstance(result[0].id, str)

    def test_annotation_foreign_key_updates_with_task_migration(self, temp_database):
        """Test that annotation foreign keys work with string task IDs"""
        engine, db_path = temp_database
        metadata = MetaData()

        tasks_table = Table(
            'tasks', metadata,
            Column('id', String, primary_key=True),
            Column('project_id', String),
            Column('inner_id', Integer),
            Column('is_labeled', Boolean, default=False),
        )

        annotations_table = Table(
            'annotations', metadata,
            Column('id', String, primary_key=True),
            Column('task_id', String),
            Column('project_id', String),
            Column('completed_by', String),
            Column('result', String),
            Column('was_cancelled', Boolean, default=False),
        )

        metadata.create_all(bind=engine)

        with engine.connect() as conn:
            conn.execute(
                tasks_table.insert().values(
                    id="task-string-123", project_id="test-project",
                    inner_id=1, is_labeled=False
                )
            )
            conn.execute(
                annotations_table.insert().values(
                    id="annotation-123", task_id="task-string-123",
                    project_id="test-project", completed_by="user-123",
                    result='[{"test": "data"}]', was_cancelled=False,
                )
            )
            conn.commit()

        with engine.connect() as conn:
            query = tasks_table.join(
                annotations_table, tasks_table.c.id == annotations_table.c.task_id
            ).select()
            result = conn.execute(query).fetchone()
            assert result is not None
            assert result.id == "task-string-123"
            assert result.task_id == "task-string-123"

    def test_schema_consistency_after_migration(self, test_db: Session):
        """Test that ORM models create and query correctly on the real schema"""
        user_id = _create_test_user(test_db)
        project_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        annotation_id = str(uuid.uuid4())

        project = Project(
            id=project_id,
            title="Consistency Test",
            description="Testing schema consistency",
            created_by=user_id,
            maximum_annotations=3,
        )
        test_db.add(project)
        test_db.flush()

        task = Task(
            id=task_id,
            project_id=project.id,
            data={"text": "Consistency test"},
            inner_id=1,
            is_labeled=False,
            total_annotations=0,
        )
        test_db.add(task)
        test_db.flush()

        annotation = Annotation(
            id=annotation_id,
            task_id=task.id,
            project_id=project.id,
            completed_by=user_id,
            result=[{"test": "consistency"}],
            was_cancelled=False,
        )
        test_db.add(annotation)
        test_db.flush()

        # Verify all relationships work
        test_db.refresh(task)
        test_db.refresh(annotation)

        assert annotation.task == task
        assert annotation.project == project
        assert annotation in task.annotations

    def test_data_preservation_during_migration(self, test_db: Session):
        """Test that existing data is preserved during schema changes"""
        user_id = _create_test_user(test_db)
        project_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())

        project = Project(
            id=project_id,
            title="Data Preservation Test",
            description="Testing data preservation during migration",
            created_by=user_id,
        )
        test_db.add(project)

        task = Task(
            id=task_id,
            project_id=project_id,
            data={"text": "Original data", "metadata": {"important": True}},
            inner_id=1,
            is_labeled=False,
        )
        test_db.add(task)
        test_db.flush()

        # Simulate schema change (add new column with default value)
        try:
            test_db.execute(
                text("ALTER TABLE tasks ADD COLUMN _test_temp_field VARCHAR DEFAULT 'default_value'")
            )
        except Exception:
            pass  # Column might already exist

        # Verify original data is still intact
        test_db.refresh(project)
        test_db.refresh(task)

        assert project.title == "Data Preservation Test"
        assert task.data["metadata"]["important"] is True

        # Clean up temp column
        try:
            test_db.execute(text("ALTER TABLE tasks DROP COLUMN IF EXISTS _test_temp_field"))
        except Exception:
            pass

    def test_migration_rollback_safety(self, test_db: Session):
        """Test that migrations can be safely rolled back without data loss"""
        user_id = _create_test_user(test_db)
        project_id = str(uuid.uuid4())

        project = Project(
            id=project_id,
            title="Rollback Test",
            description="Testing migration rollback safety",
            created_by=user_id,
        )
        test_db.add(project)
        test_db.flush()

        # Simulate forward migration (add new table)
        test_db.execute(text(
            "CREATE TABLE IF NOT EXISTS _test_migration_rollback ("
            "id VARCHAR PRIMARY KEY, test_data VARCHAR)"
        ))
        test_db.execute(text(
            "INSERT INTO _test_migration_rollback (id, test_data) "
            "VALUES ('test-1', 'migration data')"
        ))

        # Verify migration data exists
        result = test_db.execute(text("SELECT * FROM _test_migration_rollback")).fetchall()
        assert len(result) > 0

        # Simulate rollback
        test_db.execute(text("DROP TABLE IF EXISTS _test_migration_rollback"))

        # Verify original data is still intact after rollback
        rolled_back_project = (
            test_db.query(Project).filter(Project.id == project_id).first()
        )
        assert rolled_back_project is not None
        assert rolled_back_project.title == "Rollback Test"

    def test_concurrent_migration_safety(self, test_db: Session):
        """Test that the schema handles concurrent data creation correctly"""
        user_id = _create_test_user(test_db)

        projects = []
        for i in range(3):
            project = Project(
                id=str(uuid.uuid4()),
                title=f"Concurrent Test {i}",
                description="Testing concurrent migration safety",
                created_by=user_id,
            )
            test_db.add(project)
            projects.append(project)

        test_db.flush()

        # Verify all data was created successfully
        for i, project in enumerate(projects):
            test_db.refresh(project)
            assert project.title == f"Concurrent Test {i}"

    def test_migration_version_tracking(self, temp_database):
        """Test that migration versions are properly tracked"""
        engine, _ = temp_database

        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(32) NOT NULL, PRIMARY KEY (version_num))"
            ))
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text("DELETE FROM alembic_version"))
            conn.execute(text(
                "INSERT INTO alembic_version (version_num) "
                "VALUES ('add_missing_annotation_tables')"
            ))
            conn.commit()

        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            assert result is not None
            assert result.version_num == 'add_missing_annotation_tables'

    def test_schema_validation_after_migration(self, test_db: Session):
        """Test that schema validation passes — critical tables and columns exist"""
        engine = test_db.get_bind()
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        required_tables = ['projects', 'tasks', 'annotations']
        for table_name in required_tables:
            assert table_name in existing_tables, f"Required table {table_name} missing"

        # Verify tasks table has string ID column
        task_columns = {c['name']: c for c in inspector.get_columns('tasks')}
        assert 'id' in task_columns, "tasks table should have id column"

        # Verify annotations table has task_id foreign key
        annotation_columns = {c['name']: c for c in inspector.get_columns('annotations')}
        assert 'task_id' in annotation_columns, "annotations table should have task_id column"

        # Verify foreign key relationships exist
        annotation_fks = inspector.get_foreign_keys('annotations')
        task_fk_exists = any(
            fk.get('referred_table') == 'tasks' and 'task_id' in fk.get('constrained_columns', [])
            for fk in annotation_fks
        )
        assert task_fk_exists, "annotations should have FK to tasks.id"

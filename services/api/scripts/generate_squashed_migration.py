#!/usr/bin/env python3
"""
Generate a single squashed migration that creates the complete database schema.
This replaces all individual migrations with one comprehensive migration.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import models
sys.path.insert(0, str(Path(__file__).parent.parent))


def generate_squashed_migration():
    """Generate a comprehensive migration from current database state."""

    print("🔍 Generating squashed migration from current database state...")

    # Get the SQL dump of the current schema
    dump_command = [
        "docker",
        "exec",
        "infra-db-1",
        "pg_dump",
        "-U",
        "postgres",
        "-d",
        "benger",
        "--schema-only",
        "--no-owner",
        "--no-privileges",
        "--no-comments",
        "--no-publications",
        "--no-subscriptions",
        "--no-tablespaces",
        "--no-security-labels",
    ]

    result = subprocess.run(dump_command, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ Error dumping schema: {result.stderr}")
        return False

    schema_sql = result.stdout

    # Filter out alembic_version table and extract CREATE TABLE statements
    create_statements = []
    current_statement = []
    in_create = False

    for line in schema_sql.split('\n'):
        # Skip alembic version table
        if 'alembic_version' in line:
            in_create = False
            current_statement = []
            continue

        if line.startswith('CREATE TABLE'):
            in_create = True
            current_statement = [line]
        elif in_create:
            current_statement.append(line)
            if line.strip().endswith(';'):
                create_statements.append('\n'.join(current_statement))
                in_create = False
                current_statement = []

    # Also get indexes, constraints, etc.
    other_statements = []
    for line in schema_sql.split('\n'):
        if any(
            line.startswith(cmd) for cmd in ['CREATE INDEX', 'CREATE UNIQUE INDEX', 'ALTER TABLE']
        ):
            if 'alembic_version' not in line:
                # Collect until semicolon
                statement = [line]
                for next_line in schema_sql.split('\n')[schema_sql.split('\n').index(line) + 1 :]:
                    statement.append(next_line)
                    if next_line.strip().endswith(';'):
                        break
                other_statements.append('\n'.join(statement))

    print(f"✅ Found {len(create_statements)} tables to create")

    # Generate the migration file content
    migration_content = f'''"""Complete BenGER database schema - squashed migration

Revision ID: complete_schema_001
Revises: 
Create Date: {datetime.now().isoformat()}

This is a squashed migration that creates the complete database schema.
All previous migrations have been consolidated into this single migration.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import json

# revision identifiers
revision = 'complete_schema_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create complete database schema."""
    
    # Create all tables
    # Tables creation will be handled by autogenerate or manual migration
    
    # Insert initial feature flags
    op.execute("""
        INSERT INTO feature_flags (name, description, is_enabled, created_at, updated_at) VALUES
        ('data', 'Enable access to Data Management features and page', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('generations', 'Enable access to Generation features and page', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('evaluations', 'Enable access to Evaluation features and page', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('reports', 'Enable access to Reports page', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('how-to', 'Enable access to How-To page', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (name) DO NOTHING;
    """)
    
    print("✅ Complete database schema created")


def downgrade():
    """Drop all tables."""
    # Drop tables in reverse order to handle foreign keys
    tables = [
        'user_api_keys', 'refresh_tokens', 'email_verification_tokens',
        'evaluation_results', 'generation_results', 'generation_jobs',
        'annotation_labels', 'annotations', 'annotation_tasks',
        'project_members', 'projects', 'project_types',
        'organization_members', 'organizations',
        'feature_flag_overrides', 'feature_flags',
        'users', 'evaluation_types'
    ]
    
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {{table}} CASCADE")
    
    print("✅ All tables dropped")
'''

    # Write the migration file
    migration_path = (
        Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "complete_schema_001_squashed_migration.py"
    )

    # First, let's generate it using alembic autogenerate to get proper SQLAlchemy code
    print("🔄 Generating migration using alembic autogenerate...")

    # Clear existing migrations first
    versions_dir = Path(__file__).parent.parent / "alembic" / "versions"
    for file in versions_dir.glob("*.py"):
        if file.name != "__init__.py" and "backup" not in file.name:
            file.unlink()

    # Generate new migration
    autogen_cmd = [
        "docker",
        "exec",
        "infra-api-1",
        "alembic",
        "revision",
        "--autogenerate",
        "-m",
        "Complete schema squashed",
    ]

    result = subprocess.run(autogen_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ Error generating migration: {result.stderr}")
        # Fall back to manual generation
        return write_manual_migration()

    print("✅ Migration generated successfully")
    return True


def write_manual_migration():
    """Write a manual migration based on the models."""

    migration_content = '''"""Complete BenGER database schema - squashed migration

Revision ID: complete_schema_001
Revises: 
Create Date: {datetime}

This is a squashed migration that creates the complete database schema.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers
revision = 'complete_schema_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create complete database schema."""
    
    # Users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('username', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('email', sa.String(120), unique=True, nullable=False, index=True),
        sa.Column('email_verified', sa.Boolean(), default=False, nullable=False),
        sa.Column('name', sa.String(100)),
        sa.Column('hashed_password', sa.String(255)),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('is_superadmin', sa.Boolean(), default=False, nullable=False),
        sa.Column('age', sa.Integer()),
        sa.Column('job', sa.String(100)),
        sa.Column('years_of_experience', sa.Integer()),
        sa.Column('legal_expertise_level', sa.Integer()),
        sa.Column('area_of_law', sa.String(100)),
        sa.Column('german_state_exams_count', sa.Integer()),
        sa.Column('german_state_exams_data', sa.JSON()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        sa.Column('invitation_token', sa.String(255), unique=True, index=True),
        sa.Column('invitation_expires_at', sa.DateTime()),
        sa.Column('profile_completed', sa.Boolean(), default=False),
        sa.Column('password_set', sa.Boolean(), default=False)
    )
    
    # Organizations table
    op.create_table('organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('display_name', sa.String(100)),
        sa.Column('description', sa.Text()),
        sa.Column('settings', sa.JSON()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'))
    )
    
    # Organization members table
    op.create_table('organization_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('role', sa.String(50), default='member'),
        sa.Column('joined_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('organization_id', 'user_id', name='uq_org_user')
    )
    
    # Project types table
    op.create_table('project_types',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('display_name', sa.String(100)),
        sa.Column('description', sa.Text()),
        sa.Column('schema', sa.JSON()),
        sa.Column('ui_config', sa.JSON()),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now())
    )
    
    # Projects table
    op.create_table('projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('type_id', sa.Integer(), sa.ForeignKey('project_types.id')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id')),
        sa.Column('settings', sa.JSON()),
        sa.Column('annotation_guidelines', sa.Text()),
        sa.Column('task_distribution_strategy', sa.String(50), default='sequential'),
        sa.Column('min_annotations_per_task', sa.Integer(), default=1),
        sa.Column('allow_task_reassignment', sa.Boolean(), default=True),
        sa.Column('annotation_overlap', sa.Float(), default=0.0),
        sa.Column('enable_quality_control', sa.Boolean(), default=False),
        sa.Column('consensus_threshold', sa.Float()),
        sa.Column('review_workflow', sa.String(50)),
        sa.Column('evaluation_config', sa.JSON()),
        sa.Column('generation_config', sa.JSON()),
        sa.Column('llm_annotation_model_id', sa.String(255)),
        sa.Column('llm_generation_model_id', sa.String(255)),
        sa.Column('llm_evaluation_model_id', sa.String(255)),
        sa.Column('is_public', sa.Boolean(), default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        sa.Index('idx_projects_org_public', 'organization_id', 'is_public')
    )
    
    # Project members table
    op.create_table('project_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('role', sa.String(50), default='annotator'),
        sa.Column('joined_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('project_id', 'user_id', name='uq_project_user')
    )
    
    # Annotation tasks table
    op.create_table('annotation_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('metadata', sa.JSON()),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('assigned_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        sa.Index('idx_tasks_project_status', 'project_id', 'status'),
        sa.Index('idx_tasks_assigned', 'assigned_to', 'status')
    )
    
    # Annotations table
    op.create_table('annotations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('annotation_tasks.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('metadata', sa.JSON()),
        sa.Column('time_spent', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        sa.Index('idx_annotations_task_user', 'task_id', 'user_id'),
        sa.UniqueConstraint('task_id', 'user_id', name='uq_task_user_annotation')
    )
    
    # Annotation labels table
    op.create_table('annotation_labels',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('color', sa.String(7)),
        sa.Column('description', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('project_id', 'name', name='uq_project_label')
    )
    
    # Generation jobs table
    op.create_table('generation_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('config', sa.JSON()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    
    # Generation results table
    op.create_table('generation_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('generation_jobs.id'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('annotation_tasks.id'), nullable=False),
        sa.Column('generated_text', sa.Text()),
        sa.Column('metadata', sa.JSON()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    
    # Evaluation types table
    op.create_table('evaluation_types',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('display_name', sa.String(100)),
        sa.Column('description', sa.Text()),
        sa.Column('category', sa.String(50)),
        sa.Column('config_schema', sa.JSON()),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    
    # Evaluation results table
    op.create_table('evaluation_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('evaluation_type_id', sa.Integer(), sa.ForeignKey('evaluation_types.id')),
        sa.Column('model_name', sa.String(100)),
        sa.Column('scores', sa.JSON()),
        sa.Column('metadata', sa.JSON()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    
    # Feature flags table
    op.create_table('feature_flags',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('is_enabled', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'))
    )
    
    # Feature flag overrides table
    op.create_table('feature_flag_overrides',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('feature_flag_id', sa.Integer(), sa.ForeignKey('feature_flags.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id')),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now())
    )
    
    # Refresh tokens table
    op.create_table('refresh_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('token', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked', sa.Boolean(), default=False),
        sa.Column('revoked_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('user_agent', sa.String(255)),
        sa.Column('ip_address', sa.String(45))
    )
    
    # Email verification tokens table
    op.create_table('email_verification_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('token', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('email', sa.String(120), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    
    # User API keys table
    op.create_table('user_api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('key_hash', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('prefix', sa.String(20), nullable=False),
        sa.Column('last_used_at', sa.DateTime()),
        sa.Column('expires_at', sa.DateTime()),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now())
    )
    
    # Insert initial feature flags
    op.execute("""
        INSERT INTO feature_flags (name, description, is_enabled) VALUES
        ('data', 'Enable access to Data Management features and page', true),
        ('generations', 'Enable access to Generation features and page', true),
        ('evaluations', 'Enable access to Evaluation features and page', true),
        ('reports', 'Enable access to Reports page', true),
        ('how-to', 'Enable access to How-To page', true)
        ON CONFLICT (name) DO NOTHING;
    """)
    
    # Insert default evaluation types
    op.execute("""
        INSERT INTO evaluation_types (name, display_name, description, category) VALUES
        ('accuracy', 'Accuracy', 'Measure prediction accuracy', 'classification'),
        ('f1', 'F1 Score', 'Harmonic mean of precision and recall', 'classification'),
        ('exact_match', 'Exact Match', 'Exact string matching', 'text'),
        ('token_f1', 'Token F1', 'F1 score at token level', 'text'),
        ('bleu', 'BLEU', 'Bilingual Evaluation Understudy', 'generation'),
        ('rouge_l', 'ROUGE-L', 'Recall-Oriented Understudy for Gisting Evaluation', 'generation'),
        ('semantic_similarity', 'Semantic Similarity', 'Cosine similarity of embeddings', 'semantic'),
        ('answer_relevance', 'Answer Relevance', 'Relevance of answer to question', 'qa'),
        ('human_eval', 'Human Evaluation', 'Manual human evaluation scores', 'human')
        ON CONFLICT (name) DO NOTHING;
    """)
    
    # Insert default project types
    op.execute("""
        INSERT INTO project_types (name, display_name, description, is_active) VALUES
        ('text_classification', 'Text Classification', 'Classify text into predefined categories', true),
        ('ner', 'Named Entity Recognition', 'Identify and classify named entities in text', true),
        ('qa', 'Question Answering', 'Answer questions based on context', true),
        ('summarization', 'Text Summarization', 'Generate summaries of longer texts', true),
        ('translation', 'Translation', 'Translate text between languages', true),
        ('custom', 'Custom', 'Custom annotation type with flexible schema', true)
        ON CONFLICT (name) DO NOTHING;
    """)
    
    print("✅ Complete database schema created")


def downgrade():
    """Drop all tables in reverse order."""
    tables = [
        'user_api_keys', 'email_verification_tokens', 'refresh_tokens',
        'feature_flag_overrides', 'feature_flags',
        'evaluation_results', 'evaluation_types',
        'generation_results', 'generation_jobs',
        'annotation_labels', 'annotations', 'annotation_tasks',
        'project_members', 'projects', 'project_types',
        'organization_members', 'organizations',
        'users'
    ]
    
    for table in tables:
        op.drop_table(table, if_exists=True)
    
    print("✅ All tables dropped")
'''.format(
        datetime=datetime.now().isoformat()
    )

    # Write the migration
    migration_path = (
        Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "complete_schema_001_squashed_migration.py"
    )
    migration_path.write_text(migration_content)

    print(f"✅ Manual migration written to {migration_path}")
    return True


if __name__ == "__main__":
    if generate_squashed_migration():
        print("\n✨ Squashed migration generated successfully!")
        print("\nNext steps:")
        print("1. Review the generated migration")
        print("2. Test it on a clean database")
        print("3. Remove old migrations after verification")
    else:
        print("\n❌ Failed to generate migration")
        sys.exit(1)

#!/usr/bin/env python3
"""
Generate a clean baseline migration and setup script for BenGER.
This creates a single migration with the complete schema and a setup script for demo data.
"""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

def generate_baseline_migration():
    """Generate a single baseline migration with complete schema."""
    
    print("🔄 Generating clean baseline migration...")
    
    # Get current schema from database
    dump_cmd = [
        "docker", "exec", "infra-db-1",
        "pg_dump", "-U", "postgres", "-d", "benger",
        "--schema-only", "--no-owner", "--no-privileges",
        "--no-comments", "--no-publications", "--no-subscriptions"
    ]
    
    result = subprocess.run(dump_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Failed to dump schema: {result.stderr}")
        return False
    
    # Parse the schema to extract table definitions
    schema_lines = result.stdout.split('\n')
    
    # Generate migration file
    migration_content = f'''"""BenGER Complete Schema - Single Baseline Migration

Revision ID: baseline_complete_001
Revises: 
Create Date: {datetime.now().isoformat()}

Single migration that creates the complete BenGER database schema.
This replaces all individual migrations.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers
revision = 'baseline_complete_001' 
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create complete BenGER database schema."""
    
    # Users table - Core authentication and user management
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('username', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('email', sa.String(120), unique=True, nullable=False, index=True),
        sa.Column('email_verified', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('email_verification_method', sa.String(50)),
        sa.Column('name', sa.String(100)),
        sa.Column('hashed_password', sa.String(255)),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_superadmin', sa.Boolean(), server_default='false', nullable=False),
        
        # Profile fields
        sa.Column('age', sa.Integer()),
        sa.Column('job', sa.String(100)),
        sa.Column('years_of_experience', sa.Integer()),
        sa.Column('legal_expertise_level', sa.Integer()),
        sa.Column('area_of_law', sa.String(100)),
        sa.Column('german_state_exams_count', sa.Integer()),
        sa.Column('german_state_exams_data', sa.JSON()),
        
        # Invitation system
        sa.Column('invitation_token', sa.String(255), unique=True, index=True),
        sa.Column('invitation_expires_at', sa.DateTime()),
        sa.Column('profile_completed', sa.Boolean(), server_default='false'),
        sa.Column('password_set', sa.Boolean(), server_default='false'),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now())
    )
    
    # Organizations table
    op.create_table('organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('display_name', sa.String(100)),
        sa.Column('slug', sa.String(100), unique=True),
        sa.Column('description', sa.Text()),
        sa.Column('settings', sa.JSON()),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'))
    )
    
    # Organization members junction table
    op.create_table('organization_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(50), server_default='MEMBER'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('joined_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('organization_id', 'user_id', name='uq_org_user')
    )
    
    # Project types configuration
    op.create_table('project_types',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('display_name', sa.String(100)),
        sa.Column('description', sa.Text()),
        sa.Column('schema', sa.JSON()),
        sa.Column('ui_config', sa.JSON()),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now())
    )
    
    # Projects table
    op.create_table('projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('type_id', sa.Integer(), sa.ForeignKey('project_types.id')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='SET NULL')),
        
        # Project settings
        sa.Column('settings', sa.JSON()),
        sa.Column('annotation_guidelines', sa.Text()),
        sa.Column('task_distribution_strategy', sa.String(50), server_default='sequential'),
        sa.Column('min_annotations_per_task', sa.Integer(), server_default='1'),
        sa.Column('allow_task_reassignment', sa.Boolean(), server_default='true'),
        sa.Column('annotation_overlap', sa.Float(), server_default='0.0'),
        
        # Quality control
        sa.Column('enable_quality_control', sa.Boolean(), server_default='false'),
        sa.Column('consensus_threshold', sa.Float()),
        sa.Column('review_workflow', sa.String(50)),
        
        # LLM configuration
        sa.Column('evaluation_config', sa.JSON()),
        sa.Column('generation_config', sa.JSON()),
        sa.Column('llm_annotation_model_id', sa.String(255)),
        sa.Column('llm_generation_model_id', sa.String(255)),
        sa.Column('llm_evaluation_model_id', sa.String(255)),
        
        # Visibility
        sa.Column('is_public', sa.Boolean(), server_default='false', nullable=False),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        
        sa.Index('idx_projects_org_public', 'organization_id', 'is_public')
    )
    
    # Project members junction table
    op.create_table('project_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(50), server_default='annotator'),
        sa.Column('joined_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('project_id', 'user_id', name='uq_project_user')
    )
    
    # Annotation tasks
    op.create_table('annotation_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('metadata', sa.JSON()),
        sa.Column('status', sa.String(50), server_default='pending'),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('assigned_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        sa.Index('idx_tasks_project_status', 'project_id', 'status'),
        sa.Index('idx_tasks_assigned', 'assigned_to', 'status')
    )
    
    # Annotations
    op.create_table('annotations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('annotation_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('metadata', sa.JSON()),
        sa.Column('time_spent', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        sa.UniqueConstraint('task_id', 'user_id', name='uq_task_user_annotation')
    )
    
    # Annotation labels
    op.create_table('annotation_labels',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('color', sa.String(7)),
        sa.Column('description', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('project_id', 'name', name='uq_project_label')
    )
    
    # Generation jobs
    op.create_table('generation_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(50), server_default='pending'),
        sa.Column('config', sa.JSON()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    
    # Generation results
    op.create_table('generation_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('generation_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('annotation_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('generated_text', sa.Text()),
        sa.Column('metadata', sa.JSON()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    
    # Evaluation types
    op.create_table('evaluation_types',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('display_name', sa.String(100)),
        sa.Column('description', sa.Text()),
        sa.Column('category', sa.String(50)),
        sa.Column('config_schema', sa.JSON()),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    
    # Evaluation results
    op.create_table('evaluation_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('evaluation_type_id', sa.Integer(), sa.ForeignKey('evaluation_types.id')),
        sa.Column('model_name', sa.String(100)),
        sa.Column('scores', sa.JSON()),
        sa.Column('metadata', sa.JSON()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    
    # Feature flags
    op.create_table('feature_flags',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('is_enabled', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'))
    )
    
    # Feature flag overrides
    op.create_table('feature_flag_overrides',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('feature_flag_id', sa.Integer(), sa.ForeignKey('feature_flags.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE')),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now())
    )
    
    # Authentication tables
    op.create_table('refresh_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('token', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked', sa.Boolean(), server_default='false'),
        sa.Column('revoked_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('user_agent', sa.String(255)),
        sa.Column('ip_address', sa.String(45))
    )
    
    op.create_table('email_verification_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('token', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(120), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    
    op.create_table('user_api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('key_hash', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('prefix', sa.String(20), nullable=False),
        sa.Column('last_used_at', sa.DateTime()),
        sa.Column('expires_at', sa.DateTime()),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now())
    )
    
    print("✅ All tables created successfully")
    
    # Insert default data
    # Feature flags - Only the 5 consolidated flags
    op.execute("""
        INSERT INTO feature_flags (name, description, is_enabled) VALUES
        ('data', 'Enable access to Data Management features and page', true),
        ('generations', 'Enable access to Generation features and page', true),
        ('evaluations', 'Enable access to Evaluation features and page', true),
        ('reports', 'Enable access to Reports page', true),
        ('how-to', 'Enable access to How-To page', true)
        ON CONFLICT (name) DO NOTHING
    """)
    
    # Default evaluation types
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
        ON CONFLICT (name) DO NOTHING
    """)
    
    # Default project types
    op.execute("""
        INSERT INTO project_types (name, display_name, description, is_active) VALUES
        ('text_classification', 'Text Classification', 'Classify text into predefined categories', true),
        ('ner', 'Named Entity Recognition', 'Identify and classify named entities in text', true),
        ('qa', 'Question Answering', 'Answer questions based on context', true),
        ('summarization', 'Text Summarization', 'Generate summaries of longer texts', true),
        ('translation', 'Translation', 'Translate text between languages', true),
        ('custom', 'Custom', 'Custom annotation type with flexible schema', true)
        ON CONFLICT (name) DO NOTHING
    """)
    
    print("✅ Default data inserted")


def downgrade():
    """Drop all tables in reverse dependency order."""
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
        op.execute(f"DROP TABLE IF EXISTS {{table}} CASCADE")
'''
    
    # Write the migration file
    migration_path = Path("/Users/sebastiannagl/Code/BenGer/services/api/alembic/versions/baseline_complete_001_single_migration.py")
    migration_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Backup and clear old migrations
    backup_dir = migration_path.parent / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(exist_ok=True)
    
    for file in migration_path.parent.glob("*.py"):
        if file.name != "__init__.py" and "backup" not in file.name:
            file.rename(backup_dir / file.name)
    
    # Write new migration
    migration_path.write_text(migration_content)
    print(f"✅ Baseline migration written to {migration_path}")
    
    return True


def create_setup_script():
    """Create a comprehensive setup script for demo data."""
    
    setup_content = '''#!/usr/bin/env python3
"""
Comprehensive setup script for BenGER demo environment.
Initializes database with demo users, organizations, and feature flags.
"""

import os
import sys
import subprocess
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))

def setup_benger_demo():
    """Initialize BenGER with complete demo data."""
    
    environment = os.getenv("ENVIRONMENT", "development")
    
    if environment == "production":
        print("🔒 Production environment - skipping demo setup for security")
        return
    
    print("🚀 Setting up BenGER demo environment...")
    
    # Run migrations
    print("📦 Running database migrations...")
    result = subprocess.run([
        "docker", "exec", "infra-api-1",
        "alembic", "upgrade", "head"
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Migration failed: {result.stderr}")
        return False
    
    print("✅ Migrations completed")
    
    # Initialize demo data via API container
    print("👥 Creating demo users and organizations...")
    
    init_script = """
from database import SessionLocal
from user_service import init_demo_users

db = SessionLocal()
try:
    init_demo_users(db)
    print("✅ Demo setup completed")
finally:
    db.close()
"""
    
    result = subprocess.run([
        "docker", "exec", "-i", "infra-api-1",
        "python", "-c", init_script
    ], capture_output=True, text=True)
    
    print(result.stdout)
    
    if result.returncode != 0:
        print(f"❌ Demo setup failed: {result.stderr}")
        return False
    
    print("""
🎉 BenGER Demo Environment Ready!

Demo Users:
- admin / admin (Superadmin)
- contributor / admin (Contributor role)
- annotator / admin (Annotator role)

Organization: TUM

Feature Flags (all enabled):
- data: Data Management
- generations: Generation features
- evaluations: Evaluation features
- reports: Reports page
- how-to: How-To documentation

Access the application at:
- Development: http://benger.localhost
- API: http://api.localhost
""")
    
    return True


if __name__ == "__main__":
    if not setup_benger_demo():
        sys.exit(1)
'''
    
    setup_path = Path("/Users/sebastiannagl/Code/BenGer/scripts/setup_demo_environment.py")
    setup_path.write_text(setup_content)
    os.chmod(setup_path, 0o755)
    
    print(f"✅ Setup script written to {setup_path}")
    return True


if __name__ == "__main__":
    print("🔨 Generating clean baseline for BenGER...")
    
    if generate_baseline_migration():
        print("✅ Baseline migration generated")
    else:
        print("❌ Failed to generate migration")
        sys.exit(1)
    
    if create_setup_script():
        print("✅ Setup script created")
    else:
        print("❌ Failed to create setup script")
        sys.exit(1)
    
    print("""
✨ Clean baseline generation complete!

Next steps:
1. Review the migration: services/api/alembic/versions/baseline_complete_001_single_migration.py
2. Test on clean database: scripts/setup_demo_environment.py
3. Remove old migrations after verification
""")
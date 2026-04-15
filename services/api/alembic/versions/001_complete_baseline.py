"""Complete baseline - Single squashed migration for BenGER

Revision ID: 001_complete_baseline
Revises:
Create Date: 2025-10-22
Updated: 2026-01-23 (squashed migrations 002-009)

This is a comprehensive single migration containing the complete database schema.
Migrations 002-009 have been squashed into this single file for easier setup.

Includes:
- Full baseline schema with all tables
- Prompt structure support (structure_key)
- Evaluation sample results tracking
- Project reports functionality
- Skipped tasks tracking
- LLM response parsing
- Label config versioning
- User pseudonymization for privacy
- Legal expertise enum fields (migration 006)
- Additional LLM provider API keys: GLM, Grok, Mistral, Cohere (migration 007)
- Immediate evaluation setting (migration 005)
- Annotation time limit settings (migration 009)

NOTE: default_prompts table removed (deprecated in migration 002)
NOTE: total_predictions column removed from tasks (migration 004)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '001_complete_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Create all tables."""

    # ============================================================================
    # ENUM TYPES (PostgreSQL only - migration 006)
    # ============================================================================
    # Note: These are created for PostgreSQL; SQLite uses String columns instead
    # The application code handles both cases via SQLAlchemy dialect detection

    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE legalexpertiselevel AS ENUM (
                'layperson', 'law_student', 'referendar',
                'graduated_no_practice', 'practicing_lawyer', 'judge_professor'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE germanproficiency AS ENUM (
                'native', 'c2', 'c1', 'b2', 'below_b2'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE degreeprogramtype AS ENUM (
                'staatsexamen', 'llb', 'llm', 'promotion', 'not_applicable'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """
    )

    # ============================================================================
    # CORE TABLES
    # ============================================================================

    op.create_table(
        'evaluation_types',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('higher_is_better', sa.Boolean(), nullable=False),
        sa.Column('value_range', sa.JSON(), nullable=True),
        sa.Column('applicable_project_types', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_evaluation_types_id'), 'evaluation_types', ['id'], unique=False)

    op.create_table(
        'evaluations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=True),
        sa.Column('project_id', sa.String(), nullable=True),  # Added in migration 003
        sa.Column('model_id', sa.String(), nullable=False),
        sa.Column('evaluation_type_ids', sa.JSON(), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=False),
        sa.Column('eval_metadata', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('samples_evaluated', sa.Integer(), nullable=True),
        sa.Column(
            'has_sample_results', sa.Boolean(), nullable=False, server_default='false'
        ),  # Added in migration 003
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_evaluations_id'), 'evaluations', ['id'], unique=False)
    op.create_index(
        'idx_evaluations_project_id', 'evaluations', ['project_id']
    )  # Added in migration 003

    op.create_table(
        'human_evaluation_configs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=True),
        sa.Column('evaluation_project_id', sa.String(), nullable=True),
        sa.Column('evaluator_count', sa.Integer(), nullable=False),
        sa.Column('randomization_seed', sa.Integer(), nullable=True),
        sa.Column('blinding_enabled', sa.Boolean(), nullable=False),
        sa.Column('include_human_responses', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id'),
    )
    op.create_index(
        op.f('ix_human_evaluation_configs_id'), 'human_evaluation_configs', ['id'], unique=False
    )

    op.create_table(
        'llm_models',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('model_type', sa.String(), nullable=False),
        sa.Column('capabilities', sa.JSON(), nullable=False),
        sa.Column('config_schema', sa.JSON(), nullable=True),
        sa.Column('default_config', sa.JSON(), nullable=True),
        sa.Column(
            'parameter_constraints', postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),  # Added in migration 004
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_llm_models_id'), 'llm_models', ['id'], unique=False)

    op.create_table(
        'organizations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('settings', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_organizations_id'), 'organizations', ['id'], unique=False)
    op.create_index(op.f('ix_organizations_slug'), 'organizations', ['slug'], unique=True)

    op.create_table(
        'response_generations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=True),
        sa.Column('task_id', sa.String(), nullable=True),
        sa.Column('model_id', sa.String(), nullable=False),
        sa.Column('config_id', sa.String(), nullable=True),
        sa.Column('structure_key', sa.String(), nullable=True),  # Added in migration 002
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('responses_generated', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('prompt_used', sa.Text(), nullable=True),
        sa.Column('parameters', sa.JSON(), nullable=True),
        sa.Column('generation_metadata', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_response_generations_id'), 'response_generations', ['id'], unique=False
    )
    op.create_index(
        'ix_response_generations_structure_key', 'response_generations', ['structure_key']
    )  # Added in migration 002

    op.create_table(
        'template_categories',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(), nullable=True),
        sa.Column('parent_category_id', sa.String(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['parent_category_id'], ['template_categories.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_template_categories_id'), 'template_categories', ['id'], unique=False)

    op.create_table(
        'uploaded_data',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('original_filename', sa.String(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('format', sa.String(), nullable=False),
        sa.Column('document_count', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('task_id', sa.String(), nullable=True),
        sa.Column('uploaded_by', sa.String(), nullable=False),
        sa.Column(
            'upload_date',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('storage_key', sa.String(), nullable=True),
        sa.Column('storage_url', sa.Text(), nullable=True),
        sa.Column('file_hash', sa.String(length=64), nullable=True),
        sa.Column('cdn_url', sa.Text(), nullable=True),
        sa.Column('storage_type', sa.String(length=20), server_default='local', nullable=False),
        sa.Column('storage_backend', sa.String(), nullable=True),
        sa.Column('file_metadata', sa.JSON(), nullable=True),
        sa.Column('file_format', sa.String(), nullable=True),
        sa.Column('processed', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_uploaded_data_id'), 'uploaded_data', ['id'], unique=False)

    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('email_verified', sa.Boolean(), nullable=False),
        sa.Column('email_verification_token', sa.String(length=512), nullable=True),
        sa.Column('email_verification_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('email_verified_by_id', sa.String(), nullable=True),
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('email_verification_method', sa.String(), nullable=True),
        sa.Column('password_reset_token', sa.String(length=512), nullable=True),
        sa.Column('password_reset_expires', sa.DateTime(timezone=True), nullable=True),
        sa.Column('password_set', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=True),
        sa.Column('is_superadmin', sa.Boolean(), nullable=False),
        sa.Column('invitation_token', sa.String(length=255), nullable=True),
        sa.Column('invitation_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('profile_completed', sa.Boolean(), nullable=False),
        sa.Column('created_via_invitation', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('encrypted_openai_api_key', sa.Text(), nullable=True),
        sa.Column('encrypted_anthropic_api_key', sa.Text(), nullable=True),
        sa.Column('encrypted_google_api_key', sa.Text(), nullable=True),
        sa.Column('encrypted_deepinfra_api_key', sa.Text(), nullable=True),
        sa.Column('encrypted_glm_api_key', sa.Text(), nullable=True),
        sa.Column('encrypted_grok_api_key', sa.Text(), nullable=True),
        sa.Column('encrypted_mistral_api_key', sa.Text(), nullable=True),
        sa.Column('encrypted_cohere_api_key', sa.Text(), nullable=True),
        sa.Column('timezone', sa.String(), nullable=True),
        sa.Column('age', sa.Integer(), nullable=True),
        sa.Column('job', sa.Text(), nullable=True),
        sa.Column('years_of_experience', sa.Integer(), nullable=True),
        # Legal expertise fields (migration 006) - enum types created separately for PostgreSQL
        sa.Column('legal_expertise_level', sa.String(50), nullable=True),
        sa.Column('german_proficiency', sa.String(50), nullable=True),
        sa.Column('degree_program_type', sa.String(50), nullable=True),
        sa.Column('current_semester', sa.Integer(), nullable=True),
        sa.Column('legal_specializations', sa.JSON(), nullable=True),
        sa.Column('german_state_exams_count', sa.Integer(), nullable=True),
        sa.Column('german_state_exams_data', sa.JSON(), nullable=True),
        # Pseudonym columns added in migration 009
        sa.Column('pseudonym', sa.String(100), nullable=True),
        sa.Column('use_pseudonym', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['email_verified_by_id'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(
        op.f('ix_users_email_verification_token'),
        'users',
        ['email_verification_token'],
        unique=False,
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_invitation_token'), 'users', ['invitation_token'], unique=False)
    op.create_index(
        op.f('ix_users_password_reset_token'), 'users', ['password_reset_token'], unique=False
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    # Pseudonym index added in migration 009 - unique index instead of separate constraint
    op.create_index('ix_users_pseudonym', 'users', ['pseudonym'], unique=True)

    # ============================================================================
    # TABLES DEPENDENT ON USERS
    # ============================================================================

    op.create_table(
        'default_config_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('config_type', sa.String(), nullable=False),
        sa.Column('task_type', sa.String(), nullable=False),
        sa.Column('old_config', sa.JSON(), nullable=True),
        sa.Column('new_config', sa.JSON(), nullable=False),
        sa.Column('change_reason', sa.Text(), nullable=True),
        sa.Column('changed_by', sa.String(), nullable=False),
        sa.Column(
            'changed_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['changed_by'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_default_config_history_changed_at'),
        'default_config_history',
        ['changed_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_default_config_history_id'), 'default_config_history', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_default_config_history_task_type'),
        'default_config_history',
        ['task_type'],
        unique=False,
    )

    op.create_table(
        'default_evaluation_configs',
        sa.Column('task_type', sa.String(), nullable=False),
        sa.Column('evaluation_method_ids', sa.JSON(), nullable=True),
        sa.Column('generation_config', sa.JSON(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ['updated_by'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('task_type'),
    )
    op.create_index(
        op.f('ix_default_evaluation_configs_task_type'),
        'default_evaluation_configs',
        ['task_type'],
        unique=False,
    )

    # NOTE: default_prompts table removed - deprecated in favor of generation_config.prompt_structures

    op.create_table(
        'evaluation_metrics',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('evaluation_id', sa.String(), nullable=False),
        sa.Column('evaluation_type_id', sa.String(), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['evaluation_id'],
            ['evaluations.id'],
        ),
        sa.ForeignKeyConstraint(
            ['evaluation_type_id'],
            ['evaluation_types.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_evaluation_metrics_id'), 'evaluation_metrics', ['id'], unique=False)

    op.create_table(
        'feature_flags',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('configuration', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['created_by'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_feature_flags_id'), 'feature_flags', ['id'], unique=False)
    op.create_index(op.f('ix_feature_flags_name'), 'feature_flags', ['name'], unique=True)

    op.create_table(
        'human_evaluation_mappings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('config_id', sa.String(), nullable=False),
        sa.Column('anonymous_response_id', sa.String(), nullable=False),
        sa.Column('actual_response_id', sa.String(), nullable=True),
        sa.Column('model_id', sa.String(), nullable=True),
        sa.Column('anonymous_model_name', sa.String(), nullable=False),
        sa.Column('response_text', sa.Text(), nullable=False),
        sa.Column('response_type', sa.String(), nullable=False),
        sa.Column('question_data', sa.JSON(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['config_id'],
            ['human_evaluation_configs.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'config_id', 'anonymous_response_id', name='unique_anonymous_response_per_config'
        ),
        sa.UniqueConstraint('config_id', 'display_order', name='unique_display_order_per_config'),
    )
    op.create_index(
        op.f('ix_human_evaluation_mappings_id'), 'human_evaluation_mappings', ['id'], unique=False
    )

    op.create_table(
        'human_evaluation_results',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('config_id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=True),
        sa.Column('response_id', sa.String(), nullable=False),
        sa.Column('evaluator_id', sa.String(), nullable=False),
        sa.Column('correctness_score', sa.Integer(), nullable=False),
        sa.Column('completeness_score', sa.Integer(), nullable=False),
        sa.Column('style_score', sa.Integer(), nullable=False),
        sa.Column('usability_score', sa.Integer(), nullable=False),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('evaluation_time_seconds', sa.Float(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['config_id'],
            ['human_evaluation_configs.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'config_id',
            'response_id',
            'evaluator_id',
            name='unique_evaluation_per_response_evaluator',
        ),
    )
    op.create_index(
        op.f('ix_human_evaluation_results_id'), 'human_evaluation_results', ['id'], unique=False
    )

    op.create_table(
        'invitations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column(
            'role',
            sa.Enum('ORG_ADMIN', 'CONTRIBUTOR', 'ANNOTATOR', name='organizationrole'),
            nullable=False,
        ),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('invited_by', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted', sa.Boolean(), nullable=False),
        sa.Column('pending_user_id', sa.String(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['invited_by'],
            ['users.id'],
        ),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['organizations.id'],
        ),
        sa.ForeignKeyConstraint(
            ['pending_user_id'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_invitations_id'), 'invitations', ['id'], unique=False)
    op.create_index(op.f('ix_invitations_token'), 'invitations', ['token'], unique=True)

    op.create_table(
        'notification_preferences',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('notification_type', sa.String(), nullable=False),
        sa.Column('email_enabled', sa.Boolean(), nullable=False),
        sa.Column('in_app_enabled', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'notification_type', name='unique_user_notification_preference'
        ),
    )
    op.create_index(
        op.f('ix_notification_preferences_id'), 'notification_preferences', ['id'], unique=False
    )

    op.create_table(
        'notifications',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=True),
        sa.Column(
            'type',
            sa.Enum(
                'project_created',
                'project_updated',
                'project_shared',
                'project_completed',
                'project_deleted',
                'project_archived',
                'project_published',
                'data_import_success',
                'data_import_failed',
                'data_export_completed',
                'data_upload_completed',
                'annotation_completed',
                'annotation_assigned',
                'labeling_config_updated',
                'annotation_batch_completed',
                'task_assigned',
                'task_assignment_removed',
                'task_due_soon',
                'task_overdue',
                'llm_generation_completed',
                'llm_generation_failed',
                'evaluation_completed',
                'evaluation_failed',
                'organization_invitation_sent',
                'organization_invitation_accepted',
                'member_joined',
                'system_alert',
                'error_occurred',
                'model_api_key_invalid',
                'system_maintenance',
                'security_alert',
                'api_quota_warning',
                'performance_alert',
                'long_running_operation_update',
                name='notificationtype',
            ),
            nullable=False,
        ),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['organizations.id'],
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notifications_id'), 'notifications', ['id'], unique=False)

    op.create_table(
        'organization_memberships',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column(
            'role',
            sa.Enum('ORG_ADMIN', 'CONTRIBUTOR', 'ANNOTATOR', name='organizationrole'),
            nullable=False,
        ),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column(
            'joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['organizations.id'],
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'organization_id', name='unique_user_organization'),
    )
    op.create_index(
        op.f('ix_organization_memberships_id'), 'organization_memberships', ['id'], unique=False
    )

    op.create_table(
        'projects',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=False),
        # Note: organization_id removed - using project_organizations join table instead
        sa.Column('label_config', sa.Text(), nullable=True),
        # Note: generation_structure removed in migration 002 - using generation_config.prompt_structures instead
        sa.Column('expert_instruction', sa.Text(), nullable=True),
        sa.Column('show_instruction', sa.Boolean(), nullable=False),
        sa.Column('show_skip_button', sa.Boolean(), nullable=False),
        sa.Column('enable_empty_annotation', sa.Boolean(), nullable=False),
        sa.Column('maximum_annotations', sa.Integer(), nullable=False),
        sa.Column('min_annotations_per_task', sa.Integer(), nullable=False),
        sa.Column('assignment_mode', sa.String(length=50), nullable=True),
        sa.Column('show_submit_button', sa.Boolean(), nullable=False),
        sa.Column('require_comment_on_skip', sa.Boolean(), nullable=False),
        sa.Column('generation_config', sa.JSON(), nullable=True),
        sa.Column('llm_model_ids', sa.JSON(), nullable=True),
        sa.Column('evaluation_config', sa.JSON(), nullable=True),
        sa.Column('is_published', sa.Boolean(), nullable=False),
        sa.Column('is_archived', sa.Boolean(), nullable=False),
        # Immediate evaluation setting (migration 005)
        sa.Column(
            'immediate_evaluation_enabled', sa.Boolean(), nullable=False, server_default='false'
        ),
        # Annotation time limit settings (migration 009)
        sa.Column(
            'annotation_time_limit_enabled', sa.Boolean(), nullable=False, server_default='false'
        ),
        sa.Column('annotation_time_limit_seconds', sa.Integer(), nullable=True),
        # Label config versioning columns added in migration 008
        sa.Column('label_config_version', sa.String(50), nullable=True),
        sa.Column(
            'label_config_history',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['created_by'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_projects_id'), 'projects', ['id'], unique=False)
    op.create_index(
        'ix_projects_label_config_version', 'projects', ['label_config_version']
    )  # Added in migration 008

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_refresh_tokens_id'), 'refresh_tokens', ['id'], unique=False)
    op.create_index(
        op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True
    )

    op.create_table(
        'tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('normalized_name', sa.String(length=100), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['created_by'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tags_name'), 'tags', ['name'], unique=True)
    op.create_index(op.f('ix_tags_normalized_name'), 'tags', ['normalized_name'], unique=False)

    op.create_table(
        'task_templates',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('semantic_version', sa.String(), nullable=False),
        sa.Column('version_notes', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('parent_template_id', sa.String(), nullable=True),
        sa.Column('schema', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=False),
        sa.Column('is_public', sa.Boolean(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Float(), nullable=True),
        sa.Column('rating_count', sa.Integer(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('preview_image_url', sa.String(), nullable=True),
        sa.Column('template_metadata', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['created_by'],
            ['users.id'],
        ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_template_id'], ['task_templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_task_templates_id'), 'task_templates', ['id'], unique=False)

    op.create_table(
        'user_column_preferences',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=True),
        sa.Column('column_settings', sa.JSON(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'task_id', name='unique_user_task_preferences'),
    )
    op.create_index(
        op.f('ix_user_column_preferences_id'), 'user_column_preferences', ['id'], unique=False
    )

    # ============================================================================
    # TABLES DEPENDENT ON PROJECTS
    # ============================================================================

    op.create_table(
        'data_exports',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('exported_by', sa.String(), nullable=False),
        sa.Column('export_format', sa.String(), nullable=False),
        sa.Column('filters', sa.JSON(), nullable=True),
        sa.Column('total_items', sa.Integer(), nullable=False),
        sa.Column('file_name', sa.String(), nullable=False),
        sa.Column('file_url', sa.Text(), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['exported_by'],
            ['users.id'],
        ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_data_exports_id'), 'data_exports', ['id'], unique=False)

    op.create_table(
        'data_imports',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('imported_by', sa.String(), nullable=False),
        sa.Column('file_name', sa.String(), nullable=True),
        sa.Column('file_format', sa.String(), nullable=False),
        sa.Column('total_items', sa.Integer(), nullable=False),
        sa.Column('imported_items', sa.Integer(), nullable=False),
        sa.Column('failed_items', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['imported_by'],
            ['users.id'],
        ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_data_imports_id'), 'data_imports', ['id'], unique=False)

    op.create_table(
        'generations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('generation_id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=True),
        sa.Column('model_id', sa.String(), nullable=False),
        sa.Column('case_data', sa.Text(), nullable=False),
        sa.Column('response_content', sa.Text(), nullable=False),
        sa.Column('usage_stats', sa.JSON(), nullable=True),
        sa.Column('response_metadata', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        # Parsing columns added in migration 007
        sa.Column('parsed_annotation', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('parse_status', sa.String(), nullable=True),
        sa.Column('parse_error', sa.Text(), nullable=True),
        sa.Column('parse_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        # Label config versioning columns added in migration 008
        sa.Column('label_config_version', sa.String(50), nullable=True),
        sa.Column('label_config_snapshot', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['generation_id'],
            ['response_generations.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_generations_id'), 'generations', ['id'], unique=False)
    op.create_index(
        'ix_generations_label_config_version', 'generations', ['label_config_version']
    )  # Added in migration 008

    op.create_table(
        'human_evaluation_dimensions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('dimension_name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('scale_labels', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'dimension_name', name='unique_project_dimension'),
    )
    op.create_index(
        op.f('ix_human_evaluation_dimensions_id'),
        'human_evaluation_dimensions',
        ['id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_human_evaluation_dimensions_project_id'),
        'human_evaluation_dimensions',
        ['project_id'],
        unique=False,
    )

    op.create_table(
        'human_evaluation_sessions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('evaluator_id', sa.String(), nullable=False),
        sa.Column('session_type', sa.String(length=50), nullable=False),
        sa.Column('items_evaluated', sa.Integer(), nullable=False),
        sa.Column('total_items', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('session_config', sa.JSON(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['evaluator_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_human_evaluation_sessions_evaluator_id'),
        'human_evaluation_sessions',
        ['evaluator_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_human_evaluation_sessions_id'), 'human_evaluation_sessions', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_human_evaluation_sessions_project_id'),
        'human_evaluation_sessions',
        ['project_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_human_evaluation_sessions_status'),
        'human_evaluation_sessions',
        ['status'],
        unique=False,
    )

    op.create_table(
        'project_members',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('assigned_by', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'user_id', name='unique_project_member'),
    )
    op.create_index(op.f('ix_project_members_id'), 'project_members', ['id'], unique=False)
    op.create_index(
        op.f('ix_project_members_project_id'), 'project_members', ['project_id'], unique=False
    )
    op.create_index(
        op.f('ix_project_members_user_id'), 'project_members', ['user_id'], unique=False
    )

    op.create_table(
        'project_organizations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('assigned_by', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['assigned_by'],
            ['users.id'],
        ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'organization_id', name='unique_project_organization'),
    )
    op.create_index(
        op.f('ix_project_organizations_id'), 'project_organizations', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_project_organizations_organization_id'),
        'project_organizations',
        ['organization_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_project_organizations_project_id'),
        'project_organizations',
        ['project_id'],
        unique=False,
    )

    # Project reports table - Added in migration 005
    op.create_table(
        'project_reports',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_by', sa.String(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['published_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_project_reports_id'), 'project_reports', ['id'], unique=False)
    op.create_index(
        op.f('ix_project_reports_project_id'), 'project_reports', ['project_id'], unique=True
    )
    op.create_index(
        op.f('ix_project_reports_is_published'), 'project_reports', ['is_published'], unique=False
    )

    op.create_table(
        'tasks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('assigned_to', sa.String(), nullable=True),
        sa.Column('is_labeled', sa.Boolean(), nullable=False),
        sa.Column('total_annotations', sa.Integer(), nullable=False),
        sa.Column('cancelled_annotations', sa.Integer(), nullable=False),
        # NOTE: total_predictions removed (migration 004) - calculated on-the-fly from Generation table
        sa.Column('comment_count', sa.Integer(), nullable=False),
        sa.Column('unresolved_comment_count', sa.Integer(), nullable=False),
        sa.Column('last_comment_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('comment_authors', sa.JSON(), nullable=True),
        sa.Column('file_upload_id', sa.String(), nullable=True),
        sa.Column('inner_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tasks_assigned_to'), 'tasks', ['assigned_to'], unique=False)
    op.create_index(op.f('ix_tasks_id'), 'tasks', ['id'], unique=False)
    op.create_index(op.f('ix_tasks_is_labeled'), 'tasks', ['is_labeled'], unique=False)
    op.create_index(op.f('ix_tasks_project_id'), 'tasks', ['project_id'], unique=False)

    # Skipped tasks table - Added in migration 006
    op.create_table(
        'skipped_tasks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('skipped_by', sa.String(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column(
            'skipped_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skipped_by'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_skipped_tasks_id'), 'skipped_tasks', ['id'], unique=False)
    op.create_index(op.f('ix_skipped_tasks_task_id'), 'skipped_tasks', ['task_id'], unique=False)
    op.create_index(
        op.f('ix_skipped_tasks_project_id'), 'skipped_tasks', ['project_id'], unique=False
    )
    op.create_index(
        op.f('ix_skipped_tasks_skipped_by'), 'skipped_tasks', ['skipped_by'], unique=False
    )

    # Evaluation sample results table - Added in migration 003
    op.create_table(
        'evaluation_sample_results',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('evaluation_id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=False),
        sa.Column('generation_id', sa.String(), nullable=True),
        sa.Column('field_name', sa.String(), nullable=False),
        sa.Column('answer_type', sa.String(), nullable=False),
        sa.Column('ground_truth', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('prediction', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['generation_id'], ['generations.id'], ondelete='SET NULL'),
    )
    op.create_index(
        'idx_evaluation_sample_results_eval_id', 'evaluation_sample_results', ['evaluation_id']
    )
    op.create_index(
        'idx_evaluation_sample_results_task_id', 'evaluation_sample_results', ['task_id']
    )
    op.create_index('idx_evaluation_sample_results_passed', 'evaluation_sample_results', ['passed'])
    op.create_index(
        'idx_evaluation_sample_results_field_name', 'evaluation_sample_results', ['field_name']
    )

    # Add foreign key from evaluations.project_id to projects.id (Added in migration 003)
    op.create_foreign_key(
        'fk_evaluations_project_id',
        'evaluations',
        'projects',
        ['project_id'],
        ['id'],
        ondelete='CASCADE',
    )

    op.create_table(
        'template_ratings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('template_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('review', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('rating >= 1 AND rating <= 5', name='check_rating_range'),
        sa.ForeignKeyConstraint(['template_id'], ['task_templates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('template_id', 'user_id', name='unique_template_rating'),
    )
    op.create_index(op.f('ix_template_ratings_id'), 'template_ratings', ['id'], unique=False)

    op.create_table(
        'template_sharing',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('template_id', sa.String(), nullable=False),
        sa.Column('shared_with_organization_id', sa.String(), nullable=False),
        sa.Column('permission', sa.String(), nullable=False),
        sa.Column('shared_by', sa.String(), nullable=False),
        sa.Column(
            'shared_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['shared_by'],
            ['users.id'],
        ),
        sa.ForeignKeyConstraint(
            ['shared_with_organization_id'], ['organizations.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['template_id'], ['task_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'template_id', 'shared_with_organization_id', name='unique_template_sharing'
        ),
    )
    op.create_index(op.f('ix_template_sharing_id'), 'template_sharing', ['id'], unique=False)

    op.create_table(
        'template_versions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('template_id', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('schema', sa.JSON(), nullable=False),
        sa.Column('version_notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('is_major_version', sa.Boolean(), nullable=False),
        sa.Column('parent_version_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ['created_by'],
            ['users.id'],
        ),
        sa.ForeignKeyConstraint(
            ['parent_version_id'], ['template_versions.id'], ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(['template_id'], ['task_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('template_id', 'version', name='unique_template_version'),
    )
    op.create_index(op.f('ix_template_versions_id'), 'template_versions', ['id'], unique=False)

    op.create_table(
        'annotations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('completed_by', sa.String(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('draft', sa.JSON(), nullable=True),
        sa.Column('was_cancelled', sa.Boolean(), nullable=False),
        sa.Column('ground_truth', sa.Boolean(), nullable=False),
        sa.Column('lead_time', sa.Float(), nullable=True),
        sa.Column('prediction_scores', sa.JSON(), nullable=True),
        sa.Column('reviewed_by', sa.String(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_result', sa.String(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['completed_by'],
            ['users.id'],
        ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['reviewed_by'],
            ['users.id'],
        ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_annotations_completed_by'), 'annotations', ['completed_by'], unique=False
    )
    op.create_index(op.f('ix_annotations_id'), 'annotations', ['id'], unique=False)
    op.create_index(op.f('ix_annotations_project_id'), 'annotations', ['project_id'], unique=False)
    op.create_index(op.f('ix_annotations_task_id'), 'annotations', ['task_id'], unique=False)

    op.create_table(
        'likert_scale_evaluations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=False),
        sa.Column('response_id', sa.String(), nullable=False),
        sa.Column('dimension', sa.String(length=100), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('time_spent_seconds', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint('rating >= 1 AND rating <= 5', name='check_likert_rating_range'),
        sa.ForeignKeyConstraint(
            ['session_id'], ['human_evaluation_sessions.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_likert_scale_evaluations_dimension'),
        'likert_scale_evaluations',
        ['dimension'],
        unique=False,
    )
    op.create_index(
        op.f('ix_likert_scale_evaluations_id'), 'likert_scale_evaluations', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_likert_scale_evaluations_session_id'),
        'likert_scale_evaluations',
        ['session_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_likert_scale_evaluations_task_id'),
        'likert_scale_evaluations',
        ['task_id'],
        unique=False,
    )

    op.create_table(
        'preference_rankings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=False),
        sa.Column('response_a_id', sa.String(), nullable=False),
        sa.Column('response_b_id', sa.String(), nullable=False),
        sa.Column('winner', sa.String(length=10), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('time_spent_seconds', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['session_id'], ['human_evaluation_sessions.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_preference_rankings_id'), 'preference_rankings', ['id'], unique=False)
    op.create_index(
        op.f('ix_preference_rankings_session_id'),
        'preference_rankings',
        ['session_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_preference_rankings_task_id'), 'preference_rankings', ['task_id'], unique=False
    )

    op.create_table(
        'task_assignments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('assigned_by', sa.String(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column(
            'assigned_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['assigned_by'],
            ['users.id'],
        ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id', 'user_id', name='unique_task_assignment'),
    )
    op.create_index('ix_task_assignment_priority', 'task_assignments', ['priority'], unique=False)
    op.create_index('ix_task_assignment_status', 'task_assignments', ['status'], unique=False)
    op.create_index(op.f('ix_task_assignments_id'), 'task_assignments', ['id'], unique=False)
    op.create_index(
        op.f('ix_task_assignments_task_id'), 'task_assignments', ['task_id'], unique=False
    )
    op.create_index(
        op.f('ix_task_assignments_user_id'), 'task_assignments', ['user_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema - Drop all tables in reverse order."""

    # Drop all tables in reverse order of creation
    op.drop_index(op.f('ix_task_assignments_user_id'), table_name='task_assignments')
    op.drop_index(op.f('ix_task_assignments_task_id'), table_name='task_assignments')
    op.drop_index(op.f('ix_task_assignments_id'), table_name='task_assignments')
    op.drop_index('ix_task_assignment_status', table_name='task_assignments')
    op.drop_index('ix_task_assignment_priority', table_name='task_assignments')
    op.drop_table('task_assignments')
    op.drop_index(op.f('ix_preference_rankings_task_id'), table_name='preference_rankings')
    op.drop_index(op.f('ix_preference_rankings_session_id'), table_name='preference_rankings')
    op.drop_index(op.f('ix_preference_rankings_id'), table_name='preference_rankings')
    op.drop_table('preference_rankings')
    op.drop_index(
        op.f('ix_likert_scale_evaluations_task_id'), table_name='likert_scale_evaluations'
    )
    op.drop_index(
        op.f('ix_likert_scale_evaluations_session_id'), table_name='likert_scale_evaluations'
    )
    op.drop_index(op.f('ix_likert_scale_evaluations_id'), table_name='likert_scale_evaluations')
    op.drop_index(
        op.f('ix_likert_scale_evaluations_dimension'), table_name='likert_scale_evaluations'
    )
    op.drop_table('likert_scale_evaluations')
    op.drop_index(op.f('ix_annotations_task_id'), table_name='annotations')
    op.drop_index(op.f('ix_annotations_project_id'), table_name='annotations')
    op.drop_index(op.f('ix_annotations_id'), table_name='annotations')
    op.drop_index(op.f('ix_annotations_completed_by'), table_name='annotations')
    op.drop_table('annotations')
    op.drop_index(op.f('ix_template_versions_id'), table_name='template_versions')
    op.drop_table('template_versions')
    op.drop_index(op.f('ix_template_sharing_id'), table_name='template_sharing')
    op.drop_table('template_sharing')
    op.drop_index(op.f('ix_template_ratings_id'), table_name='template_ratings')
    op.drop_table('template_ratings')
    op.drop_constraint('fk_evaluations_project_id', 'evaluations', type_='foreignkey')
    op.drop_index(
        'idx_evaluation_sample_results_field_name', table_name='evaluation_sample_results'
    )
    op.drop_index('idx_evaluation_sample_results_passed', table_name='evaluation_sample_results')
    op.drop_index('idx_evaluation_sample_results_task_id', table_name='evaluation_sample_results')
    op.drop_index('idx_evaluation_sample_results_eval_id', table_name='evaluation_sample_results')
    op.drop_table('evaluation_sample_results')
    op.drop_index(op.f('ix_skipped_tasks_skipped_by'), table_name='skipped_tasks')
    op.drop_index(op.f('ix_skipped_tasks_project_id'), table_name='skipped_tasks')
    op.drop_index(op.f('ix_skipped_tasks_task_id'), table_name='skipped_tasks')
    op.drop_index(op.f('ix_skipped_tasks_id'), table_name='skipped_tasks')
    op.drop_table('skipped_tasks')
    op.drop_index(op.f('ix_tasks_project_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_is_labeled'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_assigned_to'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_index(op.f('ix_project_reports_is_published'), table_name='project_reports')
    op.drop_index(op.f('ix_project_reports_project_id'), table_name='project_reports')
    op.drop_index(op.f('ix_project_reports_id'), table_name='project_reports')
    op.drop_table('project_reports')
    op.drop_index(op.f('ix_project_organizations_project_id'), table_name='project_organizations')
    op.drop_index(
        op.f('ix_project_organizations_organization_id'), table_name='project_organizations'
    )
    op.drop_index(op.f('ix_project_organizations_id'), table_name='project_organizations')
    op.drop_table('project_organizations')
    op.drop_index(op.f('ix_project_members_user_id'), table_name='project_members')
    op.drop_index(op.f('ix_project_members_project_id'), table_name='project_members')
    op.drop_index(op.f('ix_project_members_id'), table_name='project_members')
    op.drop_table('project_members')
    op.drop_index(
        op.f('ix_human_evaluation_sessions_status'), table_name='human_evaluation_sessions'
    )
    op.drop_index(
        op.f('ix_human_evaluation_sessions_project_id'), table_name='human_evaluation_sessions'
    )
    op.drop_index(op.f('ix_human_evaluation_sessions_id'), table_name='human_evaluation_sessions')
    op.drop_index(
        op.f('ix_human_evaluation_sessions_evaluator_id'), table_name='human_evaluation_sessions'
    )
    op.drop_table('human_evaluation_sessions')
    op.drop_index(
        op.f('ix_human_evaluation_dimensions_project_id'), table_name='human_evaluation_dimensions'
    )
    op.drop_index(
        op.f('ix_human_evaluation_dimensions_id'), table_name='human_evaluation_dimensions'
    )
    op.drop_table('human_evaluation_dimensions')
    op.drop_index('ix_generations_label_config_version', table_name='generations')
    op.drop_index(op.f('ix_generations_id'), table_name='generations')
    op.drop_table('generations')
    op.drop_index(op.f('ix_data_imports_id'), table_name='data_imports')
    op.drop_table('data_imports')
    op.drop_index(op.f('ix_data_exports_id'), table_name='data_exports')
    op.drop_table('data_exports')
    op.drop_index(op.f('ix_user_column_preferences_id'), table_name='user_column_preferences')
    op.drop_table('user_column_preferences')
    op.drop_index(op.f('ix_task_templates_id'), table_name='task_templates')
    op.drop_table('task_templates')
    op.drop_index(op.f('ix_tags_normalized_name'), table_name='tags')
    op.drop_index(op.f('ix_tags_name'), table_name='tags')
    op.drop_table('tags')
    op.drop_index(op.f('ix_refresh_tokens_token_hash'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index('ix_projects_label_config_version', table_name='projects')
    op.drop_index(op.f('ix_projects_id'), table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_organization_memberships_id'), table_name='organization_memberships')
    op.drop_table('organization_memberships')
    op.drop_index(op.f('ix_notifications_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_notification_preferences_id'), table_name='notification_preferences')
    op.drop_table('notification_preferences')
    op.drop_index(op.f('ix_invitations_token'), table_name='invitations')
    op.drop_index(op.f('ix_invitations_id'), table_name='invitations')
    op.drop_table('invitations')
    op.drop_index(op.f('ix_human_evaluation_results_id'), table_name='human_evaluation_results')
    op.drop_table('human_evaluation_results')
    op.drop_index(op.f('ix_human_evaluation_mappings_id'), table_name='human_evaluation_mappings')
    op.drop_table('human_evaluation_mappings')
    op.drop_index(op.f('ix_feature_flags_name'), table_name='feature_flags')
    op.drop_index(op.f('ix_feature_flags_id'), table_name='feature_flags')
    op.drop_table('feature_flags')
    op.drop_index(op.f('ix_evaluation_metrics_id'), table_name='evaluation_metrics')
    op.drop_table('evaluation_metrics')
    # NOTE: default_prompts table removed - was deprecated
    op.drop_index(
        op.f('ix_default_evaluation_configs_task_type'), table_name='default_evaluation_configs'
    )
    op.drop_table('default_evaluation_configs')
    op.drop_index(op.f('ix_default_config_history_task_type'), table_name='default_config_history')
    op.drop_index(op.f('ix_default_config_history_id'), table_name='default_config_history')
    op.drop_index(op.f('ix_default_config_history_changed_at'), table_name='default_config_history')
    op.drop_table('default_config_history')
    op.drop_index('ix_users_pseudonym', table_name='users')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_password_reset_token'), table_name='users')
    op.drop_index(op.f('ix_users_invitation_token'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email_verification_token'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_uploaded_data_id'), table_name='uploaded_data')
    op.drop_table('uploaded_data')
    op.drop_index(op.f('ix_template_categories_id'), table_name='template_categories')
    op.drop_table('template_categories')
    op.drop_index('ix_response_generations_structure_key', table_name='response_generations')
    op.drop_index(op.f('ix_response_generations_id'), table_name='response_generations')
    op.drop_table('response_generations')
    op.drop_index(op.f('ix_organizations_slug'), table_name='organizations')
    op.drop_index(op.f('ix_organizations_id'), table_name='organizations')
    op.drop_table('organizations')
    op.drop_index(op.f('ix_llm_models_id'), table_name='llm_models')
    op.drop_table('llm_models')
    op.drop_index(op.f('ix_human_evaluation_configs_id'), table_name='human_evaluation_configs')
    op.drop_table('human_evaluation_configs')
    op.drop_index('idx_evaluations_project_id', table_name='evaluations')
    op.drop_index(op.f('ix_evaluations_id'), table_name='evaluations')
    op.drop_table('evaluations')
    op.drop_index(op.f('ix_evaluation_types_id'), table_name='evaluation_types')
    op.drop_table('evaluation_types')

    # Drop enum types (PostgreSQL only)
    op.execute("DROP TYPE IF EXISTS legalexpertiselevel")
    op.execute("DROP TYPE IF EXISTS germanproficiency")
    op.execute("DROP TYPE IF EXISTS degreeprogramtype")

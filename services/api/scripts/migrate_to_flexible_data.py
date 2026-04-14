#!/usr/bin/env python3
"""
Data migration script to convert existing projects to flexible data model

Issue #220: Migrate structured task data to flexible JSON format
"""

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import get_database_url


def migrate_task_data(db_session):
    """
    Migrate existing task data to flexible format

    Old format (list): [{"question": "...", "answer": "..."}, ...]
    New format (flexible): {"items": [{"question": "...", "answer": "..."}, ...]}

    This preserves backward compatibility while enabling flexible structures
    """

    # Get all projects

    migrated_count = 0
    skipped_count = 0
    error_count = 0

    print(f"Found {len(projects)} projects to check")

    for task in projects:
        try:
            # Skip if already migrated or has no data
            if task.data is None:
                skipped_count += 1
                continue

            # Check if data is already in flexible format (dict)
            if isinstance(task.data, dict) and not isinstance(task.data, list):
                # Already migrated or using new format
                skipped_count += 1
                continue

            # Migrate list format to flexible format
            if isinstance(task.data, list):
                print(f"Migrating task {task.id}: {task.name}")

                # Wrap list in object
                task.data = {"items": task.data}

                # If template_data exists and has fields, merge them
                if task.template_data and isinstance(task.template_data, dict):
                    fields = task.template_data.get("fields", {})
                    if fields and isinstance(fields, dict):
                        # Merge fields into data (but don't overwrite items)
                        for key, value in fields.items():
                            if key != "items":
                                task.data[key] = value

                migrated_count += 1
            else:
                print(f"Warning: Project {task.id} has unexpected data type: {type(task.data)}")
                error_count += 1

        except Exception as e:
            print(f"Error migrating task {task.id}: {str(e)}")
            error_count += 1

    # Commit all changes
    if migrated_count > 0:
        db_session.commit()
        print(f"\nSuccessfully migrated {migrated_count} projects")

    print(f"Skipped {skipped_count} projects (already migrated or no data)")
    if error_count > 0:
        print(f"Errors encountered: {error_count} projects")

    return migrated_count, skipped_count, error_count


def add_default_label_configs(db_session):
    """
    Add default label configurations for projects without them
    based on their template or task type
    """

    # Example label configs for different task types
    default_configs = {
        "qa": {
            "display": {
                "type": "object",
                "fields": [
                    {"name": "question", "label": "Question", "type": "text"},
                    {"name": "answer", "label": "Expected Answer", "type": "text"},
                ],
            }
        },
        "qa_reasoning": {
            "display": {
                "type": "object",
                "fields": [
                    {"name": "case_name", "label": "Case", "type": "text"},
                    {"name": "fall", "label": "Case Description", "type": "text"},
                    {"name": "prompt", "label": "Legal Question", "type": "text"},
                    {"name": "solution", "label": "Solution", "type": "text"},
                    {"name": "reasoning", "label": "Legal Reasoning", "type": "text"},
                ],
            }
        },
    }

    # Update projects without label_config

    updated_count = 0

    for task in projects_without_config:
        # Determine task type from template or task_type_id
        task_type = None
        if task.template_id:
            task_type = task.template_id
        elif task.task_type_id:
            task_type = task.task_type_id

        if task_type and task_type in default_configs:
            task.label_config = json.dumps(default_configs[task_type])
            updated_count += 1

    if updated_count > 0:
        db_session.commit()
        print(f"\nAdded default label configs to {updated_count} projects")

    return updated_count


def main():
    """Run the migration"""
    print("Starting flexible data migration...")

    # Create database session
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    db_session = Session()

    try:
        # Run data migration
        migrated, skipped, errors = migrate_task_data(db_session)

        # Add default label configs
        configs_added = add_default_label_configs(db_session)

        print("\nMigration complete!")
        print(f"Total projects migrated: {migrated}")
        print(f"Label configs added: {configs_added}")

        if errors > 0:
            print(f"\nWARNING: {errors} projects had errors during migration")
            return 1

        return 0

    except Exception as e:
        print(f"Migration failed: {str(e)}")
        db_session.rollback()
        return 1
    finally:
        db_session.close()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Cleanup script to remove legacy generation_prompt and system_prompt fields from task metadata
These fields are no longer used after implementing generation structure configuration (Issue #519)
"""


from sqlalchemy import text

from database import get_db


def cleanup_legacy_prompt_fields():
    """Remove generation_prompt and system_prompt from all task metadata"""
    db = next(get_db())

    try:
        # Update all tasks to remove the legacy prompt fields from metadata
        result = db.execute(
            text(
                """
            UPDATE tasks 
            SET meta = (meta::jsonb - 'generation_prompt' - 'system_prompt')::json
            WHERE meta IS NOT NULL 
            AND (meta::jsonb ? 'generation_prompt' OR meta::jsonb ? 'system_prompt')
        """
            )
        )

        db.commit()

        print(f"✅ Successfully cleaned up legacy prompt fields from {result.rowcount} tasks")
        print("   - Removed 'generation_prompt' fields")
        print("   - Removed 'system_prompt' fields")
        print("   - Tasks now use project-level generation_structure configuration")

    except Exception as e:
        db.rollback()
        print(f"❌ Error cleaning up legacy fields: {e}")

    finally:
        db.close()


if __name__ == "__main__":
    cleanup_legacy_prompt_fields()

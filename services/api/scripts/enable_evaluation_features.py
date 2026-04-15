#!/usr/bin/env python3
"""
Script to enable essential evaluation feature flags for Issue #483
This activates the comprehensive evaluation system UI and core functionality.
"""

import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

# Master feature flag for entire evaluation system
MASTER_FLAG = 'EVALUATION_SYSTEM'

# Legacy flags (deprecated but kept for compatibility)
LEGACY_FLAGS = [
    'EVALUATION_CONFIG_UI',  # Enable evaluation config in project details
    'EVALUATION_ANSWER_TYPE_DETECTION',  # Enable answer type detection
    'EVALUATION_RESULTS_DASHBOARD',  # Enable evaluation dashboard page
    'EVALUATION_AUTOMATED_METRICS',  # Enable automated NLP metrics
    'EVALUATION_HUMAN_LIKERT',  # Enable Likert scale ratings
    'EVALUATION_HUMAN_PREFERENCE',  # Enable preference ranking
    'EVALUATION_BATCH_PROCESSING',  # Enable batch processing
    'EVALUATION_GERMAN_LEGAL_METRICS',  # Enable German legal metrics
]


def get_database_url():
    """Get database URL from environment or use default."""
    return os.getenv('DATABASE_URL', 'sqlite:///test.db')


def enable_feature_flags(use_master=True):
    """Enable evaluation feature flags in the database."""

    database_url = get_database_url()
    print(
        f"Connecting to database: {database_url.split('@')[-1] if '@' in database_url else database_url}"
    )

    try:
        # Create database connection
        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        db = Session()

        if use_master:
            # Enable single master flag (recommended)
            flags_to_enable = [MASTER_FLAG]
            print(f"\n🎯 Enabling master evaluation flag: {MASTER_FLAG}")
        else:
            # Enable legacy individual flags (for compatibility)
            flags_to_enable = LEGACY_FLAGS
            print(
                f"\n🎯 Enabling {len(flags_to_enable)} individual evaluation feature flags (legacy mode)..."
            )

        enabled_count = 0
        for flag_name in flags_to_enable:
            try:
                # Update the feature flag
                result = db.execute(
                    text("UPDATE feature_flags SET is_enabled = true WHERE name = :flag_name"),
                    {"flag_name": flag_name},
                )

                if result.rowcount > 0:
                    print(f"✅ Enabled: {flag_name}")
                    enabled_count += 1
                else:
                    print(f"⚠️  Flag not found: {flag_name}")

            except Exception as e:
                print(f"❌ Error enabling {flag_name}: {e}")

        # Commit the changes
        db.commit()

        if use_master:
            print(f"\n🚀 Evaluation system activated! Single flag enabled: {MASTER_FLAG}")
        else:
            print(
                f"\n🚀 Successfully enabled {enabled_count}/{len(flags_to_enable)} individual feature flags!"
            )

        # Verify the changes
        print("\n📋 Current feature flag status:")
        result = db.execute(
            text(
                "SELECT name, is_enabled FROM feature_flags WHERE name LIKE '%EVALUATION%' ORDER BY name"
            )
        )

        for row in result:
            status = "🟢 ENABLED" if row[1] else "🔴 DISABLED"
            print(f"   {row[0]}: {status}")

        db.close()
        return True

    except OperationalError as e:
        if "could not translate host name" in str(e):
            print("❌ Cannot connect to database: Not in Docker environment")
            print("💡 To enable flags manually, run this SQL in your database:")
            print("\n" + "=" * 60)
            for flag_name in flags_to_enable:
                print(f"UPDATE feature_flags SET is_enabled = true WHERE name = '{flag_name}';")
            print("=" * 60 + "\n")
            return False
        else:
            print(f"❌ Database error: {e}")
            return False

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def check_current_status():
    """Check current status of evaluation feature flags."""

    database_url = get_database_url()

    try:
        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        db = Session()

        print("📋 Current evaluation feature flag status:")
        result = db.execute(
            text(
                "SELECT name, is_enabled FROM feature_flags WHERE name LIKE '%EVALUATION%' ORDER BY name"
            )
        )

        total_flags = 0
        enabled_flags = 0

        for row in result:
            total_flags += 1
            if row[1]:
                enabled_flags += 1
                status = "🟢 ENABLED"
            else:
                status = "🔴 DISABLED"
            print(f"   {row[0]}: {status}")

        print(f"\n📊 Summary: {enabled_flags}/{total_flags} evaluation flags enabled")
        db.close()
        return True

    except Exception as e:
        print(f"❌ Cannot check status: {e}")
        return False


if __name__ == "__main__":
    print("🔧 BenGER Evaluation System Activation Script")
    print("=" * 50)

    # Parse command line arguments
    use_legacy = "--legacy" in sys.argv
    check_only = "--status" in sys.argv

    if check_only:
        check_current_status()
    else:
        if use_legacy:
            print("🎯 Target: Individual feature flags (legacy mode)")
            success = enable_feature_flags(use_master=False)
        else:
            print("🎯 Target: Master evaluation flag (recommended)")
            success = enable_feature_flags(use_master=True)

        if success:
            print("\n✅ EVALUATION SYSTEM ACTIVATION COMPLETE!")
            print("🌐 The evaluation UI should now be accessible at:")
            print("   - http://benger.localhost/evaluation")
            print("   - Project details pages should show evaluation configuration")
            print("\n🔄 You may need to refresh your browser to see changes.")
        else:
            print("\n⚠️  Could not activate automatically - manual SQL commands provided above")

    print("\n" + "=" * 50)

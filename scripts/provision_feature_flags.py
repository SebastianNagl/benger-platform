#!/usr/bin/env python3
"""
Automated feature flag provisioning for deployments

This script ensures required feature flags exist in the database.
It's safe to run multiple times - only creates missing flags.
"""
import sys
import os
sys.path.append('/app')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import json
from datetime import datetime, timezone

# Feature flags configuration
REQUIRED_FLAGS = [
    {
        "name": "data_page",
        "description": "Enable access to Data Management page",
        "is_enabled": False,  # Coming soon - disabled by default
        "target_criteria": None,
        "rollout_percentage": 100
    },
    {
        "name": "evaluation_page", 
        "description": "Enable access to Evaluation page",
        "is_enabled": False,  # Coming soon - disabled by default
        "target_criteria": None,
        "rollout_percentage": 100
    }
]

def provision_feature_flags():
    """Provision required feature flags in database"""
    
    DATABASE_URI = os.getenv('DATABASE_URI')
    if not DATABASE_URI:
        print("❌ DATABASE_URI not found in environment")
        return False
        
    engine = create_engine(DATABASE_URI)
    
    try:
        with engine.connect() as conn:
            print("🔧 Provisioning feature flags...")
            
            # Check existing flags
            result = conn.execute(text("SELECT name FROM feature_flags"))
            existing_flags = {row[0] for row in result}
            
            created_count = 0
            skipped_count = 0
            
            for flag_config in REQUIRED_FLAGS:
                flag_name = flag_config["name"]
                
                if flag_name in existing_flags:
                    print(f"   ✓ {flag_name} (exists)")
                    skipped_count += 1
                    continue
                
                # Create missing flag
                conn.execute(text("""
                    INSERT INTO feature_flags (
                        id, name, description, is_enabled, 
                        target_criteria, rollout_percentage, 
                        created_at, created_by
                    ) VALUES (
                        :id, :name, :description, :is_enabled,
                        :target_criteria, :rollout_percentage,
                        :created_at, :created_by
                    )
                """), {
                    'id': f"flag-{flag_name}-{int(datetime.now().timestamp())}",
                    'name': flag_name,
                    'description': flag_config["description"],
                    'is_enabled': flag_config["is_enabled"],
                    'target_criteria': json.dumps(flag_config["target_criteria"]) if flag_config["target_criteria"] else None,
                    'rollout_percentage': flag_config["rollout_percentage"],
                    'created_at': datetime.now(timezone.utc),
                    'created_by': 'system-deployment'
                })
                
                print(f"   ✅ {flag_name} (created)")
                created_count += 1
            
            conn.commit()
            
            print(f"\n✅ Feature flag provisioning complete:")
            print(f"   - Created: {created_count}")
            print(f"   - Existing: {skipped_count}")
            print(f"   - Total: {len(REQUIRED_FLAGS)}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error provisioning feature flags: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = provision_feature_flags()
    sys.exit(0 if success else 1)
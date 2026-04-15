#!/bin/bash
# Docker-compatible script to enable evaluation feature flags
# Run this inside the API container: docker exec -it <api-container> bash docker_enable_evaluation.sh

echo "🔧 BenGER Evaluation System Docker Activation"
echo "=============================================="

# Check if we're in a Docker environment
if [ ! -f /.dockerenv ]; then
    echo "⚠️  Warning: Not running in Docker container"
fi

# Database connection check
echo "🔍 Checking database connection..."
python3 -c "
try:
    import os
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    
    # Get database URL
    database_url = os.getenv('DATABASE_URL', 'postgresql://user:password@db:5432/benger')
    print(f'Database URL: {database_url.split(\"@\")[-1] if \"@\" in database_url else database_url}')
    
    # Test connection
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Check if feature flags table exists
    result = db.execute(text('SELECT COUNT(*) FROM feature_flags'))
    flag_count = result.scalar()
    print(f'✅ Database connected. Found {flag_count} feature flags.')
    
    # Enable master evaluation flag (recommended)
    master_flag = 'EVALUATION_SYSTEM'
    
    result = db.execute(
        text('UPDATE feature_flags SET is_enabled = true WHERE name = :flag_name'),
        {'flag_name': master_flag}
    )
    
    if result.rowcount > 0:
        print(f'✅ Enabled master flag: {master_flag}')
        db.commit()
        print(f'\\n🚀 Evaluation system activated! Single flag enabled.')
    else:
        print(f'⚠️  Master flag not found: {master_flag}')
        print('💡 Trying to enable individual flags as fallback...')
        
        # Fallback to individual flags
        individual_flags = [
            'EVALUATION_CONFIG_UI',
            'EVALUATION_RESULTS_DASHBOARD', 
            'EVALUATION_ANSWER_TYPE_DETECTION'
        ]
        
        enabled_count = 0
        for flag_name in individual_flags:
            result = db.execute(
                text('UPDATE feature_flags SET is_enabled = true WHERE name = :flag_name'),
                {'flag_name': flag_name}
            )
            if result.rowcount > 0:
                print(f'✅ Enabled: {flag_name}')
                enabled_count += 1
            else:
                print(f'⚠️  Flag not found: {flag_name}')
        
        db.commit()
        print(f'\\n🚀 Successfully enabled {enabled_count}/{len(individual_flags)} individual flags!')
    
    # Show current status
    print('\\n📋 Current evaluation feature flags:')
    result = db.execute(
        text('SELECT name, is_enabled FROM feature_flags WHERE name LIKE \\'%EVALUATION%\\' ORDER BY name')
    )
    for row in result:
        status = '🟢 ENABLED' if row[1] else '🔴 DISABLED'  
        print(f'   {row[0]}: {status}')
    
    db.close()
    
except Exception as e:
    print(f'❌ Error: {e}')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ EVALUATION SYSTEM ACTIVATED!"
    echo "🌐 The evaluation UI should now be accessible"
    echo "🔄 Refresh your browser to see changes"
else
    echo ""
    echo "❌ ACTIVATION FAILED"
    echo "💡 Try running manually:"
    echo "   docker exec -it <api-container> python3 -c \"..."
fi

echo "=============================================="
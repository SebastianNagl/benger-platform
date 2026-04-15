#!/usr/bin/env python
"""
Check differences between SQLAlchemy models and actual database schema
"""

from sqlalchemy import create_engine, inspect

from database import DATABASE_URL
from models import Base


def check_schema_differences():
    # Connect to database
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)

    # Get all existing tables
    existing_tables = set(inspector.get_table_names())
    print(f'Existing tables in database: {len(existing_tables)}')

    # Get all model tables
    model_tables = set(Base.metadata.tables.keys())
    print(f'Model tables defined: {len(model_tables)}')

    # Missing tables
    missing = model_tables - existing_tables
    if missing:
        print('\nMissing tables:')
        for table in sorted(missing):
            print(f'  - {table}')
    else:
        print('\nAll tables exist')

    # Check for missing columns
    print('\n=== Checking for missing columns ===')
    issues_found = False

    for table_name in sorted(existing_tables & model_tables):
        model_table = Base.metadata.tables[table_name]
        db_columns = {col['name'] for col in inspector.get_columns(table_name)}
        model_columns = {col.name for col in model_table.columns}

        missing_cols = model_columns - db_columns
        if missing_cols:
            issues_found = True
            print(f'\nTable {table_name} missing columns:')
            for col_name in sorted(missing_cols):
                col = model_table.columns[col_name]
                print(f'  - {col_name}: {col.type}')

    if not issues_found:
        print('All columns match between models and database!')

    return issues_found


if __name__ == '__main__':
    has_issues = check_schema_differences()
    exit(1 if has_issues else 0)

"""
Performance Monitoring Utilities for Issue #114

Provides query performance monitoring and optimization validation tools.
"""

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

from sqlalchemy import event, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class QueryPerformanceMonitor:
    """Context manager for monitoring query performance"""

    def __init__(self, operation_name: str, warn_threshold_ms: float = 100.0):
        self.operation_name = operation_name
        self.warn_threshold_ms = warn_threshold_ms
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration_ms = (self.end_time - self.start_time) * 1000

        if duration_ms > self.warn_threshold_ms:
            logger.warning(
                f"Slow query detected: {self.operation_name} took {duration_ms:.2f}ms "
                f"(threshold: {self.warn_threshold_ms}ms)"
            )
        else:
            logger.debug(f"Query performance: {self.operation_name} took {duration_ms:.2f}ms")

    @property
    def duration_ms(self) -> Optional[float]:
        """Get duration in milliseconds if measurement is complete"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return None


@contextmanager
def monitor_query_performance(operation_name: str, warn_threshold_ms: float = 100.0):
    """Context manager for monitoring database query performance

    Usage:
        with monitor_query_performance("fetch_task_data"):
            result = db.execute(query)
    """
    monitor = QueryPerformanceMonitor(operation_name, warn_threshold_ms)
    with monitor:
        yield monitor


class DatabasePerformanceValidator:
    """Validates database performance optimizations"""

    def __init__(self, db_session):
        self.db = db_session

    def check_indexes_exist(self) -> Dict[str, bool]:
        """Check if required performance indexes exist"""

        required_indexes = [
            "idx_tasks_data_reference_answers",
            "idx_tasks_data_question",
            "idx_tasks_org_ids_gin",
            "idx_tasks_eval_type_ids_gin",
            "idx_tasks_model_ids_gin",
            "idx_tasks_org_visibility_created",
            "idx_tasks_type_created",
            "idx_tasks_created_by_date",
            "idx_tasks_data_checksum",
            "idx_tasks_annotation_count",
        ]

        result = self.db.execute(
            text(
                """
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'tasks' 
            AND indexname = ANY(:index_names)
        """
            ),
            {"index_names": required_indexes},
        )

        existing_indexes = {row[0] for row in result.fetchall()}

        return {index_name: index_name in existing_indexes for index_name in required_indexes}

    def validate_json_query_performance(self) -> Dict[str, float]:
        """Validate performance of common JSON queries"""

        test_queries = {
            "reference_answers_query": """
                SELECT COUNT(*) FROM tasks 
                WHERE data->'reference_answers' IS NOT NULL
            """,
            "organization_filter": """
                SELECT COUNT(*) FROM tasks 
                WHERE organization_ids @> '["TUM"]'::jsonb
            """,
            "question_search": """
                SELECT COUNT(*) FROM tasks 
                WHERE data->'question' IS NOT NULL
            """,
            "task_type_filter": """
                SELECT COUNT(*) FROM tasks 
                WHERE task_type_id = 'qa'
            """,
        }

        performance_results = {}

        for query_name, query_sql in test_queries.items():
            with monitor_query_performance(query_name, warn_threshold_ms=50.0) as monitor:
                try:
                    self.db.execute(text(query_sql))
                    performance_results[query_name] = monitor.duration_ms
                except Exception as e:
                    logger.error(f"Query {query_name} failed: {e}")
                    performance_results[query_name] = -1  # Indicates failure

        return performance_results

    def check_query_plans_use_indexes(self) -> Dict[str, bool]:
        """Check that query execution plans use indexes instead of sequential scans"""

        test_queries = {
            "json_gin_index": """
                EXPLAIN (ANALYZE false, FORMAT json)
                SELECT id FROM tasks 
                WHERE data->'reference_answers' IS NOT NULL
                LIMIT 10
            """,
            "organization_index": """
                EXPLAIN (ANALYZE false, FORMAT json)
                SELECT id FROM tasks 
                WHERE organization_ids @> '["TUM"]'::jsonb
                LIMIT 10
            """,
            "composite_index": """
                EXPLAIN (ANALYZE false, FORMAT json)
                SELECT id FROM tasks 
                WHERE task_type_id = 'qa'
                ORDER BY created_at DESC
                LIMIT 10
            """,
        }

        results = {}

        for query_name, query_sql in test_queries.items():
            try:
                result = self.db.execute(text(query_sql))
                explain_output = result.fetchone()[0]
                plan_text = str(explain_output)

                # Check if plan uses index instead of sequential scan
                uses_index = (
                    "Index Scan" in plan_text
                    or "Bitmap Index Scan" in plan_text
                    or "Bitmap Heap Scan" in plan_text
                ) and "Seq Scan" not in plan_text

                results[query_name] = uses_index

                if not uses_index:
                    logger.warning(f"Query {query_name} not using index: {plan_text}")

            except Exception as e:
                logger.error(f"Failed to analyze query plan for {query_name}: {e}")
                results[query_name] = False

        return results

    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance validation report"""

        report = {
            "timestamp": time.time(),
            "indexes": self.check_indexes_exist(),
            "query_performance_ms": self.validate_json_query_performance(),
            "query_plans_use_indexes": self.check_query_plans_use_indexes(),
        }

        # Calculate summary metrics
        all_indexes_exist = all(report["indexes"].values())
        all_queries_fast = all(
            duration > 0 and duration < 100 for duration in report["query_performance_ms"].values()
        )
        all_plans_use_indexes = all(report["query_plans_use_indexes"].values())

        report["summary"] = {
            "all_indexes_exist": all_indexes_exist,
            "all_queries_under_100ms": all_queries_fast,
            "all_plans_use_indexes": all_plans_use_indexes,
            "optimization_score": sum([all_indexes_exist, all_queries_fast, all_plans_use_indexes])
            / 3.0,
        }

        return report


# SQLAlchemy event listener for automatic slow query logging
@event.listens_for(Engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.time()


@event.listens_for(Engine, "after_cursor_execute")
def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.time() - context._query_start_time

    # Log slow queries (>100ms)
    if total > 0.1:
        logger.warning(f"Slow query: {total*1000:.2f}ms - {statement[:100]}...")
    elif total > 0.05:  # Log moderately slow queries for monitoring
        logger.info(f"Query: {total*1000:.2f}ms - {statement[:50]}...")


if __name__ == "__main__":
    # Example usage
    from database import get_db

    db = next(get_db())
    validator = DatabasePerformanceValidator(db)
    report = validator.generate_performance_report()

    print("Performance Validation Report:")
    print(f"Optimization Score: {report['summary']['optimization_score']:.2f}/1.0")
    print(f"All indexes exist: {report['summary']['all_indexes_exist']}")
    print(f"All queries <100ms: {report['summary']['all_queries_under_100ms']}")
    print(f"All plans use indexes: {report['summary']['all_plans_use_indexes']}")

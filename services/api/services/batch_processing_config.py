"""
Batch processing configuration for Label Studio operations.
Optimized for handling large datasets (10k+ entries).
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class BatchProcessingConfig:
    """Configuration for batch processing operations."""

    # Default batch sizes for different operations
    DEFAULT_IMPORT_BATCH_SIZE = 100
    DEFAULT_EXPORT_BATCH_SIZE = 500
    DEFAULT_SYNC_BATCH_SIZE = 200

    # Batch size recommendations based on dataset size
    BATCH_SIZE_RECOMMENDATIONS = {
        "small": {  # < 1000 items
            "import": 100,
            "export": 500,
            "sync": 200,
            "description": "Small dataset (< 1,000 items)",
        },
        "medium": {  # 1000 - 5000 items
            "import": 250,
            "export": 1000,
            "sync": 500,
            "description": "Medium dataset (1,000 - 5,000 items)",
        },
        "large": {  # 5000 - 10000 items
            "import": 500,
            "export": 2000,
            "sync": 1000,
            "description": "Large dataset (5,000 - 10,000 items)",
        },
        "xlarge": {  # > 10000 items
            "import": 1000,
            "export": 5000,
            "sync": 2000,
            "description": "Extra large dataset (> 10,000 items)",
        },
    }

    # Rate limiting configuration
    RATE_LIMIT_CONFIG = {
        "enterprise": {
            "requests_per_second": 10,
            "concurrent_requests": 5,
            "retry_after_seconds": 1,
        },
        "local": {
            "requests_per_second": 50,
            "concurrent_requests": 10,
            "retry_after_seconds": 0.2,
        },
    }

    # Timeout configuration (in seconds)
    TIMEOUT_CONFIG = {
        "small": {"connect": 10, "read": 30, "write": 60},
        "medium": {"connect": 10, "read": 60, "write": 120},
        "large": {"connect": 10, "read": 120, "write": 300},
        "xlarge": {"connect": 10, "read": 300, "write": 600},
    }

    @classmethod
    def get_dataset_size_category(cls, item_count: int) -> str:
        """Determine dataset size category based on item count."""
        if item_count < 1000:
            return "small"
        elif item_count < 5000:
            return "medium"
        elif item_count < 10000:
            return "large"
        else:
            return "xlarge"

    @classmethod
    def get_optimal_batch_size(
        cls, operation: str, item_count: int, instance_type: str = "local"
    ) -> int:
        """
        Get optimal batch size based on operation type and dataset size.

        Args:
            operation: Type of operation ('import', 'export', 'sync')
            item_count: Number of items to process
            instance_type: 'enterprise' or 'local'

        Returns:
            Optimal batch size
        """
        category = cls.get_dataset_size_category(item_count)
        batch_config = cls.BATCH_SIZE_RECOMMENDATIONS.get(
            category, cls.BATCH_SIZE_RECOMMENDATIONS["medium"]
        )

        # Adjust for enterprise instances (more conservative)
        if instance_type == "enterprise":
            return batch_config[operation] // 2

        return batch_config[operation]

    @classmethod
    def get_timeout_config(cls, item_count: int) -> Dict[str, int]:
        """Get timeout configuration based on dataset size."""
        category = cls.get_dataset_size_category(item_count)
        return cls.TIMEOUT_CONFIG[category]

    @classmethod
    def get_rate_limit_config(cls, instance_type: str = "local") -> Dict[str, Any]:
        """Get rate limiting configuration for instance type."""
        return cls.RATE_LIMIT_CONFIG.get(instance_type, cls.RATE_LIMIT_CONFIG["local"])

    @classmethod
    def calculate_estimated_time(
        cls, item_count: int, operation: str, instance_type: str = "local"
    ) -> Dict[str, Any]:
        """
        Calculate estimated processing time for operation.

        Returns:
            Dictionary with estimated time and batching information
        """
        batch_size = cls.get_optimal_batch_size(operation, item_count, instance_type)
        num_batches = (item_count + batch_size - 1) // batch_size

        # Base processing time per batch (seconds)
        base_times = {
            "import": {"enterprise": 2.0, "local": 0.5},
            "export": {"enterprise": 1.0, "local": 0.2},
            "sync": {"enterprise": 3.0, "local": 1.0},
        }

        time_per_batch = base_times.get(operation, {}).get(instance_type, 1.0)
        total_seconds = num_batches * time_per_batch

        # Add overhead for large datasets
        if item_count > 5000:
            total_seconds *= 1.2  # 20% overhead

        return {
            "batch_size": batch_size,
            "num_batches": num_batches,
            "estimated_seconds": round(total_seconds, 1),
            "estimated_minutes": round(total_seconds / 60, 1),
            "items_per_second": (round(item_count / total_seconds, 1) if total_seconds > 0 else 0),
        }

    @classmethod
    def log_batch_info(cls, operation: str, item_count: int, instance_type: str = "local") -> None:
        """Log batch processing information."""
        category = cls.get_dataset_size_category(item_count)
        batch_size = cls.get_optimal_batch_size(operation, item_count, instance_type)
        estimate = cls.calculate_estimated_time(item_count, operation, instance_type)

        logger.info(f"Batch processing configuration for {operation}:")
        logger.info(f"  Dataset: {cls.BATCH_SIZE_RECOMMENDATIONS[category]['description']}")
        logger.info(f"  Items: {item_count}")
        logger.info(f"  Batch size: {batch_size}")
        logger.info(f"  Batches: {estimate['num_batches']}")
        logger.info(f"  Estimated time: {estimate['estimated_minutes']} minutes")
        logger.info(f"  Processing rate: {estimate['items_per_second']} items/second")

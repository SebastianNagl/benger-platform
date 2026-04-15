"""
Unit tests for services/batch_processing_config.py — 83% coverage (11 uncovered lines).

Tests BatchProcessingConfig class methods for dataset categorization, batch sizing,
timeout config, rate limiting, and estimated time calculation.
"""

import pytest


class TestGetDatasetSizeCategory:
    """Test dataset size categorization."""

    def test_small_dataset(self):
        from services.batch_processing_config import BatchProcessingConfig
        assert BatchProcessingConfig.get_dataset_size_category(0) == "small"
        assert BatchProcessingConfig.get_dataset_size_category(500) == "small"
        assert BatchProcessingConfig.get_dataset_size_category(999) == "small"

    def test_medium_dataset(self):
        from services.batch_processing_config import BatchProcessingConfig
        assert BatchProcessingConfig.get_dataset_size_category(1000) == "medium"
        assert BatchProcessingConfig.get_dataset_size_category(3000) == "medium"
        assert BatchProcessingConfig.get_dataset_size_category(4999) == "medium"

    def test_large_dataset(self):
        from services.batch_processing_config import BatchProcessingConfig
        assert BatchProcessingConfig.get_dataset_size_category(5000) == "large"
        assert BatchProcessingConfig.get_dataset_size_category(7500) == "large"
        assert BatchProcessingConfig.get_dataset_size_category(9999) == "large"

    def test_xlarge_dataset(self):
        from services.batch_processing_config import BatchProcessingConfig
        assert BatchProcessingConfig.get_dataset_size_category(10000) == "xlarge"
        assert BatchProcessingConfig.get_dataset_size_category(100000) == "xlarge"


class TestGetOptimalBatchSize:
    """Test optimal batch size calculation."""

    def test_import_small_local(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.get_optimal_batch_size("import", 500)
        assert result == 100

    def test_import_medium_local(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.get_optimal_batch_size("import", 2000)
        assert result == 250

    def test_import_large_local(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.get_optimal_batch_size("import", 7000)
        assert result == 500

    def test_import_xlarge_local(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.get_optimal_batch_size("import", 15000)
        assert result == 1000

    def test_export_small_local(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.get_optimal_batch_size("export", 500)
        assert result == 500

    def test_export_xlarge_local(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.get_optimal_batch_size("export", 20000)
        assert result == 5000

    def test_sync_medium_local(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.get_optimal_batch_size("sync", 3000)
        assert result == 500

    def test_enterprise_halves_batch_size(self):
        from services.batch_processing_config import BatchProcessingConfig
        local = BatchProcessingConfig.get_optimal_batch_size("import", 500, "local")
        enterprise = BatchProcessingConfig.get_optimal_batch_size("import", 500, "enterprise")
        assert enterprise == local // 2

    def test_enterprise_large_export(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.get_optimal_batch_size("export", 7000, "enterprise")
        assert result == 1000  # 2000 // 2


class TestGetTimeoutConfig:
    """Test timeout configuration."""

    def test_small_timeout(self):
        from services.batch_processing_config import BatchProcessingConfig
        config = BatchProcessingConfig.get_timeout_config(500)
        assert config["connect"] == 10
        assert config["read"] == 30
        assert config["write"] == 60

    def test_medium_timeout(self):
        from services.batch_processing_config import BatchProcessingConfig
        config = BatchProcessingConfig.get_timeout_config(3000)
        assert config["read"] == 60
        assert config["write"] == 120

    def test_large_timeout(self):
        from services.batch_processing_config import BatchProcessingConfig
        config = BatchProcessingConfig.get_timeout_config(7000)
        assert config["read"] == 120
        assert config["write"] == 300

    def test_xlarge_timeout(self):
        from services.batch_processing_config import BatchProcessingConfig
        config = BatchProcessingConfig.get_timeout_config(50000)
        assert config["read"] == 300
        assert config["write"] == 600


class TestGetRateLimitConfig:
    """Test rate limiting configuration."""

    def test_local_config(self):
        from services.batch_processing_config import BatchProcessingConfig
        config = BatchProcessingConfig.get_rate_limit_config("local")
        assert config["requests_per_second"] == 50
        assert config["concurrent_requests"] == 10

    def test_enterprise_config(self):
        from services.batch_processing_config import BatchProcessingConfig
        config = BatchProcessingConfig.get_rate_limit_config("enterprise")
        assert config["requests_per_second"] == 10
        assert config["concurrent_requests"] == 5

    def test_unknown_type_defaults_to_local(self):
        from services.batch_processing_config import BatchProcessingConfig
        config = BatchProcessingConfig.get_rate_limit_config("unknown")
        assert config == BatchProcessingConfig.RATE_LIMIT_CONFIG["local"]


class TestCalculateEstimatedTime:
    """Test estimated processing time calculation."""

    def test_small_import_local(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.calculate_estimated_time(500, "import")
        assert "batch_size" in result
        assert "num_batches" in result
        assert "estimated_seconds" in result
        assert "estimated_minutes" in result
        assert "items_per_second" in result
        assert result["batch_size"] == 100
        assert result["num_batches"] == 5

    def test_xlarge_export_with_overhead(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.calculate_estimated_time(10000, "export")
        # Should have 20% overhead for > 5000 items
        assert result["estimated_seconds"] > 0
        assert result["items_per_second"] > 0

    def test_enterprise_import(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.calculate_estimated_time(3000, "import", "enterprise")
        assert result["batch_size"] == 125  # 250 // 2

    def test_sync_operation(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.calculate_estimated_time(1000, "sync")
        assert result["batch_size"] > 0

    def test_unknown_operation_raises_key_error(self):
        from services.batch_processing_config import BatchProcessingConfig
        with pytest.raises(KeyError):
            BatchProcessingConfig.calculate_estimated_time(100, "unknown_op")

    def test_zero_items(self):
        from services.batch_processing_config import BatchProcessingConfig
        result = BatchProcessingConfig.calculate_estimated_time(0, "import")
        # 0 items -> should still return a result
        assert result["batch_size"] > 0


class TestLogBatchInfo:
    """Test batch info logging."""

    def test_log_batch_info_runs_without_error(self):
        from services.batch_processing_config import BatchProcessingConfig
        # Just verify it doesn't raise
        BatchProcessingConfig.log_batch_info("import", 5000)
        BatchProcessingConfig.log_batch_info("export", 500, "enterprise")
        BatchProcessingConfig.log_batch_info("sync", 15000, "local")

"""
Test script for improved batch processing functionality.
Tests handling of large datasets (up to 10k entries).
"""


from batch_processing_config import BatchProcessingConfig


class TestBatchProcessingConfig:
    """Test batch processing configuration logic."""

    def test_dataset_size_categories(self):
        """Test dataset size categorization."""
        assert BatchProcessingConfig.get_dataset_size_category(500) == "small"
        assert BatchProcessingConfig.get_dataset_size_category(1500) == "medium"
        assert BatchProcessingConfig.get_dataset_size_category(7500) == "large"
        assert BatchProcessingConfig.get_dataset_size_category(15000) == "xlarge"

    def test_optimal_batch_sizes(self):
        """Test optimal batch size calculation."""
        # Small dataset, local instance
        assert BatchProcessingConfig.get_optimal_batch_size("import", 500, "local") == 100
        assert BatchProcessingConfig.get_optimal_batch_size("export", 500, "local") == 500

        # Large dataset, local instance
        assert BatchProcessingConfig.get_optimal_batch_size("import", 7500, "large") == 500
        assert BatchProcessingConfig.get_optimal_batch_size("export", 7500, "local") == 2000

        # Extra large dataset, enterprise instance (should be halved)
        assert (
            BatchProcessingConfig.get_optimal_batch_size("import", 15000, "enterprise") == 500
        )  # 1000 / 2
        assert (
            BatchProcessingConfig.get_optimal_batch_size("export", 15000, "enterprise") == 2500
        )  # 5000 / 2

    def test_timeout_configuration(self):
        """Test timeout configuration based on dataset size."""
        small_timeout = BatchProcessingConfig.get_timeout_config(500)
        assert small_timeout["connect"] == 10
        assert small_timeout["read"] == 30
        assert small_timeout["write"] == 60

        xlarge_timeout = BatchProcessingConfig.get_timeout_config(15000)
        assert xlarge_timeout["connect"] == 10
        assert xlarge_timeout["read"] == 300
        assert xlarge_timeout["write"] == 600

    def test_estimated_time_calculation(self):
        """Test processing time estimation."""
        # Small import on local instance
        estimate = BatchProcessingConfig.calculate_estimated_time(500, "import", "local")
        assert estimate["batch_size"] == 100
        assert estimate["num_batches"] == 5
        assert estimate["estimated_seconds"] == 2.5  # 5 batches * 0.5 seconds

        # Large export on enterprise instance
        estimate = BatchProcessingConfig.calculate_estimated_time(10000, "export", "enterprise")
        assert estimate["batch_size"] == 2500  # 5000 / 2 for enterprise
        assert estimate["num_batches"] == 4
        assert estimate["estimated_seconds"] == 4.8  # 4 batches * 1.0 * 1.2 overhead


# Label Studio integration tests removed - migrated to native annotation system

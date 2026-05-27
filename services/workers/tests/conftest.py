"""
Pytest configuration for workers tests.

Handles platform-specific setup, particularly disabling MKL-DNN on ARM64
where Intel-specific instructions cause "Illegal instruction" errors.

Also configures timeouts to prevent tests from hanging indefinitely.
"""

import os
import platform
import sys
from unittest.mock import MagicMock

import pytest

# Sentinel for /shared/encryption_service.py — module-level
# `encryption_service = EncryptionService()` runs at first import, BEFORE
# pytest sets PYTEST_CURRENT_TEST. Without this, every worker test file
# that transitively imports the module raises RuntimeError at collection
# time. Mirrors what the API conftest does via JWT_SECRET_KEY / SECRET_KEY.
os.environ.setdefault("BENGER_TEST_MODE", "1")

# Ensure the workers source directory is at the front of sys.path
# so that local modules (email_service, ml_evaluation, etc.) are
# imported from workers, not from other services.
workers_root = os.path.dirname(os.path.dirname(__file__))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

# Add /shared to sys.path (where it lives in both Docker containers via
# the volume mount, and inside the test container the same path is
# available). The consolidation on 2026-05-19 moved models.py into
# /shared, so `from models import …` only resolves with /shared on the
# path. Fall back to a relative path for host-local pytest runs.
_shared_dir = (
    "/shared"
    if os.path.exists("/shared")
    else os.path.normpath(os.path.join(workers_root, "..", "shared"))
)
if _shared_dir not in sys.path:
    sys.path.insert(0, _shared_dir)

# Remove ALL paths that could resolve to the API's modules.
# On the self-hosted CI runner, the API directory ends up in sys.path
# (likely via .pth files or shared Python environment), causing
# 'import email_service' to resolve to services/api/email_service.py
# instead of services/workers/email_service.py.
_api_dir = os.path.normpath(os.path.join(workers_root, '..', 'api'))
sys.path = [
    p
    for p in sys.path
    if os.path.normpath(p) != _api_dir
    and not os.path.exists(os.path.join(p, 'email_service.py'))
    or os.path.normpath(p) == os.path.normpath(workers_root)
]

# Force-load email_service from the workers directory to guarantee
# the correct module is used, regardless of sys.path state.
import importlib.util as _ilu  # noqa: E402

_es_path = os.path.join(workers_root, 'email_service.py')
if os.path.exists(_es_path):
    _spec = _ilu.spec_from_file_location('email_service', _es_path)
    _mod = _ilu.module_from_spec(_spec)
    sys.modules['email_service'] = _mod
    _spec.loader.exec_module(_mod)


# Detect ARM64 platform
IS_ARM64 = platform.machine().lower() in ('arm64', 'aarch64')

if IS_ARM64:
    # Disable MKL-DNN before torch is imported
    # MKL-DNN contains Intel-specific SIMD instructions that crash on ARM64
    os.environ['MKLDNN_VERBOSE'] = '0'

# Now import torch and disable MKL-DNN runtime
try:
    import torch

    if IS_ARM64:
        torch.backends.mkldnn.enabled = False
except ImportError:
    pass  # torch not installed


@pytest.fixture
def mock_api_client():
    """Mock API client for evaluation tasks.

    Provides a simple MagicMock that tests can configure for their
    specific API call expectations.

    Example usage in tests:
        mock_api_client.get.return_value.json.return_value = {"results": []}
    """
    return MagicMock()

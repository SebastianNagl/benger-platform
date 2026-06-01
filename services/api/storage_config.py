"""Compatibility shim — implementation moved to /shared/storage/storage_config.py (issue #158).

Aliases the top-level ``storage_config`` name to the canonical ``storage.storage_config``
module. /shared is first on sys.path in both the api and worker containers.
"""
import sys

import storage.storage_config as _canonical

sys.modules[__name__] = _canonical

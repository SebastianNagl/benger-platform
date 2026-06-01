"""Compatibility shim — implementation moved to /shared/storage/storage_service.py (issue #158).

Aliases the top-level ``storage_service`` name to the canonical ``storage.storage_service``
module. /shared is first on sys.path in both the api and worker containers.
"""
import sys

import storage.storage_service as _canonical

sys.modules[__name__] = _canonical

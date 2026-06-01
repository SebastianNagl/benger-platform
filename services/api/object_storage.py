"""Compatibility shim — implementation moved to /shared/storage/object_storage.py (issue #158).

Aliases the top-level ``object_storage`` name to the canonical ``storage.object_storage``
module so that ``from object_storage import object_storage`` call sites keep the same
singleton instance. /shared is first on sys.path in both the api and worker containers.
"""
import sys

import storage.object_storage as _canonical

sys.modules[__name__] = _canonical

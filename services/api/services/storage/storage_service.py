"""Compatibility shim — implementation moved to /shared/storage/storage_service.py (issue #158).

Aliases this module name to the canonical ``storage.storage_service`` (sys.modules
replacement) so that ``from services.storage.storage_service import ...`` AND any
``mock.patch("services.storage.storage_service....")`` resolve to the *same* module
object. /shared is first on sys.path in both the api and worker containers.
"""
import sys

import storage.storage_service as _canonical

sys.modules[__name__] = _canonical

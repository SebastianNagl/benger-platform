"""Compatibility shim — implementation moved to /shared/storage/storage_config.py (issue #158).

Aliases this module name to the canonical ``storage.storage_config`` (sys.modules
replacement) so that ``from services.storage.storage_config import ...`` AND any
``mock.patch("services.storage.storage_config....")`` resolve to the *same* module
object. /shared is first on sys.path in both the api and worker containers.
"""
import sys

import storage.storage_config as _canonical

sys.modules[__name__] = _canonical

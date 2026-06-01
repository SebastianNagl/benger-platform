"""Compatibility shim — implementation moved to /shared/storage/object_storage.py (issue #158).

Aliases this module name to the canonical ``storage.object_storage`` (sys.modules
replacement) so that ``from services.storage.object_storage import ...`` AND any
``mock.patch("services.storage.object_storage....")`` resolve to the *same* module
object — preserving call sites, module-global patch targets, and the singleton
instance. /shared is first on sys.path in both the api and worker containers.
"""
import sys

import storage.object_storage as _canonical

sys.modules[__name__] = _canonical

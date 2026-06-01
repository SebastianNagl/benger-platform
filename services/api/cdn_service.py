"""Compatibility shim — implementation moved to /shared/storage/cdn_service.py (issue #158).

Aliases the top-level ``cdn_service`` name to the canonical ``storage.cdn_service``
module so that ``from cdn_service import cdn_service`` call sites keep the same
singleton instance. /shared is first on sys.path in both the api and worker containers.
"""
import sys

import storage.cdn_service as _canonical

sys.modules[__name__] = _canonical

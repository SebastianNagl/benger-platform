"""Compatibility shim — implementation moved to /shared/serializers.py (issue #158).

Relocated so the import worker (whose image only carries services/workers/* +
/shared) can import the same serializers. Aliases this module name to the canonical
``serializers`` (sys.modules replacement) so that ``from routers.projects.serializers
import X`` call sites — including the underscore-prefixed ``_isoformat``/``_parse_iso``
helpers — AND any ``mock.patch("routers.projects.serializers....")`` resolve to the
*same* module object. /shared is first on sys.path in both containers.
"""
import sys

import serializers as _canonical

sys.modules[__name__] = _canonical

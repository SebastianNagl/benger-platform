"""Compatibility shim — implementation moved to /shared/import_stream.py (issue #158).

Relocated so the import worker (whose image only carries services/workers/* +
/shared) can run the same streaming import drivers. Aliases this module name to
the canonical ``import_stream`` (sys.modules replacement) so that
``from routers.projects._import_stream import X`` call sites AND any
``mock.patch("routers.projects._import_stream....")`` resolve to the *same*
module object. /shared is first on sys.path in both containers.
"""
import sys

import import_stream as _canonical

sys.modules[__name__] = _canonical

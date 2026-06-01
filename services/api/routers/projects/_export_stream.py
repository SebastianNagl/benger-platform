"""Compatibility shim — implementation moved to /shared/export_stream.py (issue #158).

Relocated so the export worker (whose image only carries services/workers/* +
/shared) can import the same streaming generators. Aliases this module name to the
canonical ``export_stream`` (sys.modules replacement) so that
``from routers.projects._export_stream import X`` call sites AND any
``mock.patch("routers.projects._export_stream....")`` resolve to the *same* module
object. /shared is first on sys.path in both containers.
"""
import sys

import export_stream as _canonical

sys.modules[__name__] = _canonical

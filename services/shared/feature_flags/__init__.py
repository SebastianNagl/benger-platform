"""Feature flags (platform, core 2.41): registry, evaluation, caching and the
worker gate. The FastAPI dependencies live in ``services/api/feature_flags``.

Overlays register their own flags with :func:`register_flags`; every loaded
extension package also gets a master flag ``extension.<EXTENSION_ID>``
(:func:`register_master_flag`, see ``extension_activation``).

The API's half of the package (``services/api/feature_flags/deps.py``) is a
directory without ``__init__.py``; ``extend_path`` below adds it to this
package's path, so ``feature_flags.deps`` imports in the API while the
workers (no API tree on ``sys.path``) only see the shared modules.
"""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from .registry import (  # noqa: E402,F401
    FEATURE_DISABLED,
    FEATURE_DISABLED_MESSAGE,
    MASTER_PREFIX,
    PLATFORM_OWNER,
    PUBLIC_API,
    STATE_ALLOWLIST,
    STATE_EVERYONE,
    STATE_OFF,
    STATES,
    FlagDefinition,
    all_flags,
    flag,
    flag_owner,
    is_master,
    master_flag_name,
    master_for_owner,
    register_flags,
    register_master_flag,
    unregister_flags,
)

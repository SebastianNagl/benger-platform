"""Single source of truth for the open-core extension handshake.

CORE_API_VERSION is the contract version the platform exposes to the
proprietary benger_extended overlay. The extended package declares
COMPATIBLE_CORE_VERSIONS; every loader (services/api/extensions.py,
services/workers/ml_evaluation/__init__.py, services/workers/tasks.py)
checks this constant against that list at startup.

This module lives in /shared so the api and the workers import the exact
same value — it was previously hand-copied into all three loaders with
"keep in sync" comments, which is how versions drift.

The extended repo's tests/test_version_handshake.py string-parses this file
(it deliberately avoids importing platform modules), so keep the assignment
on a single line in the form: CORE_API_VERSION = "<version>".
"""

import os

CORE_API_VERSION = "2.2"


def extended_required() -> bool:
    """True when this deployment must run the extended edition.

    Set BENGER_REQUIRE_EXTENDED=true (Helm: {api,workers}.extraEnv, see
    benger-extended/infra/helm/values-extended.yaml) to make a failed
    extended import or a handshake mismatch crash the process at startup
    instead of silently degrading to the community edition. Unset (the
    default) preserves graceful degradation for community installs and
    local development.
    """
    return os.getenv("BENGER_REQUIRE_EXTENDED", "").strip().lower() in ("1", "true", "yes")

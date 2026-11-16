"""The version of the running deployment, for provenance records.

The Helm chart sets ``BENGER_APP_VERSION`` to the image tag of each
deployment (``v<date>-<extended sha>-<platform sha>``) in the api, every
worker, the beat and the migration job. Rows that record how something was
made (``rubric_generation_jobs.app_version``,
``task_rubric_review_events.app_version``) store it, so a result can be
traced to the code that produced it.

Unset (tests, bare local runs, a compose stack that does not set it) means
"no deployed version": :func:`app_version` returns ``None`` and the column
stays NULL, rather than a made-up label that would look like a release.
"""

from __future__ import annotations

import os
from typing import Optional

ENV_VAR = "BENGER_APP_VERSION"


def app_version() -> Optional[str]:
    """The deployed image tag (``v<date>-<extended sha>-<platform sha>``), from the
    env var ``BENGER_APP_VERSION``; None when unset (tests, bare local runs).

    Reads the environment on every call (cheap, and tests can set it per
    case). Surrounding whitespace is stripped; an empty value means None.
    """
    value = os.environ.get(ENV_VAR, "").strip()
    return value or None

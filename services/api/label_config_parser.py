"""Backward-compatibility shim for the open-core label-config parser path.

The former top-level ``label_config_parser`` module moved to
``services/label_config/parser.py`` during the Tier-2 decomposition. All
*platform-internal* callers were updated to ``from services.label_config.parser
import LabelConfigParser``, but the top-level path is part of the open-core
contract surface: the extended my-korrektur detail endpoint
(``benger_extended/api/routers/korrektur.py``) lazily does
``from label_config_parser import LabelConfigParser`` to sanitize reference
fields out of the task payload before returning it to an annotator.

``CORE_API_VERSION`` is unchanged (2.2) — the contract did NOT change — so we keep
this thin re-export rather than break the extended overlay. Remove only alongside
a coordinated handshake bump + an extended import update.
"""

from services.label_config.parser import LabelConfigParser  # noqa: F401

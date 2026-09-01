#!/usr/bin/env python3
"""Loader for the CANONICAL v2 rubric contract implementation.

v1 kept a hand-mirrored reference implementation here ("behavioural
lockstep"); v2 removes the duplication — the contract lives ONLY in
``benger-extended/benger_extended/workers/bewertungsbogen_constants.py``
(stdlib-only by design) and this module loads it by file path so
publication scripts and notebooks can validate/flatten/render documents
without installing the extended package:

    from rubric_schema import contract
    errors = contract().validate_document(doc)
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path

CONSTANTS = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "benger-extended"
    / "benger_extended"
    / "workers"
    / "bewertungsbogen_constants.py"
)


@lru_cache(maxsize=1)
def contract():
    spec = importlib.util.spec_from_file_location(
        "bewertungsbogen_constants", CONSTANTS
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    mod = contract()
    print(f"loaded contract v{mod.CONTRACT_VERSION} from {CONSTANTS}")

"""Versions of the analysis engine.

``ENGINE_VERSION`` is recorded on every analysis run. Any change that can move
a number the engine reports (estimator code, a convention's default, the
frame builder's coercion rules, the expression grammar) bumps it, and the
golden-file tests in ``services/workers/tests/analysis/`` fail until the
goldens are regenerated for the new version. Same frame, same spec and same
engine version give bit-identical estimates on the same machine.

``SPEC_VERSION`` is the version of the analysis spec format
(``schemas/analysis_spec.schema.json``); a spec names it in ``spec_version``.

``EXPRESSION_GRAMMAR_VERSION`` is the version of the measure expression
language (``expression.py``); it is part of the engine version on purpose, so
a grammar change is never silent.
"""

ENGINE_VERSION = "1.0.0"
SPEC_VERSION = 1
EXPRESSION_GRAMMAR_VERSION = 1
FRAME_FORMAT_VERSION = 1

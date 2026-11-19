"""The analysis engine for variant experiments.

A project whose tasks carry a variant assignment (``tasks.meta.benger_variant``:
design, unit, factors) can be analysed as a factorial experiment: the frame
builder turns its generations into one row per answer with the design
factors and declared measures (:mod:`analysis.frame`, :mod:`analysis.measures`,
:mod:`analysis.expression`), and the estimators compute fixed-effects OLS
with explicit inference conventions, contrasts, equivalence tests (TOST) and
multiplicity-adjusted p-values over declared families
(:mod:`analysis.estimators`, :mod:`analysis.ols`, :mod:`analysis.inference`,
:mod:`analysis.multiplicity`, :mod:`analysis.runner`). Analysis runs persist
the spec, the frame snapshot's hash and every estimate.

Importing this package is cheap and pulls in no numeric library: the API
validates specs (:mod:`analysis.spec`) without numpy, pandas or statsmodels;
the workers import the numeric modules when they run an analysis.
"""

from analysis.version import (  # noqa: F401
    ENGINE_VERSION,
    EXPRESSION_GRAMMAR_VERSION,
    FRAME_FORMAT_VERSION,
    SPEC_VERSION,
)

"""
Shared statistics package for BenGER.

Importable from both api and workers. Consolidates helpers that were previously
duplicated across `api/routers/leaderboards.py`, `api/routers/evaluations/metadata.py`
(nested functions), `api/services/analytics_service.py`, and
`workers/ml_evaluation/inter_annotator_agreement.py`.
"""

from .agreement import (
    AgreementReport,
    cohens_kappa,
    compute_agreement,
    fleiss_kappa,
    percent_agreement,
)
from .bootstrap import bootstrap_ci
from .correlation import pearson, spearman
from .descriptive import confidence_interval, mean, stddev, variance
from .effect_size import cliffs_delta, cohens_d

__all__ = [
    "AgreementReport",
    "bootstrap_ci",
    "cliffs_delta",
    "cohens_d",
    "cohens_kappa",
    "compute_agreement",
    "confidence_interval",
    "fleiss_kappa",
    "mean",
    "pearson",
    "percent_agreement",
    "spearman",
    "stddev",
    "variance",
]

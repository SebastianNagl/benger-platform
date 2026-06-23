"""Per-metric-family computation modules for :class:`SampleEvaluator`.

This package decomposes the metric-family compute helpers that used to live
directly on ``SampleEvaluator`` into module-level functions taking the
evaluator instance (``ev``) as their first parameter, so they can still call
sibling ``ev._helper(...)`` methods and read instance attributes exactly as
before.

``sample_evaluator.py`` remains the orchestrator: it owns the sample loop,
the dispatch chains (``_compute_metric`` / ``_compute_metric_legacy`` /
``_compute_metric_with_details``), the provenance ``*_with_details`` helpers,
and confidence/serialization. The thin method shims on the class delegate
into the functions exported from these modules.

Functions that need the lazy-loaders, ``IS_ARM64`` flag, or other module
globals that tests monkeypatch on ``ml_evaluation.sample_evaluator`` import
them lazily from ``..sample_evaluator`` inside the function body, so patches
applied to that module take effect.
"""

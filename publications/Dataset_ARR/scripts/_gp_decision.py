"""Normalised Ja/Nein decision matching for the Grundprinzipien corpus.

The exported ``accuracy`` metric does an EXACT string match, but gold labels
in ``task.data.binary_solution`` carry trailing punctuation (``"Ja."`` /
``"Nein."``) while models answer ``"Ja"`` / ``"Nein"``. That produces ~5% false
mismatches (understating accuracy 70.6% -> 75.8%). Recompute the match by
normalising both sides to a bare ja/nein token. Shared by
derive_grundprinzipien_summary.py, derive_error_analysis.py, and
derive_leaderboard_csvs.py so every GP accuracy number uses the same rule.
"""

from __future__ import annotations

import json
import re


def normalise_decision(x):
    """Map a raw decision string to 'ja' / 'nein', or None if neither is found."""
    if x is None:
        return None
    m = re.match(r"\s*(ja|nein)", str(x).strip().lower())
    return m.group(1) if m else None


def model_decision(response_content):
    """Extract the model's normalised Ja/Nein from a GP response_content
    (a JSON string with a 'kurzantwort' field, or a bare string)."""
    if isinstance(response_content, str):
        try:
            return normalise_decision(json.loads(response_content).get("kurzantwort"))
        except Exception:
            return normalise_decision(response_content)
    if isinstance(response_content, dict):
        return normalise_decision(response_content.get("kurzantwort"))
    return None


def decision_accuracy(response_content, gold_binary_solution):
    """1.0 if the model's normalised decision matches the gold, else 0.0.

    Returns None only when the gold label itself is unparseable (so the caller
    can skip it); an unparseable / missing model answer counts as 0.0 (wrong).
    """
    gold = normalise_decision(gold_binary_solution)
    if gold is None:
        return None
    return 1.0 if model_decision(response_content) == gold else 0.0

"""A coder plugin as an overlay would ship it (test fixture).

It lives in a real module so the registry can read its source and hash it;
the tests install a fake overlay package whose workers module registers it
through ``register_coders``. Invented rule: an answer names the side it
blames first ("claimant" or "respondent"), how often it names a side and
whether it hedges.
"""

from __future__ import annotations

import re

from analysis.coders import Coder

_SIDES = (("P", re.compile(r"\bclaimant\b", re.I)), ("D", re.compile(r"\brespondent\b", re.I)))


class FirstBlamed(Coder):
    name = "first_blamed"
    version = "2"
    outputs = {"side": "text", "mentions": "number", "hedged": "bool"}

    def code(self, text, context):
        if text is None:
            return {}
        hits = []
        for side, rx in _SIDES:
            m = rx.search(text)
            if m:
                hits.append((m.start(), side))
        side = min(hits)[1] if hits else context.parameters.get("default", "none")
        # A design factor reaches the coder: on swapped tasks the roles flip.
        if context.factors.get("swap") == 1 and side in ("P", "D"):
            side = "D" if side == "P" else "P"
        return {
            "side": side,
            "mentions": sum(len(rx.findall(text)) for _, rx in _SIDES),
            "hedged": "perhaps" in text.lower(),
        }


def register_coders(registry):
    registry.register(FirstBlamed())

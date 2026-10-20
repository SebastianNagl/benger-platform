"""Margin notes (Randbemerkungen) of the LLM judges.

Besides its scores, a judge sets notes on passages of the answer, as a
human Korrektor writes in the margin: what is good there, what is wrong or
missing and how to do better. Each note names the step (Bewertungsbogen) or
dimension (Falllösung) whose score it explains, so the student can read the
score and the passages behind it together.

The judge returns ``annotations``; :func:`finalize_margin_notes` keeps the
notes it can trust. A note's quote must pass the same check as a step's
evidence (:func:`evidence_check.verify_evidence`); only then is it located
in the answer (:func:`locate_quote`) and carries ``anchor_text``, the exact
passage of the answer the viewer highlights. A note whose quote is not in
the answer keeps its comment but no anchor, so a made-up quote never marks
text the student did not write.

Pure code, except :func:`margin_notes_enabled`, which reads the platform
feature flag ``margin_notes``.
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .evidence_check import EvidenceIndex, verify_evidence

logger = logging.getLogger(__name__)

MARGIN_NOTE_KINDS = ("positiv", "mangel", "hinweis")
# A note about the answer as a whole (style, structure), tied to no step.
MARGIN_NOTE_GENERAL_REF = "allgemein"
MARGIN_NOTES_MAX = 15
# Completion tokens a judge needs on top of its scores to write the notes.
# Measured: on gpt-5-mini the Falllösung judge spent 2830 tokens without
# notes and 4015 with eight notes on a 373-character answer, past its 4096
# default, which then came back empty. Reasoning models bill their thinking
# against the same cap, and up to MARGIN_NOTES_MAX notes on a long answer
# take several times that. A cap is not a spend: only emitted tokens bill.
MARGIN_NOTES_MAX_TOKENS_HEADROOM = 8000

_TOKEN_RE = re.compile(r"\w+")
_ELLIPSIS_RE = re.compile(r"\[\s*(?:…|\.{3})\s*\]|…|\.{3,}")
# A located window must cover this share of the quote's words.
_LOCATE_MIN_RATIO = 0.6
# Words between a lone edge match and the rest beyond which it is dropped.
_LOCATE_EDGE_GAP = 5


def margin_notes_max_tokens(max_tokens: Any) -> Any:
    """``max_tokens`` with room for the notes; unset or unreadable stays as is."""
    try:
        return int(max_tokens) + MARGIN_NOTES_MAX_TOKENS_HEADROOM
    except (TypeError, ValueError):
        return max_tokens


def margin_notes_enabled(metric_parameters: Any) -> bool:
    """Whether a judge writes margin notes for this grading.

    The feature flag ``margin_notes`` must be on in the current context (the
    project's organizations of the evaluation, see
    ``extension_activation.flag_active``), and the judge config must not set
    ``margin_notes: false``. If the flag cannot be read, the notes stay off.
    """
    if isinstance(metric_parameters, dict) and metric_parameters.get("margin_notes") is False:
        return False
    try:
        from extension_activation import flag_active
        from feature_flags import MARGIN_NOTES

        return flag_active(MARGIN_NOTES)
    except Exception:
        logger.warning("margin notes: flag %r unreadable, notes off", "margin_notes", exc_info=True)
        return False


def margin_notes_schema(refs: Iterable[str], use_enum: bool = True) -> Dict[str, Any]:
    """Strict JSON schema of the ``annotations`` array.

    ``ref`` is one of ``refs`` or :data:`MARGIN_NOTE_GENERAL_REF`. Without
    ``use_enum`` (a schema near OpenAI's strict-mode enum budget) it is a
    plain string and :func:`finalize_margin_notes` drops unknown refs.
    """
    ref_schema: Dict[str, Any] = {"type": "string"}
    if use_enum:
        ref_schema["enum"] = [*refs, MARGIN_NOTE_GENERAL_REF]
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "ref": ref_schema,
                "kind": {"type": "string", "enum": list(MARGIN_NOTE_KINDS)},
                "quote": {"type": "string"},
                "comment": {"type": "string"},
            },
            "required": ["ref", "kind", "quote", "comment"],
            "additionalProperties": False,
        },
    }


# Enum values and properties the annotations array adds to a schema, for the
# strict-mode budget of the schema builders.
def margin_notes_schema_cost(ref_count: int) -> Tuple[int, int]:
    """``(properties, enum_values)`` of :func:`margin_notes_schema`."""
    return 5, ref_count + 1 + len(MARGIN_NOTE_KINDS)


def margin_notes_rules(unit: str, ref_hint: str, reason_field: str) -> str:
    """The prompt block that asks for margin notes.

    ``unit`` names what a note belongs to ("Schritt", "Dimension"),
    ``ref_hint`` says where the keys come from, ``reason_field`` where a
    point deduction without a passage to quote is explained instead.
    """
    return f"""RANDBEMERKUNGEN (Feld "annotations"):
Setze wie ein Korrektor Randbemerkungen an konkrete Stellen der Bearbeitung. Der Bearbeiter soll sehen, was gelungen ist, was fehlerhaft oder unvollständig ist und wie er es besser macht. Sprich ihn mit "du" an.
- "ref": {ref_hint}, zu dem die Bemerkung gehört, oder "{MARGIN_NOTE_GENERAL_REF}" für eine Bemerkung zur Bearbeitung als Ganzes (zum Beispiel Stil oder Gliederung).
- "kind" richtet sich danach, was an der zitierten Stelle steht, nicht nach der vergebenen Punktzahl:
  "mangel": an dieser Stelle steht ein Fehler, also eine falsche Aussage, eine falsche Norm, eine fehlerhafte Subsumtion, ein falsches Ergebnis, ein Prüfungsschritt, der hier falsch oder lückenhaft durchgeführt ist, oder eine bloße Behauptung, wo das Gutachten eine Begründung oder Subsumtion verlangt.
  "hinweis": die Stelle ist richtig und begründet, lässt sich aber verbessern (Begründung oder Definition ausbaufähig, Gewichtung, Formulierung, Zitierweise).
  "positiv": die Stelle ist gelungen (treffend, sauber begründet, gut gewichtet).
  Ist eine Stelle richtig begründet, aber knapper als ideal, ist das ein "hinweis", kein "mangel".
  Eine Bemerkung hat genau eine Art: ein "positiv" lobt nur. Fehlt an einer gelungenen Stelle noch etwas, setze dafür eine eigene Bemerkung "hinweis".
- "quote": ein kurzes, wörtliches Zitat aus der Bearbeitung (ein Satz oder Halbsatz), an dem die Bemerkung steht. Es gelten dieselben Regeln wie für Zitate: zeichengenau, keine Umformulierung, nie aus Musterlösung, Bewertungsbogen oder Sachverhalt.
- "comment": ein bis drei Sätze, sachlich und konkret: was hier gut ist, oder was fehlt oder falsch ist und wie es richtig oder besser wäre.
- Gehe dafür deine Punktvergabe {unit} für {unit} durch. Für jeden Abzug, zu dem die Bearbeitung etwas schreibt, setzt du mindestens eine Bemerkung an die Stelle, die ihn begründet: "mangel", wenn dort ein Fehler steht, sonst "hinweis".
- Fehlt der Punkt in der Bearbeitung ganz, gibt es nichts zu zitieren: dann keine Randbemerkung, das gehört in "{reason_field}".
- Halte auch fest, was gelungen ist: gelungene Stellen erhalten eine Bemerkung "positiv", auch dort, wo du insgesamt Punkte abziehst. Jede Bemerkung muss zu deiner Punktvergabe passen. Lobe nichts, wofür du keine Punkte gibst.
- Höchstens {MARGIN_NOTES_MAX} Randbemerkungen. Reicht das nicht, gehen die Bemerkungen "mangel" zu den größten Abzügen vor, dann "hinweis", dann "positiv"."""


def _longest_fragment(quote: str) -> List[str]:
    fragments = [_TOKEN_RE.findall(part.casefold()) for part in _ELLIPSIS_RE.split(quote or "")]
    return max(fragments, key=len, default=[])


def locate_quote(quote: str, answer: str) -> Optional[Tuple[int, int]]:
    """Where in ``answer`` the quote stands, as ``(start, end)`` offsets.

    Word-level and tolerant: the quote's longest fragment (quotes are split
    on ellipses) is aligned against the answer's words around their longest
    common run, so a typo or a left-out word does not lose the anchor. The
    span runs from the first to the last aligned word. ``None`` when fewer
    than :data:`_LOCATE_MIN_RATIO` of the quote's words line up.

    Only call this for a quote :func:`verify_evidence` accepted; it finds
    the most likely place, it does not judge whether the quote is genuine.
    """
    words = list(_TOKEN_RE.finditer(answer or ""))
    tokens = [m.group().casefold() for m in words]
    needle = _longest_fragment(quote)
    if len(needle) < 2 or not tokens:
        return None
    seed = SequenceMatcher(None, tokens, needle, autojunk=False).find_longest_match(
        0, len(tokens), 0, len(needle)
    )
    if seed.size == 0:
        return None
    slack = max(3, len(needle) // 2)
    lo = max(0, seed.a - seed.b - slack)
    hi = min(len(tokens), seed.a + (len(needle) - seed.b) + slack)
    blocks = [
        b
        for b in SequenceMatcher(None, tokens[lo:hi], needle, autojunk=False).get_matching_blocks()
        if b.size
    ]
    # A lone word matched far off at either edge ("die", "der") is not part
    # of the passage; it would stretch the anchor over unrelated text.
    while len(blocks) > 1 and blocks[0].size == 1 and blocks[1].a - (blocks[0].a + 1) >= _LOCATE_EDGE_GAP:
        blocks.pop(0)
    while len(blocks) > 1 and blocks[-1].size == 1 and blocks[-1].a - (blocks[-2].a + blocks[-2].size) >= _LOCATE_EDGE_GAP:
        blocks.pop()
    if sum(b.size for b in blocks) < _LOCATE_MIN_RATIO * len(needle):
        return None
    first = lo + blocks[0].a
    last = lo + blocks[-1].a + blocks[-1].size - 1
    return words[first].start(), words[last].end()


def finalize_margin_notes(
    raw: Any,
    answer: str,
    refs: Iterable[str],
    *,
    index: Optional[EvidenceIndex] = None,
    zeroed_refs: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    """The judge's notes as stored on the evaluation row.

    Each kept note is ``{id, ref, kind, comment, quote, verified,
    anchor_text}``; ``anchor_text`` is the located passage of ``answer``,
    or None. Notes without a comment or with an unknown ``ref`` are
    dropped, an unknown ``kind`` reads as "hinweis", at most
    :data:`MARGIN_NOTES_MAX` are kept. A "positiv" note on a step in
    ``zeroed_refs`` (its points fell to the evidence check) is dropped: it
    would praise points that do not count. ``index`` is the answer's
    :class:`EvidenceIndex` when the caller has one already.
    """
    if not isinstance(raw, list):
        return []
    allowed = set(refs) | {MARGIN_NOTE_GENERAL_REF}
    zeroed = set(zeroed_refs)
    index = index or EvidenceIndex(answer or "")
    notes: List[Dict[str, Any]] = []
    for item in raw:
        if len(notes) >= MARGIN_NOTES_MAX:
            break
        if not isinstance(item, dict):
            continue
        ref = item.get("ref")
        comment = item.get("comment")
        if ref not in allowed or not isinstance(comment, str) or not comment.strip():
            continue
        kind = item.get("kind") if item.get("kind") in MARGIN_NOTE_KINDS else "hinweis"
        if kind == "positiv" and ref in zeroed:
            continue
        quote = item.get("quote") if isinstance(item.get("quote"), str) else ""
        verified = bool(quote.strip()) and verify_evidence(quote, index)
        span = locate_quote(quote, answer) if verified else None
        notes.append(
            {
                "id": f"n{len(notes) + 1}",
                "ref": ref,
                "kind": kind,
                "comment": comment.strip(),
                "quote": quote,
                "verified": verified,
                "anchor_text": answer[span[0]:span[1]] if span else None,
            }
        )
    return notes

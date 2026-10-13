"""Evidence check for the Bewertungsbogen judge (``llm_judge_rubric``).

The judge quotes the answer for every step it gives points; a step whose
quote is not in the answer is zeroed (see ``_finalize_multidim_scores`` in
``llm_judge_evaluator``). This module decides whether a quote is really in
the answer: :class:`EvidenceIndex` prepares the answer once (normalized
text, word positions, a second copy without PDF page layout), and
:func:`verify_evidence` checks one quote against it, tolerant of layout,
spacing, typos and omissions but strict on everything that could change
what the answer says (negations, result words, numbers).

Pure code, no IO; it has its own nightly mutation shard.
"""

import bisect
import functools
import re
import unicodedata
from typing import Dict, List, Optional, Tuple


_MD_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~<\"'])")
_HTML_TAG_RE = re.compile(r"<[^<>\n]{0,200}>")
_MARKDOWN_MARKER_RE = re.compile(r"[*_`#>]+")
# Layout, not text: an escape sequence a judge copied out of JSON literally
# ("wahren.\n\nIX. Frist"), and a markdown hard line break (a backslash at
# the end of a line of an uploaded answer).
_LAYOUT_ESCAPE_RE = re.compile(r"\\[nrt]|\\(?=\s|$)")
# A footnote reference glued to the text ("erfassen.[4] Zwar …") is layout
# too; a quote that leaves it out still quotes the sentence.
_FOOTNOTE_MARK_RE = re.compile(r"(?<=\S)\[\^?\d{1,3}\]")
# Text pasted from Word arrives with its footnote references as in-page links
# ("ist,[\[12\]](#_ftn12) ist eine") and floating text boxes as images
# ("![](file:///…/clip_image003.gif "Textfeld: 2")"). A link to an anchor
# keeps its text (a footnote number then goes with _FOOTNOTE_MARK_RE); an
# image is dropped.
_ANCHOR_LINK_RE = re.compile(r"\[(\[\^?\d{1,3}\]|[^\[\]\n]{0,200})\]\(#[^()\s]{0,200}\)")
_MD_IMAGE_RE = re.compile(r"!\[[^\[\]\n]{0,200}\]\([^()\n]{0,500}\)")
# Text pasted from a PDF carries the page layout into the middle of its
# sentences: running footers ("Seite 3 von 12"), page and footnote numbers on
# lines of their own, footnote numbers glued to the next word ("4einiger",
# "9Die"), footnote text between two lines of a sentence ("1 §§ sind solche
# des VwVfG.") and a "tt" ligature the PDF font turns into a bracket
# ("Rechtsmi\[els"). A judge quotes the sentence without them, so the evidence
# index keeps a second copy of the answer with that layout removed
# (_strip_pdf_layout) and a quote counts when either copy holds it.
_PDF_FOOTER_LINE_RE = re.compile(
    r"^[ \t]*(?:Seite|Page)[ \t]+\d{1,3}(?:[ \t]*(?:von|of|/)[ \t]*\d{1,3})?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_PDF_NUMBER_LINE_RE = re.compile(r"^[ \t]*-?[ \t]*\d{1,3}[ \t]*-?[ \t]*$", re.MULTILINE)
# A footnote's text: its number, a space, then a "§" or a word ("1 §§ sind
# …", "12 Vgl. BVerwG …"). A citation continued on the next line ("2 I GG).")
# starts with a Roman numeral and stays.
_PDF_FOOTNOTE_LINE_RE = re.compile(
    r"^[ \t]*\d{1,2}[ \t]+(?![IVX]+\b)(?=[§A-Za-zÄÖÜäöü])[^\n]{1,160}$", re.MULTILINE
)
_PDF_GLUED_NUMBER_RE = re.compile(r"(?<![\w§.,/-])\d{1,2}(?=[A-Za-zÄÖÜäöü][a-zäöüß]{2,})")
_PDF_TT_LIGATURE_RE = re.compile(r"(?<=[a-zäöü])\\?\[(?=[a-zäöü])")
_BLANK_LINES_RE = re.compile(r"\n(?:[ \t]*\n)+")
# Preposition-article contractions read as their two words, so a judge that
# writes "bei dem Verwaltungsgericht" for the answer's "beim
# Verwaltungsgericht" quotes it.
_CONTRACTIONS = {"beim": "bei dem", "vom": "von dem", "zum": "zu dem", "zur": "zu der", "im": "in dem", "am": "an dem"}
_CONTRACTION_RE = re.compile(r"(?<!\w)(" + "|".join(_CONTRACTIONS) + r")(?!\w)", re.IGNORECASE)


def _expand_contraction(match: "re.Match[str]") -> str:
    word = match.group(1)
    expanded = _CONTRACTIONS[word.casefold()]
    return expanded[0].upper() + expanded[1:] if word[0].isupper() else expanded

# A token is a word, or a whole number with its inner separators ("10.000",
# "3,5"), so "10" never matches a piece of "10.000".
_WORD_RE = re.compile(r"\d+(?:[.,]\d+)+|\w+")
_ELLIPSIS_SPLIT_RE = re.compile(r"\.{3,}")
# Judges often glue passages from different places into one quote without the
# ellipsis the rules ask for; such a fragment is checked sentence by sentence.
# A candidate break is punctuation plus whitespace; a period is a break only
# when it does not end an abbreviation (see _period_ends_sentence).
_SENTENCE_BREAK_CANDIDATE_RE = re.compile(r"([.!?:;])\s+")
# Casefolded words that take an abbreviation period in legal German. A period
# after one of them (or after a single letter, a number or a Roman numeral)
# never ends a sentence: "gem. § 42", "Abs. 2 S. 1", "i.V.m.", "vgl. BGH".
_ABBREVIATIONS = frozenset({
    "abl", "abs", "abschn", "abzgl", "allg", "alt", "amtl", "anh", "anl", "anm", "art", "artt", "aufl", "az",
    "bd", "bearb", "begr", "bekl", "beschl", "bgbl", "bl", "bsp", "bspw", "buchst", "bzgl", "bzw", "ca",
    "ders", "dgl", "dr", "einschl", "entspr", "erg", "etc", "evtl", "exkl", "ff", "fn", "fr", "gegr", "gem",
    "ggf", "ggü", "grds", "halbs", "hr", "hrsg", "hs", "inkl", "insb", "insbes", "jew", "kap", "kl", "lit",
    "ls", "lt", "max", "min", "mind", "mio", "mrd", "mtl", "nachw", "nr", "nrn", "od", "prof", "rdnr", "rn",
    "rspr", "rz", "sog", "st", "str", "tz", "urt", "usw", "var", "verf", "vgl", "vorbem", "vorl", "vs",
    "ziff", "zit", "zust", "zzgl",
})
# "un- zulässig", "un-\nzulässig" and "un zulässig" are one word: "unzulässig".
_UN_SPLIT_RE = re.compile(r"(?<!\w)(un)(?:- ?| )(?!(?:und|oder|bzw|sowie)\b)(?=[^\W\d_])", re.IGNORECASE)
# Everything but letters and digits, for the spacing-insensitive comparison of
# long fragments (hyphenation splits like "entrichte ten", "10.000,– €").
_COMPACT_RE = re.compile(r"[\W_]+")
_COMPACT_CHAR_RE = re.compile(r"[^\W_]")
EVIDENCE_MIN_COMPACT_CHARS = 20
_PUNCT_TRANSLATION = str.maketrans(
    {
        "„": '"', "“": '"', "”": '"', "‟": '"', "«": '"', "»": '"',
        "‚": "'", "‘": "'", "’": "'", "‛": "'", "‹": "'", "›": "'",
        "–": "-", "—": "-", "‒": "-", "‐": "-", "‑": "-", "−": "-",
        "­": "",
    }
)
# The short-hand result marks "(+)" and "(-)" become words, so a quote that
# turns one into the other no longer matches.
_POLARITY_MARK_RE = re.compile(r"\(\s*([+-])\s*\)")
_POLARITY_MARKS = {"+": " positiv ", "-": " negativ "}
# Negations (and every "kein…" form, see _is_negation). With the normalized
# result marks they are the polarity tokens.
_NEGATION_TOKENS = frozenset({"nicht", "nichts", "nie", "niemals", "ohne", "weder"})
_RESULT_MARK_TOKENS = frozenset({"positiv", "negativ"})
_POLARITY_TOKENS = _NEGATION_TOKENS | _RESULT_MARK_TOKENS
# Protected tokens beyond polarity and numbers: words that state, qualify or
# hedge a result. A quote may never drop one, add one, swap one for another
# word, or step over one in the answer. Casefolded, so "ß" is "ss".
_QUALIFIER_TOKENS = frozenset({
    "nur", "teilweise", "kaum", "allenfalls", "insoweit", "stets",
    "jemand", "jemanden", "jemandem", "niemand", "niemanden", "niemandem",
    "vermutlich", "möglicherweise", "eventuell", "vielleicht",
})
_RESULT_WORD_RE = re.compile(
    r"(?:rechtmässig|rechtswidrig|bejah|vernein|erforderlich|entbehrlich|formell|materiell)\w*"
    r"|gegeben(?:e[mnrs]?)?|fehl(?:t|te|ten|en|end|ende[mnrs]?)"
    r"|besteh(?:t|en|end|ende[mnrs]?)|bestand(?:en)?"
    r"|(?:richtig|falsch|wirksam|gültig|vorsätzlich|fahrlässig|strafbar|straflos|verjährt|schuldhaft|schuldlos"
    r"|vermeintlich|angeblich|scheinbar|mutmasslich|fraglich|zweifelhaft)(?:e[mnrs]?)?"
)
# Words a token-wise match may leave out of the answer or find missing in it:
# articles, pronouns, simple prepositions, auxiliaries and filler particles.
# Everything else is a content word: a quote may leave out one content word
# of the answer, but never add one, and never swap a word for another.
_FUNCTION_WORDS = frozenset({
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines", "einem", "einen",
    "dieser", "diese", "dieses", "diesem", "diesen", "jener", "jene", "jenes", "jenem", "jenen",
    "sein", "seine", "seiner", "seines", "seinem", "seinen", "ihr", "ihre", "ihrer", "ihres", "ihrem", "ihren",
    "welcher", "welche", "welches", "welchem", "welchen", "dessen", "deren",
    "er", "sie", "es", "ihm", "ihn", "ihnen", "sich", "man", "wir", "uns",
    "in", "im", "ins", "an", "am", "ans", "auf", "aus", "bei", "beim", "mit", "nach", "seit", "von", "vom",
    "zu", "zum", "zur", "für", "gegen", "um", "durch", "über", "unter", "vor", "wegen", "gemäss", "laut",
    "bis", "ab", "gegenüber", "hinsichtlich", "bezüglich", "mangels", "aufgrund", "infolge",
    "und", "sowie", "bzw", "als", "wie", "dass", "weil", "da", "denn",
    "also", "daher", "deshalb", "somit", "mithin", "folglich", "damit", "dabei", "hierbei", "hierzu", "dazu",
    "ist", "sind", "war", "waren", "wird", "werden", "wurde", "wurden", "worden", "hat", "haben", "hatte",
    "hatten", "sei", "seien", "gewesen", "geworden",
    "auch", "noch", "schon", "bereits", "hier", "dort", "so", "dann", "nun", "ja", "eben", "etwa",
    "jedenfalls", "zudem", "ferner", "vorliegend", "zunächst", "ebenfalls", "sodann", "hierfür", "dafür",
})
# A quote may leave out at most this many content words of the answer.
_EVIDENCE_MAX_CONTENT_SKIPS = 1
# Any "un-" form of an adjective ("unzulässig", "unbegründet", "unstreitig",
# "unmittelbar") flips a result; words with these beginnings only start
# with "un" ("unter", "unsere", "Universität").
_UN_WORD_EXCEPTIONS = ("unser", "unter", "union", "univers", "unfall", "ungarn")
_ROMAN_NUMERALS = frozenset({
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx",
})
# Edge rules (see _edges_ok). Question and condition words, which a token
# match never steps over (see _tokens_in_order); words that open a clause
# whose content the clause in front of it governs ("Es ist nicht
# ersichtlich, dass …"); and the conjunctions that end a clause scan.
_EDGE_BEFORE_WORDS = frozenset({"ob", "wenn", "falls", "sofern", "soweit", "inwieweit", "inwiefern"})
_CONTENT_CLAUSE_OPENERS = frozenset({"dass", "ob", "inwieweit", "inwiefern", "warum", "weshalb", "wieso"})
# Subordinating conjunctions: they open a clause of their own, so a scan
# around a match stops at them.
_SUBORDINATORS = _CONTENT_CLAUSE_OPENERS | {
    "weil", "denn", "obwohl", "obgleich", "nachdem", "bevor", "sodass", "indem", "wodurch", "wobei",
}
_COORDINATORS = frozenset({"und", "oder", "sowie", "bzw", "aber", "sondern", "doch", "jedoch", "allerdings"})
# "ohne Weiteres" and "ohne Zweifel" affirm what comes before them.
_AFFIRMING_AFTER_OHNE = frozenset({"weiteres", "zweifel"})
# The scan after a match ends at the clause's verb: a negation behind it
# belongs to that verb, not to the quoted words in front of it ("[Der
# Anspruch des K] besteht nicht" leaves the quoted noun phrase intact).
_PREDICATE_WORDS = frozenset({
    "ist", "sind", "war", "waren", "wird", "werden", "wurde", "wurden", "hat", "haben", "hatte", "hatten",
    "sei", "seien", "wäre", "wären", "hätte", "hätten", "kann", "können", "konnte", "konnten", "könnte",
    "könnten", "muss", "müssen", "musste", "mussten", "müsste", "soll", "sollen", "sollte", "darf", "dürfen",
    "durfte", "liegt", "liegen", "lag", "lagen", "greift", "greifen", "kommt", "kommen", "scheidet",
    "scheiden", "gilt", "gelten", "steht", "stehen", "handelt", "reicht", "genügt", "trifft", "folgt",
    "ergibt",
})
# A blank line: the scans around a match stop there, so a heading ("Keine
# Einwilligung") does not govern the paragraph below it.
_PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n")
# Norm citations: a fragment made only of these (plus digits, Roman numerals
# and single letters) is a citation, not a quote of the step's reasoning.
_CITATION_WORDS = frozenset({
    "art", "artt", "abs", "nr", "nrn", "lit", "satz", "alt", "var", "hs", "halbs", "buchst", "ivm", "ff",
    "rn", "rdnr",
})
# Words that only connect a citation ("gem. § 433 BGB", "nach § 40 VwGO",
# "§ 280 BGB i.V.m. § 241 BGB", "im Sinne des § 145 BGB"). A fragment made of
# citation tokens and these is still only a citation.
_CITATION_CONNECTORS = frozenset({
    "gem", "gemäss", "nach", "aus", "in", "im", "isd", "isv", "verbindung", "mit", "sinne", "des", "der",
    "den", "dem", "von", "vom", "und", "sowie", "bzw", "oder", "vgl", "siehe", "analog", "entspr",
    "entsprechend", "zu", "zum", "zur", "bis",
})
# Law abbreviations keep their capitals: VwGO, GG, BGB, BayVwVfG, StPO.
_LAW_ABBREVIATION_RE = re.compile(r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]{1,11}")
# Evidence needs this many word characters in total to count at all, so a
# quote like "(+)" or "der" cannot verify a step.
EVIDENCE_MIN_WORD_CHARS = 4
# A fragment (one ellipsis-separated part of the quote) verifies only with
# at least EVIDENCE_MIN_TOKENS tokens, or with two tokens that together
# carry at least EVIDENCE_MIN_LONG_FRAGMENT_CHARS word characters. A single
# token never does: "VwGO", or "Recht" inside "Rechtsweg", is a keyword
# the answer happens to contain, not a quote of the step's reasoning.
EVIDENCE_MIN_TOKENS = 3
EVIDENCE_MIN_LONG_FRAGMENT_CHARS = 15
# A word this long that is not protected may differ from the answer by one
# edit (a typo on either side).
EVIDENCE_TYPO_MIN_CHARS = 5
# Fragments with fewer tokens than this must match the answer on word
# boundaries; longer ones may also match token-wise in order.
_EVIDENCE_SHORT_FRAGMENT_TOKENS = 4
_EDGE_PUNCTUATION = " \"'.,;:!?()[]-"


def _normalize_evidence_text(text: str, casefold: bool = True) -> str:
    """Canonical form for comparing a quote with the answer.

    NFKC, literal ``\\n`` escapes and markdown hard breaks, markdown escapes
    (``1\\.``), footnote references (``[4]``, also as Word's in-page links
    ``[\\[4\\]](#_ftn4)``), images and emphasis/heading markers removed,
    inline HTML (Word bookmark anchors) dropped, quotes/dashes
    unified, ellipsis as ``...``, ``(+)``/``(-)`` as ``positiv``/``negativ``,
    a split "un-" joined to its word ("un- zulässig" is "unzulässig"),
    contractions spelled out ("beim" is "bei dem", :data:`_CONTRACTIONS`),
    casefolded (unless ``casefold`` is False), whitespace collapsed.
    """
    t = unicodedata.normalize("NFKC", text or "")
    t = _LAYOUT_ESCAPE_RE.sub(" ", t)
    t = _MD_ESCAPE_RE.sub(r"\1", t)
    t = _MD_IMAGE_RE.sub(" ", t)
    t = _ANCHOR_LINK_RE.sub(r"\1", t)
    t = _FOOTNOTE_MARK_RE.sub("", t)
    t = _HTML_TAG_RE.sub(" ", t)
    t = t.translate(_PUNCT_TRANSLATION).replace("…", "...")
    t = _POLARITY_MARK_RE.sub(lambda m: _POLARITY_MARKS[m.group(1)], t)
    t = _MARKDOWN_MARKER_RE.sub(" ", t)
    t = _CONTRACTION_RE.sub(_expand_contraction, t)
    if casefold:
        t = t.casefold()
    t = re.sub(r"\s+", " ", t).strip()
    return _UN_SPLIT_RE.sub(r"\1", t)


def _is_negation(token: str) -> bool:
    """nicht, nichts, nie, niemals, ohne, weder, or any "kein…" form."""
    return token in _NEGATION_TOKENS or token.startswith("kein")


def _is_polarity(token: str) -> bool:
    """A negation or a normalized result mark (positiv, negativ)."""
    return _is_negation(token) or token in _POLARITY_TOKENS


def _has_digit(token: str) -> bool:
    return any(ch.isdigit() for ch in token)


def _is_function_word(token: str) -> bool:
    """An article, pronoun, simple preposition, auxiliary or filler word
    (:data:`_FUNCTION_WORDS`) that is not protected."""
    return token in _FUNCTION_WORDS and not _is_protected(token)


@functools.lru_cache(maxsize=65536)
def _is_protected(token: str) -> bool:
    """Tokens a quote may not drop, add, swap or step over: polarity (every
    "nicht…" and "kein…" form, a bare "un"), result and antonym words (every
    "un-" form, rechtmäßig/rechtswidrig, bejaht/verneint, erforderlich/
    entbehrlich, gegeben/besteht/fehlt, richtig/falsch, wirksam, vorsätzlich/
    fahrlässig, jemand/niemand, stets), qualifiers and hedges (nur,
    teilweise, formell, materiell, kaum, allenfalls, insoweit, vermeintlich,
    mutmaßlich, fraglich), Roman numerals I-XX and every token with a digit."""
    return (
        _is_polarity(token)
        or token.startswith("nicht")
        or token == "un"
        or _has_digit(token)
        or token in _QUALIFIER_TOKENS
        or token in _ROMAN_NUMERALS
        or (len(token) >= 6 and token.startswith("un") and not token.startswith(_UN_WORD_EXCEPTIONS))
        or _RESULT_WORD_RE.fullmatch(token) is not None
    )


def _is_inflection(a: str, b: str) -> bool:
    """``rechtsweg`` / ``rechtswegs``: one word at least four characters
    long, the other the same plus at most two characters."""
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and len(long_) - len(short) <= 2 and long_.startswith(short)


def _is_transposition(a: str, b: str) -> bool:
    """Equal but for two neighbouring characters swapped ("nciht", "nicht").
    The first letter stays."""
    if len(a) != len(b):
        return False
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    return (
        len(diff) == 2
        and diff[0] > 0
        and diff[1] == diff[0] + 1
        and a[diff[0]] == b[diff[1]]
        and a[diff[1]] == b[diff[0]]
    )


_UMLAUTS = frozenset("äöü")


def _is_typo(a: str, b: str) -> bool:
    """One edit or one transposition that keeps the first letter and adds,
    removes or swaps no umlaut: "verlezt" / "verletzt" are a typo;
    "nichtig" / "richtig" (first letter) and "hatte" / "hätte" (umlaut) are
    different words."""
    if not a or not b or a[0] != b[0] or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return a[diff[0]] not in _UMLAUTS and b[diff[0]] not in _UMLAUTS
        return _is_transposition(a, b)
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = next((k for k in range(len(short)) if short[k] != long_[k]), len(short))
    return short[i:] == long_[i + 1:] and long_[i] not in _UMLAUTS


def _tokens_match(quoted: str, answer: str) -> bool:
    """Equal tokens, a small inflection difference on a long word, or a typo.

    ``rechtsweg`` / ``rechtswegs`` match; different words do not. Numbers
    only match exactly ("1000" is not "10000"). A protected token only
    matches the same word or an inflection of it ("unzulässig" /
    "unzulässige"; never "nicht" / "nichtig", "unzulässig" / "zulässig" or
    "nichtig" / "richtig"); the one typo allowed is two letters swapped
    ("nciht" / "nicht"), which never spells another word. Other words of at
    least :data:`EVIDENCE_TYPO_MIN_CHARS` characters may carry a typo
    (:func:`_is_typo`).
    """
    if quoted == answer:
        return True
    if _has_digit(quoted) or _has_digit(answer):
        return False
    long_enough = min(len(quoted), len(answer)) >= EVIDENCE_TYPO_MIN_CHARS
    protected_quote, protected_answer = _is_protected(quoted), _is_protected(answer)
    if protected_quote or protected_answer:
        if long_enough and _is_transposition(quoted, answer):
            return True
        return (
            protected_quote
            and protected_answer
            and quoted not in _NEGATION_TOKENS
            and answer not in _NEGATION_TOKENS
            and _is_inflection(quoted, answer)
        )
    return _is_inflection(quoted, answer) or (long_enough and _is_typo(quoted, answer))


def _strip_pdf_layout(answer: str) -> str:
    """``answer`` without the page layout a PDF paste leaves in its sentences
    (footers, page and footnote numbers, footnote text, see
    :data:`_PDF_FOOTER_LINE_RE` and its neighbours), with a broken "tt"
    ligature repaired and blank lines collapsed, so a sentence split across a
    page break reads as one."""
    text = answer or ""
    for pattern in (_PDF_FOOTER_LINE_RE, _PDF_NUMBER_LINE_RE, _PDF_FOOTNOTE_LINE_RE):
        text = pattern.sub("", text)
    text = _PDF_GLUED_NUMBER_RE.sub("", text)
    text = _PDF_TT_LIGATURE_RE.sub("tt", text)
    return _BLANK_LINES_RE.sub("\n", text)


class EvidenceIndex:
    """The normalized answer, built once per judge call.

    ``layout_free`` is the same answer without PDF page layout
    (:func:`_strip_pdf_layout`), or None when there is none to remove;
    :func:`verify_evidence` accepts a quote found in either."""

    def __init__(self, answer: str, *, with_layout_free: bool = True):
        stripped = _strip_pdf_layout(answer) if with_layout_free else None
        self.layout_free: Optional["EvidenceIndex"] = (
            EvidenceIndex(stripped, with_layout_free=False)
            if stripped is not None and stripped != _BLANK_LINES_RE.sub("\n", answer or "")
            else None
        )
        self.text = _normalize_evidence_text(answer)
        spans = [m.span() for m in _WORD_RE.finditer(self.text)]
        self.tokens = [self.text[s:e] for s, e in spans]
        # Where each token occurs (for :func:`_substituted_fragment_in_answer`).
        self.positions: Dict[str, List[int]] = {}
        for pos, token in enumerate(self.tokens):
            self.positions.setdefault(token, []).append(pos)
        self.starts = [s for s, _e in spans]
        self.ends = [e for _s, e in spans]
        # Position in ``text`` of every character of ``compact``.
        self.compact_pos = [m.start() for m in _COMPACT_CHAR_RE.finditer(self.text)]
        self.compact = "".join(self.text[i] for i in self.compact_pos)
        # Indices of the tokens that open a paragraph after a blank line. Left
        # empty when the paragraphs do not line up with the tokens (a word
        # joined across the break), so the edge scans then run on.
        self.paragraph_starts: set = set()
        paragraphs = _PARAGRAPH_BREAK_RE.split(answer or "")
        if len(paragraphs) > 1:
            counts = [len(_WORD_RE.findall(_normalize_evidence_text(p))) for p in paragraphs]
            if sum(counts) == len(self.tokens):
                total = 0
                for count in counts[:-1]:
                    total += count
                    self.paragraph_starts.add(total)


def _is_abbreviation_token(token: str) -> bool:
    """A word a period after which is an abbreviation mark, not the end of a
    sentence: a known abbreviation ("gem", "Abs", "vgl"), a single letter
    ("S", "K", the parts of "i.V.m."), a number or a Roman numeral."""
    folded = token.casefold()
    return (
        (len(folded) == 1 and folded.isalpha())
        or folded in _ABBREVIATIONS
        or _has_digit(folded)
        or folded in _ROMAN_NUMERALS
    )


def _period_ends_sentence(text: str, dot: int) -> bool:
    """Does the period at ``text[dot]`` end a sentence? Not after an
    abbreviation (:func:`_is_abbreviation_token`), and not before a "§" or a
    lowercase word ("entspr. der Regel", "gem. § 42"), unless that word is a
    list label ("… liegt vor. b) Subjektiver Tatbestand")."""
    word = re.search(r"\w+$", text[:dot])
    if word and _is_abbreviation_token(word.group(0)):
        return False
    following = re.match(r"\s*(§|\w+\)?)", text[dot + 1 :])
    if not following:
        return True
    head = following.group(1)
    return not (head == "§" or (head[0].islower() and not head.endswith(")")))


def _split_sentences(text: str) -> List[str]:
    """``text`` cut after every ``.``, ``!``, ``?``, ``:`` and ``;`` that is
    followed by whitespace, except a period that does not end a sentence
    (:func:`_period_ends_sentence`). Each piece keeps its punctuation."""
    pieces: List[str] = []
    last = 0
    for m in _SENTENCE_BREAK_CANDIDATE_RE.finditer(text):
        if m.group(1) == "." and not _period_ends_sentence(text, m.start()):
            continue
        pieces.append(text[last : m.start() + 1])
        last = m.end()
    pieces.append(text[last:])
    return pieces


def _gap_level(index: "EvidenceIndex", before: int, gap_start: int, gap_end: int) -> int:
    """How strongly ``text[gap_start:gap_end]`` separates the words around
    it: 2 for a sentence break (``;``, ``:``, ``!``, ``?``, an ellipsis or a
    period that is no abbreviation mark after token ``before``), 1 for a
    comma, 0 for none."""
    gap = index.text[gap_start:gap_end]
    if any(ch in gap for ch in ";:!?") or "..." in gap:
        return 2
    if "." in gap and not (0 <= before < len(index.tokens) and _is_abbreviation_token(index.tokens[before])):
        return 2
    return 1 if "," in gap else 0


def _turns_round_after(index: "EvidenceIndex", j: int) -> bool:
    """Does token ``j``, standing after a match, negate it? A negation (but
    not "ohne Weiteres" or "ohne Zweifel") or "(-)". A condition ("…, wenn",
    "…, soweit") only limits the quote and does not count: the judge weighs
    what the passage is worth, the check only guards against quotes the
    answer turns into their opposite."""
    token = index.tokens[j]
    if token == "ohne" and j + 1 < len(index.tokens) and index.tokens[j + 1] in _AFFIRMING_AFTER_OHNE:
        return False
    return _is_negation(token) or token == "negativ"


def _opens_clause(index: EvidenceIndex, k: int) -> bool:
    """Is token ``k`` a subordinating conjunction? "da" only counts right
    after a comma ("…, da T nicht …"); elsewhere it is mostly an adverb."""
    token = index.tokens[k]
    if token in _SUBORDINATORS:
        return True
    return token == "da" and k > 0 and _gap_level(index, k - 1, index.ends[k - 1], index.starts[k]) == 1


def _turns_round_before(token: str) -> bool:
    """A negation. Question, condition and doubt words ("Fraglich ist, ob
    …", "wenn …") do not count: Gutachtenstil states nearly every point as a
    question first, and whether a raised question earns points is the
    judge's call."""
    return _is_negation(token)


def _parenthetical_before(index: EvidenceIndex, k: int, gap_end: int) -> Optional[int]:
    """When the gap between token ``k`` and text offset ``gap_end`` closes a
    parenthesis, the offset of its opening "(" (None otherwise, or when it
    does not open on the same line)."""
    if k < 0 or ")" not in index.text[index.ends[k]:gap_end]:
        return None
    depth = 0
    for pos in range(gap_end - 1, max(-1, gap_end - 400), -1):
        ch = index.text[pos]
        if ch == ")":
            depth += 1
        elif ch == "(":
            depth -= 1
            if depth == 0:
                return pos
    return None


def _in_parenthetical(index: EvidenceIndex, k: int, gap_end: int) -> bool:
    """Is token ``k`` inside a parenthesis that closes before ``gap_end``
    without being its last word? Such a word belongs to the aside: in
    "mit einer (ordnungsgemäßen, d. h. nicht floskelhaften) Begründung" the
    "nicht" negates "floskelhaften", not "Begründung". The aside's last word
    still counts ("(nicht) begründet")."""
    opener = _parenthetical_before(index, k, gap_end)
    if opener is None:
        return False
    last = bisect.bisect_right(index.ends, gap_end) - 1
    while last >= 0 and index.text.find(")", index.ends[last], gap_end) == -1:
        last -= 1
    return index.starts[k] > opener and k != last


def _clause_start_before(index: EvidenceIndex, first: int, start: int) -> Optional[int]:
    """Scan back from token ``first`` (the last token before text offset
    ``start``) to the start of its clause and return the index of the
    clause's first token. A comma, a sentence break, a blank line, a result
    mark or a coordinating conjunction ends the scan in front of the clause;
    a subordinating conjunction ("dass", "weil") is the clause's first token.
    Returns None when a scanned token turns the text after it round; words
    inside a parenthesis that closes before the match do not (see
    :func:`_in_parenthetical`)."""
    tokens = index.tokens
    k, gap_end = first, start
    while k >= 0 and not _gap_level(index, k, index.ends[k], gap_end) and (k + 1) not in index.paragraph_starts:
        token = tokens[k]
        if token in _RESULT_MARK_TOKENS or token in _COORDINATORS:
            break
        if _turns_round_before(token) and not _in_parenthetical(index, k, start):
            return None
        if token in _SUBORDINATORS:
            return k
        gap_end = index.starts[k]
        k -= 1
    return k + 1


def _governing_clause_ok(index: EvidenceIndex, opener: int, match_first: int) -> bool:
    """A clause opened by "dass", "ob" or a similar word states what the
    clause in front of it says about it: "Es ist nicht ersichtlich, dass …"
    denies it, "Fraglich ist, ob …" asks. That clause (back to its own
    start) may hold no negation, question, condition or doubt word. A quote
    that itself starts with a question word ("ob der Verkäufer …") keeps the
    question and passes."""
    tokens = index.tokens
    if not (0 < opener < len(tokens)) or tokens[opener] not in _CONTENT_CLAUSE_OPENERS:
        return True
    if opener == match_first and tokens[opener] != "dass":
        return True
    if opener in index.paragraph_starts:
        return True
    if _gap_level(index, opener - 1, index.ends[opener - 1], index.starts[opener]) > 1:
        return True
    k = opener - 1
    while k >= 0:
        if _turns_round_before(tokens[k]):
            return False
        if k == 0 or k in index.paragraph_starts or _gap_level(index, k - 1, index.ends[k - 1], index.starts[k]):
            return True
        k -= 1
    return True


def _edges_ok(index: EvidenceIndex, start: int, end: int) -> bool:
    """The answer around a match at ``text[start:end]`` does not turn it round.

    Before the match: no negation back to the start of its clause (see
    :func:`_clause_start_before`), so "kein [Anspruch auf …]" fails. When
    the clause opens with "dass", "ob" or a similar word after a comma, the
    clause in front of it is read the same way: "Es ist nicht ersichtlich,
    [dass der Verkäufer …]" fails. Questions, conditions and doubt words
    ("Fraglich ist, ob [der Verkäufer …]") pass (see
    :func:`_turns_round_before`).

    After the match: no negation or "(-)" as the next word in the same
    sentence ("[Der Anspruch besteht] nicht", "[… hat der Käufer] keinen";
    a condition such as "[Die Klage ist begründet], soweit …" passes), and
    none in the rest of its clause up to the clause's verb ("[Ein Anspruch besteht]
    daher nicht"; but "[Der Anspruch des K] besteht nicht" keeps the noun
    phrase). A coordinating or subordinating conjunction ("und", "weil") also
    ends that scan. A match that ends with a result mark or a subordinating
    conjunction closes its own clause.

    The word right next to the match counts even across a blank line (a
    hard page break must not hide a "nicht"); the scans beyond it stop at
    blank lines, so a heading does not govern the paragraph below it. A
    result mark before the match belongs to the text in front of it and
    does not count. A period after an abbreviation ("gem.", "Abs.") is no
    break.
    """
    tokens = index.tokens
    i = bisect.bisect_right(index.ends, start) - 1
    if i >= 0 and not _gap_level(index, i, index.ends[i], start):
        if tokens[i] not in _RESULT_MARK_TOKENS and _turns_round_before(tokens[i]):
            return False
    opener = _clause_start_before(index, i, start)
    if opener is None or not _governing_clause_ok(index, opener, i + 1):
        return False

    j = bisect.bisect_left(index.starts, end)
    if j >= len(tokens):
        return True
    if j > 0 and _opens_clause(index, j - 1):
        return True  # the words after it belong to the clause it opens
    level = _gap_level(index, j - 1, end, index.starts[j])
    if level < 2 and _turns_round_after(index, j):
        return False
    if j > 0 and tokens[j - 1] in _RESULT_MARK_TOKENS:
        return True
    while level == 0 and j not in index.paragraph_starts:
        token = tokens[j]
        if (
            token in _COORDINATORS
            or token in _SUBORDINATORS
            or token in _PREDICATE_WORDS
            or _RESULT_WORD_RE.fullmatch(token)
        ):
            break
        if _turns_round_after(index, j):
            return False
        j += 1
        if j >= len(tokens):
            break
        level = _gap_level(index, j - 1, index.ends[j - 1], index.starts[j])
    return True


def _clause_starts_at(index: EvidenceIndex, start: int) -> bool:
    """Is answer token ``start`` the first word of its clause (or paragraph)?"""
    return (
        start == 0
        or start in index.paragraph_starts
        or _gap_level(index, start - 1, index.ends[start - 1], index.starts[start]) > 0
    )


def _tokens_in_order(fragment: List[str], index: EvidenceIndex) -> bool:
    """True when the fragment's tokens occur in order in a tight answer window.

    Tolerates punctuation and markup differences (tokens ignore them),
    inflections and typos (:func:`_tokens_match`), and small omissions and
    additions:

    - Between two quoted words the answer may have up to two words the quote
      leaves out. They must be function words (:data:`_FUNCTION_WORDS`),
      except for one content word per quote. A protected answer word
      (:func:`_is_protected`) or a question or condition word is never
      stepped over.
    - The quote may add one function word per eight words that the answer
      lacks, also at its start when the match starts a clause of the answer.
      It never adds a content word or a protected word, and never ends with
      an added word.
    - A word the quote adds where the answer has a word the quote leaves out
      is a substitution ("Berechtigter" for "Nichtberechtigter", "fahrlässig"
      for "vorsätzlich") and fails.
    - A protected quoted word must be the very next answer word: nothing may
      be stepped over in front of it, so a moved "nicht" fails.

    A paraphrase changes many words and fails. The match must pass
    :func:`_edges_ok`.
    """
    answer = index.tokens
    n = len(fragment)
    if n == 0:
        return False
    allowed_misses = n // 8
    window = n + max(2, n // 4)
    max_step = 3
    for first in range(min(allowed_misses, n - 1) + 1):
        if not all(_is_function_word(t) for t in fragment[:first]):
            break
        for start, token in enumerate(answer):
            if not _tokens_match(fragment[first], token):
                continue
            # Words the quote adds in front of the match are an addition only
            # where the answer's clause starts; otherwise they stand in for
            # the answer's words in front of the match.
            if first and not _clause_starts_at(index, start):
                continue
            misses = first
            content_skips = 0
            pos = start + 1
            gap_missed = False
            ok = True
            for quoted in fragment[first + 1 :]:
                found = None
                if _is_protected(quoted):
                    if pos < len(answer) and _tokens_match(quoted, answer[pos]):
                        found = pos
                else:
                    for p in range(pos, min(pos + max_step, len(answer))):
                        if _tokens_match(quoted, answer[p]):
                            found = p
                            break
                        if _is_protected(answer[p]) or answer[p] in _EDGE_BEFORE_WORDS:
                            break
                if found is None:
                    misses += 1
                    if not _is_function_word(quoted) or misses > allowed_misses:
                        ok = False
                        break
                    gap_missed = True
                    continue
                skipped = answer[pos:found]
                if skipped and gap_missed:
                    ok = False  # a substitution
                    break
                content_skips += sum(not _is_function_word(t) for t in skipped)
                if content_skips > _EVIDENCE_MAX_CONTENT_SKIPS:
                    ok = False
                    break
                pos = found + 1
                gap_missed = False
                if pos - start > window:
                    ok = False
                    break
            if ok and not gap_missed and _edges_ok(index, index.starts[start], index.ends[pos - 1]):
                return True
    return False


def _is_citation_token(token: str) -> bool:
    """Part of a norm citation: §-free pieces like "Art", "Abs", "S", "Nr",
    "lit", digits, Roman numerals, single letters, and law abbreviations
    (``token`` keeps its case: "VwGO", "GG", "BGB")."""
    folded = token.casefold()
    if len(folded) == 1 or _has_digit(folded) or folded in _ROMAN_NUMERALS or folded in _CITATION_WORDS:
        return True
    if _LAW_ABBREVIATION_RE.fullmatch(token) and sum(ch.isupper() for ch in token) >= 2:
        return not token.isupper() or len(token) <= 6
    return False


def _fragment_is_quotable(tokens: List[str], cased: Optional[List[str]] = None) -> bool:
    """Long enough to be a quote rather than a keyword (see the constants),
    and more than a norm citation: at least one token that is neither part
    of the citation nor a word that only connects it
    (:data:`_CITATION_CONNECTORS`).
    "nach § 40 I 1 VwGO als Leistungsklage statthaft" is a quote; "§ 40 I 1
    VwGO", "nach § 40 I 1 VwGO" and "gem. § 280 BGB i.V.m. § 241 BGB" are
    not. ``cased`` are the same tokens with their case, for the law
    abbreviations."""
    if len(tokens) < EVIDENCE_MIN_TOKENS and not (
        len(tokens) == 2 and sum(len(t) for t in tokens) >= EVIDENCE_MIN_LONG_FRAGMENT_CHARS
    ):
        return False
    return not all(
        _is_citation_token(t) or t.casefold() in _CITATION_CONNECTORS for t in (cased or tokens)
    )


def _cased_tokens(cased_text: str, tokens: List[str]) -> Optional[List[str]]:
    """The tokens of ``cased_text`` when they line up with the casefolded
    ``tokens`` (casefolding can split a token in rare scripts)."""
    cased = _WORD_RE.findall(cased_text)
    return cased if len(cased) == len(tokens) else None


def _find_all(haystack: str, needle: str):
    start = haystack.find(needle)
    while start != -1:
        yield start
        start = haystack.find(needle, start + 1)


def _continues_number(text: str, index: int, step: int) -> bool:
    """Does a number go on at ``index`` (a digit, or ``.``/``,`` then a
    digit, read in direction ``step``)?"""
    if not 0 <= index < len(text):
        return False
    if text[index].isdigit():
        return True
    nxt = index + step
    return text[index] in ".," and 0 <= nxt < len(text) and text[nxt].isdigit()


def _ends_protected(part: str, tokens: List[str]) -> bool:
    """Does ``part`` end with a protected token ("§ 80", "Art. 8 I", "nicht")?"""
    return bool(tokens) and part.endswith(tokens[-1]) and _is_protected(tokens[-1])


def _text_match_ok(index: EvidenceIndex, start: int, end: int, part: str, tokens: List[str]) -> bool:
    """A substring match starts on a word boundary ("zulässig" is not in
    "unzulässig", "Berechtigter" not in "Nichtberechtigter"), cuts no number,
    ends on a word boundary when the quote ends with a protected token ("§ 80"
    is not "§ 80a", "Art. 8 I" not "Art. 8 II", "nicht" not "nichtig"), and
    passes :func:`_edges_ok`."""
    text = index.text
    if start and text[start - 1].isalnum():
        return False
    if part[:1].isdigit() and _continues_number(text, start - 1, -1):
        return False
    if _ends_protected(part, tokens) and end < len(text) and (
        text[end].isalnum() or _continues_number(text, end, 1)
    ):
        return False
    return _edges_ok(index, start, end)


_THOUSANDS_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?")


def _number_tokens(tokens: List[str]) -> List[str]:
    """The numbers among ``tokens``, thousands dots dropped ("10.000" is
    "10000"; "10,5" stays "10,5")."""
    return [t.replace(".", "") if _THOUSANDS_RE.fullmatch(t) else t for t in tokens if _has_digit(t)]


def _compact_match_ok(index: EvidenceIndex, start: int, end: int, part: str, tokens: List[str]) -> bool:
    """Digit boundaries in the compact text, the same numbers in the same
    order in the matched span ("10,5" is not "105", "§§ 1, 2" is not
    "§ 12"), then the substring rules on the matched span of the answer
    text."""
    compact = index.compact
    if compact[start].isdigit() and start and compact[start - 1].isdigit():
        return False
    if compact[end - 1].isdigit() and end < len(compact) and compact[end].isdigit():
        return False
    text_start, text_end = index.compact_pos[start], index.compact_pos[end - 1] + 1
    if _number_tokens(_WORD_RE.findall(index.text[text_start:text_end])) != _number_tokens(tokens):
        return False
    return _text_match_ok(index, text_start, text_end, part, tokens)


def _fragment_in_answer(part: str, tokens: List[str], index: EvidenceIndex) -> bool:
    """Short fragments must sit on word boundaries ("des Verwaltungsrechtsweg"
    does not match "des Verwaltungsrechtswegs"); longer ones may be a
    substring or match token-wise in order (see :func:`_tokens_in_order`).
    Every path applies the boundary and edge rules of :func:`_text_match_ok`,
    and none lets a number match part of a longer number."""
    if len(tokens) < _EVIDENCE_SHORT_FRAGMENT_TOKENS:
        return any(
            _text_match_ok(index, m.start(), m.end(), part, tokens)
            for m in re.finditer(rf"(?<!\w){re.escape(part)}(?!\w)", index.text)
        )
    if any(_text_match_ok(index, s, s + len(part), part, tokens) for s in _find_all(index.text, part)):
        return True
    if _tokens_in_order(tokens, index):
        return True
    # Source artifacts (a hyphenation split, spacing inside numbers) break the
    # token match of an otherwise verbatim long quote: compare letters and
    # digits only.
    compact = _COMPACT_RE.sub("", part)
    if len(compact) >= EVIDENCE_MIN_COMPACT_CHARS and any(
        _compact_match_ok(index, s, s + len(compact), part, tokens) for s in _find_all(index.compact, compact)
    ):
        return True
    # A long quote with a word swapped here and there (see
    # :func:`_substituted_fragment_in_answer`).
    if _substituted_fragment_in_answer(tokens, index):
        return True
    # A long quote the judge copied loosely (see
    # :func:`_near_verbatim_fragment_in_answer`).
    return _near_verbatim_fragment_in_answer(tokens, index)


_UMLAUT_FOLD = str.maketrans("äöü", "aou")


def _fold_umlauts(token: str) -> str:
    return token.translate(_UMLAUT_FOLD)


EVIDENCE_SUBSTITUTION_MIN_TOKENS = 8
_EVIDENCE_SUBSTITUTION_ANCHORS = 3


def _substituted_fragment_in_answer(tokens: List[str], index: EvidenceIndex) -> bool:
    """A long quote (at least :data:`EVIDENCE_SUBSTITUTION_MIN_TOKENS`
    words) whose words line up one to one with an answer passage except for
    its first or last word (one per eight words, at most those two): a judge
    that writes "Heute werden in dem Schreiben …" for "Allerdings werden in
    dem Schreiben …" still quotes the passage. A swap inside the quote
    ("Erstattung" for "Minderung") changes what it says and fails, as does
    a swapped word that is protected (:func:`_is_protected`: negations,
    numbers, result words) or differs only by an umlaut ("hatte" for
    "hätte"). The passage must pass :func:`_edges_ok`. Candidate passages
    are found through the quote's longest words, which must match exactly
    somewhere."""
    n = len(tokens)
    if n < EVIDENCE_SUBSTITUTION_MIN_TOKENS:
        return False
    allowed = min(2, n // 8)
    answer = index.tokens
    anchors = sorted(range(n), key=lambda i: -len(tokens[i]))[:_EVIDENCE_SUBSTITUTION_ANCHORS]
    positions = index.positions
    starts = {
        pos - i
        for i in anchors
        for pos in positions.get(tokens[i], ())
        if 0 <= pos - i <= len(answer) - n
    }
    for start in sorted(starts):
        misses = 0
        for i, (quoted, found) in enumerate(zip(tokens, answer[start : start + n])):
            if _tokens_match(quoted, found):
                continue
            misses += 1
            if (
                misses > allowed
                or i not in (0, n - 1)
                or _is_protected(quoted)
                or _is_protected(found)
                or _fold_umlauts(quoted) == _fold_umlauts(found)
            ):
                break
        else:
            if _edges_ok(index, index.starts[start], index.ends[start + n - 1]):
                return True
    return False


EVIDENCE_NEAR_MIN_CONTENT_TOKENS = 5
# One content word in this many may be missing from the answer or swapped.
_EVIDENCE_NEAR_CONTENT_PER_MISS = 6
_EVIDENCE_NEAR_ANCHORS = 4


def _align_content(content: List[str], answer: List[str], lo: int, hi: int) -> List[Tuple[int, int]]:
    """Longest in-order alignment of the quote's ``content`` words with
    ``answer[lo:hi]`` under :func:`_tokens_match`, as (content index, answer
    index) pairs."""
    width = hi - lo
    lengths = [[0] * (width + 1) for _ in range(len(content) + 1)]
    for i in range(len(content) - 1, -1, -1):
        row, below = lengths[i], lengths[i + 1]
        for j in range(width - 1, -1, -1):
            if _tokens_match(content[i], answer[lo + j]):
                row[j] = below[j + 1] + 1
            else:
                row[j] = max(below[j], row[j + 1])
    pairs: List[Tuple[int, int]] = []
    i = j = 0
    while i < len(content) and j < width:
        if _tokens_match(content[i], answer[lo + j]) and lengths[i][j] == lengths[i + 1][j + 1] + 1:
            pairs.append((i, lo + j))
            i += 1
            j += 1
        elif lengths[i + 1][j] >= lengths[i][j + 1]:
            i += 1
        else:
            j += 1
    # The walk takes every match as early as it can, so a common first word
    # ("Klage") may pair with an occurrence far before the passage. Pull each
    # match right up to the next one to keep the passage tight.
    for k in range(len(pairs) - 2, -1, -1):
        i, j = pairs[k]
        for later in range(pairs[k + 1][1] - 1, j, -1):
            if _tokens_match(content[i], answer[later]):
                pairs[k] = (i, later)
                break
    return pairs


# Subjunctive forms hedge what they state ("hätte prüfen müssen" is not
# "hatte"); the near-verbatim match never leaves one out or swaps it.
_SUBJUNCTIVE_TOKENS = frozenset({
    "hätte", "hätten", "wäre", "wären", "würde", "würden", "könnte", "könnten", "müsste", "müssten",
    "dürfte", "dürften", "sollte", "sollten",
})
# Two words of at least this many characters ending (or starting) alike are
# variants of one compound ("Beihilfebescheide" / "Bewilligungsbescheide",
# "gunsten" / "zugunsten"); a judge may write one for the other.
_EVIDENCE_COMPOUND_PART_CHARS = 6


def _is_compound_variant(a: str, b: str) -> bool:
    """Same compound head or same compound start, no protected word, not an
    umlaut variant ("hatte" / "hätte")."""
    if _is_protected(a) or _is_protected(b) or _fold_umlauts(a) == _fold_umlauts(b):
        return False
    n = _EVIDENCE_COMPOUND_PART_CHARS
    return len(a) >= n and len(b) >= n and (a[-n:] == b[-n:] or a[:n] == b[:n])


def _breaks_sentence(index: EvidenceIndex, first: int, last: int) -> bool:
    """Does a sentence end between answer tokens ``first`` and ``last``?"""
    return any(
        _gap_level(index, k, index.ends[k], index.starts[k + 1]) > 1 for k in range(first, last)
    )


def _near_verbatim_fragment_in_answer(tokens: List[str], index: EvidenceIndex) -> bool:
    """A long quote whose content words stand in the answer in the same order,
    with the small liberties judges take when they copy: function words
    dropped, added or moved ("Da B im vorliegenden …" for "B ist
    vorliegend …"), a few answer words left out without an ellipsis ("…
    denselben Beklagten, stehen im Zusammenhang" for "… denselben
    Beklagten, die erlassende Widerspruchsbehörde, stehen im
    Zusammenhang"), and a different first or last word.

    Needs at least :data:`EVIDENCE_NEAR_MIN_CONTENT_TOKENS` content words
    (words that are not :func:`_is_function_word`), at most one in
    :data:`_EVIDENCE_NEAR_CONTENT_PER_MISS` of them unmatched. Inside the
    quote an unmatched content word fails unless the answer has a variant of
    the same compound in its place (:func:`_is_compound_variant`): a swap
    ("Erstattung" for "Minderung") or an added word ("der mangelhaften
    Sache") changes what the passage says. Unmatched words at the quote's
    start or end may be none of the protected words. Every protected quoted
    word (negations, numbers, result and qualifier words, see
    :func:`_is_protected`) must be matched, and the answer words the quote
    leaves out may hold no protected, question or condition word, no
    subjunctive (:data:`_SUBJUNCTIVE_TOKENS`: "hatte" never quotes
    "hätte"), no sentence end, and at most a quarter of the quote's content words (at
    least two). The passage spans at most the quote plus a third and must
    pass :func:`_edges_ok`. A sentence the answer does not contain, such as
    one from the Musterlösung, misses most content words and fails.
    Candidate passages come from the quote's longest content words."""
    content_at = [i for i, token in enumerate(tokens) if not _is_function_word(token)]
    content = [tokens[i] for i in content_at]
    if len(content) < EVIDENCE_NEAR_MIN_CONTENT_TOKENS:
        return False
    allowed_misses = max(1, len(content) // _EVIDENCE_NEAR_CONTENT_PER_MISS)
    allowed_left_out = max(2, len(content) // 4)
    slack = max(4, len(tokens) // 3)
    max_span = len(tokens) + slack
    answer = index.tokens
    anchors = sorted(range(len(content)), key=lambda i: -len(content[i]))[:_EVIDENCE_NEAR_ANCHORS]
    windows = set()
    for i in anchors:
        for pos in index.positions.get(content[i], ()):
            lo = max(0, pos - content_at[i] - slack)
            windows.add((lo, min(len(answer), lo + len(tokens) + 2 * slack)))
    for lo, hi in sorted(windows):
        pairs = _align_content(content, answer, lo, hi)
        if len(pairs) < 2 or len(content) - len(pairs) > allowed_misses:
            continue
        first, last = pairs[0][1], pairs[-1][1]
        if last - first + 1 > max_span:
            continue
        unmatched = [i for i in range(len(content)) if i not in {qi for qi, _aj in pairs}]
        if any(_is_protected(content[i]) or content[i] in _SUBJUNCTIVE_TOKENS for i in unmatched):
            continue
        # A quoted function word may be dropped, never stand in for a hedge.
        span_quote = set(tokens)
        if any(
            t in _SUBJUNCTIVE_TOKENS and t not in span_quote for t in answer[first : last + 1]
        ):
            continue
        ok = True
        left_out_content = 0
        for (qi, aj), (qn, an) in zip(pairs, pairs[1:]):
            gap_answer = answer[aj + 1 : an]
            gap_quote = content[qi + 1 : qn]
            if gap_answer and _breaks_sentence(index, aj, an):
                ok = False
                break
            if any(_is_protected(t) or t in _EDGE_BEFORE_WORDS or t in _SUBJUNCTIVE_TOKENS for t in gap_answer):
                ok = False
                break
            answer_content = [t for t in gap_answer if not _is_function_word(t)]
            left_out_content += len(answer_content)
            # Unmatched quote words inside the quote: each needs a compound
            # variant of itself in the answer's gap.
            for quoted in gap_quote:
                variant = next((t for t in answer_content if _is_compound_variant(quoted, t)), None)
                if variant is None:
                    ok = False
                    break
                answer_content.remove(variant)
                left_out_content -= 1
            if not ok:
                break
        if not ok or left_out_content > allowed_left_out:
            continue
        if _edges_ok(index, index.starts[first], index.ends[last]):
            return True
    return False


def _stitched_fragment_in_answer(cased_part: str, index: EvidenceIndex) -> bool:
    """A fragment that is not one passage of the answer may be several
    passages glued together without an ellipsis. It is split into sentences
    (:func:`_split_sentences`: never after an abbreviation, so "Der Käufer
    ist gem. § 437 Nr. 2 BGB zum Rücktritt berechtigt" stays one piece), and
    every piece must be quotable on its own and in the answer. A piece too
    short to be a quote ("VwGO.", "Kein Anspruch.", "§ 40 VwGO.") is glued
    back to its neighbour, separator included, and the glued text must be in
    the answer. So a keyword cannot ride along with a real sentence, and an
    invented sentence fails the whole quote. ``cased_part`` is the
    normalized fragment before casefolding."""
    pieces: List[str] = []
    for piece in _split_sentences(cased_part):
        if _WORD_RE.search(piece) or not pieces:
            pieces.append(piece)
        else:
            pieces[-1] = f"{pieces[-1]} {piece}"

    def quotable(piece: str) -> bool:
        tokens = _WORD_RE.findall(piece.casefold())
        return _fragment_is_quotable(tokens, _cased_tokens(piece, tokens))

    while len(pieces) > 1:
        short = next((i for i, p in enumerate(pieces) if not quotable(p)), None)
        if short is None:
            break
        # The previous neighbour; a leading piece goes with the next one.
        i = short - 1 if short else 0
        pieces[i : i + 2] = [f"{pieces[i]} {pieces[i + 1]}"]
    if len(pieces) < 2:
        return False
    for piece in pieces:
        piece = piece.strip(_EDGE_PUNCTUATION).casefold()
        if not _fragment_in_answer(piece, _WORD_RE.findall(piece), index):
            return False
    return True


_EVIDENCE_STRAY_FRAGMENT_TOKENS = 2


def _is_stray_fragment(cased: str, part: str, tokens: List[str], index: EvidenceIndex) -> bool:
    """A piece of a quote too short to be quoted on its own, without a
    protected token ("nicht", a number, a result word) or a piece of a norm
    citation ("GVG", "Abs"), that stands in the answer as whole words (see
    :func:`verify_evidence`)."""
    cased_tokens = _cased_tokens(cased, tokens) or tokens
    return (
        len(tokens) <= _EVIDENCE_STRAY_FRAGMENT_TOKENS
        and not _fragment_is_quotable(tokens, cased_tokens)
        and not any(_is_protected(t) for t in tokens)
        and not any(_is_citation_token(t) for t in cased_tokens)
        and re.search(rf"(?<!\w){re.escape(part)}(?!\w)", index.text) is not None
    )


# An outline label at the start of a quoted heading ("2. Formelle
# Rechtmäßigkeit", "B. Zulässigkeit"): judges renumber headings ("2." for the
# answer's "II." or "3."), and the label is not what earns the points.
_OUTLINE_LABEL_RE = re.compile(r"^(?:\d{1,2}|[IVX]{1,5}|[A-Za-z])[.)]\s+(?=[A-ZÄÖÜ])")


def verify_evidence(evidence: str, index: EvidenceIndex) -> bool:
    """Is ``evidence`` really in the answer?

    Checked against the answer as submitted and, when it differs, against
    the answer without PDF page layout (``index.layout_free``, see
    :func:`_strip_pdf_layout`): a quote counts when either holds it
    (:func:`_verify_evidence_in`)."""
    if _verify_evidence_in(evidence, index):
        return True
    return index.layout_free is not None and _verify_evidence_in(evidence, index.layout_free)


def _verify_evidence_in(evidence: str, index: EvidenceIndex) -> bool:
    """Is every fragment of ``evidence`` really in this answer?

    Fragments are split on ellipses (``…``, ``...``, ``[...]``); a leading
    outline label ("2.", "II.", "B.") is dropped (:data:`_OUTLINE_LABEL_RE`).
    At least one fragment must be quotable (:func:`_fragment_is_quotable`:
    at least three tokens, or two long ones, never a single token, never
    only a norm citation), and every quotable fragment must be in the answer
    (:func:`_fragment_in_answer`, or glued passages, see
    :func:`_stitched_fragment_in_answer`) with nothing around it that turns
    it round (:func:`_edges_ok`). Protected tokens (negations, result marks,
    result and qualifier words, Roman numerals, numbers) must match exactly.
    Empty evidence, or evidence with fewer than
    :data:`EVIDENCE_MIN_WORD_CHARS` word characters, is not verified.

    A fragment of two or more words too short to be a quote on its own (a
    norm citation such as "§ 54 I BeamtStG", a date such as "am 14.2.2026")
    does not carry the quote but must still stand in the answer, and only
    next to quotable fragments with at least
    :data:`EVIDENCE_NEAR_MIN_CONTENT_TOKENS` content words; a lone keyword
    ("… GVG") voids the quote. Judges also often end a quote
    with the last word of the sentence after an ellipsis ("ruft einen
    Irrtum ... hervor."); such a stray piece (at most
    :data:`_EVIDENCE_STRAY_FRAGMENT_TOKENS` words, none of them protected,
    standing in the answer as words) is left out when another fragment is
    quoted; it adds nothing the judge could lean on.
    """
    fragments = []
    for cased in _ELLIPSIS_SPLIT_RE.split(_normalize_evidence_text(evidence, casefold=False)):
        cased = cased.strip(_EDGE_PUNCTUATION)
        cased = _OUTLINE_LABEL_RE.sub("", cased).strip(_EDGE_PUNCTUATION)
        part = cased.casefold()
        tokens = _WORD_RE.findall(part)
        if tokens:
            fragments.append((cased, part, tokens))
    if len(fragments) > 1:
        kept = [f for f in fragments if not _is_stray_fragment(*f, index)]
        if kept:
            fragments = kept
    if not fragments:
        return False
    if sum(len(tok) for _cased, _part, tokens in fragments for tok in tokens) < EVIDENCE_MIN_WORD_CHARS:
        return False
    quotable = [_fragment_is_quotable(tokens, _cased_tokens(cased, tokens)) for cased, _part, tokens in fragments]
    if not any(quotable):
        return False
    # A lone keyword ("… GVG") still voids the quote: it is not a citation
    # the answer states but a word it happens to contain. A longer citation
    # or date rides along only with a substantial quote, never with a bare
    # phrase ("Der Anspruch des K … § 433 II BGB").
    if not all(quotable):
        if any(not ok and len(tokens) < 2 for (_c, _p, tokens), ok in zip(fragments, quotable)):
            return False
        carried = sum(
            not _is_function_word(t)
            for (_c, _p, tokens), ok in zip(fragments, quotable)
            if ok
            for t in tokens
        )
        if carried < EVIDENCE_NEAR_MIN_CONTENT_TOKENS:
            return False
    return all(
        (_fragment_in_answer(part, tokens, index) or (is_quotable and _stitched_fragment_in_answer(cased, index)))
        for (cased, part, tokens), is_quotable in zip(fragments, quotable)
    )

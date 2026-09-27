#!/usr/bin/env python3
"""Build the local D2 pack: the exam author's Polizeirecht exam, his 46-step
Bewertungsbogen, and every human- or model-graded script of that exam.

Two cohorts of the same case (only dates and two words differ between the
yearly versions):

  D2a  15 typed PDF scripts from the 2024/2025 runs (H01-H15), each with
       per-step BE in the matching Korrekturbogen xlsx ("Ihre BE").
  D2b  25 submissions written on the platform in September 2026 (B01-B25),
       with the stored instant rubric-judge grades and the exam author's
       Korrektur where it exists. Read from a read-only prod pull that lives
       in data/raw (the pull itself is not scripted in this public repo).

Everything this script writes is personal data or third-party exam text and
stays in data/interim/human/ (git-ignored). The data root comes from
scripts/local_config.py (PILOT_DATA_ROOT or .pilot.local.json).

Cleaning, per script:
  - PDF text: page count from pdfinfo; broken ff/fi/fl ligature glyphs
    repaired per PDF and checked against a vocabulary; running page headers,
    footers and page numbers removed.
  - Header blocks before the first content heading are dropped, examiner
    lines (Dr., Prof., Korrektor) are stripped, e-mail addresses are scrubbed.
  - The PII scanner looks for standalone name lines: 2-5 words, each a
    capitalised word or an all-caps one of 4+ letters (any script's letters,
    so diacritics count) or a name particle (von, van, de, zu ...), at least
    two of them names, at most one comma ("Surname, First"), no outline
    label (A., VI., d)), at least one name not in the case, Musterloesung or
    sheet vocabulary. It also flags labelled names
    ("Bearbeiter:", "Verfasser:", "Name:" ...), id keywords and long numbers.
    Every hit must be listed by the sha256 of its normalised line in
    KEY.local.json "redact_lines" (action "redact" or "allow"); an unlisted
    hit FAILS the build. Listed "redact" lines are removed wherever they
    occur. The per-year case texts are scanned too (examiner lines, links
    and passwords there are flagged, not stripped).
  - Platform texts: <br /> tags, <u> tags and NBSP residue normalised.
  - Duplicates and overlap by 8-gram containment (case text removed first):
    duplicate_of, duplicate_kind (near_copy, or copy_then_extend when the
    later script holds the earlier one plus more), exclude_reason,
    related_to.
  - case_year from the PDF creation date, checked against the years the text
    cites. Per-year case texts come from exam/Angabe_<year>.docx when present;
    otherwise the script carries case_text_year_mismatch. Their sha256 and
    length are taken after the same blank-line collapse the pack stores.
  - Sheet state per script: the step labels and maxima of its xlsx against
    the current sheet. The grader is "pending" for the xlsx grades, with
    xlsx_last_modified_by_differs per sheet (no names are stored).
Case text and Musterloesung: Markdown unescaped, table of contents dropped,
heading labels taken over from the table of contents, footnotes kept; the
sha256 and length of the raw and cleaned texts are stored.

Inputs  (<data>/raw/human/heidebach_polr/, git-ignored):
  rubric/Korrekturbogen_BE.xlsx, scripts/H??.{pdf,xlsx}, exam/*.docx,
  platform_2026/prod_<project>_pull_*.jsonl, platform_2026/KEY.local.json
  (<project>: d2_pull_project in .pilot.local.json, else the only one there)
Outputs (<data>/interim/human/, git-ignored):
  heidebach_exam.json         case text, Musterloesung, sheet, states, key
  heidebach_scripts.json      40 scripts: text + human and stored model grades
  heidebach_pack_report.json  counts and hashes only (no text)
Needs: pdftotext, pdfinfo, pdffonts (poppler).

  extract_heidebach_pack.py                  build the pack
  extract_heidebach_pack.py --check          scan and report counts only; writes nothing
  extract_heidebach_pack.py --show-unlisted  also print unlisted PII lines (local review)
  extract_heidebach_pack.py --list redact|allow SHA256 CATEGORY [SCRIPT]
                                             add an entry to redact_lines
  extract_heidebach_pack.py --selftest       the scanner and overlap rules on synthetic lines
"""

from __future__ import annotations

import argparse
import collections
import difflib
import hashlib
import itertools
import json
import re
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent.parent
PLATFORM = HERE.parent.parent
sys.path[:0] = [str(HERE / "scripts"), str(PLATFORM / "services" / "shared"), str(PLATFORM / "services" / "api")]

import local_config
from services.rubric_import import (
    _read_docx,
    _read_xlsx_grid,
    parse_rubric_file,
)

DATA = local_config.data_root()
RAW = DATA / "raw" / "human" / "heidebach_polr"
OUT = DATA / "interim" / "human"
# P-code key, the exam author's prod user id and the PII line list (local only).
KEY_FILE = RAW / "platform_2026" / "KEY.local.json"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# The exam's key (identical to the prod project's custom key): BE thresholds
# for 1..18 Notenpunkte, totals rounded down ("bei 0,5 BE wird abgerundet").
EXAM_THRESHOLDS = [10, 20, 30, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96]
PASS_GRADE = 4
PLATFORM_YEAR = "2026"  # the case version on the platform (D2b, the research task)

# --- text helpers -------------------------------------------------------------

MD_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|<>~\"'])")
MARKUP = re.compile(r"</?u>|<br\s*/?>|[*_#>]+|\\")


def sha(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def unescape_md(text: str) -> str:
    return MD_ESCAPE.sub(r"\1", text or "")


def norm_line(line: str) -> str:
    """A line without Markdown/HTML markup, NFC, whitespace collapsed."""
    text = unicodedata.normalize("NFC", line or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", MARKUP.sub(" ", text)).strip()


def line_hash(line: str) -> str:
    return sha(norm_line(line))


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÄÖÜäöüß]+", text or "")


def scrub(text: str) -> tuple[str, int]:
    return EMAIL.subn("[E-Mail entfernt]", text or "")


def collapse_blank_lines(text: str) -> str:
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --- key file -----------------------------------------------------------------


def load_key() -> dict[str, Any]:
    try:
        key = json.loads(KEY_FILE.read_text())
    except FileNotFoundError:
        raise SystemExit(f"{KEY_FILE} is missing. It holds the exam author's prod user id under "
                         "'martin_user_id' (local only, never in git).") from None
    uid = key.get("martin_user_id") if isinstance(key, dict) else None
    if not isinstance(uid, str) or not uid.strip():
        raise SystemExit(f"{KEY_FILE} has no 'martin_user_id' (the exam author's prod user id, local only); "
                         "it tells his Korrektur and test uploads from the students'.")
    key.setdefault("redact_lines", [])
    return key


def save_key(key: dict[str, Any]) -> None:
    KEY_FILE.write_text(json.dumps(key, indent=1, ensure_ascii=False) + "\n")


def add_listed_line(action: str, digest: str, category: str, script_id: str | None) -> int:
    if action not in ("redact", "allow") or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SystemExit("--list needs redact|allow, a sha256 hex digest and a category")
    key = load_key()
    entries = [e for e in key["redact_lines"] if e.get("sha256") != digest]
    entries.append({"sha256": digest, "action": action, "category": category,
                    **({"script_id": script_id} if script_id else {})})
    key["redact_lines"] = entries
    save_key(key)
    print(f"{KEY_FILE.name}: {action} {digest[:12]} ({category}); {len(entries)} listed lines")
    return 0


# --- PII scanner ----------------------------------------------------------------

ID_KEYWORD = re.compile(r"matrikel|kennziffer|klausurnummer|\bname\s*:|geburtsdatum|\bmat\.?-?nr", re.IGNORECASE)
LONG_NUMBER = re.compile(r"(?<![\d/.,])\d{6,}(?![\d/])")
EXAMINER = re.compile(r"^(?:Dr\.|Prof\.|PD\s)|\bKorrektor(?:in)?\b|\bPrüfer(?:in)?\b")
# "Bearbeiter: X", "Name: X", "Verfasserin -", "Unterschrift:": a label that
# introduces a person, with or without the value on the same line.
NAME_LABEL = re.compile(
    r"\b(?:Bearbeiter(?:in)?|Verfasser(?:in)?|Vor-?\s?name|Nach-?\s?name|Familienname|Name|Autor(?:in)?|"
    r"Student(?:in)?|Studierende[rn]?|Kandidat(?:in)?|Prüfling|Teilnehmer(?:in)?|Unterschrift|"
    r"Eingereicht\s+von|Vorgelegt\s+von)\s*[:=–-]", re.IGNORECASE)
# Name particles (von der Leyen, van den Berg, de la Cruz, zu Guttenberg).
# der/den/des/dem/la/las/los count only right after one of the leading ones.
NAME_PARTICLES = {"von", "van", "de", "zu", "vom", "zur", "zum", "ter", "ten", "di", "da", "del", "della", "du",
                  "le", "dos", "das", "af", "av", "bin", "ibn", "al", "el", "y", "d", "l"}
NAME_PARTICLES_AFTER = {"der", "den", "des", "dem", "la", "las", "los", "lo"}
# Links and passwords (flagged in case texts: a case once carried an upload link and its password).
LINK_OR_SECRET = re.compile(r"https?://|\bwww\.|\b(?:passwort|password|kennwort|zugangscode|zugangsdaten)\b",
                            re.IGNORECASE)
VOCAB_WORD = re.compile(r"[^\W\d_]+")


# Outline labels (A., VI., IX, d), aa), 1., (2)): a line holding one is a
# heading, not a name line. Roman numerals never count as a name.
OUTLINE_TOKEN = re.compile(r"(?:[A-Z]|[a-z]{1,3}|\d{1,3}|[IVXLC]+)[.)]|\(\w{1,3}\)|[IVXLC]+")


def is_name_token(token: str) -> bool:
    """A capitalised word (Müller, Çelik, O'Neil, Müller-Lüdenscheid) or an
    all-caps one of 4+ letters (MÜLLER; shorter all-caps words are mostly
    abbreviations); letters of any script."""
    parts = [p for p in re.split(r"[-'’]", token) if p]
    if not parts or len(parts) > 3:
        return False
    capitalised = [p for p in parts if p not in NAME_PARTICLES]  # al-Hassan, d'Alembert
    if not capitalised:
        return False
    for part in capitalised:
        if not part.isalpha() or not part[0].isupper():
            return False
        if not (part[1:].islower() or part[1:] == "" or (part.isupper() and len(part) >= 4)
                or re.fullmatch(r"(?:Mc|Mac)[A-Z][a-z]+", part)):
            return False
    return len(token) >= 2


def name_shape(core: str, vocab: set[str]) -> bool:
    """A standalone name line: 2-5 words, each a name or a particle, at least
    two names, at least one name outside the exam's vocabulary. One comma is
    allowed ("Surname, First"); a line with an outline label or with more
    commas (a list of nouns) is not a name line."""
    if core.count(",") > 1:
        return False
    tokens = []
    for raw in core.replace(",", " ").split():
        if OUTLINE_TOKEN.fullmatch(raw.rstrip(":;")):
            return False
        token = raw.strip(".:;()[]\"'„“")
        if token:
            tokens.append(token)
    if not 2 <= len(tokens) <= 5:
        return False
    names, previous = [], None
    for token in tokens:
        low = token.casefold()
        if low in NAME_PARTICLES or (low in NAME_PARTICLES_AFTER and previous in NAME_PARTICLES):
            previous = low
            continue
        if not is_name_token(token):
            return False
        names.append(token)
        previous = low
    return len(names) >= 2 and any(n.casefold() not in vocab for n in names)


class PiiLog:
    """Every scanner hit, by script id and category. Never the text."""

    def __init__(self, listed: list[dict[str, Any]], vocab: set[str], show: bool):
        self.listed = {e["sha256"]: e for e in listed if isinstance(e, dict) and e.get("sha256")}
        self.vocab = vocab
        self.show = show
        self.hits: list[dict[str, Any]] = []
        self.used: set[str] = set()

    def category(self, core: str, links: bool = False) -> str | None:
        if NAME_LABEL.search(core):
            return "labelled_name"
        if name_shape(core, self.vocab):
            return "name_shape"
        if ID_KEYWORD.search(core) or LONG_NUMBER.search(core):
            return "id_keyword"
        if links and LINK_OR_SECRET.search(core):
            return "link_or_secret"
        return None

    def log(self, script_id: str, line_no: int, category: str, action: str, core: str) -> None:
        digest = sha(core)
        self.hits.append({"script_id": script_id, "line": line_no, "category": category,
                          "action": action, "sha256": digest})
        if action == "UNLISTED":
            detail = f"  text: {core!r}" if self.show else ""
            print(f"PII UNLISTED {script_id} line {line_no} {category} sha256 {digest}{detail}")

    def apply(self, script_id: str, text: str, examiner: str = "strip", links: bool = False) -> str:
        """The text without listed "redact" lines; every other hit is logged.

        ``examiner`` "strip" removes short examiner lines (scripts); "flag"
        treats them as a hit that must be listed (case texts, which must not
        change silently). ``links`` also flags links and passwords."""
        kept = []
        for no, line in enumerate(text.split("\n")):
            core = norm_line(line)
            if not core:
                kept.append(line)
                continue
            digest = sha(core)
            entry = self.listed.get(digest)
            if entry is not None:
                self.used.add(digest)
            if entry is not None and entry.get("action") == "redact":
                self.log(script_id, no, entry.get("category") or "listed", "redacted", core)
                continue
            is_examiner = len(core.split()) <= 8 and EXAMINER.search(core)
            if is_examiner and examiner == "strip":
                self.log(script_id, no, "examiner_line", "stripped", core)
                continue
            category = "examiner_line" if is_examiner else self.category(core, links=links)
            if category:
                self.log(script_id, no, category, "allowed" if entry is not None else "UNLISTED", core)
            kept.append(line)
        return "\n".join(kept)

    def scan_only(self, script_id: str, lines: list[str], where: str) -> None:
        """Scan a block that is dropped anyway (header blocks): hits are logged
        and, like every other hit, must be listed."""
        for no, line in enumerate(lines):
            core = norm_line(line)
            if not core:
                continue
            entry = self.listed.get(sha(core))
            if entry is not None:
                self.used.add(sha(core))
            if entry is not None and entry.get("action") == "redact":
                self.log(script_id, no, entry.get("category") or "listed", f"redacted_{where}", core)
            elif len(core.split()) <= 8 and EXAMINER.search(core):
                self.log(script_id, no, "examiner_line", f"stripped_{where}", core)
            elif self.category(core):
                action = f"allowed_{where}" if entry is not None else "UNLISTED"
                self.log(script_id, no, self.category(core), action, core)

    def unlisted(self) -> list[dict[str, Any]]:
        return [h for h in self.hits if h["action"] == "UNLISTED"]

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = collections.defaultdict(lambda: collections.defaultdict(list))
        for h in self.hits:
            out[h["category"]][h["action"]].append(h["script_id"])
        return {cat: {act: sorted(ids) for act, ids in acts.items()} for cat, acts in out.items()}


# --- header blocks --------------------------------------------------------------

CONTENT_HEADING = re.compile(r"^(?:(?:Frage|Aufgabe|Teil|Fallfrage)\s*(?:1|I|Nr\.?\s*1)\b|(?:A|I|1)\s*[.):](?:\s|$))",
                             re.IGNORECASE)
LABEL_START = re.compile(r"^(?:[A-H]|[IVX]+|\d+|[a-z]{1,2})\s*[.)]\s")
MAX_HEADER_LINES = 8


def header_block(lines: list[str]) -> int:
    """Index of the first content heading when everything before it is a
    header block (short, no sentence, no outline label), else 0."""
    block = 0
    for i, line in enumerate(lines[:40]):
        core = norm_line(line)
        if not core:
            continue
        if CONTENT_HEADING.match(core):
            return i if block else 0
        if len(core.split()) > 10 or core.endswith(".") or LABEL_START.match(core) or block >= MAX_HEADER_LINES:
            return 0
        block += 1
    return 0


# --- PDF extraction ---------------------------------------------------------------

LIGATURE_CHARS = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}
LIGATURE_REPLACEMENTS = ("ff", "fi", "fl", "ffi", "ffl")
WORD_WITH_DIGITS = re.compile(r"[A-Za-zÄÖÜäöüß0-9]+")
VOWELS = set("aeiouäöüAEIOUÄÖÜ")
WELL_FORMED = re.compile(r"^[A-ZÄÖÜ]?[a-zäöüß]+$")
PAGE_NUMBER = re.compile(r"^(?:Seite\s*)?\d{1,3}(?:\s*(?:von|/)\s*\d{1,3})?$", re.IGNORECASE)


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def pdf_facts(pdf: Path) -> dict[str, Any]:
    info = run(["pdfinfo", str(pdf)])
    pages = int(re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE).group(1))
    created = re.search(r"^CreationDate:\s+.*?(\d{4})\s*(?:[A-Z]{2,5})?\s*$", info, re.MULTILINE)
    fonts = []
    for line in run(["pdffonts", str(pdf)]).splitlines()[2:]:
        parts = line.split()
        if len(parts) >= 7:
            fonts.append({"font": parts[0].split("+", 1)[-1], "tounicode": parts[-3] == "yes"})
    return {"pages": pages, "created_year": created.group(1) if created else None, "fonts": fonts}


def suspicious(word: str, char: str) -> list[int]:
    """Positions of ``char`` between a vowel and a lowercase letter."""
    return [i for i, c in enumerate(word) if c == char and 0 < i < len(word) - 1
            and word[i - 1] in VOWELS and word[i + 1].islower()]


def detect_broken_glyphs(text: str, vocab: set[str]) -> dict[str, dict[str, Any]]:
    """Characters that stand for a ligature glyph in this PDF's text layer.

    A digit or capital letter inside a word (after a vowel, before a
    lowercase letter) is a candidate. It counts as a broken ligature when
    replacing it with ff/fi/fl/ffi/ffl turns at least 2 such words, and at
    least 60 % of them, into vocabulary words.
    """
    candidates = collections.Counter(
        c for w in WORD_WITH_DIGITS.findall(text) for i, c in enumerate(w)
        if (c.isdigit() or c.isupper()) and i in suspicious(w, c))
    found = {}
    for char in candidates:
        tokens = [w for w in WORD_WITH_DIGITS.findall(text) if suspicious(w, char)]
        best = None
        for rep in LIGATURE_REPLACEMENTS:
            hits = sum(1 for w in tokens if w.replace(char, rep).casefold() in vocab)
            if best is None or hits > best[1]:
                best = (rep, hits)
        if best and best[1] >= 2 and best[1] / len(tokens) >= 0.6:
            found[char] = {"replacement": best[0], "vocab_hits": best[1], "tokens": len(tokens)}
    return found


def repair_ligatures(text: str, broken: dict[str, dict[str, Any]], vocab: set[str]) -> tuple[str, dict[str, Any]]:
    stats = {"unicode_ligatures": 0, "glyph_repairs": 0, "vocab_confirmed": 0, "rule_only": 0,
             "rule_only_words": [], "residual": 0}
    for char, rep in LIGATURE_CHARS.items():
        stats["unicode_ligatures"] += text.count(char)
        text = text.replace(char, rep)

    def fix(match: re.Match) -> str:
        word = match.group(0)
        for char, info in broken.items():
            positions = suspicious(word, char)
            if not positions:
                continue
            chars = list(word)
            for i in positions:
                chars[i] = info["replacement"]
            fixed = "".join(chars)
            if fixed.casefold() in vocab:
                stats["vocab_confirmed"] += 1
            elif len(fixed) >= 5:
                stats["rule_only"] += 1
                stats["rule_only_words"].append(fixed)
            else:
                continue
            stats["glyph_repairs"] += 1
            word = fixed
        return word

    text = WORD_WITH_DIGITS.sub(fix, text)
    stats["residual"] = sum(len(suspicious(w, c)) for w in WORD_WITH_DIGITS.findall(text) for c in broken)
    stats["rule_only_words"] = sorted(set(stats["rule_only_words"]))
    return text, stats


def strip_running_lines(pages: list[str]) -> tuple[list[str], int]:
    """Remove page numbers and lines that repeat at the top or bottom of most pages."""
    def edges(lines: list[str]) -> list[int]:
        idx = [i for i, line in enumerate(lines) if line.strip()]
        return sorted(set(idx[:2] + idx[-2:]))

    split = [page.split("\n") for page in pages]
    counts = collections.Counter()
    for lines in split:
        counts.update({re.sub(r"\d+", "#", lines[i].strip()) for i in edges(lines)})
    threshold = max(3, (len(pages) + 1) // 2)
    running = {k for k, n in counts.items() if n >= threshold}
    removed = 0
    out = []
    for lines in split:
        drop = {i for i in edges(lines)
                if PAGE_NUMBER.match(lines[i].strip()) or re.sub(r"\d+", "#", lines[i].strip()) in running}
        removed += len(drop)
        out.append("\n".join(line for i, line in enumerate(lines) if i not in drop))
    return out, removed


def pdf_pages(pdf: Path) -> list[str]:
    text = run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"])
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return pages


def normalise_pdf_text(text: str) -> str:
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return collapse_blank_lines(text)


CITED_YEAR = re.compile(r"\b(?:\d{1,2}\.\s?\d{1,2}\.|\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|"
                        r"September|Oktober|November|Dezember))\s*(20[2-3]\d)\b|\b(20[2-3]\d)\b")


def cited_years(text: str) -> dict[str, int]:
    years = collections.Counter(m.group(1) or m.group(2) for m in CITED_YEAR.finditer(text))
    return dict(sorted(years.items()))


def case_year_of(created: str | None, cited: dict[str, int]) -> tuple[str | None, bool]:
    """(case year, whether the cited years disagree with it).

    The case year is the PDF's creation year. The case cites the event
    year and the end of the measure one year later, so cited years in
    {year, year + 1} agree; any other year that is cited more often than the
    creation year counts as a disagreement.
    """
    if created is None:
        return None, True
    fitting = cited.get(created, 0) + cited.get(str(int(created) + 1), 0)
    other = max((n for y, n in cited.items() if y not in (created, str(int(created) + 1))), default=0)
    return created, other > fitting


# --- sheet and grades ----------------------------------------------------------------


def norm_label(label: Any) -> str:
    return re.sub(r"\s+", " ", str(label or "").replace("\xa0", " ").lstrip("·•- ").strip())


def sheet_rows(xlsx_bytes: bytes) -> tuple[list[tuple[int, str, float, float]], float | None]:
    """(step rows as (row, label, max, got), the Gesamt-BE cell)."""
    rows, total_cell = [], None
    for r, cells in _read_xlsx_grid(xlsx_bytes):
        label = str(cells.get(0, "")).strip()
        if label.startswith("Gesamt-BE"):
            total_cell = float(str(cells.get(2) or 0))
            break
        try:
            mx = float(str(cells.get(1)))
        except (TypeError, ValueError):
            continue
        got = str(cells.get(2) or "").strip()
        rows.append((r, norm_label(label), mx, float(got) if got else 0.0))
    return rows, total_cell


def section_labels(xlsx_bytes: bytes) -> dict[int, str]:
    """Label cells of the non-step rows (sections), without the author block."""
    out = {}
    for r, cells in _read_xlsx_grid(xlsx_bytes):
        label = norm_label(cells.get(0, ""))
        if label.startswith("Gesamt-BE"):
            break
        try:
            float(str(cells.get(1)))
        except (TypeError, ValueError):
            if label:
                out[r] = label
    return out


def last_modified_by_differs(xlsx: Path) -> bool | None:
    """Whether the xlsx was last saved by someone other than its creator (no names kept)."""
    with zipfile.ZipFile(xlsx) as zf:
        if "docProps/core.xml" not in zf.namelist():
            return None
        core = zf.read("docProps/core.xml").decode("utf-8", "replace")
    creator = re.search(r"<dc:creator>(.*?)</dc:creator>", core, re.DOTALL)
    modifier = re.search(r"<cp:lastModifiedBy>(.*?)</cp:lastModifiedBy>", core, re.DOTALL)
    if not creator or not modifier:
        return None
    return creator.group(1).strip() != modifier.group(1).strip()


def grade(total_be: float) -> int:
    return sum(1 for t in EXAM_THRESHOLDS if int(total_be) >= t)


def sheet_steps():
    raw = (RAW / "rubric" / "Korrekturbogen_BE.xlsx").read_bytes()
    res = parse_rubric_file("Korrekturbogen_BE.xlsx", raw)
    steps = [n for n in res["structure"]["nodes"] if n["kind"] == "step"]
    assert len(steps) == 46 and res["total_points"] == 100, (len(steps), res["total_points"])
    ref_rows, _ = sheet_rows(raw)
    assert [mx for _, _, mx, _ in ref_rows] == [float(s["max_score"]) for s in steps]
    return res, steps, ref_rows, section_labels(raw)


def human_grades(xlsx: Path, steps, ref_rows, ref_sections) -> tuple[dict[str, Any], tuple]:
    rows, total_cell = sheet_rows(xlsx.read_bytes())
    assert len(rows) == len(steps), (xlsx.name, len(rows))
    maxima = [mx for _, _, mx, _ in rows]
    assert abs(sum(maxima) - 100) < 1e-9, (xlsx.name, sum(maxima))
    per_step = {step["key"]: got for (_, _, _, got), step in zip(rows, steps)}
    for (_, _, mx, got), step in zip(rows, steps):
        assert 0 <= got <= mx, (xlsx.name, step["key"], got, mx)
    total = sum(per_step.values())
    assert total_cell is not None and abs(total - total_cell) < 1e-9, (xlsx.name, total, total_cell)
    maxima_current = all(abs(mx - r[2]) < 1e-9 for mx, r in zip(maxima, ref_rows))
    label_steps = [i for i, (row, ref) in enumerate(zip(rows, ref_rows), 1) if row[1] != ref[1]]
    sections = section_labels(xlsx.read_bytes())
    section_rows = sorted(r for r in set(sections) | set(ref_sections)
                          if sections.get(r) != ref_sections.get(r) and r < ref_rows[-1][0] + 1)
    human = {"steps": per_step, "total": total, "grade_points": grade(total), "passed": grade(total) >= PASS_GRADE,
             "grader": "pending", "xlsx_last_modified_by_differs": last_modified_by_differs(xlsx),
             "step_maxima": {step["key"]: mx for mx, step in zip(maxima, steps)}}
    signature = (tuple(maxima), tuple(label_steps), maxima_current, tuple(section_rows))
    return human, signature


STATE_NAMES = {(True, False): "current", (True, True): "current_maxima_older_labels",
               (False, True): "earlier_maxima", (False, False): "earlier_maxima"}


# --- case text and Musterloesung -----------------------------------------------------

TOC_ENTRY = re.compile(r"^(?:(?P<label>[A-Z]\.|[IVX]+\.|\d+\.|[a-z]{1,2}\)|\(\d+\))\s+)?(?P<title>.+?)\s+(?P<page>\d{1,3})$")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
FOOTNOTE_DEF = re.compile(r"^\s*(\d{1,3})\.\s+(.*?)\s*↑\s*$")


def _title(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_]+", "", text)).strip()


def clean_musterloesung(raw: str) -> tuple[str, dict[str, Any]]:
    lines = unescape_md(raw).replace("\xa0", " ").split("\n")
    norm = [_title(line) for line in lines]
    lh = next(i for i, t in enumerate(norm) if t == "Lösungshinweise")
    body = next(i for i in range(lh + 1, len(lines)) if re.fullmatch(r"Frage 1:?", norm[i]))
    doc_title = " ".join(t for t in norm[:lh] if t)
    toc = []
    for t in norm[lh + 1:body]:
        m = TOC_ENTRY.match(t) if t else None
        if m and _title(m.group("title")) != doc_title:
            toc.append((m.group("label"), _title(m.group("title"))))
    rest = lines[body:]
    # footnote definitions at the end
    fn_start = len(rest)
    for i in range(len(rest) - 1, -1, -1):
        if not rest[i].strip():
            continue
        if FOOTNOTE_DEF.match(rest[i]):
            fn_start = i
        else:
            break
    footnotes = [FOOTNOTE_DEF.match(line).groups() for line in rest[fn_start:] if line.strip()]
    out, pointer, labelled, headings = [], 0, 0, 0
    for line in rest[:fn_start]:
        m = HEADING.match(line)
        if not m:
            out.append(line)
            continue
        headings += 1
        title = _title(m.group(2))
        best, best_j = 0.0, None
        for j in range(pointer, min(pointer + 3, len(toc))):
            ratio = difflib.SequenceMatcher(None, title.casefold(), toc[j][1].casefold()).ratio()
            if ratio > best:
                best, best_j = ratio, j
        label = None
        if best_j is not None and best >= 0.6:
            label, pointer = toc[best_j][0], best_j + 1
            labelled += 1 if label else 0
        out.append(f"{m.group(1)} {label + ' ' if label else ''}{title}")
    text = f"{doc_title}\n\nLösungshinweise\n\n" + "\n".join(out)
    if footnotes:
        text += "\n\nFußnoten\n\n" + "\n".join(f"[{n}] {t.strip()}" for n, t in footnotes)
    text = collapse_blank_lines(text)
    refs = sorted(set(re.findall(r"\[(\d{1,3})\]", text.split("\n\nFußnoten\n\n")[0])), key=int)
    return text, {"toc_entries_dropped": len(toc) + 1, "headings": headings, "headings_labelled": labelled,
                  "footnotes": len(footnotes), "footnote_refs": len(refs),
                  "escapes_removed": len(MD_ESCAPE.findall(raw or ""))}


def clean_sachverhalt(raw: str) -> tuple[str, dict[str, Any]]:
    text = collapse_blank_lines(unescape_md(raw).replace("\xa0", " "))
    return text, {"escapes_removed": len(MD_ESCAPE.findall(raw or ""))}


def docx_text(path: Path) -> str:
    paragraphs = []
    for kind, block in _read_docx(path.read_bytes()).blocks:
        if kind != "p" or not block.text.strip():
            continue
        label = getattr(block, "auto_label", None)
        paragraphs.append(f"{label} {block.text}" if label else block.text)
    return "\n\n".join(paragraphs)


def similarity(a: str, b: str) -> float:
    ta, tb = [w.casefold() for w in words(a)], [w.casefold() for w in words(b)]
    return round(difflib.SequenceMatcher(None, ta, tb, autojunk=False).ratio(), 4)


def text_meta(raw: str, clean: str, **extra) -> dict[str, Any]:
    return {"raw_sha256": sha(raw), "raw_chars": len(raw or ""), "sha256": sha(clean), "chars": len(clean), **extra}


# --- platform texts -------------------------------------------------------------------


def clean_platform_text(text: str) -> tuple[str, dict[str, int]]:
    counts = {"br": len(re.findall(r"<br\s*/?>", text, re.IGNORECASE)), "u_tags": len(re.findall(r"</?u>", text, re.IGNORECASE)),
              "nbsp": text.count("\xa0") + text.count("&nbsp;")}
    text = re.sub(r"(?im)^[ \t]*<br\s*/?>[ \t]*$", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?u>", "", text, flags=re.IGNORECASE)
    text = text.replace("&nbsp;", " ").replace("\xa0", " ")
    return collapse_blank_lines(text), counts


def stored_scores(details, keys_in_order):
    scores = details.get("scores") or {}
    out = {}
    for key in keys_in_order:
        s = scores.get(key) or {}
        entry = {"score": s.get("score"), "max": s.get("max")}
        for extra in ("evidence_verified", "model_score"):
            if extra in s:
                entry[extra] = s[extra]
        out[key] = entry
    return out


# --- overlap -------------------------------------------------------------------------------

DUPLICATE_AT = 0.9
RELATED_AT = 0.15


def shingles(text: str, n: int = 8) -> set[tuple[str, ...]]:
    w = re.findall(r"\w+", (text or "").casefold())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def overlap(scripts: list[dict[str, Any]], case_texts: list[str]) -> list[dict[str, Any]]:
    """8-gram containment between scripts, the case text's 8-grams removed."""
    base = set().union(*(shingles(t) for t in case_texts))
    sets = {s["script_id"]: shingles(s["text"]) - base for s in scripts}
    pairs = []
    for a, b in itertools.combinations([s["script_id"] for s in scripts], 2):
        A, B = sets[a], sets[b]
        if not A or not B:
            continue
        shared = len(A & B)
        pairs.append({"a": a, "b": b, "a_in_b": round(shared / len(A), 4), "b_in_a": round(shared / len(B), 4)})
    return pairs


def mark_duplicates(scripts: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> None:
    """duplicate_of, duplicate_kind and related_to from the overlap pairs.

    A pair where either script's 8-grams sit to DUPLICATE_AT in the other is
    one text twice: the later script (pack order) is the duplicate of the
    earlier one. "near_copy" when the later one is contained in the earlier
    one; "copy_then_extend" when the earlier one is contained in the later
    one, which adds text of its own (a copy that was then extended). Pairs
    between RELATED_AT and DUPLICATE_AT are related_to each other.
    """
    order = {s["script_id"]: i for i, s in enumerate(scripts)}
    by_id = {s["script_id"]: s for s in scripts}
    for s in scripts:
        s.update(duplicate_of=None, duplicate_kind=None, exclude_reason=None, related_to=[])
    for p in sorted(pairs, key=lambda p: (order[p["a"]], order[p["b"]])):
        a, b = by_id[p["a"]], by_id[p["b"]]
        if order[p["b"]] > order[p["a"]]:
            later, earlier, later_in_earlier, earlier_in_later = b, a, p["b_in_a"], p["a_in_b"]
        else:
            later, earlier, later_in_earlier, earlier_in_later = a, b, p["a_in_b"], p["b_in_a"]
        if max(later_in_earlier, earlier_in_later) >= DUPLICATE_AT:
            if later["duplicate_of"] is None and earlier["duplicate_of"] is None:
                later["duplicate_of"] = earlier["script_id"]
                later["duplicate_kind"] = "near_copy" if later_in_earlier >= DUPLICATE_AT else "copy_then_extend"
        elif max(later_in_earlier, earlier_in_later) >= RELATED_AT:
            share = max(p["a_in_b"], p["b_in_a"])
            a["related_to"].append({"script_id": b["script_id"], "shared_8grams": share})
            b["related_to"].append({"script_id": a["script_id"], "shared_8grams": share})


def pull_files() -> list[Path]:
    """The prod pull files of the D2 project, oldest first.

    The project id prefix is local configuration (d2_pull_project in
    .pilot.local.json or PILOT_D2_PULL_PROJECT); without it the folder must
    hold pulls of exactly one project."""
    folder = RAW / "platform_2026"
    project = local_config.setting("d2_pull_project")
    if project:
        files = sorted(folder.glob(f"prod_{project}_pull_*.jsonl"))
    else:
        files = sorted(folder.glob("prod_*_pull_*.jsonl"))
        projects = {f.name.split("_pull_", 1)[0] for f in files}
        if len(projects) > 1:
            raise SystemExit(f"{folder} holds pulls of {len(projects)} projects: set d2_pull_project in "
                             ".pilot.local.json (or PILOT_D2_PULL_PROJECT)")
    if not files:
        raise SystemExit(f"no prod pull in {folder} (prod_<project>_pull_*.jsonl)")
    return files


# --- main ---------------------------------------------------------------------------------


def check_report(pii: PiiLog, scripts: list[dict[str, Any]], case_texts: dict[str, Any],
                 unlisted: list[dict[str, Any]]) -> int:
    """--check: counts, ids and hashes only; nothing is written."""
    counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for h in pii.hits:
        counts[h["category"]][h["action"]] += 1
    print("PII hits by category and action: " + json.dumps({c: dict(a) for c, a in sorted(counts.items())}))
    by_where = collections.Counter((h["script_id"], h["category"]) for h in unlisted)
    print(f"unlisted: {len(unlisted)}" + ("" if not by_where else " (" + ", ".join(
        f"{sid} {cat} x{n}" for (sid, cat), n in sorted(by_where.items())) + ")"))
    dups = [(s["script_id"], s["duplicate_of"], s.get("duplicate_kind")) for s in scripts if s.get("duplicate_of")]
    print(f"duplicates: {dups or 'none'}; related pairs: "
          f"{sum(len(s['related_to']) for s in scripts) // 2}; excluded: "
          f"{sorted((s['script_id'], s['exclude_reason']) for s in scripts if s.get('exclude_reason'))}")
    print("case texts: " + ", ".join(f"{y} sha256 {c['sha256'][:12]} ({c['chars']} chars)"
                                     for y, c in sorted(case_texts.items())))
    print("check only: nothing written")
    return 1 if unlisted else 0


def selftest() -> int:
    """The scanner and the overlap rules on synthetic lines (no pack data)."""
    failures: list[str] = []

    def check(name: str, ok: bool) -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            failures.append(name)

    vocab = {w.casefold() for w in VOCAB_WORD.findall("Die Polizei Maßnahme Rechtmäßigkeit der Verfügung Anspruch")}
    pii = PiiLog([], vocab, show=False)
    hits = {
        "two capitalised names": "Erika Mustermann",
        "all caps": "ERIKA MUSTERMANN",
        "particle von": "Anna von Beispielberg",
        "particles van den": "Jan van den Voorbeeld",
        "particle zu": "Karl zu Probenstein",
        "Surname, First": "Mustermann, Erika",
        "Surname, First with particle": "von Beispielberg, Anna",
        "diacritics": "Zoë Çelik-Dvořák",
        "apostrophe": "Siobhán O'Brien",
        "label Bearbeiter": "Bearbeiter: E. Mustermann",
        "label Name without value": "Name:",
        "label Verfasserin": "Verfasserin – Mustermann",
        "label Unterschrift": "Unterschrift: ______",
    }
    for name, line in hits.items():
        check(f"scanner flags {name}", pii.category(norm_line(line)) is not None)
    misses = {
        "a heading in the exam vocabulary": "Rechtmäßigkeit der Maßnahme",
        "a sentence": "Die Polizei hat die Verfügung erlassen und der Anspruch besteht.",
        "one name alone": "Mustermann",
        "an outline label": "A. Zulässigkeit",
        "a roman outline label with a period": "VI. Unbekanntes Merkmal",
        "a roman outline label without a period": "IX Unbekanntes Merkmal",
        "a letter outline label": "d) Unbekannter Eingriff",
        "a short all-caps abbreviation": "Materielle RMK",
        "a list of nouns": "Unbekannte, Merkmale, Beispiele",
    }
    for name, line in misses.items():
        check(f"scanner leaves {name}", pii.category(norm_line(line)) is None)
    check("scanner flags a link only where links are checked",
          pii.category("siehe https://example.org/upload") is None
          and pii.category("siehe https://example.org/upload", links=True) == "link_or_secret")
    check("scanner flags a password line in a case text", pii.category("Passwort: abc123", links=True) is not None)
    case = "Zeile eins\nProf. Dr. Beispiel\nZeile drei"
    flagged = PiiLog([], vocab, show=False)
    kept = flagged.apply("case_2025", case, examiner="flag")
    check("case texts: an examiner line is flagged, not stripped",
          kept == case and [h["category"] for h in flagged.unlisted()] == ["examiner_line"])
    stripped = PiiLog([], vocab, show=False).apply("H01", case)
    check("scripts: an examiner line is stripped", "Beispiel" not in stripped)

    base = " ".join(f"wort{i} satz{i} teil{i}" for i in range(80))
    extra = " ".join(f"neu{i} zusatz{i} mehr{i}" for i in range(60))
    other = " ".join(f"anders{i} fremd{i} text{i}" for i in range(80))
    scripts = [{"script_id": "S1", "text": base}, {"script_id": "S2", "text": base + " " + extra},
               {"script_id": "S3", "text": base}, {"script_id": "S4", "text": other}]
    mark_duplicates(scripts, overlap(scripts, []))
    by_id = {s["script_id"]: s for s in scripts}
    check("overlap: a later copy that adds text is a duplicate (copy_then_extend)",
          by_id["S2"]["duplicate_of"] == "S1" and by_id["S2"]["duplicate_kind"] == "copy_then_extend")
    check("overlap: a later identical copy is a duplicate (near_copy)",
          by_id["S3"]["duplicate_of"] == "S1" and by_id["S3"]["duplicate_kind"] == "near_copy")
    check("overlap: an unrelated script stays independent",
          by_id["S4"]["duplicate_of"] is None and not by_id["S4"]["related_to"])
    shorter = [{"script_id": "L1", "text": base + " " + extra}, {"script_id": "L2", "text": base}]
    mark_duplicates(shorter, overlap(shorter, []))
    check("overlap: a later truncated copy is a near_copy of the longer original",
          shorter[1]["duplicate_of"] == "L1" and shorter[1]["duplicate_kind"] == "near_copy")
    print(f"\nselftest: {'FAILED ' + str(len(failures)) if failures else 'all passed'}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the local D2 pack (see the module docstring).")
    parser.add_argument("--show-unlisted", action="store_true", help="print the text of unlisted PII hits (local review)")
    parser.add_argument("--list", nargs="+", metavar="ARG", help="redact|allow SHA256 CATEGORY [SCRIPT_ID]")
    parser.add_argument("--check", action="store_true",
                        help="run the scanner and the overlap check, print counts only, write nothing")
    parser.add_argument("--selftest", action="store_true", help="scanner and overlap rules on synthetic lines")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.list:
        if len(args.list) not in (3, 4):
            parser.error("--list needs redact|allow SHA256 CATEGORY [SCRIPT_ID]")
        return add_listed_line(*args.list[:3], args.list[3] if len(args.list) == 4 else None)

    key = load_key()
    martin = key["martin_user_id"].strip()
    if not args.check:
        OUT.mkdir(parents=True, exist_ok=True)
    res, steps, ref_rows, ref_sections = sheet_steps()
    keys = [s["key"] for s in steps]

    # ---- the prod pull: exam text, rubric, D2b submissions ----------------------------
    pulls = pull_files()
    rows = [json.loads(line) for line in pulls[-1].read_text().splitlines() if line.strip()]
    end = next(r for r in rows if r["kind"] == "end")
    exam = next(r for r in rows if r["kind"] == "exam")
    annotations = sorted((r for r in rows if r["kind"] == "annotation"), key=lambda r: r["created_at"])
    evaluations = [r for r in rows if r["kind"] == "evaluation"]
    assert len(annotations) == end["n_annotations"] and len(evaluations) == end["n_evaluations"]
    data = exam["data"]

    sv_raw, sv_emails = scrub(data.get("sachverhalt", ""))
    ml_raw, ml_emails = scrub(data.get("musterloesung", ""))
    sachverhalt, sv_meta = clean_sachverhalt(sv_raw)
    musterloesung, ml_meta = clean_musterloesung(ml_raw)
    bewertungsbogen_text, bb_emails = scrub(data.get("bewertungsbogen", ""))
    vocab = {w.casefold() for t in (sachverhalt, musterloesung, bewertungsbogen_text) for w in VOCAB_WORD.findall(t)}

    # ---- D2a: PDF scripts + xlsx grades (first pass: raw text) ------------------------------
    pdfs = sorted((RAW / "scripts").glob("H??.pdf"))
    raw_pages = {pdf.stem: pdf_pages(pdf) for pdf in pdfs}
    facts = {pdf.stem: pdf_facts(pdf) for pdf in pdfs}
    # repair vocabulary: exam texts plus every word of the scripts that has no candidate glyph
    platform_texts = {a["annotation_id"]: next((e["value"].get("markdown") for e in a["result"]
                                                if e.get("from_name") == "loesung" and isinstance(e.get("value"), dict)),
                                               "") or "" for a in annotations}
    repair_vocab = {w.casefold() for t in (sachverhalt, musterloesung, bewertungsbogen_text) for w in words(t)}
    for text in ["\n".join(pages) for pages in raw_pages.values()] + list(platform_texts.values()):
        for char, rep in LIGATURE_CHARS.items():
            text = text.replace(char, rep)
        repair_vocab.update(w.casefold() for w in WORD_WITH_DIGITS.findall(text) if WELL_FORMED.match(w))
    broken = {sid: detect_broken_glyphs("\n".join(pages), repair_vocab) for sid, pages in raw_pages.items()}

    pii = PiiLog(key["redact_lines"], vocab, args.show_unlisted)
    scripts, states, signatures = [], {}, {}
    ligature_report = {}
    for pdf in pdfs:
        sid = pdf.stem
        pages, running = strip_running_lines(raw_pages[sid])
        raw_text = "\n".join(pages)
        repaired, lig = repair_ligatures(raw_text, broken[sid], repair_vocab)
        ligature_report[sid] = {"broken_glyphs": {c: i["replacement"] for c, i in broken[sid].items()},
                                **{k: v for k, v in lig.items() if k != "rule_only_words"},
                                "rule_only_distinct": len(lig["rule_only_words"]),
                                "fonts": sorted({f["font"] for f in facts[sid]["fonts"]}),
                                "all_fonts_have_tounicode": all(f["tounicode"] for f in facts[sid]["fonts"])}
        years = cited_years(repaired)
        case_year, disagrees = case_year_of(facts[sid]["created_year"], years)
        text = normalise_pdf_text(repaired)
        lines = text.split("\n")
        cut = header_block(lines)
        pii.scan_only(sid, lines[:cut], "header_block")
        text = "\n".join(lines[cut:])
        text = pii.apply(sid, text)
        text, emails = scrub(text)
        text = collapse_blank_lines(text)
        human, signature = human_grades(pdf.with_suffix(".xlsx"), steps, ref_rows, ref_sections)
        signatures.setdefault(signature, []).append(sid)
        scripts.append({"script_id": sid, "cohort": "D2a", "case_year": case_year,
                        "case_year_evidence": {"pdf_created": facts[sid]["created_year"], "cited_years": years,
                                               "disagrees": disagrees},
                        "source": "pdf", "pages": facts[sid]["pages"], "chars": len(text), "text": text,
                        "human": human, "llm_prod": None, "_signature": signature,
                        "cleaning": {"header_lines_dropped": sum(1 for line in lines[:cut] if line.strip()),
                                     "running_lines_removed": running, "emails": emails,
                                     "ligatures_repaired": lig["glyph_repairs"] + lig["unicode_ligatures"]}})

    # sheet states: maxima and step labels against the current sheet
    for signature, ids in sorted(signatures.items(), key=lambda kv: kv[1][0]):
        maxima, label_steps, current, section_rows = signature
        name = STATE_NAMES[(current, bool(label_steps))]
        if name in states:
            name = f"{name}_{sum(1 for s in states if s.startswith(name)) + 1}"
        states[name] = {"step_maxima": dict(zip(keys, maxima)), "total_points": sum(maxima),
                        "label_steps_differing": list(label_steps), "section_rows_differing": list(section_rows),
                        "scripts": sorted(ids)}
        for s in scripts:
            if s.get("_signature") == signature:
                s["sheet_state"] = name
    if "current" not in states:
        states["current"] = {"step_maxima": {k: float(s["max_score"]) for k, s in zip(keys, steps)},
                             "total_points": 100.0, "label_steps_differing": [], "section_rows_differing": [],
                             "scripts": []}
    for s in scripts:
        s.pop("_signature", None)

    # ---- D2b: prod pull ------------------------------------------------------------------------
    rubric = exam["rubric"]
    prod_steps = [n for n in (rubric.get("structure") or {}).get("nodes", []) if n.get("kind") == "step"]
    prod_keys = [n["key"] for n in prod_steps]
    assert [float(n["max_score"]) for n in prod_steps] == [float(s["max_score"]) for s in steps], \
        "prod sheet differs from the xlsx"
    key_map = dict(zip(prod_keys, keys))  # prod key -> xlsx key (same order, same maxima)

    codes = {a["annotation_id"]: f"B{i:02d}" for i, a in enumerate(annotations, 1)}
    key["note"] = "LOCAL ONLY. B-code -> prod annotation/user id; PII line list. Never share."
    key["codes"] = {codes[a["annotation_id"]]: {"annotation_id": a["annotation_id"], "user_id": a["user_id"]}
                    for a in annotations}
    key["renamed_from"] = {codes[a["annotation_id"]]: f"P{i:02d}" for i, a in enumerate(annotations, 1)}
    by_annotation = collections.defaultdict(list)
    for ev in evaluations:
        by_annotation[ev["annotation_id"]].append(ev)
    platform_cleaning = {}
    for a in annotations:
        sid = codes[a["annotation_id"]]
        text, residue = clean_platform_text(platform_texts[a["annotation_id"]])
        lines = text.split("\n")
        cut = header_block(lines)
        pii.scan_only(sid, lines[:cut], "header_block")
        text = pii.apply(sid, "\n".join(lines[cut:]))
        text, emails = scrub(text)
        text = collapse_blank_lines(text)
        llm, human = None, None
        for ev in by_annotation.get(a["annotation_id"], []):
            metrics = ev["metrics"] or {}
            if "llm_judge_rubric" in metrics:
                d = metrics["llm_judge_rubric"].get("details") or {}
                llm = {"judge_model_id": ev.get("judge_model_id"), "created_at": ev["created_at"],
                       "total": d.get("total_score"), "grade_points": d.get("grade_points"),
                       "passed": d.get("passed"), "rubric_id": d.get("rubric_id"),
                       "steps": {key_map[k]: v for k, v in stored_scores(d, prod_keys).items()}}
            if "korrektur_custom" in metrics:
                d = metrics["korrektur_custom"].get("details") or {}
                per_step = {key_map[k]: (v.get("score") or 0.0) for k, v in stored_scores(d, prod_keys).items()}
                human = {"steps": per_step, "total": d.get("total_score"),
                         "grade_points": d.get("grade_points"), "passed": d.get("passed"),
                         "grader": "exam_author" if ev.get("created_by") == martin else "other",
                         "created_at": ev["created_at"]}
        platform_cleaning[sid] = residue
        scripts.append({"script_id": sid, "cohort": "D2b", "case_year": PLATFORM_YEAR,
                        "case_year_evidence": {"submitted": a["created_at"][:10]},
                        "source": "platform", "chars": len(text), "text": text, "sheet_state": "current",
                        "submitted_at": a["created_at"][:10], "human": human, "llm_prod": llm,
                        "author_account": a["user_id"] == martin,
                        "cleaning": {"header_lines_dropped": sum(1 for line in lines[:cut] if line.strip()),
                                     "emails": emails, **residue}})
    states["current"]["scripts"] = sorted(set(states["current"]["scripts"])
                                          | {s["script_id"] for s in scripts if s["cohort"] == "D2b"})

    # ---- per-year case texts (scanned like the scripts; hashed as stored) ------------------------------
    # Examiner lines, links and passwords are flagged, not stripped: a case
    # text changes only through a listed "redact" line.
    sachverhalt = collapse_blank_lines(pii.apply(f"case_{PLATFORM_YEAR}", sachverhalt, examiner="flag", links=True))
    case_texts = {PLATFORM_YEAR: {"sachverhalt": sachverhalt, "source": "platform task data (cleaned)",
                                  "sha256": sha(sachverhalt), "chars": len(sachverhalt)}}
    docx_checks = {}
    for docx in sorted((RAW / "exam").glob("Angabe_*.docx")):
        year = docx.stem.split("_", 1)[1]
        text, _ = scrub(docx_text(docx))
        if year == PLATFORM_YEAR:
            docx_checks[docx.name] = {"word_similarity_to_platform_text": similarity(text, sachverhalt)}
            continue
        text = collapse_blank_lines(pii.apply(f"case_{year}", collapse_blank_lines(text), examiner="flag", links=True))
        case_texts[year] = {"sachverhalt": text, "source": docx.name, "sha256": sha(text), "chars": len(text)}
    loesung = RAW / "exam" / "Loesung.docx"
    if loesung.exists():
        docx_checks[loesung.name] = {"word_similarity_to_musterloesung": similarity(docx_text(loesung), musterloesung)}
    for s in scripts:
        s["case_text_year_mismatch"] = s["case_year"] not in case_texts

    # ---- PII gate ---------------------------------------------------------------------------------
    unlisted = pii.unlisted()
    if unlisted:
        print(f"\nFAIL: {len(unlisted)} PII scanner hits are not listed in {KEY_FILE.name} redact_lines. "
              "Review them locally (--show-unlisted) and list each one:\n"
              "  extract_heidebach_pack.py --list redact|allow SHA256 CATEGORY SCRIPT_ID")
        if not args.check:
            return 1

    # ---- duplicates and overlap ----------------------------------------------------------------------
    pairs = overlap(scripts, [sachverhalt, musterloesung])
    mark_duplicates(scripts, pairs)
    for s in scripts:
        if s.get("author_account"):
            s["exclude_reason"] = "exam_author_test_upload"
        elif s["duplicate_of"]:
            s["exclude_reason"] = "duplicate"

    if args.check:
        return check_report(pii, scripts, case_texts, unlisted)

    # ---- write ---------------------------------------------------------------------------------------
    save_key(key)
    exam_doc = {
        "note": "D2 exam (2026 version, as graded on the platform). bewertungsbogen_text is the exam author's "
                "sheet rendered into task data: NEVER give it to a generator or a holistic judge.",
        "sachverhalt": sachverhalt,
        "musterloesung": musterloesung,
        "bewertungsbogen_text": bewertungsbogen_text,
        "texts": {"sachverhalt": text_meta(sv_raw, sachverhalt, **sv_meta),
                  "musterloesung": text_meta(ml_raw, musterloesung, **ml_meta)},
        "case_texts": case_texts,
        "docx_checks": docx_checks,
        "sheet": {"total_points": res["total_points"], "structure": res["structure"],
                  "step_keys": keys, "prod_rubric_id": rubric["id"], "states": states},
        "grade_scale": {"thresholds_be": EXAM_THRESHOLDS, "rounding": "floor", "pass_grade": PASS_GRADE},
    }
    (OUT / "heidebach_exam.json").write_text(json.dumps(exam_doc, ensure_ascii=False, indent=1))
    for s in scripts:
        s.pop("author_account", None)
    (OUT / "heidebach_scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1))

    graded = [s for s in scripts if s["human"]]
    usable = [s for s in scripts if not s["exclude_reason"]]
    report = {
        "scripts": len(scripts), "cohorts": collections.Counter(s["cohort"] for s in scripts),
        "usable": len(usable), "usable_by_cohort": collections.Counter(s["cohort"] for s in usable),
        "excluded": {s["script_id"]: {"reason": s["exclude_reason"], "duplicate_of": s["duplicate_of"],
                                      "duplicate_kind": s.get("duplicate_kind")}
                     for s in scripts if s["exclude_reason"]},
        "related": {s["script_id"]: s["related_to"] for s in scripts if s["related_to"]},
        "case_year": collections.Counter(f"{s['cohort']} {s['case_year']}" for s in scripts),
        "case_year_disagrees": [s["script_id"] for s in scripts if s["case_year_evidence"].get("disagrees")],
        "case_text_year_mismatch": collections.Counter(str(s["case_text_year_mismatch"]) for s in scripts),
        "sheet_states": {k: {"scripts": v["scripts"], "label_steps_differing": v["label_steps_differing"],
                             "section_rows_differing": v["section_rows_differing"],
                             "maxima_differ_from_current": [i for i, (a, b) in enumerate(
                                 zip(v["step_maxima"].values(), states["current"]["step_maxima"].values()), 1)
                                 if abs(a - b) > 1e-9]} for k, v in states.items()},
        "human_graded": len(graded),
        "grader": collections.Counter(s["human"]["grader"] for s in graded),
        "xlsx_last_modified_by_differs": sorted(s["script_id"] for s in scripts
                                                if (s["human"] or {}).get("xlsx_last_modified_by_differs")),
        "pii": pii.summary(),
        "pii_listed_lines": len(pii.listed), "pii_listed_lines_unused": len(set(pii.listed) - pii.used),
        "emails_scrubbed": {"sachverhalt": sv_emails, "musterloesung": ml_emails, "bewertungsbogen": bb_emails,
                            "scripts": sum(s["cleaning"]["emails"] for s in scripts)},
        "ligatures": ligature_report,
        "platform_residue": {k: v for k, v in platform_cleaning.items() if any(v.values())},
        "running_lines_removed": {s["script_id"]: s["cleaning"]["running_lines_removed"]
                                  for s in scripts if s["cleaning"].get("running_lines_removed")},
        "header_lines_dropped": {s["script_id"]: s["cleaning"]["header_lines_dropped"]
                                 for s in scripts if s["cleaning"]["header_lines_dropped"]},
        "texts": exam_doc["texts"], "docx_checks": docx_checks,
        "case_texts": {y: {k: v for k, v in c.items() if k != "sachverhalt"} for y, c in case_texts.items()},
    }
    (OUT / "heidebach_pack_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=dict))

    print(f"sheet: {len(keys)} steps / {res['total_points']} BE; states: "
          + ", ".join(f"{k} ({len(v['scripts'])})" for k, v in states.items()))
    print(f"D2a: {sum(s['cohort'] == 'D2a' for s in scripts)} scripts; D2b: "
          f"{sum(s['cohort'] == 'D2b' for s in scripts)} submissions; usable {len(usable)} "
          f"({dict(report['usable_by_cohort'])}); excluded {report['excluded']}")
    print(f"case years: {dict(report['case_year'])}; case text year mismatch: "
          f"{dict(report['case_text_year_mismatch'])}; disagreeing citations: {report['case_year_disagrees'] or 'none'}")
    print(f"human-graded {len(graded)} (grader {dict(report['grader'])}); xlsx saved by someone other than "
          f"its creator: {len(report['xlsx_last_modified_by_differs'])}")
    print(f"PII: {json.dumps(report['pii'])}")
    lig_total = sum(v["glyph_repairs"] + v["unicode_ligatures"] for v in ligature_report.values())
    per_pdf = {k: v["glyph_repairs"] + v["unicode_ligatures"] for k, v in ligature_report.items()
               if v["glyph_repairs"] or v["unicode_ligatures"]}
    print(f"ligatures repaired: {lig_total} ({per_pdf})")
    for name, meta in exam_doc["texts"].items():
        print(f"{name}: {meta['raw_chars']} -> {meta['chars']} chars, sha256 {meta['raw_sha256'][:12]} -> {meta['sha256'][:12]}")
    print(f"-> {OUT}/heidebach_exam.json, heidebach_scripts.json, heidebach_pack_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

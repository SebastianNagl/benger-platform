"""
Tests for the evidence check of the Bewertungsbogen judge
(``ml_evaluation/evidence_check.py``): is a step's quote really in the answer?

Pure and fast on purpose: the nightly mutation shard of evidence_check.py runs
this file once per mutant.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.evidence_check import (  # noqa: E402
    EvidenceIndex,
    _normalize_evidence_text,
    verify_evidence,
)

# Shaped like an uploaded answer: markdown escapes, emphasis, typographic
# quotes, blank lines. (test_llm_judge_evaluator.py builds its rubric prompts
# from the same text.)
_ANSWER = (
    "A. Zulässigkeit\n\n"
    "I\\. Eröffnung des Zivilrechtswegs\n\n"
    "Mangels abdrängender Sonderzuweisung richtet sich der Rechtsweg nach **§ 13 GVG**. "
    "Die Streitigkeit ist bürgerlich-rechtlich.\n\n"
    "1\\. Die Bestellung ist eine „Willenserklärung“ im Sinne des § 130 Abs. 1 S. 1 BGB, "
    "denn K hat gegenüber V verbindlich erklärt, das Fahrrad zu kaufen."
)


class TestEvidenceNormalization:
    def test_markdown_escapes_and_emphasis_are_removed(self):
        assert _normalize_evidence_text("1\\. **Fett** und _kursiv_") == "1. fett und kursiv"

    def test_quotes_dashes_ellipsis_and_whitespace_are_unified(self):
        assert _normalize_evidence_text("„Zitat“ – so\n\n weiter…") == '"zitat" - so weiter...'

    def test_word_bookmark_anchors_are_dropped(self):
        assert _normalize_evidence_text('<a id="_Toc1"></a>Probeklausur') == "probeklausur"


class TestVerifyEvidence:
    @pytest.mark.parametrize(
        "evidence",
        [
            # verbatim sentence
            "Mangels abdrängender Sonderzuweisung richtet sich der Rechtsweg nach § 13 GVG.",
            # the answer escapes "I\." and bolds the norm; the quote does not
            "I. Eröffnung des Zivilrechtswegs",
            "richtet sich der Rechtsweg nach § 13 GVG",
            # the quote keeps the markdown escape itself
            "1\\. Die Bestellung ist eine",
            # whitespace and line breaks differ
            "Die  Streitigkeit\nist bürgerlich-rechtlich",
            # plain quotes where the answer has typographic ones
            'eine "Willenserklärung" im Sinne des § 130 Abs. 1',
            # ellipsis-split fragments, both spellings
            "Mangels abdrängender Sonderzuweisung … Die Streitigkeit ist bürgerlich-rechtlich",
            "Die Bestellung ist eine [...] verbindlich erklärt",
            # one word left out of a long quote
            "denn K hat gegenüber V erklärt, das Fahrrad zu kaufen",
            # small inflection difference on a long word
            "Die Bestellungen ist eine Willenserklärung",
            # three tokens: a hyphenated compound, a short sentence tail
            "ist bürgerlich-rechtlich",
            "Streitigkeit ist bürgerlich-rechtlich",
            # two tokens carry enough characters (>= 15) to be a quote
            "verbindlich erklärt",
            "Streitigkeit ist",
            # two passages from different places glued without an ellipsis
            "Die Streitigkeit ist bürgerlich-rechtlich. Die Bestellung ist eine „Willenserklärung“ im Sinne des § 130 Abs. 1 S. 1 BGB",
        ],
    )
    def test_quotes_from_the_answer_verify(self, evidence):
        assert verify_evidence(evidence, EvidenceIndex(_ANSWER)) is True

    @pytest.mark.parametrize(
        "evidence",
        [
            # paraphrase
            "Der Rechtsweg bestimmt sich mangels Sonderzuweisung nach § 13 GVG",
            # content only the reference solution has
            "Eine Anfechtung ist hier irrelevant",
            # one real fragment, one invented
            "Mangels abdrängender Sonderzuweisung … Ein Rücktrittsrecht besteht nicht",
            # empty or content-free
            "",
            "   ",
            "(+)",
            "der",
            "…",
            # a single token is a keyword, not a quote (also inside a word)
            "GVG",
            "Fahr",
            "Zivilrechtswegs",
            # two short tokens are not a quote either
            "der Rechtsweg",
            "ist eine",
            "Fahrrad zu",
            # reordered words of the answer are a paraphrase
            "bürgerlich-rechtliche Streitigkeit",
            # short fragments sit on word boundaries: a cut word does not match
            "des Zivilrechtsweg",
            # one keyword fragment poisons an otherwise verbatim quote
            "Mangels abdrängender Sonderzuweisung … GVG",
            # a norm citation alone is not a quote, even when it is verbatim,
            # and neither is one with only a connecting word
            "§ 13 GVG",
            "§ 130 Abs. 1 S. 1 BGB",
            "nach § 13 GVG",
            "im Sinne des § 130 Abs. 1 S. 1 BGB",
            # glued passages: one real sentence, one invented
            "Die Streitigkeit ist bürgerlich-rechtlich. Ein Rücktrittsrecht besteht hier offensichtlich nicht.",
        ],
    )
    def test_everything_else_is_rejected(self, evidence):
        assert verify_evidence(evidence, EvidenceIndex(_ANSWER)) is False

    def test_spacing_artifacts_in_the_source_do_not_break_a_long_quote(self):
        answer = "S hat etwas erlangt, nämlich Eigentum und Besitz an den entrichte ten 10.000,– € durch Leistung."
        quote = "Eigentum und Besitz an den entrichteten 10.000,– € durch Leistung"
        assert verify_evidence(quote, EvidenceIndex(answer)) is True
        # still no match for content the answer lacks
        assert verify_evidence("Eigentum an dem gestohlenen Fahrrad des K ist übergegangen", EvidenceIndex(answer)) is False

    def test_the_thresholds_are_the_documented_ones(self):
        from ml_evaluation.evidence_check import (
            EVIDENCE_MIN_LONG_FRAGMENT_CHARS,
            EVIDENCE_MIN_TOKENS,
            EVIDENCE_MIN_WORD_CHARS,
        )

        assert (EVIDENCE_MIN_TOKENS, EVIDENCE_MIN_LONG_FRAGMENT_CHARS, EVIDENCE_MIN_WORD_CHARS) == (
            3, 15, 4
        )


def _some_run_verifies(answer, evidence):
    """Some run of three or more words of the quote verifies on its own."""
    index = EvidenceIndex(answer)
    pieces = [w.split() for w in re.split(r"(?<=[.!?:;])\s+|…", evidence)]
    return any(
        verify_evidence(" ".join(words[i:j]), index)
        for words in pieces for i in range(len(words)) for j in range(i + 3, len(words) + 1)
    )


def _some_run_stands_in_the_answer(answer, evidence):
    """Some run of three or more words of the quote stands in the answer word
    for word, so only its surroundings in the answer make the quote fail."""
    text = _normalize_evidence_text(answer)
    pieces = [w.split() for w in re.split(r"(?<=[.!?:;])\s+|…", evidence)]
    runs = (
        _normalize_evidence_text(" ".join(words[i:j])).strip(" .,;:")
        for words in pieces for i in range(len(words)) for j in range(i + 3, len(words) + 1)
    )
    return any(re.search(rf"(?<!\w){re.escape(run)}(?!\w)", text) for run in runs)


class TestVerifyEvidenceAdversarial:
    """Quotes whose positive part is in the answer but which say something the
    answer does not: a keyword riding along, a dropped or added negation, a
    flipped result mark, a changed number. All must fail."""

    REJECTED = [
        # 1. a keyword glued to a real passage, with a full stop or an ellipsis
        ("Mangels abdrängender Sonderzuweisung ist der Zivilrechtsweg nach § 13 GVG eröffnet.",
         "Mangels abdrängender Sonderzuweisung. GVG."),
        ("Mangels abdrängender Sonderzuweisung ist der Zivilrechtsweg nach § 13 GVG eröffnet.",
         "Mangels abdrängender Sonderzuweisung … GVG"),
        # 2. a short sentence from another context glued to a real one
        ("Die Klage ist zulässig. Sie ist auch begründet. Gegen den Bruder des K besteht dagegen "
         "kein Anspruch, weil er nicht Vertragspartei ist.",
         "Die Klage ist zulässig. Kein Anspruch."),
        # 3. the negation of the answer skipped
        ("Ein Schadensersatzanspruch besteht nicht, da keine Pflichtverletzung vorliegt.",
         "Ein Schadensersatzanspruch besteht, da keine Pflichtverletzung vorliegt"),
        # 4. a different number in a sentence long enough for one missed word
        ("Nach alledem steht fest, dass ein Anspruch des M gegen V auf Rückzahlung von 10 Euro besteht.",
         "… dass ein Anspruch des M gegen V auf Rückzahlung von 40 Euro besteht"),
        # 5. a number cut short
        ("Der Anspruch auf Rückzahlung von 10 Euro besteht.", "Der Anspruch auf Rückzahlung von 1"),
        ("Der Anspruch auf Rückzahlung von 10.000 Euro besteht.", "Der Anspruch auf Rückzahlung von 10"),
        ("Der Anspruch auf Rückzahlung von 10.000 Euro besteht.", "Anspruch auf Rückzahlung von 10 Euro"),
        # 6. a negation added to a stitched quote, short and long
        ("Der Mangel ist erheblich, weil die Nutzung der Sache eingeschränkt ist. Im Übrigen gilt: "
         "Die Frist ist abgelaufen.",
         "Der Mangel ist nicht erheblich. Die Frist ist abgelaufen."),
        ("Der Mangel ist erheblich, weil die Nutzung der Sache eingeschränkt ist. Im Übrigen gilt: "
         "Die Frist ist abgelaufen.",
         "Der Mangel ist nicht erheblich, weil die Nutzung der Sache eingeschränkt ist. Die Frist ist abgelaufen."),
        # 8. a single keyword riding along
        ("Der Beklagte ist als Besitzer verantwortlich, weil er die Sache selbst beschädigt hat. "
         "Die Frist ist abgelaufen.",
         "Besitzer. Die Frist ist abgelaufen."),
        # 10. a four-digit number that is a prefix of the answer's number
        ("Der Kaufpreis beträgt 10000 Euro und ist sofort fällig.",
         "Der Kaufpreis beträgt 1000 Euro und ist sofort fällig"),
        ("Der Kaufpreis beträgt 10000 Euro und ist sofort fällig.", "Der Kaufpreis beträgt 1000"),
    ]

    # The quoted words stand in the answer, but a negation, "(-)" or "kein"
    # governs the whole clause they stand in.
    REJECTED_IN_CONTEXT = [
        # 7. the negation of the answer skipped inside a norm citation
        ("Der Anspruch ist nicht nach § 327m Abs. 2 S. 1 BGB ausgeschlossen.",
         "Der Anspruch ist nach § 327m Abs. 2 S. 1 BGB ausgeschlossen"),
        # 9. the result mark flipped, in either spelling of the minus
        ("Voraussetzung einer abdrängenden Sonderzuweisung (-). Der Zivilrechtsweg ist eröffnet.",
         "Voraussetzung einer abdrängenden Sonderzuweisung (+)"),
        ("Voraussetzung einer abdrängenden Sonderzuweisung (−). Der Zivilrechtsweg ist eröffnet.",
         "Voraussetzung einer abdrängenden Sonderzuweisung (+)"),
        # "Ein" inside "Kein", as a substring and with the first word skipped
        ("Kein Anspruch auf Schadensersatz besteht gegen den Verkäufer.",
         "Ein Anspruch auf Schadensersatz besteht gegen den Verkäufer"),
        ("Kein Anspruch auf Schadensersatz aus § 280 Abs. 1 BGB besteht gegen den Verkäufer.",
         "Ein Anspruch auf Schadensersatz aus § 280 Abs. 1 BGB besteht gegen den Verkäufer"),
        # a negation dropped at the very end of a long quote
        ("Der Mangel ist nach den Feststellungen des Gutachters im Ergebnis nicht erheblich.",
         "Der Mangel ist nach den Feststellungen des Gutachters im Ergebnis erheblich"),
    ]

    ACCEPTED = [
        # two real sentences from different places, glued
        ("Die Klage ist zulässig. Sie ist auch begründet. Die Frist ist abgelaufen.",
         "Die Klage ist zulässig. Die Frist ist abgelaufen."),
        # a norm citation with abbreviations, verbatim and glued to another sentence
        ("Der Anspruch ist nach § 327m Abs. 2 S. 1 BGB ausgeschlossen.",
         "Der Anspruch ist nach § 327m Abs. 2 S. 1 BGB ausgeschlossen"),
        ("Die Frist ist abgelaufen. Im Übrigen gilt Folgendes. Der Anspruch ist nach § 327m Abs. 2 S. 1 BGB "
         "ausgeschlossen.",
         "Die Frist ist abgelaufen. Der Anspruch ist nach § 327m Abs. 2 S. 1 BGB ausgeschlossen."),
        # hyphenation splits in the source (compact path)
        ("Die Nacherfüllung ist fehlge schlagen, weil der Verkäufer zweimal erfolglos nachge bessert hat.",
         "Die Nacherfüllung ist fehlgeschlagen, weil der Verkäufer zweimal erfolglos nachgebessert hat"),
        # negations and marks that are in the answer
        ("Ein Schadensersatzanspruch besteht nicht, da keine Pflichtverletzung vorliegt.",
         "Ein Schadensersatzanspruch besteht nicht, da keine Pflichtverletzung vorliegt"),
        ("Voraussetzung einer abdrängenden Sonderzuweisung (-). Der Zivilrechtsweg ist eröffnet.",
         "Voraussetzung einer abdrängenden Sonderzuweisung (−)"),
        ("Die Zulässigkeit (+). Die Begründetheit (+).", "Die Zulässigkeit (+)"),
        # a number that matches exactly, also before a full stop
        ("Der Anspruch auf Rückzahlung von 10.000 Euro besteht.", "Anspruch auf Rückzahlung von 10.000 Euro"),
        ("M verlangt Rückzahlung von 10. Das ist berechtigt.", "M verlangt Rückzahlung von 10"),
        # a quote that leaves out a word the answer has, next to no negation
        ("Der Anspruch des M gegen V auf Rückzahlung der Anzahlung besteht in voller Höhe.",
         "Der Anspruch des M gegen V auf Rückzahlung der Anzahlung besteht in Höhe"),
    ]

    @pytest.mark.parametrize("answer,evidence", REJECTED + REJECTED_IN_CONTEXT)
    def test_rejected(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is False

    @pytest.mark.parametrize("answer,evidence", REJECTED)
    def test_the_positive_part_is_in_the_answer(self, answer, evidence):
        # Each case is a real near miss: some run of three or more of its words verifies.
        assert _some_run_verifies(answer, evidence), evidence

    @pytest.mark.parametrize("answer,evidence", REJECTED_IN_CONTEXT)
    def test_the_quoted_words_stand_in_the_answer(self, answer, evidence):
        # Only the governing negation or mark around them makes these fail.
        assert _some_run_stands_in_the_answer(answer, evidence), evidence

    @pytest.mark.parametrize("answer,evidence", ACCEPTED)
    def test_accepted(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is True

    def test_token_rules(self):
        from ml_evaluation.evidence_check import _tokens_match

        assert not _tokens_match("1000", "10000")
        assert not _tokens_match("nicht", "nichtig")
        assert _tokens_match("kein", "keine") and _tokens_match("rechtsweg", "rechtswegs")
        assert _normalize_evidence_text("Sonderzuweisung (+), Rechtsweg ( − )") == (
            "sonderzuweisung positiv , rechtsweg negativ")


class TestVerifyEvidenceStrict:
    """Review round 3 (all synthetic): word boundaries, protected result and
    qualifier words, Roman numerals and numbers at the end of a quote, the
    edges of every fragment, norm-only quotes and typos."""

    REJECTED = [
        # a match must start on a word boundary: substring and compact paths
        ("Die Klage ist unzulässig, weil die Klagefrist bereits abgelaufen ist.",
         "zulässig, weil die Klagefrist bereits abgelaufen ist"),
        ("B hat als Nichtberechtigter über das Fahrrad verfügt, weil ihm das Eigentum fehlte.",
         "Berechtigter über das Fahrrad verfügt"),
        ("B ist nach dem Sachverhalt Nichtberechtigter im Sinne des Bürgerlichen Gesetz buchs.",
         "Berechtigter im Sinne des Bürgerlichen Gesetzbuchs"),
        # a result or antonym word swapped for another word
        ("Die Wegnahme war rechtswidrig, weil der Täter auf die Sache keinen fälligen Anspruch hatte.",
         "Die Wegnahme war rechtmäßig, weil der Täter auf die Sache keinen fälligen Anspruch hatte"),
        ("Das Gericht hat die Frage nach dem Vertragsschluss im Ergebnis verneint und die Klage abgewiesen.",
         "Das Gericht hat die Frage nach dem Vertragsschluss im Ergebnis bejaht und die Klage abgewiesen"),
        ("Nach alledem ist die Klage des K gegen den Verkäufer zulässig und begründet.",
         "Nach alledem ist die Klage des K gegen den Verkäufer unzulässig und begründet"),
        ("Eine Fristsetzung war nach den Umständen des Falles entbehrlich, weil der Verkäufer jede Leistung verweigerte.",
         "Eine Fristsetzung war nach den Umständen des Falles erforderlich, weil der Verkäufer jede Leistung verweigerte"),
        ("Ein Anspruch auf Schadensersatz fehlt nach alledem in dieser Konstellation.",
         "Ein Anspruch auf Schadensersatz besteht nach alledem in dieser Konstellation"),
        ("Ein gegenwärtiger Angriff auf den Körper des A ist hier gegeben, weil der Schlag unmittelbar bevorsteht.",
         "Ein gegenwärtiger Angriff auf den Körper des A ist hier entfallen, weil der Schlag unmittelbar bevorsteht"),
        ("Im Zeitpunkt der Brandlegung war niemand in dem Wohnhaus anwesend und gefährdet.",
         "Im Zeitpunkt der Brandlegung war jemand in dem Wohnhaus anwesend und gefährdet"),
        ("Das Urteil ist formell rechtskräftig geworden, weil die Berufungsfrist abgelaufen ist.",
         "Das Urteil ist materiell rechtskräftig geworden, weil die Berufungsfrist abgelaufen ist"),
        # a qualifier of the answer stepped over
        ("Der Anspruch besteht nur teilweise in Höhe der Anzahlung von 500 Euro.",
         "Der Anspruch besteht in Höhe der Anzahlung von 500 Euro"),
        ("Eine Täuschung des Käufers durch den Verkäufer ist allenfalls entfernt denkbar und reicht nicht aus.",
         "Eine Täuschung des Käufers durch den Verkäufer ist entfernt denkbar"),
        ("Der Angegriffene muss stets das mildeste gleich geeignete Mittel wählen.",
         "Der Angegriffene muss das mildeste gleich geeignete Mittel wählen"),
        # a Roman numeral swapped, a number of the answer stepped over
        ("Der Anspruch ergibt sich aus § 823 II BGB, weil der Beklagte ein Schutzgesetz verletzt hat.",
         "Der Anspruch ergibt sich aus § 823 I BGB, weil der Beklagte ein Schutzgesetz verletzt hat"),
        ("Der Anspruch folgt aus § 280 Abs. 1 und 3, § 281 BGB und besteht in voller Höhe.",
         "Der Anspruch folgt aus § 280 Abs. 1, § 281 BGB und besteht in voller Höhe"),
        # a quote ending in a number or numeral continues in the answer
        ("Die Pflicht richtet sich nach § 312a BGB und gilt für Verbraucherverträge.", "Die Pflicht richtet sich nach § 312"),
        ("Der Schutz ergibt sich aus § 823 II BGB.", "Der Schutz ergibt sich aus § 823 I"),
        ("Der Vertrag ist nichtig, weil er gegen ein gesetzliches Verbot verstößt.", "Der Vertrag ist nicht"),
        # a negation right before the match
        ("Der Vermieter hat nicht rechtmäßig gehandelt, als er die Wohnung räumen ließ.",
         "rechtmäßig gehandelt, als er die Wohnung räumen ließ"),
        # a negation or a condition right after the match
        ("Der Anspruch des Klägers auf Herausgabe des Fahrzeugs besteht nicht.",
         "Der Anspruch des Klägers auf Herausgabe des Fahrzeugs besteht"),
        # the edge rules hold on each side of an ellipsis
        ("Die Klage ist zulässig. Der Anspruch auf Herausgabe besteht nicht.",
         "Die Klage ist zulässig … Der Anspruch auf Herausgabe besteht"),
        # a one-letter change that turns a word into a negation
        ("Der Schuldner hat seine Pflicht aus dem Vertrag schuldhaft verletzt.",
         "Der Schuldner hat keine Pflicht aus dem Vertrag schuldhaft verletzt"),
    ]

    # The quoted words stand in the answer, but a question, condition,
    # "kein" or "(-)" governs the whole clause they stand in.
    REJECTED_IN_CONTEXT = [
        ("Es besteht kein Anspruch auf Rückzahlung der Kaution gegen den Vermieter.",
         "Anspruch auf Rückzahlung der Kaution gegen den Vermieter"),
        ("Voraussetzung einer abdrängenden Sonderzuweisung (-)",
         "Voraussetzung einer abdrängenden Sonderzuweisung"),
    ]

    NORM_ONLY = [
        ("Der Anspruch des K folgt aus § 433 II BGB und ist fällig.", "§ 433 II BGB"),
        ("Das Eigentum ist durch Art. 14 Abs. 1 GG geschützt.", "Art. 14 Abs. 1 GG"),
        ("Der Anspruch folgt aus §§ 280 Abs. 1, 3, 281 BGB i.V.m. Art. 229 § 5 EGBGB.",
         "§§ 280 Abs. 1, 3, 281 BGB i.V.m. Art. 229 § 5 EGBGB"),
        ("Der Anspruch des K folgt aus § 433 II BGB und ist fällig.", "Der Anspruch des K … § 433 II BGB"),
        ("Der Anspruch folgt aus § 433 II BGB. Er ist fällig. Die Frist ist gewahrt.",
         "§ 433 II BGB. Die Frist ist gewahrt."),
    ]

    ACCEPTED = [
        # the negation stands in another clause or sentence
        ("Die Mahnung erfolgte nicht; der Verzug ist dennoch eingetreten.",
         "der Verzug ist dennoch eingetreten"),
        ("Die Klage ist zulässig. Nicht zu prüfen ist die Begründetheit.", "Die Klage ist zulässig"),
        ("Die Klage ist begründet. Wenn überhaupt, fehlt es an der Frist.", "Die Klage ist begründet"),
        # a result mark belongs to the text before it
        ("Zulässigkeit (+) Die Klage ist auch begründet.", "Die Klage ist auch begründet"),
        # protected words that are in the answer
        ("Die Klage ist unzulässig, weil die Klagefrist bereits abgelaufen ist.",
         "Die Klage ist unzulässig, weil die Klagefrist bereits abgelaufen ist"),
        ("Der Anspruch besteht nur teilweise in Höhe der Anzahlung von 500 Euro.",
         "Der Anspruch besteht nur teilweise in Höhe der Anzahlung"),
        # a norm with text around it, a numeral at the end of the quote
        ("Der Anspruch des K folgt aus § 433 II BGB und ist fällig.", "aus § 433 II BGB und ist fällig"),
        ("Der Schutz ergibt sich aus § 823 I BGB.", "Der Schutz ergibt sich aus § 823 I"),
        # a typo in the answer the judge corrected, and one of the judge
        ("Die Verteidigung war nciht geboten, weil ein milderes Mittel zur Verfügung stand.",
         "Die Verteidigung war nicht geboten, weil ein milderes Mittel zur Verfügung stand"),
        ("Der Beklagte hat die Verkehrssicherungspflicht verlezt, weil er nicht gestreut hat.",
         "Der Beklagte hat die Verkehrssicherungspflicht verletzt, weil er nicht gestreut hat"),
        ("Der Beklagte hat die Verkehrssicherungspflicht verletzt, weil er nicht gestreut hat.",
         "Der Beklagte hat die Verkehrssicherungsplicht verletzt, weil er nicht gestreut hat"),
        # layout the quote leaves out or copies literally
        ("Die Frist ist gewahrt.\n\nIX. Rechtsschutzbedürfnis\n\nDas Rechtsschutzbedürfnis besteht.",
         "Die Frist ist gewahrt.\\n\\nIX. Rechtsschutzbedürfnis\\n\\nDas Rechtsschutzbedürfnis besteht."),
        ("Der Kaufvertrag ist wirksam[4] geschlossen worden, weil beide Parteien zustimmten.",
         "Der Kaufvertrag ist wirksam geschlossen worden, weil beide Parteien zustimmten"),
        ("Nach alledem gilt: Die Frist\\\nist gewahrt.", "Frist ist gewahrt"),
    ]

    @pytest.mark.parametrize("answer,evidence", REJECTED + REJECTED_IN_CONTEXT + NORM_ONLY)
    def test_rejected(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is False

    @pytest.mark.parametrize("answer,evidence", REJECTED)
    def test_the_positive_part_is_in_the_answer(self, answer, evidence):
        # Each case is a real near miss: some run of three or more of its words verifies.
        assert _some_run_verifies(answer, evidence), evidence

    @pytest.mark.parametrize("answer,evidence", REJECTED_IN_CONTEXT)
    def test_the_quoted_words_stand_in_the_answer(self, answer, evidence):
        assert _some_run_stands_in_the_answer(answer, evidence), evidence

    @pytest.mark.parametrize("answer,evidence", ACCEPTED)
    def test_accepted(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is True

    def test_token_rules(self):
        from ml_evaluation.evidence_check import _is_protected, _tokens_match

        for word in ("unzulässig", "unbegründet", "unstreitig", "rechtmässig", "rechtswidrige", "bejahte",
                     "verneint", "erforderlich", "entbehrlich", "gegeben", "fehlt", "besteht", "niemand",
                     "jemand", "stets", "nur", "teilweise", "formell", "materiellen", "kaum", "allenfalls",
                     "insoweit", "ii", "xx", "80a", "keineswegs", "negativ"):
            assert _is_protected(word), word
        for word in ("unter", "und", "unsere", "gegebenenfalls", "zulässig", "begründet", "xxi", "klage"):
            assert not _is_protected(word), word
        assert not _tokens_match("zulässig", "unzulässig")
        assert not _tokens_match("rechtmässig", "rechtswidrig")
        assert not _tokens_match("i", "ii") and not _tokens_match("80", "80a")
        assert not _tokens_match("keine", "seine") and not _tokens_match("nicht", "licht")
        assert _tokens_match("nicht", "nciht") and _tokens_match("nciht", "nicht")
        assert _tokens_match("verletzt", "verlezt") and _tokens_match("dieses", "dieser")
        assert _tokens_match("bejaht", "bejahte") and _tokens_match("formell", "formelle")
        assert not _tokens_match("ist", "iss")  # short words need an exact match

    def test_law_abbreviations_keep_their_case(self):
        from ml_evaluation.evidence_check import _fragment_is_quotable

        assert not _fragment_is_quotable(["art", "8", "gg"], ["Art", "8", "GG"])
        assert not _fragment_is_quotable(["40", "i", "1", "vwgo"], ["40", "I", "1", "VwGO"])
        # a word that only connects the citation does not make it a quote
        assert not _fragment_is_quotable(["nach", "40", "vwgo"], ["nach", "40", "VwGO"])
        assert _fragment_is_quotable(["nach", "40", "vwgo", "eröffnet"], ["nach", "40", "VwGO", "eröffnet"])
        # without the cased tokens the abbreviation reads as a word (lenient)
        assert _fragment_is_quotable(["40", "i", "1", "vwgo"])


class TestVerifyEvidenceRound4:
    """Review round 4 (all synthetic). Each REJECTED case verified before this
    round: abbreviation periods split glued quotes, long quotes swapped or
    moved a decisive word, typos crossed antonyms, a split "un-" fell off,
    numbers merged in the compact path, the edge rules missed negations
    after the match and governing words earlier in the clause, and a
    citation with a connecting word counted as a quote."""

    REJECTED = [
        # 1. a period after an abbreviation is no sentence end: the quote stays
        #    one piece and must stand in the answer as a whole
        ("Der Käufer ist gem. § 437 Nr. 2 BGB nicht zum Rücktritt berechtigt, weil er keine Frist gesetzt hat. "
         "Die Verkäuferin ist nach § 437 Nr. 2 BGB zum Rücktritt berechtigt.",
         "Der Käufer ist gem. § 437 Nr. 2 BGB zum Rücktritt berechtigt"),
        ("Die Frist beginnt nach § 199 Abs. 1 BGB nicht vor Kenntnis des Gläubigers. "
         "Sie endet gem. § 188 Abs. 1 BGB mit dem Schluss des Jahres.",
         "Die Frist beginnt nach § 199 Abs. 1 BGB mit dem Schluss des Jahres"),
        ("Der Anspruch ist nach § 275 Abs. 1 S. 1 BGB nicht ausgeschlossen. "
         "Die Leistung ist nach § 275 Abs. 2 S. 1 BGB ausgeschlossen.",
         "Der Anspruch ist nach § 275 Abs. 1 S. 1 BGB ausgeschlossen"),
        # 2. a word swapped for another one, or a negation moved, in a long quote
        ("Nach alledem hat B hier als Nichtberechtigter über das Fahrrad des K wirksam zugunsten des C verfügt.",
         "Nach alledem hat B hier als Berechtigter über das Fahrrad des K wirksam zugunsten des C verfügt"),
        ("Der Täter handelte nach den Feststellungen des Gerichts bei der Tat mit Blick auf den Erfolg "
         "vorsätzlich und schuldhaft.",
         "Der Täter handelte nach den Feststellungen des Gerichts bei der Tat mit Blick auf den Erfolg "
         "fahrlässig und schuldhaft"),
        ("Der Käufer verlangte nach Ablauf der gesetzten Frist von dem Verkäufer die Minderung des gezahlten "
         "Kaufpreises.",
         "Der Käufer verlangte nach Ablauf der gesetzten Frist von dem Verkäufer die Erstattung des gezahlten "
         "Kaufpreises"),
        ("Nach alledem ist die Klage des K gegen den Verkäufer zwar zulässig, aber nicht begründet und daher "
         "abzuweisen.",
         "Nach alledem ist die Klage des K gegen den Verkäufer zwar nicht zulässig, aber begründet und daher "
         "abzuweisen"),
        # ... and a content word the answer does not have
        ("Der Käufer hat dem Verkäufer nach Übergabe der Sache eine angemessene Frist zur Nacherfüllung gesetzt.",
         "Der Käufer hat dem Verkäufer nach Übergabe der mangelhaften Sache eine angemessene Frist zur "
         "Nacherfüllung gesetzt"),
        # 3. a "typo" that is another word: first letter, umlaut
        ("Der zwischen den Parteien geschlossene Vertrag ist nichtig.",
         "Der zwischen den Parteien geschlossene Vertrag ist richtig"),
        ("Der Verkäufer hätte die Sache vor der Übergabe an den Käufer prüfen müssen.",
         "Der Verkäufer hatte die Sache vor der Übergabe an den Käufer prüfen müssen"),
        ("Der Mieter würde die Wohnung zum Ende des Monats räumen.",
         "Der Mieter wurde die Wohnung zum Ende des Monats räumen"),
        # 4. a split "un-" belongs to its word
        ("Die Klage ist un- zulässig, weil die Einspruchsfrist abgelaufen ist.",
         "Die Klage ist zulässig, weil die Einspruchsfrist abgelaufen ist"),
        ("Die Klage ist un-\nzulässig, weil die Einspruchsfrist abgelaufen ist.",
         "Die Klage ist zulässig, weil die Einspruchsfrist abgelaufen ist"),
        ("Die Klage ist un zulässig, weil die Einspruchsfrist abgelaufen ist.",
         "Die Klage ist zulässig, weil die Einspruchsfrist abgelaufen ist"),
        ("Die Klage ist un- zulässig. Die Frist ist abgelaufen.", "Die Klage ist zulässig"),
        # 5. numbers never merge in the spacing-insensitive comparison
        ("Der Zinssatz des Darlehens beträgt 10,5 Prozent pro Jahr und ist fest vereinbart.",
         "Der Zinssatz des Darlehens beträgt 105 Prozent pro Jahr und ist fest vereinbart"),
        ("Der Zinssatz des Darlehens beträgt 10 5 Prozent pro Jahr und ist fest vereinbart.",
         "Der Zinssatz des Darlehens beträgt 105 Prozent pro Jahr und ist fest vereinbart"),
        ("Der Anspruch ergibt sich aus §§ 1, 2 des Vertrages zwischen den beiden Parteien.",
         "Der Anspruch ergibt sich aus § 12 des Vertrages zwischen den beiden Parteien"),
        # 6. every negation right after the match, and one later in its clause
        ("Einen Anspruch auf Schadensersatz statt der Leistung hat der Käufer keinen.",
         "Einen Anspruch auf Schadensersatz statt der Leistung hat der Käufer"),
        ("Eine Pflicht zur Nacherfüllung hat der Verkäufer keine.", "Eine Pflicht zur Nacherfüllung hat der Verkäufer"),
        ("Einer Fristsetzung durch den Käufer bedurfte es keiner.", "Einer Fristsetzung durch den Käufer bedurfte es"),
        ("Für den Mangel der Sache kann der Verkäufer nichts.", "Für den Mangel der Sache kann der Verkäufer"),
        ("Der Käufer trat vom Vertrag zurück ohne Grund.", "Der Käufer trat vom Vertrag zurück"),
        ("Der Verkäufer hat die Sache geliefert weder rechtzeitig noch vollständig.",
         "Der Verkäufer hat die Sache geliefert"),
        ("Ein Anspruch des Käufers auf Rückzahlung des Kaufpreises besteht daher im Ergebnis nicht.",
         "Ein Anspruch des Käufers auf Rückzahlung des Kaufpreises besteht"),
        ("Der Käufer zahlte den vereinbarten Kaufpreis bis heute nicht.", "Der Käufer zahlte den vereinbarten Kaufpreis"),
        # 7. a negation, question or doubt word earlier in the clause, or in the
        #    clause that governs a "dass" clause
        ("Es ist nicht ersichtlich, dass der Verkäufer die Sache mangelfrei geliefert hat.",
         "der Verkäufer die Sache mangelfrei geliefert hat"),
        ("Es ist nicht ersichtlich, dass der Verkäufer die Sache mangelfrei geliefert hat.",
         "dass der Verkäufer die Sache mangelfrei geliefert hat"),
        ("Es besteht kein fälliger Anspruch des Verkäufers auf Zahlung des Kaufpreises.",
         "Anspruch des Verkäufers auf Zahlung des Kaufpreises"),
        ("Der Käufer ist nicht gem. § 437 Nr. 2 BGB zum Rücktritt berechtigt.",
         "§ 437 Nr. 2 BGB zum Rücktritt berechtigt"),
        # 8. a citation with only connecting words is no quote
        ("Der Anspruch folgt gem. § 433 Abs. 2 BGB und ist fällig.", "gem. § 433 Abs. 2 BGB"),
        ("Der Anspruch folgt nach § 433 Abs. 2 BGB und ist fällig.", "nach § 433 Abs. 2 BGB"),
        ("Der Anspruch folgt aus § 280 Abs. 1 BGB i.V.m. § 241 Abs. 2 BGB.",
         "aus § 280 Abs. 1 BGB i.V.m. § 241 Abs. 2 BGB"),
        ("Der Anspruch folgt gemäß § 280 Abs. 1 BGB i. V. m. § 241 Abs. 2 BGB.",
         "gemäß § 280 Abs. 1 BGB i. V. m. § 241 Abs. 2 BGB"),
        ("Die Sache ist ein Gegenstand im Sinne des § 90 BGB.", "im Sinne des § 90 BGB"),
    ]

    # Genuine quotes with harmless variation keep verifying.
    ACCEPTED = [
        # glued passages at real sentence ends, also with abbreviations inside
        ("Die Klage ist zulässig. Sie ist auch begründet. Die Frist ist abgelaufen.",
         "Die Klage ist zulässig. Die Frist ist abgelaufen."),
        ("Die Klage ist zulässig. Der Anspruch folgt aus § 433 Abs. 2 BGB. Die Frist ist abgelaufen.",
         "Die Klage ist zulässig. Der Anspruch folgt aus § 433 Abs. 2 BGB."),
        ("Der Käufer ist gem. § 437 Nr. 2 BGB zum Rücktritt berechtigt, weil die Frist abgelaufen ist.",
         "Der Käufer ist gem. § 437 Nr. 2 BGB zum Rücktritt berechtigt"),
        ("Der Vertrag wurde am 10. Mai 2020 geschlossen und ist wirksam.",
         "Der Vertrag wurde am 10. Mai 2020 geschlossen"),
        ("Ein Mangel liegt vor. Der Käufer hat gezahlt.\n\nb) Rücktrittserklärung\n\nK hat den Rücktritt erklärt.",
         "Ein Mangel liegt vor. b) Rücktrittserklärung"),
        # hyphenation, a ligature, spacing inside numbers, thousands dots
        ("Die Nacherfüllung ist fehl-\ngeschlagen, weil der Verkäufer zweimal erfolglos nachgebessert hat.",
         "Die Nacherfüllung ist fehlgeschlagen, weil der Verkäufer zweimal erfolglos nachgebessert hat"),
        ("Der Käufer hat die Pﬂicht zur Abnahme der Sache verletzt.",
         "Der Käufer hat die Pflicht zur Abnahme der Sache verletzt"),
        ("S hat etwas erlangt, nämlich Eigentum und Besitz an den entrichte ten 10.000,– € durch Leistung.",
         "Eigentum und Besitz an den entrichteten 10.000,– € durch Leistung"),
        ("Der Kaufpreis von 10.000 Euro ist nach Übergabe der Sache sofort fällig.",
         "Der Kaufpreis von 10000 Euro ist nach Übergabe der Sache sofort fällig"),
        # a split "un-" on either side
        ("Die Klage ist un- zulässig, weil die Einspruchsfrist abgelaufen ist.",
         "Die Klage ist unzulässig, weil die Einspruchsfrist abgelaufen ist"),
        ("Die Klage ist unzulässig, weil die Einspruchsfrist abgelaufen ist.",
         "Die Klage ist un- zulässig, weil die Einspruchsfrist abgelaufen ist"),
        # a typo in a word that is not protected, on either side
        ("Der Beklagte hat die Verkehrssicherungspflicht verlezt, weil er nicht gestreut hat.",
         "Der Beklagte hat die Verkehrssicherungspflicht verletzt, weil er nicht gestreut hat"),
        # a word left out, a function word added or left out
        ("Der Anspruch des M gegen V auf Rückzahlung der Anzahlung besteht in voller Höhe.",
         "Der Anspruch des M gegen V auf Rückzahlung der Anzahlung besteht in Höhe"),
        ("Der Käufer hat dem Verkäufer nach der Übergabe eine angemessene Frist zur Nacherfüllung gesetzt.",
         "Der Käufer hat dem Verkäufer nach Übergabe eine angemessene Frist zur Nacherfüllung gesetzt"),
        ("Der Käufer hat dem Verkäufer nach Übergabe eine angemessene Frist zur Nacherfüllung gesetzt.",
         "Der Käufer hat dem Verkäufer nach der Übergabe eine angemessene Frist zur Nacherfüllung gesetzt"),
        # the negation belongs to the verb after the quoted noun phrase, to a
        # heading above the paragraph, or affirms ("ohne Weiteres")
        ("Der Anspruch des Klägers auf Herausgabe des Fahrzeugs besteht nicht.",
         "Der Anspruch des Klägers auf Herausgabe des Fahrzeugs"),
        ("II. Keine Einwilligung\n\nDie Körperverletzung ist rechtswidrig, weil keine Einwilligung vorliegt.",
         "Die Körperverletzung ist rechtswidrig"),
        ("I. Anspruch aus § 985 BGB\n\nDer Anspruch scheitert, weil K nicht Eigentümer ist.",
         "Anspruch aus § 985 BGB"),
        ("Der Anspruch des Käufers besteht ohne Weiteres.", "Der Anspruch des Käufers besteht"),
        # a quote ending with "weil" stops where the new clause starts
        ("Eine Strafbarkeit wegen Mordes scheidet aus, weil kein Mordmerkmal erfüllt ist.",
         "Eine Strafbarkeit wegen Mordes scheidet aus, weil"),
        ("Insbesondere liegt kein Notwehrexzess nach § 33 StGB vor, da T nicht aus Furcht handelte.",
         "Insbesondere liegt kein Notwehrexzess nach § 33 StGB vor, da"),
        # a "dass" clause under an affirming clause, a quote that keeps its "ob"
        ("Es ist unstreitig, dass der Verkäufer die Sache mangelfrei geliefert hat.",
         "der Verkäufer die Sache mangelfrei geliefert hat"),
        ("Fraglich ist, ob der Verkäufer die Sache mangelfrei geliefert hat.",
         "ob der Verkäufer die Sache mangelfrei geliefert hat"),
        # a citation with reasoning around it
        ("Der Anspruch des K folgt aus § 433 II BGB und ist fällig.", "aus § 433 II BGB und ist fällig"),
    ]

    @pytest.mark.parametrize("answer,evidence", REJECTED)
    def test_rejected(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is False

    @pytest.mark.parametrize("answer,evidence", REJECTED)
    def test_the_quoted_words_stand_in_the_answer(self, answer, evidence):
        assert _some_run_stands_in_the_answer(answer, evidence), evidence

    @pytest.mark.parametrize("answer,evidence", ACCEPTED)
    def test_accepted(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is True

    def test_sentences_never_end_at_an_abbreviation(self):
        from ml_evaluation.evidence_check import _split_sentences

        assert _split_sentences("Der Käufer ist gem. § 437 Nr. 2 BGB zum Rücktritt berechtigt.") == [
            "Der Käufer ist gem. § 437 Nr. 2 BGB zum Rücktritt berechtigt."
        ]
        for text in (
            "Der Anspruch folgt aus § 280 Abs. 1 S. 1 i.V.m. § 241 Abs. 2 BGB.",
            "Das gilt vgl. BGH NJW 2020, 1 und z. B. für Kaufverträge.",
            "Der Vertrag wurde am 10. Mai 2020 geschlossen.",
            "So auch entspr. der Regel des § 133 BGB.",
            "Das folgt aus Art. 14 II. Der Eigentümer ist geschützt.",
        ):
            assert len(_split_sentences(text)) == 1, text
        assert _split_sentences("Die Klage ist zulässig. Sie ist begründet: Die Frist ist gewahrt.") == [
            "Die Klage ist zulässig.", "Sie ist begründet:", "Die Frist ist gewahrt."
        ]
        # a list label after a real sentence end starts a new piece
        assert _split_sentences("Ein Mangel liegt vor. b) Rücktritt") == ["Ein Mangel liegt vor.", "b) Rücktritt"]

    def test_token_rules(self):
        from ml_evaluation.evidence_check import _is_protected, _tokens_match

        for word in ("nichtig", "nichtberechtigter", "un", "wirksam", "richtig", "falsche", "vorsätzlich",
                     "fahrlässige", "vermeintlich", "mutmasslich", "fraglich", "vielleicht"):
            assert _is_protected(word), word
        assert not _tokens_match("nichtig", "richtig") and not _tokens_match("richtig", "nichtig")
        assert not _tokens_match("hatte", "hätte") and not _tokens_match("wurde", "würde")
        assert not _tokens_match("müssen", "mussen") and not _tokens_match("gesetzt", "besetzt")
        assert not _tokens_match("nicht", "nichts") and not _tokens_match("wirksam", "unwirksam")
        assert _tokens_match("unzulässig", "unzulässige") and _tokens_match("nichtig", "nichtige")
        assert _tokens_match("verletzt", "verlezt") and _tokens_match("kaufpreis", "kaufpries")

    def test_a_split_un_is_joined(self):
        for text in ("un- zulässig", "un-\nzulässig", "un-\\nzulässig", "un zulässig", "Un-Zulässig"):
            assert _normalize_evidence_text(text) == "unzulässig", text
        assert _normalize_evidence_text("un- und rechtmäßig") == "un- und rechtmässig"
        assert _normalize_evidence_text("Un- zulässig", casefold=False) == "Unzulässig"


class TestVerifyEvidenceWordPasteAndAsides:
    """False negatives from a pasted Word solution (2026-10-09): Word
    footnote links and images, an aside with "nicht" before the quote, a
    condition after a hedged quote, and a stray last word after an
    ellipsis."""

    ACCEPTED = [
        # Word footnote references arrive as in-page links
        ("Da B als Beamtin Adressatin belastender Verwaltungsakte ist,[\\[12\\]](#_ftn12) ist eine Verletzung "
         "in ihren Beihilfeansprüchen (insb. aus § 67 SBG) sowie in ihrem Recht aus Art. 33 Abs. 5 "
         "GG[\\[13\\]](#_ftn13) nicht von vornherein auszuschließen.",
         "Da B als Beamtin Adressatin belastender Verwaltungsakte ist, ist eine Verletzung in ihren "
         "Beihilfeansprüchen ... sowie in ihrem Recht aus Art. 33 Abs. 5 GG nicht von vornherein auszuschließen"),
        # a Word text box pasted as an image
        ('![](file:///C:/Users/x/AppData/Local/Temp/msohtmlclip1/01/clip_image003.gif "Textfeld: 2")'
         " a) Bejahende Ansicht Nach einer Meinung ruft ein unterbliebener Hinweis einen Irrtum hervor.",
         "Nach einer Meinung ruft ein unterbliebener Hinweis einen Irrtum hervor"),
        # "nicht" inside an aside before the quote negates the aside
        ("Schriftliche Verwaltungsakte sind mit einer (ordnungsgemäßen, d. h. nicht floskelhaften) "
         "Begründung zu versehen.",
         "Schriftliche Verwaltungsakte sind mit einer ... Begründung zu versehen."),
        ("Schriftliche Verwaltungsakte sind mit einer (ordnungsgemäßen, d. h. nicht floskelhaften) "
         "Begründung zu versehen.",
         "Begründung zu versehen"),
        # a condition after a quote that leaves the result open
        ("Jedoch könnte die Frist gem. § 58 Abs. 2 S. 1 VwGO ein Jahr betragen, wenn die "
         "Rechtsbehelfsbelehrung unterblieben ist.",
         "Jedoch könnte die Frist gem. § 58 Abs. 2 S. 1 VwGO ein Jahr betragen"),
        # a stray last word after an ellipsis
        ("Nach einer Meinung ruft ein unterbliebener Hinweis auf die elektronische Klagemöglichkeit einen "
         "Irrtum über die Formerfordernisse hervor.",
         "Nach einer Meinung ruft ein unterbliebener Hinweis auf die elektronische Klagemöglichkeit einen "
         "Irrtum ... hervor."),
    ]

    REJECTED = [
        # the aside's own last word still turns the quote round
        ("Die Klage ist (nicht) begründet und hat Erfolg.", "begründet und hat Erfolg"),
        # an unhedged result is still limited by a following condition
        # a stray piece that carries a negation is never dropped
        ("Ein Anspruch des K auf Herausgabe besteht im Ergebnis nicht.",
         "Ein Anspruch des K auf Herausgabe besteht ... nicht"),
        # a stray piece must stand in the answer
        ("Nach einer Meinung ruft ein Hinweis einen Irrtum hervor.",
         "Nach einer Meinung ruft ein Hinweis einen Irrtum ... herbei"),
        # a norm citation after an ellipsis is never a stray piece
        ("Mangels abdrängender Sonderzuweisung richtet sich der Rechtsweg nach § 13 GVG.",
         "Mangels abdrängender Sonderzuweisung … GVG"),
        # a lone stray piece is no quote
        ("Nach einer Meinung ruft ein Hinweis einen Irrtum hervor.", "hervor"),
    ]

    @pytest.mark.parametrize("answer,evidence", ACCEPTED)
    def test_accepted(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is True

    @pytest.mark.parametrize("answer,evidence", REJECTED)
    def test_rejected(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is False

    def test_word_links_and_images_normalize_away(self):
        assert _normalize_evidence_text("ist,[\\[12\\]](#_ftn12) ist") == "ist, ist"
        assert _normalize_evidence_text('a ![](file:///C:/x/clip_image003.gif "Textfeld: 2") b') == "a b"
        # an ordinary link keeps its text
        assert _normalize_evidence_text("siehe [unten](#abschnitt-2) dazu") == "siehe unten dazu"


class TestVerifyEvidencePermissiveEdges:
    """Policy 2026-10-09: conditions, questions and doubt words around a
    quote do not void it; only a negation does. The judge decides what a
    hedged or questioned passage is worth; the check only guards against
    quotes that are not in the answer or that the answer turns into their
    opposite."""

    ACCEPTED = [
        ("Die Klage ist begründet, soweit sie sich gegen den Zinsanspruch richtet.",
         "Die Klage ist begründet"),
        ("Ein Mangel liegt vor, wenn die Sache nicht die vereinbarte Beschaffenheit hat.",
         "Ein Mangel liegt vor"),
        ("Fraglich ist, ob die Übergabe der Sache in den Geschäftsräumen stattfand.",
         "die Übergabe der Sache in den Geschäftsräumen stattfand"),
        ("Wenn die Frist gewahrt ist, ist die Klage zulässig.",
         "die Frist gewahrt ist"),
        ("Fraglich ist, ob der Verkäufer die Sache mangelfrei geliefert hat.",
         "Verkäufer die Sache mangelfrei geliefert hat"),
        ("Zweifelhaft ist daher, dass der Verkäufer die Sache mangelfrei geliefert hat.",
         "der Verkäufer die Sache mangelfrei geliefert hat"),
        ("Der Beklagte bestreitet, dass er die Sache vorsätzlich beschädigt hat.",
         "er die Sache vorsätzlich beschädigt hat"),
        ("Die Klage ist begründet, soweit die Bescheide rechtswidrig sind.",
         "Die Klage ist begründet"),
        # the false negative from the EKK test run
        ("Nach § 44 VwGO darf der Kläger mehrere Klagebegehren in einer Klage zusammen verfolgen, wenn sie "
         "sich gegen denselben Beklagten richten.",
         "Nach § 44 VwGO darf der Kläger mehrere Klagebegehren in einer Klage zusammen verfolgen"),
    ]

    SUBSTITUTED_ANSWER = (
        "Allerdings werden in dem Schreiben explizit auch die Bescheide vom 13.4.2024 und 15.6.2024 "
        "aufgehoben, also aus einer Zeit, in der B gar nicht mehr bei A in Behandlung war."
    )

    def test_a_long_quote_may_swap_a_word(self):
        quote = (
            "Heute werden in dem Schreiben explizit auch die Bescheide vom 13.4.2024 und 15.6.2024 "
            "aufgehoben, also aus einer Zeit"
        )
        assert verify_evidence(quote, EvidenceIndex(self.SUBSTITUTED_ANSWER)) is True

    def test_swaps_stay_rare_and_never_touch_protected_words(self):
        index = EvidenceIndex(self.SUBSTITUTED_ANSWER)
        # two swaps in a 14-word quote
        assert verify_evidence(
            "Heute werden in dem Brief explizit auch die Bescheide vom 13.4.2024 und 15.6.2024 aufgehoben", index
        ) is False
        # a swapped number
        assert verify_evidence(
            "Allerdings werden in dem Schreiben explizit auch die Bescheide vom 13.4.2023 und 15.6.2024 aufgehoben",
            index,
        ) is False
        # short quotes get no swap
        assert verify_evidence("Heute werden in dem Schreiben", index) is False
        answer = "Die Klage ist im Ergebnis zulässig und auch in vollem Umfang begründet und hat Erfolg."
        assert verify_evidence(
            "Die Klage ist im Ergebnis unzulässig und auch in vollem Umfang begründet und hat Erfolg",
            EvidenceIndex(answer),
        ) is False

    REJECTED = [
        # a negation still turns the quote round, before or after
        ("Ein Mangel liegt nicht vor, wenn die Sache die vereinbarte Beschaffenheit hat.", "Ein Mangel liegt"),
        ("Es ist nicht ersichtlich, dass der Verkäufer die Sache mangelfrei geliefert hat.",
         "der Verkäufer die Sache mangelfrei geliefert hat"),
        ("Der Anspruch des Klägers auf Herausgabe besteht nicht.", "Der Anspruch des Klägers auf Herausgabe besteht"),
    ]

    @pytest.mark.parametrize("answer,evidence", ACCEPTED)
    def test_accepted(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is True

    @pytest.mark.parametrize("answer,evidence", REJECTED)
    def test_rejected(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is False


class TestVerifyEvidencePdfPasteAndLooseCopies:
    """False negatives from the EKK exam (2026-10-10, all synthetic here):
    answers pasted from a PDF carry page footers, page and footnote numbers,
    footnote text and a broken "tt" ligature into their sentences; judges
    copy loosely (reordered or dropped function words, a pronoun spelled
    out, answer words left out without an ellipsis, a renumbered heading, a
    compound variant, "bei dem" for "beim"); and a norm citation after an
    ellipsis voided an otherwise verbatim quote. Quotes taken from the
    Musterlösung, swaps that change the meaning and hidden negations still
    fail."""

    ACCEPTED = [
        # a running page footer inside the sentence
        ("Als Adressatin belastender Verwaltungsakte kann B eine mögliche Verletzung ihrer\n\nSeite 3 von 12\n"
         "allgemeinen Handlungsfreiheit geltend machen.",
         "Als Adressatin belastender Verwaltungsakte kann B eine mögliche Verletzung ihrer allgemeinen "
         "Handlungsfreiheit geltend machen"),
        # a page number on a line of its own
        ("Sie hätte die Überzahlung leicht erkennen können. Daher ist\n11\n\nzumindest eine grob fahrlässige "
         "Unkenntnis der Rechtswidrigkeit zu bejahen.",
         "Daher ist zumindest eine grob fahrlässige Unkenntnis der Rechtswidrigkeit zu bejahen"),
        # a footnote number glued to the next word
        ("Mithin stellt die Angabe nur\n\n4einiger zulässiger Formen der Klageerhebung eine Schlechterstellung dar.",
         "Mithin stellt die Angabe nur einiger zulässiger Formen der Klageerhebung eine Schlechterstellung dar"),
        # footnote text between two lines of the sentence
        ("Nach der Adressatentheorie ist der Adressat eines belastenden\nVerwaltungsakts stets\n"
         "1 §§ sind solche des VwVfG.\n\nklagebefugt, weil zumindest Art. 2 I GG verletzt sein kann.",
         "Nach der Adressatentheorie ist der Adressat eines belastenden Verwaltungsakts stets klagebefugt"),
        # a "tt" ligature the PDF font turned into a bracket
        ("E contrario muss die Rechtsbehelfsbelehrung gar keine Aussage über die Form des Rechtsmi\\[els treffen.",
         "die Rechtsbehelfsbelehrung gar keine Aussage über die Form des Rechtsmittels treffen"),
        # "bei dem" for "beim"
        ("Die Klage hat innerhalb eines Monats beim Verwaltungsgericht des Saarlandes zu erfolgen.",
         "bei dem Verwaltungsgericht des Saarlandes zu erfolgen"),
        # a renumbered heading
        ("II. Formelle Rechtmäßigkeit\nDie Aufhebung ist formell rechtmäßig, wenn die zuständige Behörde gehandelt hat.",
         "2. Formelle Rechtmäßigkeit Die Aufhebung ist formell rechtmäßig, wenn die zuständige Behörde gehandelt hat"),
        # a citation fragment next to a substantial, loosely copied quote
        ("Vorliegend könnte sich aus § 54 I BeamtStG eine aufdrängende Sonderzuweisung ergeben. Das BBG gilt nur "
         "für Bundesbeamte. B ist vorliegend beim saarländischen Finanzministerium tätig und somit Landesbeamtin.",
         "§ 54 I BeamtStG … Da B im vorliegenden beim saarländischen Finanzministerium tätig ist und somit "
         "Landesbeamtin"),
        # answer words left out inside a sentence, without an ellipsis
        ("Die Klagen richten sich gegen denselben Beklagten, die erlassende Behörde, stehen im Zusammenhang und "
         "für beide ist das VG Saarlouis zuständig.",
         "Die Klagen richten sich gegen denselben Beklagten, stehen im Zusammenhang und für beide ist das VG "
         "Saarlouis zuständig"),
        # a pronoun spelled out
        ("Sie sind mithin begünstigende Verwaltungsakte und die Rücknahme ist nur unter den Voraussetzungen "
         "des § 48 II-IV VwVfG möglich.",
         "Die Beihilfebescheide sind mithin begünstigende Verwaltungsakte und die Rücknahme ist nur unter den "
         "Voraussetzungen des § 48 II-IV VwVfG möglich"),
        # a compound variant with the same head
        ("Offensichtlich wurden die Beihilfebescheide von einer Behörde erlassen und regeln einen Einzelfall.",
         "Offensichtlich wurden die Bewilligungsbescheide von einer Behörde erlassen und regeln einen Einzelfall"),
        # function words moved
        ("Der Wortlaut spricht daher dafür, dass nicht über jede Form der Klageerhebung belehrt werden muss.",
         "Daher spricht der Wortlaut dafür, dass nicht über jede Form der Klageerhebung belehrt werden muss"),
    ]

    REJECTED = [
        # a sentence from the Musterlösung the answer does not contain
        ("Die Behörde hat die Bescheide teilweise zurückgenommen. B hat das Geld ausgegeben.",
         "An der Zuständigkeit und am Verfahren (v. a. § 28 Abs. 1 VwVfG) bestehen keine Bedenken"),
        ("B wusste von dem Rabatt. Sie hat die Rechnungen trotzdem eingereicht.",
         "Nach § 818 Abs. 3 BGB ist die Verpflichtung zur Herausgabe des Erlangten ausgeschlossen, soweit der "
         "Empfänger nicht mehr bereichert ist"),
        # removing a page footer never hides a negation
        ("Die Klage ist\nSeite 2 von 5\nnicht fristgerecht erhoben worden, weil die Monatsfrist ablief.",
         "Die Klage ist fristgerecht erhoben worden, weil die Monatsfrist ablief"),
        # a left-out passage may not hold a negation or a hedge
        ("Die Rücknahme ist, anders als B meint, nicht ermessensfehlerhaft und daher im Ergebnis rechtmäßig erfolgt.",
         "Die Rücknahme ist, anders als B meint, ermessensfehlerhaft und daher im Ergebnis rechtmäßig erfolgt"),
        # a content word swapped inside the quote that is no compound variant
        ("Offensichtlich wurden die Beihilfebescheide von einer Behörde erlassen und regeln einen Einzelfall.",
         "Offensichtlich wurden die Rückforderungen von einer Behörde erlassen und regeln einen Einzelfall"),
        # a content word added inside the quote
        ("Die Klagen richten sich gegen denselben Beklagten und stehen im Zusammenhang miteinander.",
         "Die Klagen richten sich gegen denselben unzuständigen Beklagten und stehen im Zusammenhang miteinander"),
    ]

    @pytest.mark.parametrize("answer,evidence", ACCEPTED)
    def test_accepted(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is True

    @pytest.mark.parametrize("answer,evidence", REJECTED)
    def test_rejected(self, answer, evidence):
        assert verify_evidence(evidence, EvidenceIndex(answer)) is False

    def test_layout_free_copy_only_when_there_is_layout(self):
        assert EvidenceIndex("Die Klage ist zulässig.\n\nSie ist begründet.").layout_free is None
        index = EvidenceIndex("Die Klage ist\nSeite 2 von 5\nzulässig.")
        assert index.layout_free is not None
        assert "seite" not in index.layout_free.text

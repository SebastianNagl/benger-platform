import type { HowToGuide } from '@/lib/howto'

export const EVALUATION_GUIDES: HowToGuide[] = [
  {
    id: 'bewertungsbogen-upload-format',
    category: 'evaluation',
    title: {
      de: 'Wie muss ein Korrekturbogen aussehen, damit ich ihn hochladen kann?',
      en: 'What does a grading sheet have to look like so I can upload it?',
    },
    summary: {
      de: 'Eine Tabelle mit **einer Spalte Text** (Gliederungspunkt) und **einer Spalte Punkte** (max. BE je Schritt) genügt. Hochladen auf der **Aufgabenseite → Bewertungsbogen → Hochladen** als `.xlsx`, `.docx`, `.csv`, `.md` oder `.json`. Vor dem Speichern öffnet sich immer der Gliederungs-Editor zur fachlichen Prüfung — es wird nichts ungeprüft aktiviert.',
      en: 'A table with **one text column** (outline item) and **one points column** (max BE per step) is enough. Upload on the **task page → Bewertungsbogen → Hochladen** as `.xlsx`, `.docx`, `.csv`, `.md` or `.json`. The outline editor always opens before saving, so nothing is activated unreviewed.',
    },
    steps: {
      de: [
        '**Gliederung über die Beschriftung**: Die Ebene wird aus dem Anfang der Zeile gelesen — `Frage 1`, dann `A.`, `I.`, `1.`, `a)`, `aa)`, `(1)` und Aufzählungszeichen. Mehr als diese Reihenfolge braucht es nicht; acht Ebenen tief funktioniert.',
        '**Punkte**: Eine Zeile **mit** Punktwert wird ein Prüfungsschritt, eine Zeile **ohne** ein Abschnitt. Erlaubt sind `10`, `0,5`, `2 BE`, `3 P.` — Dezimalkomma ist in Ordnung, halbe BE sind erlaubt.',
        '**Punktespalte erkennen**: Eine Überschrift `max. BE` oder `Punkte` reicht; sonst wird die erste Zahlenspalte rechts vom Text genommen. Spalten mit `Ihre BE`, `Bewertung`, `erreicht` oder `Korrektor` werden ignoriert — eine leere Korrektur-Spalte stört also nicht.',
        '**Schwerpunkte**: `(Schwerpunkt!)` oder `(weiterer Schwerpunkt!)` hinter dem Titel markiert den Schritt; der Zusatz wird aus dem Titel entfernt.',
        '**Abschnitts-Hinweis**: `insgesamt 21 BE` wird als Notiz am Abschnitt übernommen und gegen die Summe der Schritte geprüft.',
        '**Bewertungshinweise**: Aufzählungspunkte unter einem Schritt werden dessen Hinweise — genau die Hinweise, die später Korrektorinnen und der KI-Judge sehen.',
        '**Notenschlüssel**: Eine Tabelle `Rohpunkte → Notenpunkte` am Ende (z. B. `0–9 | 0`, `10–19 | 1`, …) wird als Notenschlüssel der Klausur übernommen, samt Rundungsregel („bei 0,5 BE wird abgerundet“).',
        '**Summenzeilen** wie `Gesamt-BE` oder `Summe` werden übersprungen, der angegebene Wert aber mit der berechneten Summe verglichen.',
      ],
      en: [
        '**Hierarchy comes from the label**: the level is read from the start of the line — `Frage 1`, then `A.`, `I.`, `1.`, `a)`, `aa)`, `(1)` and bullets. Nothing beyond that ordering is needed; eight levels deep works.',
        '**Points**: a row **with** a point value becomes a scored step, a row **without** one becomes a section. `10`, `0,5`, `2 BE`, `3 P.` all work — decimal commas are fine and half points are allowed.',
        '**Finding the points column**: a `max. BE` or `Punkte` header is enough; otherwise the first numeric column right of the text is used. Columns headed `Ihre BE`, `Bewertung`, `erreicht` or `Korrektor` are ignored, so an empty marking column does no harm.',
        '**Focus points**: `(Schwerpunkt!)` or `(weiterer Schwerpunkt!)` after the title marks the step; the marker is stripped from the title.',
        '**Section note**: `insgesamt 21 BE` is kept as a note on the section and checked against the sum of its steps.',
        '**Grading hints**: bullet points under a step become its hints — exactly the hints human correctors and the AI judge see later.',
        '**Grade scale**: a `raw points → grade points` table at the end (e.g. `0–9 | 0`, `10–19 | 1`, …) is adopted as the exam grade scale, including the rounding rule.',
        '**Total rows** such as `Gesamt-BE` or `Summe` are skipped, but the stated value is compared against the computed sum.',
      ],
    },
    tips: {
      de: [
        '`.xlsx` ist die verlässlichste Quelle: In einer Tabelle stehen Text und Punkte sauber nebeneinander. In `.docx` ergibt sich die Zuordnung aus der Absatz-Reihenfolge in der Zelle — das klappt meistens, wird aber gemeldet, wenn es unsicher ist.',
        '`.csv` und `.md` sind für selbst geschriebene Bögen oft am einfachsten. In Markdown genügt eine Liste: `- I. Eröffnung des Verwaltungsrechtswegs — 1 BE`, auch `(2,5 BE)` oder `[3 Punkte]`.',
        '`.json` ist der verlustfreie Weg: Ein einmal im Editor gepflegter Bogen kann exportiert, außerhalb bearbeitet und exakt wieder eingelesen werden — Schritte, Schlüssel, Schwerpunkte und Notenschlüssel bleiben identisch.',
        'Bei `.csv` mit Komma als Trennzeichen müssen Dezimalkommas in Anführungszeichen stehen (`"2,5"`). Mit Semikolon — was deutsches Excel schreibt — entfällt das Problem.',
        'Passt die Datei in keines dieser Muster — Fließtext, eine Lösungsskizze, ein Bogen ohne Tabelle —, bietet der Upload **Mit KI strukturieren** an (erweiterte Edition). Ein Modell liest das Dokument und schlägt eine Gliederung vor; es erfindet dabei keine Punkte, sondern übernimmt nur, was dasteht. Das Ergebnis landet im selben Gliederungs-Editor und ist ausdrücklich ein Entwurf. Lesbare Tabellen werden weiterhin exakt eingelesen und nie an ein Modell gegeben.',
        'Der Bogen muss nicht vollständig sein: Was der Import nicht erkennt, ergänzen Sie im Gliederungs-Editor, bevor Sie aktivieren.',
      ],
      en: [
        '`.xlsx` is the most reliable source: text and points sit cleanly side by side. In `.docx` the mapping follows the paragraph order inside the cell — usually fine, and flagged when it is uncertain.',
        '`.csv` and `.md` are often easiest for a sheet you write yourself. In Markdown a list is enough: `- I. Opening of the administrative court process — 1 BE`, and `(2,5 BE)` or `[3 Punkte]` work too.',
        '`.json` is the lossless route: a sheet curated once in the editor can be exported, edited elsewhere and read back exactly — steps, keys, focus markers and grade scale stay identical.',
        'With `.csv` using a comma delimiter, decimal commas must be quoted (`"2,5"`). With a semicolon — what German Excel writes — the problem does not arise.',
        'If the file fits none of these shapes — prose, a solution sketch, a sheet without a table — the upload offers **Mit KI strukturieren** (extended edition). A model reads the document and proposes an outline; it invents no points, it only picks up what is there. The result lands in the same outline editor and is explicitly a draft. Readable tables are still parsed exactly and never handed to a model.',
        'The sheet need not be complete: whatever the import does not recognise, you add in the outline editor before activating.',
      ],
    },
    pitfalls: {
      de: [
        'Gescannte PDFs und Bilder lassen sich nicht einlesen. Es braucht eine Datei mit echtem Text.',
        'Stehen Text und Punkte **in derselben Zelle** (`Sachmangel 10 BE`), findet der Import keine Punktespalte. In `.md` funktioniert genau das dagegen — dort sind Punkte am Zeilenende vorgesehen.',
        'Word-Autonummerierung steht nicht in der Datei: Nummerierte Absätze kommen ohne Beschriftung an (Meldung `auto_numbering`). Die Ebene stimmt, die Nummer tragen Sie im Editor nach oder Sie schreiben sie im Dokument als Text.',
        'Ohne erkennbare Punktespalte bricht der Import mit einer klaren Meldung ab, statt einen leeren Bogen anzulegen. Nutzen Sie dann **Mit KI strukturieren** oder legen Sie den Bogen von Hand an.',
        'Meldungen wie `alignment_uncertain` oder `subtotal_mismatch` sind kein Fehler des Imports, sondern ein Hinweis, wo Sie im Editor hinschauen sollten.',
      ],
      en: [
        'Scanned PDFs and images cannot be read. The file needs real text.',
        'If text and points sit **in the same cell** (`Sachmangel 10 BE`), the import finds no points column. In `.md` that is exactly the expected form — there points belong at the end of the line.',
        'Word auto-numbering is not in the file: numbered paragraphs arrive without a label (warning `auto_numbering`). The level is right; add the number in the editor or type it into the document as text.',
        'With no recognisable points column the import stops with a clear message rather than creating an empty sheet. Use **Mit KI strukturieren** then, or write the sheet by hand.',
        'Warnings such as `alignment_uncertain` or `subtotal_mismatch` are not import failures — they mark where to look in the editor.',
      ],
    },
    keywords: {
      de: [
        'Korrekturbogen',
        'Bewertungsbogen',
        'Bewertungseinheiten',
        'BE',
        'hochladen',
        'Excel',
        'Word',
        'CSV',
        'Markdown',
        'JSON',
        'Notenschlüssel',
        'Schwerpunkt',
        'Format',
        'Vorlage',
      ],
      en: [
        'grading sheet',
        'rubric',
        'upload',
        'excel',
        'word',
        'csv',
        'markdown',
        'json',
        'grade scale',
        'format',
        'template',
      ],
    },
  },
  {
    id: 'evaluation-methods',
    category: 'evaluation',
    title: {
      de: 'Welche Bewertungsverfahren gibt es und wie stelle ich sie ein?',
      en: 'Which evaluation methods exist and how do I configure them?',
    },
    summary: {
      de: 'Im Assistenten (Schritt *Evaluation*) oder auf der Projektseite unter **Evaluierungskonfiguration → Evaluierungsmethoden**. Sie wählen Verfahren an, ordnen ein **Vorhersagefeld** (was bewertet wird) und ein **Referenzfeld** (Musterlösung) zu und wählen bei LLM-Judges das Bewertungsmodell.',
      en: 'In the wizard (step *Evaluation*) or on the project page under **Evaluation configuration → Evaluation methods**. You tick methods, map a **prediction field** (what is scored) and a **reference field** (model solution) and pick the judge model for LLM judges.',
    },
    steps: {
      de: [
        '**Lexikalisch**: Exact Match, BLEU, ROUGE, METEOR, chrF. Schnell, vergleichen Wortlaut mit der Referenz.',
        '**Semantisch**: Semantic Similarity, BERTScore, MoverScore. Vergleichen Bedeutung über Embeddings, laufen nur in der Batch-Evaluation.',
        '**Klassifikation**: Accuracy, Precision, Recall, F1 für Auswahlaufgaben.',
        '**LLM-as-Judge**: *Classic* (vordefinierte Dimensionen), *Custom* (eigener Prompt und eigene Kriterien), *Falllösung* (10 juristische Dimensionen mit Notenpunkten 0 bis 18), *LLM Custom Rubric* (pro Aufgabe automatisch erzeugter Bewertungsbogen).',
        '**Menschliche Korrektur**: *Korrektur (Classic)* mit Kommentaren und Markierungen, *Korrektur (Falllösung)* und *Korrektur (Custom Rubric)* nach demselben Schema wie der jeweilige Judge. Sie schalten die Seite **Korrektur** im Projekt frei.',
        'Für jedes Verfahren: **Vorhersagefeld** (z.B. `loesung` oder *Alle Modellausgaben*) und **Referenzfeld** (z.B. `task.musterloesung`). Bei mehreren Referenzen zählt der beste Treffer.',
      ],
      en: [
        '**Lexical**: Exact Match, BLEU, ROUGE, METEOR, chrF. Fast, compare wording with the reference.',
        '**Semantic**: Semantic Similarity, BERTScore, MoverScore. Compare meaning via embeddings, batch evaluation only.',
        '**Classification**: Accuracy, Precision, Recall, F1 for choice tasks.',
        '**LLM-as-Judge**: *Classic* (predefined dimensions), *Custom* (your own prompt and criteria), *Falllösung* (10 legal dimensions with grade points 0 to 18), *LLM Custom Rubric* (a per-task auto-generated grading sheet).',
        '**Human grading**: *Korrektur (Classic)* with comments and highlights, *Korrektur (Falllösung)* and *Korrektur (Custom Rubric)* on the same scheme as the respective judge. They unlock the **Korrektur** page in the project.',
        'For every method: **prediction field** (e.g. `loesung` or *All model outputs*) and **reference field** (e.g. `task.musterloesung`). With several references the best match counts.',
      ],
    },
    tips: {
      de: [
        'Klausur-Projekte bekommen automatisch **zwei** Falllösungs-Judges auf zwei verschiedenen Modellen (z. B. *Notenpunkte (gpt-5-mini)* und *Notenpunkte (gpt-5.4-mini)*). Bei der Sofort-Korrektur läuft genau einer davon. Die Batch-Evaluation führt beide aus. Das ist gewollt.',
        'Erweiterte Einstellungen (Judge-Modell, Temperatur, Denkbudget, mehrere Judges als Ensemble, Läufe pro Judge) finden Sie nach dem Anlegen auf der Projektseite.',
        'Eine eigene Rubrik geben Sie beim *Custom LLM Judge* als Kriterien mit Beschreibung und Maximalpunktzahl an. Mit Maximalpunktzahl bewertet der Judge alle Kriterien in einem Durchgang.',
      ],
      en: [
        'Exam projects automatically get **two** case-solution judges on two different models (e.g. *Notenpunkte (gpt-5-mini)* and *Notenpunkte (gpt-5.4-mini)*). Immediate grading runs exactly one of them. Batch evaluation runs both. This is intended.',
        'Advanced settings (judge model, temperature, thinking budget, several judges as an ensemble, runs per judge) are on the project page after creation.',
        'A custom rubric is entered on the *Custom LLM Judge* as criteria with description and maximum score. With a maximum score the judge scores all criteria in one pass.',
      ],
    },
    pitfalls: {
      de: [
        'Ein Verfahren mit dem Badge **Nur Batch** läuft nicht in der Sofort-Evaluation, weil es ein großes Modell lädt.',
        'LLM-Judges brauchen einen API-Schlüssel für das Bewertungsmodell. Ohne Schlüssel schlägt die Bewertung fehl.',
        'Vorhersage- und Referenzfeld müssen existieren. Nach einem Umbenennen von Feldern in der Annotationsvorlage passen Sie die Verfahren an.',
      ],
      en: [
        'A method with the **Batch only** badge does not run in immediate evaluation because it loads a large model.',
        'LLM judges need an API key for the judge model. Without a key the evaluation fails.',
        'Prediction and reference fields must exist. After renaming fields in the labeling template, adjust the methods.',
      ],
    },
    links: [
      {
        label: { de: 'API-Schlüssel einrichten', en: 'Setting up API keys' },
        href: '/how-to#api-keys',
      },
    ],
    keywords: {
      de: [
        'Evaluation',
        'Bewertungsverfahren',
        'Metrik',
        'Metriken',
        'Judge',
        'LLM-Judge',
        'Falllösung',
        'Rubrik',
        'BLEU',
        'ROUGE',
        'Vorhersagefeld',
        'Referenzfeld',
        'Notenpunkte',
      ],
      en: [
        'evaluation',
        'metrics',
        'judge',
        'rubric',
        'bleu',
        'rouge',
        'prediction field',
        'reference field',
        'grade points',
      ],
    },
  },
  {
    id: 'immediate-evaluation',
    category: 'evaluation',
    title: {
      de: 'Was ist die Sofort-Evaluation (KI-Votum) und wann läuft sie?',
      en: 'What is immediate evaluation (KI-Votum) and when does it run?',
    },
    summary: {
      de: 'Ist **Sofortige Evaluation** im Projekt aktiv, wird jede Abgabe direkt nach dem Absenden mit den konfigurierten Verfahren bewertet. Annotierende sehen das Ergebnis sofort in einem Fenster. Bei Klausuren ist das die KI-Korrektur mit Notenpunkten und Begründung je Dimension.',
      en: 'With **Immediate evaluation** enabled in the project, every submission is evaluated with the configured methods right after submitting. Annotators see the result immediately in a modal. For exams this is the AI grading with grade points and a justification per dimension.',
    },
    steps: {
      de: [
        'Einschalten: Assistent Schritt *Evaluation* → **Sofortige Evaluation**, oder Projektseite → Evaluierungskonfiguration. Klausur-Projekte haben sie automatisch an.',
        'Nach dem Absenden erscheint *Ihre Annotation wird evaluiert…*, dann das Ergebnis je Verfahren. Bei Klausuren: Notenpunkte, Punkte je Dimension, Gesamtbewertung, Verbesserungsbereiche.',
        'Ergebnisse, die verloren gingen (Tab geschlossen, Netzfehler), holt ein stündlicher Hintergrundlauf nach.',
      ],
      en: [
        'Enable: wizard step *Evaluation* → **Immediate evaluation**, or project page → evaluation configuration. Exam projects have it on automatically.',
        'After submitting, *Your annotation is being evaluated…* appears, then the result per method. For exams: grade points, points per dimension, overall assessment, areas to improve.',
        'Results that got lost (tab closed, network error) are caught up by an hourly background run.',
      ],
    },
    pitfalls: {
      de: [
        '*Die konfigurierten Evaluationsmethoden laufen nur in der Batch-Evaluation*: Alle Verfahren sind entweder menschliche Korrektur oder semantische Metriken. Fügen Sie z.B. einen LLM-Judge hinzu.',
        'Die Sofort-Evaluation ist Teil der erweiterten Edition.',
      ],
      en: [
        '*The configured evaluation methods run in batch evaluation only*: all methods are either human grading or semantic metrics. Add e.g. an LLM judge.',
        'Immediate evaluation is part of the extended edition.',
      ],
    },
    keywords: {
      de: [
        'Sofort-Evaluation',
        'Sofortige Evaluation',
        'KI-Votum',
        'sofort',
        'nach Abgabe',
        'Korrektur sofort',
      ],
      en: ['immediate evaluation', 'instant feedback', 'after submit'],
    },
  },
  {
    id: 'batch-evaluation',
    category: 'evaluation',
    title: {
      de: 'Wie starte ich eine Batch-Evaluation und wo sehe ich die Ergebnisse?',
      en: 'How do I start a batch evaluation and where do I see the results?',
    },
    summary: {
      de: 'Projektseite → **Evaluierungskonfiguration → Evaluierung starten** oder [Evaluierungen](/evaluations) → Projekt wählen. Im Dialog wählen Sie Modus, Verfahren, Modelle, Annotator:innen und Prompt-Strukturen. Ergebnisse erscheinen unter *Evaluierungen*, Läufe unter *Läufe*.',
      en: 'Project page → **Evaluation configuration → Start evaluation** or [Evaluations](/evaluations) → pick the project. In the dialog choose mode, methods, models, annotators and prompt structures. Results appear under *Evaluations*, runs under *Runs*.',
    },
    steps: {
      de: [
        '**Evaluationsmodus**: *Nur fehlende/fehlgeschlagene evaluieren* (Standard) oder *Alle evaluieren* (überschreibt bestehende Ergebnisse).',
        '**Metriken**, **Modelle** (Generierungen), **Annotator:innen** (menschliche Abgaben) und **Prompt-Strukturen** an- oder abwählen. Die Kostenschätzung zeigt Zellen und Judge-Modelle.',
        '**Evaluation starten**. Pro Verfahren wird ein eigener Lauf gestartet, Teilergebnisse erscheinen sofort.',
        'Ergebnisse: [Evaluierungen](/evaluations) mit Filtern für Projekt, Modelle, Metriken und Analyseebene; Tabelle *Ergebnisse pro Aufgabe*, Trends, Signifikanz. Export als **JSON** oder **CSV**.',
        'Einzelne Läufe mit Pausieren, Fortsetzen und Erneut versuchen: im Banner *Auswertungen laufen gerade* oder unter [Läufe](/runs).',
      ],
      en: [
        '**Evaluation mode**: *Evaluate only missing/failed* (default) or *Evaluate all* (overwrites existing results).',
        'Tick or untick **metrics**, **models** (generations), **annotators** (human submissions) and **prompt structures**. The cost estimate shows cells and judge models.',
        '**Start evaluation**. One run per method is started, partial results appear immediately.',
        'Results: [Evaluations](/evaluations) with filters for project, models, metrics and analysis level; *Results per task* table, trends, significance. Export as **JSON** or **CSV**.',
        'Individual runs with pause, resume and retry: in the *Evaluations running* banner or under [Runs](/runs).',
      ],
    },
    keywords: {
      de: [
        'Batch',
        'Evaluierung starten',
        'Ergebnisse',
        'Läufe',
        'Export CSV',
        'Signifikanz',
        'neu evaluieren',
      ],
      en: [
        'batch',
        'start evaluation',
        'results',
        'runs',
        'csv export',
        'significance',
        're-evaluate',
      ],
    },
  },
  {
    id: 'korrektur-review',
    category: 'evaluation',
    title: {
      de: 'Wie korrigieren Menschen Abgaben (Korrektur) und was ist der Review-Workflow?',
      en: 'How do humans grade submissions (Korrektur) and what is the review workflow?',
    },
    summary: {
      de: '**Korrektur** ist die menschliche Bewertung von Abgaben nach dem Falllösungsschema, einer eigenen Rubrik oder mit Kommentaren. Sie wird über die Verfahren *Korrektur (…)* aktiviert und über die Schnellaktion **Korrektur** bedient. **Review** ist eine Prüfphase, in der Annotationen vor der Finalisierung geprüft werden.',
      en: '**Korrektur** is human grading of submissions on the case-solution scheme, a custom rubric or with comments. It is enabled via the *Korrektur (…)* methods and used via the quick action **Korrektur**. **Review** is a checking phase in which annotations are reviewed before finalization.',
    },
    steps: {
      de: [
        'Korrektur aktivieren: Verfahren *Korrektur (Falllösung)*, *Korrektur (Custom Rubric)* oder *Korrektur (Classic)* auswählen. Im Verfahren stellen Sie Warteschlange (wer korrigiert was), blinde Korrektur (fremde Bewertungen verbergen) und Zeitlimit ein.',
        'Korrigieren: Projektseite → **Korrektur** → nächste Abgabe. Punkte je Dimension, Gesamtwürdigung und Verbesserungstipps, optional Randbemerkungen.',
        'Annotierende sehen ihre Korrektur unter **Meine Aufgaben** bzw. Studierende unter *Feedback* in der Klausur. Eine menschliche Note überschreibt die KI-Note in der Bestenliste und in der Lernplattform.',
        'Review: Projektseite → *Annotationsablauf & -verhalten* → **Überprüfungsphase aktivieren**, Modus *Direkte Korrektur*, *Unabhängige Überprüfung* oder *Beides*. Bedienung über die Schnellaktion **Review-Workflow**.',
      ],
      en: [
        'Enable grading: pick the method *Korrektur (Falllösung)*, *Korrektur (Custom Rubric)* or *Korrektur (Classic)*. Inside the method you set the queue (who grades what), blind grading (hide other assessments) and a time limit.',
        'Grade: project page → **Korrektur** → next submission. Points per dimension, overall assessment and improvement tips, optional margin notes.',
        'Annotators see their grading under **My tasks**, students under *Feedback* in the exam. A human grade overrides the AI grade on the leaderboard and in the learning platform.',
        'Review: project page → *Annotation workflow & behavior* → **Enable review phase**, mode *Direct correction*, *Independent review* or *Both*. Used via the quick action **Review workflow**.',
      ],
    },
    keywords: {
      de: [
        'Korrektur',
        'menschliche Bewertung',
        'Korrigieren',
        'Review',
        'Überprüfung',
        'Randbemerkung',
        'Feedback',
        'blind',
      ],
      en: ['grading', 'human evaluation', 'review', 'feedback', 'blind'],
    },
  },
  {
    id: 'reports-leaderboards',
    category: 'evaluation',
    title: {
      de: 'Was zeigen Berichte, Bestenlisten und die Lernstatistik?',
      en: 'What do reports, leaderboards and learning statistics show?',
    },
    summary: {
      de: '**Berichte** fassen ein Projekt zusammen (Daten, Annotationen, Generierung, Evaluationsergebnisse) und lassen sich für die Organisation veröffentlichen. **Bestenlisten** ranken LLMs, menschliche Annotator:innen und KI-Zusammenarbeit. Die **Lernstatistik** zeigt Ihre eigenen fälligen Karten, offenen Klausuren und den Notenverlauf.',
      en: '**Reports** summarize a project (data, annotations, generation, evaluation results) and can be published to the organization. **Leaderboards** rank LLMs, human annotators and AI co-creation. **Learning statistics** show your own due cards, open exams and score history.',
    },
    steps: {
      de: [
        '**Bericht**: Projektseite → Karte *Projektbericht* → **Bericht bearbeiten** (Texte, Interpretation, Metriken, Judge-Konfiguration, Diagramme) → **Veröffentlichen**, wahlweise nur für die Projektorganisationen oder **öffentlich** (auch ohne Anmeldung lesbar). Voraussetzung: Aufgaben, Generierungen und Evaluationen sind vorhanden. Die Zahlen werden beim Veröffentlichen eingefroren; **Daten aktualisieren** im Editor berechnet sie neu. Berichte stehen unter [Berichte](/reports).',
        '**Bestenlisten** ([Bestenlisten](/leaderboards)): Tabs *Menschliche Annotatoren*, *KI-Zusammenarbeit* und *LLMs*. Metrik und Zeitraum wählbar, Vorgabe sind Notenpunkte. Die LLM-Liste blendet Modelle mit weniger als 50 Generierungen oder Evaluationen aus, bis Sie *Statistische Relevanz* ausschalten.',
        'Eigene Modelle erscheinen in der LLM-Bestenliste nur, wenn sie öffentlich sind.',
        '**Lernstatistik** ([Lernstatistik](/learning-stats)): heute fällige Karteikarten, offene Klausuren mit Frist, Notenverlauf (KI und Mensch) und Behaltensrate.',
      ],
      en: [
        '**Report**: project page → *Project report* card → **Edit report** (texts, interpretation, metrics, judge configuration, charts) → **Publish**, either for the project organizations only or **publicly** (readable without signing in). Requires tasks, generations and evaluations. Numbers are frozen on publish; **Refresh data** in the editor recomputes them. Reports are listed under [Reports](/reports).',
        '**Leaderboards** ([Leaderboards](/leaderboards)): tabs *Human annotators*, *AI co-creation* and *LLMs*. Metric and time frame selectable, default is grade points. The LLM list hides models with fewer than 50 generations or evaluations until you switch off *Statistical relevance*.',
        'Custom models only appear on the LLM leaderboard when they are public.',
        '**Learning statistics** ([Learning statistics](/learning-stats)): flashcards due today, open exams with deadline, score history (AI and human) and retention.',
      ],
    },
    keywords: {
      de: [
        'Bericht',
        'Berichte',
        'veröffentlichen',
        'Bestenliste',
        'Rangliste',
        'Leaderboard',
        'Lernstatistik',
        'Notenverlauf',
      ],
      en: [
        'report',
        'publish',
        'leaderboard',
        'ranking',
        'learning statistics',
        'score history',
      ],
    },
  },
]

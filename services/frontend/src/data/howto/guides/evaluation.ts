import type { HowToGuide } from '@/lib/howto'

export const EVALUATION_GUIDES: HowToGuide[] = [
  {
    id: 'evaluation-methods',
    category: 'evaluation',
    title: { de: 'Welche Bewertungsverfahren gibt es und wie stelle ich sie ein?', en: 'Which evaluation methods exist and how do I configure them?' },
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
        'Klausur-Projekte bekommen automatisch **zwei** Falllösungs-Judges, *Gratis-Modell* und *Abo-Modell*. Bei der Sofort-Korrektur läuft genau einer davon, je nachdem wer die Korrektur bezahlt. Die Batch-Evaluation führt beide aus. Das ist gewollt.',
        'Erweiterte Einstellungen (Judge-Modell, Temperatur, Denkbudget, mehrere Judges als Ensemble, Läufe pro Judge) finden Sie nach dem Anlegen auf der Projektseite.',
        'Eine eigene Rubrik geben Sie beim *Custom LLM Judge* als Kriterien mit Beschreibung und Maximalpunktzahl an. Mit Maximalpunktzahl bewertet der Judge alle Kriterien in einem Durchgang.',
      ],
      en: [
        'Exam projects automatically get **two** case-solution judges, *free model* and *subscription model*. Immediate grading runs exactly one of them, depending on who pays for the grading. Batch evaluation runs both. This is intended.',
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
    links: [{ label: { de: 'API-Schlüssel einrichten', en: 'Setting up API keys' }, href: '/how-to#api-keys' }],
    keywords: { de: ['Evaluation', 'Bewertungsverfahren', 'Metrik', 'Metriken', 'Judge', 'LLM-Judge', 'Falllösung', 'Rubrik', 'BLEU', 'ROUGE', 'Vorhersagefeld', 'Referenzfeld', 'Notenpunkte'], en: ['evaluation', 'metrics', 'judge', 'rubric', 'bleu', 'rouge', 'prediction field', 'reference field', 'grade points'] },
  },
  {
    id: 'immediate-evaluation',
    category: 'evaluation',
    title: { de: 'Was ist die Sofort-Evaluation (KI-Votum) und wann läuft sie?', en: 'What is immediate evaluation (KI-Votum) and when does it run?' },
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
    keywords: { de: ['Sofort-Evaluation', 'Sofortige Evaluation', 'KI-Votum', 'sofort', 'nach Abgabe', 'Korrektur sofort'], en: ['immediate evaluation', 'instant feedback', 'after submit'] },
  },
  {
    id: 'batch-evaluation',
    category: 'evaluation',
    title: { de: 'Wie starte ich eine Batch-Evaluation und wo sehe ich die Ergebnisse?', en: 'How do I start a batch evaluation and where do I see the results?' },
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
    keywords: { de: ['Batch', 'Evaluierung starten', 'Ergebnisse', 'Läufe', 'Export CSV', 'Signifikanz', 'neu evaluieren'], en: ['batch', 'start evaluation', 'results', 'runs', 'csv export', 'significance', 're-evaluate'] },
  },
  {
    id: 'korrektur-review',
    category: 'evaluation',
    title: { de: 'Wie korrigieren Menschen Abgaben (Korrektur) und was ist der Review-Workflow?', en: 'How do humans grade submissions (Korrektur) and what is the review workflow?' },
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
    keywords: { de: ['Korrektur', 'menschliche Bewertung', 'Korrigieren', 'Review', 'Überprüfung', 'Randbemerkung', 'Feedback', 'blind'], en: ['grading', 'human evaluation', 'review', 'feedback', 'blind'] },
  },
  {
    id: 'reports-leaderboards',
    category: 'evaluation',
    title: { de: 'Was zeigen Berichte, Bestenlisten und die Lernstatistik?', en: 'What do reports, leaderboards and learning statistics show?' },
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
    keywords: { de: ['Bericht', 'Berichte', 'veröffentlichen', 'Bestenliste', 'Rangliste', 'Leaderboard', 'Lernstatistik', 'Notenverlauf'], en: ['report', 'publish', 'leaderboard', 'ranking', 'learning statistics', 'score history'] },
  },
]

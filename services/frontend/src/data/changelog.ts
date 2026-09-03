import type { ChangelogEntry } from '@/lib/extensions/changelog'

/**
 * Platform changelog entries, newest first. One short user-facing bullet
 * per meaningful change; both languages. Extended-edition entries live in
 * the extended package and are merged in via registerChangelogEntries().
 */
export const PLATFORM_CHANGELOG: ChangelogEntry[] = [
  {
    date: '2026-09-03',
    audience: 'benger',
    text: {
      de: 'Öffentliche Projekte abgesichert: Auch bei öffentlichen Projekten können nur noch Mitglieder mit Bearbeitungsrechten die Bewertungskonfiguration ändern, Evaluierungsläufe starten, Aufgaben-Metadaten bearbeiten oder Exporte erzeugen. Außenstehende sehen weiterhin nur, was ihre Rolle erlaubt.',
      en: 'Public projects hardened: on public projects, only members with edit rights can change the evaluation configuration, launch evaluation runs, edit task metadata or create exports. Outside users still see only what their role allows.',
    },
  },
  {
    date: '2026-09-02',
    audience: 'benger',
    text: {
      de: 'Berichte neu aufgebaut: Berichte können jetzt öffentlich (auch ohne Anmeldung) veröffentlicht werden, zeigen Modelle mit Anzeigenamen, korrekte Rangfolge und Notenpunkte, trennen Judge-Konfigurationen, und visualisieren die Verteilung der Notenpunkte von Menschen und Modellen. Die Zahlen werden beim Veröffentlichen eingefroren und lassen sich gezielt aktualisieren.',
      en: 'Reports rebuilt: reports can now be published publicly (readable without signing in), show models by display name with correct ranking and grade points, keep judge configurations apart, and visualize how grade points are distributed across humans and models. Numbers are frozen on publish and can be refreshed deliberately.',
    },
  },
  {
    date: '2026-09-02',
    audience: 'benger',
    text: {
      de: 'Architektur-Seite aktualisiert: Open-Core-Aufbau (Plattform + Erweiterungen), die zwei Oberflächen BenGER und Vertretbar, Worker-Warteschlangen, Objektspeicher, Gruppen, LTI sowie der aktuelle Deployment- und CI-Ablauf.',
      en: 'Architecture page updated: open-core structure (platform + extensions), the two interfaces BenGER and Vertretbar, worker queues, object storage, groups, LTI and the current deployment and CI flow.',
    },
  },
  {
    date: '2026-09-02',
    audience: 'benger',
    text: {
      de: 'Anleitungen neu: Die Seite „Anleitungen" ist jetzt ein durchsuchbarer Katalog kurzer Frage-Antwort-Anleitungen (Organisationen & Gruppen, Projekte, Datenimport, Annotations-XML, API-Schlüssel, Bewertungsverfahren, Moodle/ILIAS, Fehlerbehebung). Die Suche in der Kopfzeile findet jetzt alle Seiten und jede einzelne Anleitung.',
      en: 'New guides: the "How-to guides" page is now a searchable catalog of short question-and-answer guides (organizations & groups, projects, data import, annotation XML, API keys, evaluation methods, Moodle/ILIAS, troubleshooting). The header search now finds every page and every individual guide.',
    },
  },
  {
    date: '2026-09-02',
    audience: 'benger',
    text: {
      de: 'Generierung: Platzhalter wie $sachverhalt innerhalb eines Prompt-Textes werden jetzt durch den Aufgabeninhalt ersetzt. Bisher wurde der Platzhalter wörtlich an das Modell geschickt.',
      en: 'Generation: placeholders such as $sachverhalt inside a prompt text are now replaced with the task content. Previously the placeholder was sent to the model literally.',
    },
  },
  {
    date: '2026-09-02',
    audience: 'benger',
    text: {
      de: 'Startseite: Der Abschnitt „Gruppe & Netzwerk" führt jetzt alle Beteiligten in einem Block auf; die Benchmark-Zitation ist als Preprint (angenommen bei EMNLP 2026) gekennzeichnet.',
      en: 'Landing page: the "Group & Network" section now lists everyone involved in one block; the benchmark citation is marked as a preprint accepted at EMNLP 2026.',
    },
  },
  {
    date: '2026-09-02',
    audience: 'benger',
    text: {
      de: 'Kontextmenü oben rechts: Lange Organisationsnamen werden jetzt einzeilig mit „…" gekürzt (voller Name als Tooltip), statt umzubrechen und das Symbol zu stauchen.',
      en: 'Top-right context menu: long organization names are now cut to one line with "…" (full name as tooltip) instead of wrapping and squeezing the icon.',
    },
  },
  {
    date: '2026-09-02',
    audience: 'benger',
    text: {
      de: 'Bestenliste: Der Tab „Klausur-Kohorte" ist entfernt. Menschliche Ranglisten stehen unter „Menschliche Annotatoren", das Kohorten-Ranking je Klausur weiterhin auf der Projektseite. Die Lernstatistik-Seite nutzt jetzt denselben Seitenabstand wie die übrigen Seiten.',
      en: 'Leaderboards: the "Exam cohort" tab is gone. Human rankings live under "Human Annotators"; the per-exam cohort ranking stays on the project page. The learning statistics page now uses the same page spacing as the other pages.',
    },
  },
  {
    date: '2026-09-01',
    audience: 'benger',
    text: {
      de: 'Organisationen können Mitglieder, Projekte und API-Schlüssel jetzt in Gruppen (z.B. Lehrstühle) aufteilen — Gruppen sehen nur ihre eigenen Projekte und nutzen ihre eigenen Schlüssel; Gruppen-Admins verwalten ihre Gruppe selbst.',
      en: 'Organizations can now split members, projects, and API keys into groups (e.g. chairs) — groups only see their own projects and spend their own keys; group admins manage their group themselves.',
    },
  },
  {
    date: '2026-08-31',
    audience: 'benger',
    text: {
      de: 'Projektseite: neue Karte „Abrechnung" zeigt, wessen API-Schlüssel die KI-Auswertungen bezahlt.',
      en: 'Project page: new "Billing" card shows whose API key pays for AI evaluations.',
    },
  },
  {
    date: '2026-08-31',
    audience: 'benger',
    text: {
      de: 'Cloud-Speicher-Import: Organisationen können S3-kompatible Speicher verbinden; Dateien lassen sich direkt aus dem Bucket als Aufgaben importieren.',
      en: 'Cloud storage import: organizations can connect S3-compatible storage and import files from the bucket as tasks.',
    },
  },
  {
    date: '2026-08-31',
    audience: 'benger',
    text: {
      de: 'Projekt-Assistent: klarere Datenquellen-Auswahl — bei Klausur-Projekten steht „Klausur erfassen“ jetzt an erster Stelle, „Tabelle/JSON einfügen“ heißt, was es ist.',
      en: 'Project wizard: clearer data-source picker — for exam projects "Enter exam" now comes first, and paste is labeled for what it is.',
    },
  },
  {
    date: '2026-08-31',
    audience: 'benger',
    text: {
      de: 'Projekt-Assistent: „Klausur erfassen“ übernimmt eingegebene Inhalte jetzt automatisch — die Klausur-Aufgabe geht nicht mehr verloren, wenn „Übernehmen“ übersprungen wurde.',
      en: 'Project wizard: "Enter exam" now saves entered content automatically — the exam task is no longer lost when "Apply" was skipped.',
    },
  },
  {
    date: '2026-08-31',
    audience: 'benger',
    text: {
      de: 'Organisationsverwaltung: Eine geänderte Beschreibung ist sofort sichtbar, ohne die Seite neu zu laden.',
      en: 'Organization management: an edited description now shows immediately, without reloading the page.',
    },
  },
  {
    date: '2026-08-25',
    audience: 'benger',
    text: {
      de: 'AI-Bewertungsbogen ist jetzt ein eigener Schritt im Projekt-Assistenten (experimentell) und funktioniert für jede Klausur, nicht nur KI-generierte.',
      en: 'The AI grading rubric is now its own project-wizard step (experimental) and works for any exam, not just AI-generated ones.',
    },
  },
  {
    date: '2026-08-25',
    audience: 'both',
    text: {
      de: 'Alle Nutzer:innen können jetzt über das Kontomenü zwischen Studierenden- und Expertenansicht wechseln.',
      en: 'Everyone can now switch between the student and expert interface from the account menu.',
    },
  },
  {
    date: '2026-08-25',
    audience: 'benger',
    text: {
      de: 'Projekttyp (Klausur / Kartenstapel) ist jetzt in den Projektdetails änderbar und steuert die Sichtbarkeit für Studierende.',
      en: 'The project type (exam / flashcard deck) is now editable in the project details and controls student visibility.',
    },
  },
  {
    date: '2026-08-24',
    audience: 'both',
    text: {
      de: 'Neue Changelog-Seite: alle Neuerungen im Überblick, erreichbar über den Footer.',
      en: "New changelog page: an overview of what's new, reachable from the footer.",
    },
  },
]

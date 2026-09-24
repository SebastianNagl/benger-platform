import type { ChangelogEntry } from '@/lib/extensions/changelog'

/**
 * Platform changelog entries, newest first. One short user-facing bullet
 * per meaningful change; both languages. Extended-edition entries live in
 * the extended package and are merged in via registerChangelogEntries().
 */
export const PLATFORM_CHANGELOG: ChangelogEntry[] = [
  {
    date: '2026-09-24',
    audience: 'benger',
    text: {
      de: 'In der Datenverwaltung funktionieren „Als abgeschlossen markieren“ und „Als unvollständig markieren“ wieder. Die Tabelle zeigt den neuen Status sofort an.',
      en: 'In data management, “Mark as complete” and “Mark as incomplete” work again. The table shows the new status right away.',
    },
  },
  {
    date: '2026-09-24',
    audience: 'benger',
    text: {
      de: 'Auf der Modellseite stehen eigene Modelle jetzt ganz oben. Die Schaltfläche „Modell registrieren“ sitzt wie auf den anderen Seiten über der Filterleiste.',
      en: 'On the Models page, custom models now appear at the top. The “Register model” button sits above the filter bar, like on the other pages.',
    },
  },
  {
    date: '2026-09-19',
    audience: 'both',
    text: {
      de: 'Anmeldung und Passwort-Zurücksetzen erkennen die E-Mail-Adresse jetzt unabhängig von Groß- und Kleinschreibung. Bisher scheiterte die Anmeldung mit „T.Name@…“ statt „t.name@…“, und die Mail zum Zurücksetzen kam nie an.',
      en: 'Sign-in and password reset now recognise your email address regardless of upper or lower case. Until now, signing in as “T.Name@…” instead of “t.name@…” failed, and the reset email never arrived.',
    },
  },
  {
    date: '2026-09-19',
    audience: 'both',
    text: {
      de: 'Organisationen erscheinen im Organisationswechsler und im Kontomenü alphabetisch. Der Wechsler auf der Organisationsseite sieht aus wie die übrigen Auswahllisten, schließt bei Klick daneben oder mit Esc und lässt sich mit den Pfeiltasten bedienen.',
      en: 'Organizations are listed alphabetically in the organization switcher and the account menu. The switcher on the Organizations page looks like the other dropdowns, closes on a click outside or Esc, and works with the arrow keys.',
    },
  },
  {
    date: '2026-09-17',
    audience: 'both',
    text: {
      de: 'Die Liste der ausstehenden Einladungen zeigt jetzt, ob die Einladungs-E-Mail wirklich versendet wurde, und nennt bei einem Fehler den Grund. Einladungen lassen sich erneut senden, ohne sie abzubrechen und neu anzulegen. Der bereits versendete Link bleibt dabei gültig.',
      en: 'The pending invitation list now shows whether the invitation email really went out, and names the reason when it did not. Invitations can be resent without cancelling and recreating them. A link already sent keeps working.',
    },
  },
  {
    date: '2026-09-17',
    audience: 'both',
    text: {
      de: 'Mitgliederlisten zeigen Rollen mit ihrer Bezeichnung, und der Korrektur-Reiter für Bewertungsbögen ist beschriftet. Die Anleitungen zu ILIAS empfehlen jetzt eine Identifikation ohne E-Mail-Adresse, weil ILIAS 10.9 sonst keine Noten annimmt.',
      en: 'Member lists show roles by their label, and the grading tab for grading sheets has a label. The ILIAS guides now recommend identifying people without their email address, because ILIAS 10.9 otherwise accepts no grades.',
    },
  },
  {
    date: '2026-09-17',
    audience: 'both',
    text: {
      de: 'Die Registrierung einer Lernplattform per Link zeigt ihr Ergebnis jetzt direkt in Moodle an. Die Anleitungen nennen außerdem die drei Tool-Einstellungen, die die Moodle-Administration danach ändert. Das Tool erscheint dann in der Aktivitätsauswahl, startet in einem neuen Fenster und darf Bewertungen eintragen.',
      en: 'Registering a learning platform by link now shows its result right inside Moodle. The guides also name the three tool settings the Moodle administration changes afterwards. The tool then appears in the activity chooser, opens in a new window and may enter grades.',
    },
  },
  {
    date: '2026-09-17',
    audience: 'both',
    text: {
      de: 'Projekte mit Aufgabenzuweisungen lassen sich wieder importieren. Bisher brach ein solcher Import mit einem Fehler ab.',
      en: 'Projects with task assignments can be imported again. Until now, such an import stopped with an error.',
    },
  },
  {
    date: '2026-09-17',
    audience: 'both',
    text: {
      de: 'Wer aus einer Organisation entfernt wurde, kann wieder eingeladen werden. Mit dem Annehmen der Einladung ist die Mitgliedschaft wieder aktiv. Bisher schlug das Annehmen mit einem Fehler fehl.',
      en: 'People removed from an organization can be invited again. Accepting the invitation makes the membership active again. Until now, accepting failed with an error.',
    },
  },
  {
    date: '2026-09-17',
    audience: 'benger',
    text: {
      de: 'Organisations-Admins richten Moodle- und ILIAS-Anbindungen jetzt selbst ein und verwalten sie unter Benutzer & Organisationen → Mehr → Lernplattform (LTI). Neue Anbindungen sind sofort aktiv, die Adresse des Tools ist pro Anbindung wählbar, und das Panel zeigt Aktivitäten, LMS-Konten, Notenübertragungen und einen Verlauf. Über die Lernplattform angelegte Konten lassen sich anonymisieren. Gruppen-Admins verwalten die Anbindungen ihrer Gruppe.',
      en: 'Organization admins now set up and manage Moodle and ILIAS connections themselves under Users & organizations → More → Learning platform (LTI). New connections are active at once, the tool address can be chosen per connection, and the panel shows activities, LMS accounts, grade transfers and a history. Accounts created through the learning platform can be anonymized. Group admins manage their group’s connections.',
    },
  },
  {
    date: '2026-09-17',
    audience: 'benger',
    text: {
      de: 'Mitwirkende und Admins einer Organisation sehen Klausuren, die mit einer Lernplattform der Organisation verknüpft sind, und können sie korrigieren, auch wenn die Klausur privat ist. Die Verknüpfung gibt niemandem das Recht, die Klausur zu löschen. Personen aus der Lernplattform erscheinen in Mitgliederlisten, Aufgabenlisten und Exporten unter ihrem Pseudonym. Klarnamen sehen nur Admins, die Lehrenden der verknüpften Kurse und wer die Klausur bewerten darf.',
      en: 'Contributors and admins of an organization see exams linked to a learning platform of the organization and can grade them, even when the exam is private. The link gives nobody the right to delete the exam. People from the learning platform appear under their pseudonym in member lists, task lists and exports. Only admins, the teachers of the linked courses and those who may grade the exam see real names.',
    },
  },
  {
    date: '2026-09-17',
    audience: 'both',
    text: {
      de: 'Die Anleitungen zur Lernplattform-Anbindung sind überarbeitet. Neu sind Anleitungen zum Verwalten einer Anbindung und zu Noten aus der Lernplattform, und die Hilfe zu Fehlern beim Start aus Moodle oder ILIAS nennt für jeden Fehlercode Ursache, Lösung und Ansprechpartner. Die Datenschutzerklärung beschreibt jetzt auch die Verarbeitung bei der Anbindung.',
      en: 'The guides on the learning platform integration were revised. New guides cover managing a connection and grades from the learning platform, and the help on failed launches from Moodle or ILIAS gives cause, fix and contact for every error code. The privacy policy now also describes the processing for the integration.',
    },
  },
  {
    date: '2026-09-16',
    audience: 'both',
    text: {
      de: 'Die Anleitungen haben eine neue Anleitung zum Datenschutz der Lernplattform-Anbindung (Moodle, ILIAS) und verweisen auf die ausführliche technische Referenz für Hochschul-IT. Außerdem lässt sich die Themenliste links jetzt scrollen, wenn sie länger als das Fenster ist.',
      en: 'The guides now include one on data protection for the LMS integration (Moodle, ILIAS) and link out to the detailed technical reference for university IT. The topic list on the left can also be scrolled now when it is longer than the window.',
    },
  },
  {
    date: '2026-09-16',
    audience: 'both',
    text: {
      de: 'Neue Modelle zur Auswahl: GPT-6 Astra, Claude Fable 5.1, Gemini 3.7 und 3.8 Flash, Grok 4.6 sowie Kimi K3, GLM-5.3, DeepSeek V4.1 Flash, Qwen3.8 Flash und Nemotron 3.5 Lightning. Mistral Large steht nicht mehr zur Verfügung, und die Preise mehrerer Modelle wurden korrigiert.',
      en: 'New models to choose from: GPT-6 Astra, Claude Fable 5.1, Gemini 3.7 and 3.8 Flash, Grok 4.6, plus Kimi K3, GLM-5.3, DeepSeek V4.1 Flash, Qwen3.8 Flash and Nemotron 3.5 Lightning. Mistral Large is no longer available, and the prices of several models were corrected.',
    },
  },
  {
    date: '2026-09-15',
    audience: 'both',
    text: {
      de: 'Bearbeitete Klausuren bleiben mit Abgabe, Korrektur und freigegebener Musterlösung einsehbar, auch nach Ablauf des Zeitfensters, Archivierung oder Änderungen an der Organisation.',
      en: 'Exams you have worked on stay viewable with your submission, grading and any released model solution, even after the time window closed, the project was archived or your organization changed.',
    },
  },
  {
    date: '2026-09-15',
    audience: 'benger',
    text: {
      de: 'Die Benachrichtigungseinstellungen haben neue Einträge für Bewertungen der eigenen Bearbeitungen, etwa durch KI-Korrekturen und Evaluierungsläufe. E-Mail-Benachrichtigungen kommen jetzt auch an, wenn In-App ausgeschaltet ist.',
      en: 'The notification settings have new entries for gradings of your own submissions, such as AI gradings and evaluation runs. Email notifications now also arrive when in-app notifications are switched off.',
    },
  },
  {
    date: '2026-09-15',
    audience: 'benger',
    text: {
      de: 'Die Seite eines Evaluierungslaufs öffnet jetzt auch Sofort-Bewertungen nach einer Abgabe, und der Reiter Judges zeigt jeden Judge-Lauf mit dem Mittelwert seiner eigenen Metrik.',
      en: 'The evaluation run page now opens immediate gradings after a submission, and the Judges tab shows each judge run with the mean of its own metric.',
    },
  },
  {
    date: '2026-09-15',
    audience: 'benger',
    text: {
      de: 'Auf der Projektseite steht die Karte Teilnahme jetzt unter den Schnellaktionen und bleibt verborgen, wenn es nichts zu verlassen und keine Kohorte anzuzeigen gibt.',
      en: 'On the project page the Participation card now sits below the quick actions and stays hidden when there is nothing to leave and no cohort to show.',
    },
  },
  {
    date: '2026-09-15',
    audience: 'benger',
    text: {
      de: 'Lokale Entwürfe sind jetzt an das angemeldete Konto gebunden: Ein zweites Konto im selben Browser sieht sie nicht mehr, und beim Abmelden werden sie entfernt.',
      en: 'Local drafts are now bound to the signed-in account: a second account in the same browser no longer sees them, and they are removed on sign-out.',
    },
  },
  {
    date: '2026-09-15',
    audience: 'benger',
    text: {
      de: 'Die Seite eines Evaluierungslaufs sieht jetzt aus wie der Rest der App: Projekttitel statt ID, übersetzter Status, verständliche Metriknamen, lesbare Musterlösung und Antwort sowie erklärte Gründe, wenn ein Lauf nichts bewerten konnte.',
      en: 'The evaluation run page now matches the rest of the app: project title instead of its id, translated status, readable metric names, readable reference and answer text, and explained reasons when a run found nothing to grade.',
    },
  },
  {
    date: '2026-09-15',
    audience: 'benger',
    text: {
      de: 'Projekt-Import übernimmt jetzt Projektart, Symbol und Einstellungen wie Zeitlimit und Zwischenstände, legt das Projekt in der aktuell gewählten Organisation an und weist Aufgaben-Exporte mit einem Hinweis auf die Seite Projektdaten zurück.',
      en: 'Project import now keeps the project kind, icon and settings such as time limit and checkpoints, creates the project in the organization you are working in, and rejects task exports with a pointer to the Project data page.',
    },
  },
  {
    date: '2026-09-15',
    audience: 'benger',
    text: {
      de: 'Der Metrik-Katalog, die Aufgabenposition und die Bearbeitungszeit auf der Annotationsseite folgen jetzt der eingestellten Sprache. Beim Anlegen eines Projekts erscheint nur noch eine Erfolgsmeldung, und Projekte ohne Beschreibung zeigen keinen Platzhaltertext mehr.',
      en: 'The metric catalogue, the task position and the elapsed time on the labeling page now follow the interface language. Creating a project shows a single success message, and projects without a description no longer show placeholder text.',
    },
  },
  {
    date: '2026-09-15',
    audience: 'benger',
    text: {
      de: 'Persönliche API-Schlüssel, die der Anbieter ablehnt, werden beim Speichern jetzt zurückgewiesen, und die Meldung nennt den Grund.',
      en: 'Personal API keys that the provider rejects are now refused when saving, and the message shows the reason.',
    },
  },
  {
    date: '2026-09-15',
    audience: 'both',
    text: {
      de: 'Beim Hochladen von Word-Dateien landen Inhaltsverzeichnis-Links und unsichtbare Textmarken nicht mehr im Text.',
      en: 'Uploaded Word files no longer leave table-of-contents links and hidden bookmarks in the extracted text.',
    },
  },
  {
    date: '2026-09-15',
    audience: 'both',
    text: {
      de: 'Die Kostenschätzung für Bewertungsbogen-Korrekturen zählt jetzt den vollständigen Judge-Prompt mit Bogen und Antwort, und ihre Hinweise erscheinen in der eingestellten Sprache.',
      en: 'The cost estimate for grading-sheet judges now counts the full judge prompt including sheet and answer, and its notes follow the interface language.',
    },
  },
  {
    date: '2026-09-08',
    audience: 'both',
    text: {
      de: 'Aufgeräumte Werkzeugleiste auf „Benutzer & Organisationen“: Neben der Organisationsauswahl stehen nur noch „Gruppen“, „API-Schlüssel“ und ein „Mehr“-Menü (Cloud-Speicher, Lernplattform-Anbindung); Superadmins sehen zusätzlich „Organisation erstellen“.',
      en: 'Tidier toolbar on “Users & Organizations”: next to the organization picker only “Groups”, “API keys” and a “More” menu (cloud storage, learning-platform integration) remain; superadmins additionally see “Create organization”.',
    },
  },
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

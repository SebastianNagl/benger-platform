import type { HowToGuide } from '@/lib/howto'

export const START_GUIDES: HowToGuide[] = [
  {
    id: 'what-is-benger',
    category: 'start',
    title: { de: 'Was ist BenGER, was ist Vertretbar?', en: 'What is BenGER, what is Vertretbar?' },
    summary: {
      de: '**BenGER** (what-a-benger.net) ist die Expertenplattform: Projekte anlegen, Daten hochladen, annotieren lassen, Antworten mit KI-Modellen generieren und auswerten. **Vertretbar** (vertretbar.net) ist die Plattform für Studierende: Klausuren im Gutachtenstil üben, in Sekunden eine KI-Korrektur mit Notenpunkten bekommen, mit Karteikarten lernen. Beide sind Oberflächen desselben Systems, mit derselben Datenbank und demselben Konto.',
      en: '**BenGER** (what-a-benger.net) is the expert platform: create projects, upload data, have them annotated, generate answers with AI models and evaluate. **Vertretbar** (vertretbar.net) is the platform for students: practise exams in the legal expert style, get an AI grading in seconds with grade points, learn with flashcards. Both are interfaces of the same system, with the same database and the same account.',
    },
    steps: {
      de: [
        '**BenGER** für Lehrende, Forschende und Annotierende: Dashboard, Projekte, Daten, Generierung, Evaluation, Berichte, Bestenlisten.',
        '**Vertretbar** für Studierende: Lernstatistik, Klausuren, Karteikarten, Entdecken, Bestenliste. Studierende brauchen keinen eigenen API-Schlüssel, die KI-Korrektur ist für sie derzeit kostenlos.',
        'Eine Klausur, die Sie in BenGER als Projekt vom Typ *Klausur* anlegen und freigeben, erscheint bei Studierenden in Vertretbar in der Klausurenliste bzw. unter *Entdecken*. Ihre Abgaben und KI-Korrekturen sehen Sie im BenGER-Projekt.',
        'Die Vertretbar-Oberfläche ist auch von BenGER aus erreichbar: oben rechts im Kontomenü auf **Studierendenansicht**. Auf what-a-benger.net heißt sie dann *Lernbereich*. Zurück geht es in der Seitenleiste über **Expertenansicht**.',
      ],
      en: [
        '**BenGER** for teachers, researchers and annotators: dashboard, projects, data, generation, evaluation, reports, leaderboards.',
        '**Vertretbar** for students: learning statistics, exams, flashcards, discover, leaderboard. Students need no API key of their own; AI grading is currently free for them.',
        'An exam you create in BenGER as a project of type *Exam* and share appears for students in Vertretbar in their exam list or under *Discover*. You see their submissions and AI gradings in the BenGER project.',
        'The Vertretbar interface is also reachable from BenGER: top right in the account menu via **Studierendenansicht**. On what-a-benger.net it is then called *Lernbereich*. Back via **Expertenansicht** in the sidebar.',
      ],
    },
    tips: {
      de: [
        'Die Anmeldung gilt pro Adresse: Auf vertretbar.net und what-a-benger.net meldet man sich jeweils separat an, mit denselben Zugangsdaten.',
        'Die Community-Edition von BenGER (Open Source) enthält nur die Expertenplattform. Vertretbar ist Teil der erweiterten Edition.',
      ],
      en: [
        'Login is per address: you sign in separately on vertretbar.net and what-a-benger.net, with the same credentials.',
        'The open-source community edition of BenGER contains only the expert platform. Vertretbar is part of the extended edition.',
      ],
    },
    links: [{ label: { de: 'Klausur für Studierende freigeben', en: 'Sharing an exam with students' }, href: '/how-to#share-with-students' }],
    keywords: { de: ['Vertretbar', 'Lernbereich', 'Studierendenansicht', 'Expertenansicht', 'Unterschied', 'Ansicht wechseln', 'vertretbar.net', 'what-a-benger.net'], en: ['Vertretbar', 'student platform', 'expert platform', 'difference', 'switch view'] },
  },
  {
    id: 'first-steps',
    category: 'start',
    title: { de: 'Was richte ich als Erstes ein?', en: 'What should I set up first?' },
    summary: {
      de: 'In dieser Reihenfolge: in die richtige Organisation wechseln, einen API-Schlüssel klären (eigener oder Organisation), ein Projekt anlegen, Daten hochladen, dann annotieren, generieren und auswerten.',
      en: 'In this order: switch to the right organization, sort out an API key (your own or the organization’s), create a project, upload data, then annotate, generate and evaluate.',
    },
    steps: {
      de: [
        '**Kontext prüfen**: Oben rechts im Kontomenü unter *Kontext wechseln* Ihre Organisation wählen. Im Kontext *Privat* sehen Sie keine Organisationsprojekte.',
        '**API-Schlüssel**: Stellt Ihre Organisation Schlüssel bereit, müssen Sie nichts tun. Sonst hinterlegen Sie unter [Profil](/profile) → *API-Schlüssel-Verwaltung* einen Schlüssel des KI-Anbieters, den Sie nutzen wollen.',
        '**Projekt anlegen**: [Projekte](/projects) → *Neues Projekt*, Projekttyp und Funktionen wählen.',
        '**Daten hochladen**: im Assistenten oder später über *Projektdaten* (JSON, CSV, TSV, TXT).',
        '**Annotieren**: *Annotation starten* auf der Projektseite. **Generieren** und **Evaluieren** über die jeweilige Konfigurationskarte.',
        '**Ergebnisse**: [Evaluation](/evaluations), [Berichte](/reports) und [Bestenlisten](/leaderboards).',
      ],
      en: [
        '**Check the context**: top right in the account menu under *Switch context* pick your organization. In the *Private* context you do not see organization projects.',
        '**API key**: if your organization provides keys, nothing to do. Otherwise store a key of the AI provider you want to use under [Profile](/profile) → *API key management*.',
        '**Create a project**: [Projects](/projects) → *New project*, pick type and functions.',
        '**Upload data**: in the wizard or later via *Project data* (JSON, CSV, TSV, TXT).',
        '**Annotate**: *Start annotation* on the project page. **Generate** and **evaluate** via the respective configuration card.',
        '**Results**: [Evaluation](/evaluations), [Reports](/reports) and [Leaderboards](/leaderboards).',
      ],
    },
    keywords: { de: ['Einstieg', 'Start', 'Checkliste', 'Anfang', 'los'], en: ['getting started', 'checklist', 'onboarding'] },
  },
  {
    id: 'navigation-overview',
    category: 'start',
    title: { de: 'Wo finde ich was in der Navigation?', en: 'Where do I find what in the navigation?' },
    summary: {
      de: 'Die Seitenleiste hat drei Gruppen. **Schnellstart**: Dashboard, Berichte, Lernstatistik, Bestenlisten. **Projekte & Daten**: Projekte, Datenverwaltung, Generierung, Evaluation. **Wissen**: Anleitungen, Modelle, Architektur. Alles Persönliche liegt oben rechts im Kontomenü.',
      en: 'The sidebar has three groups. **Quick start**: dashboard, reports, learning statistics, leaderboards. **Projects & data**: projects, data management, generation, evaluation. **Knowledge**: guides, models, architecture. Everything personal sits top right in the account menu.',
    },
    steps: {
      de: [
        '**Kontomenü** (oben rechts, Ihr Name): Profil-Einstellungen, Benachrichtigungs-Einstellungen, *Kontext wechseln* (Privat oder Organisation), Läufe, Benutzer & Organisationen, Studierendenansicht, Abmelden.',
        '**Suche** (Lupe in der Kopfzeile): findet Seiten, Projekte und diese Anleitungen. Deutsch und Englisch, auch bei Tippfehlern.',
        '**Läufe** zeigt alle Generierungs- und Evaluationsläufe mit Status. **Benachrichtigungen** (Glocke) informiert über abgeschlossene Läufe und Einladungen.',
        '**Modelle** ist der Modellkatalog mit Preisen und der Stelle, an der Sie eigene Modelle registrieren.',
      ],
      en: [
        '**Account menu** (top right, your name): profile settings, notification settings, *Switch context* (private or organization), runs, users & organizations, student view, sign out.',
        '**Search** (magnifier in the header): finds pages, projects and these guides. German and English, typos tolerated.',
        '**Runs** lists every generation and evaluation run with status. **Notifications** (bell) reports finished runs and invitations.',
        '**Models** is the model catalog with prices and the place to register your own models.',
      ],
    },
    keywords: { de: ['Navigation', 'Menü', 'Seitenleiste', 'Kontomenü', 'Suche', 'wo finde ich'], en: ['navigation', 'menu', 'sidebar', 'account menu', 'search', 'where'] },
  },
]

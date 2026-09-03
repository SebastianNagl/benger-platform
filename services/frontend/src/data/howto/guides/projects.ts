import type { HowToGuide } from '@/lib/howto'

export const PROJECT_GUIDES: HowToGuide[] = [
  {
    id: 'create-project',
    category: 'projects',
    title: { de: 'Wie lege ich ein neues Projekt an?', en: 'How do I create a new project?' },
    summary: {
      de: 'Über **Projekte → Neues Projekt** startet der Projekt-Assistent. Sie geben Name und Projekttyp an, wählen die Funktionen, die das Projekt braucht, und der Assistent zeigt nur die dazu passenden Schritte.',
      en: 'Go to **Projects → New project** to start the project wizard. Give the project a name and type, tick the functions it needs, and the wizard shows only the matching steps.',
    },
    steps: {
      de: [
        'Öffnen Sie [Projekte](/projects) und klicken Sie auf **Neues Projekt**.',
        '**Projektinformationen**: Name (Pflicht), Beschreibung, Symbol und der **Projekttyp** – *Generisch*, *Klausur* oder *Kartenstapel* (siehe „Welchen Projekttyp wähle ich?“).',
        'Haken Sie unter **Projektfunktionen** an, was Sie brauchen: *Datenimport*, *Annotation*, *LLM-Generierung*, *Evaluation*. Jede Funktion blendet einen eigenen Schritt ein.',
        'Wählen Sie die **Sichtbarkeit**: *Privat* (nur Sie), *Organisation* (Mitglieder einer oder mehrerer Organisationen, optional nur eine Gruppe) oder *Öffentlich*.',
        'Gehen Sie mit **Weiter** durch die Schritte *Datenimport*, *Annotation einrichten*, *Anweisungen*, *Modelle*, *Prompts*, *Evaluation* und *Einstellungen*.',
        'Klicken Sie im letzten Schritt auf **Projekt erstellen**. Sie landen auf der Projektseite.',
      ],
      en: [
        'Open [Projects](/projects) and click **New project**.',
        '**Project info**: name (required), description, icon and the **project type** – *Generic*, *Exam* or *Flashcard deck* (see “Which project type should I pick?”).',
        'Under **Project functions** tick what you need: *Data import*, *Annotation*, *LLM generation*, *Evaluation*. Each function adds its own step.',
        'Choose the **visibility**: *Private* (only you), *Organization* (members of one or more organizations, optionally a single group) or *Public*.',
        'Click **Next** through *Data import*, *Labeling setup*, *Instructions*, *Models*, *Prompts*, *Evaluation* and *Settings*.',
        'Click **Create project** on the last step. You land on the project page.',
      ],
    },
    tips: {
      de: [
        'Die Schritt-Chips oben sind klickbar. Sie können jederzeit zu einem früheren Schritt springen.',
        'Alles außer dem Namen lässt sich später auf der Projektseite ändern. Ein leerer Schritt ist kein Fehler.',
        'Ein Klausur-Projekt bekommt automatisch die Annotationsvorlage *Klausurlösung*, die KI-Korrektur (zwei Bewertungsverfahren) und die Sofort-Evaluation. Sie müssen dafür nichts einstellen.',
      ],
      en: [
        'The step chips at the top are clickable, so you can jump back to any earlier step.',
        'Everything except the name can be changed later on the project page. An empty step is not an error.',
        'An exam project automatically gets the *Klausurlösung* labeling template, the AI grading (two evaluation methods) and immediate evaluation. Nothing to configure.',
      ],
    },
    pitfalls: {
      de: [
        'Nur der Projektname wird geprüft. Ein Projekt ohne Daten oder ohne Annotationsvorlage lässt sich anlegen, ist dann aber leer.',
        'Schlägt ein Teilschritt beim Erstellen fehl (z.B. der Datenimport), existiert das Projekt trotzdem. Beheben Sie den Fehler dann auf der Projektseite statt den Assistenten erneut abzuschließen, sonst entsteht ein zweites Projekt.',
      ],
      en: [
        'Only the project name is validated. A project without data or without a labeling template can be created, it is simply empty.',
        'If one sub-step fails during creation (e.g. the data import), the project still exists. Fix the problem on the project page instead of finishing the wizard again, or you end up with a second project.',
      ],
    },
    links: [
      { label: { de: 'Neues Projekt', en: 'New project' }, href: '/projects/create' },
      { label: { de: 'Projekttyp wählen', en: 'Choosing the project type' }, href: '/how-to#project-kind' },
    ],
    keywords: { de: ['Assistent', 'Wizard', 'anlegen', 'erstellen', 'Neues Projekt'], en: ['wizard', 'setup'] },
  },
  {
    id: 'project-kind',
    category: 'projects',
    title: { de: 'Welchen Projekttyp wähle ich: Generisch, Klausur oder Kartenstapel?', en: 'Which project type should I pick: Generic, Exam or Flashcard deck?' },
    summary: {
      de: 'Der Projekttyp steuert, was das Projekt automatisch mitbringt und ob Studierende es finden können. *Klausur* für Falllösungen mit KI-Korrektur, *Kartenstapel* für Karteikarten mit Lernplan, *Generisch* für alles andere (Benchmarks, Annotationsstudien).',
      en: 'The project type decides what the project brings along automatically and whether students can find it. *Exam* for case solutions with AI grading, *Flashcard deck* for flashcards with a learning schedule, *Generic* for everything else (benchmarks, annotation studies).',
    },
    steps: {
      de: [
        '**Generisch**: Benchmark- oder Annotationsprojekt ohne Klausur- oder Kartenlogik. Sie wählen Vorlage, Modelle und Bewertungsverfahren selbst.',
        '**Klausur**: Sachverhalt plus Musterlösung, Annotationsvorlage *Klausurlösung* (Angabe, Notizen, Gliederung, Lösung), KI-Korrektur mit Notenpunkten, Sofort-Evaluation und Anzeige der Musterlösung nach der Abgabe. Für Studierende lösbar.',
        '**Kartenstapel**: Karten mit Vorder- und Rückseite, Lernplan mit Wiederholungen (SRS), Import und Export im Anki-Format. Für Studierende lernbar.',
        'Der Typ lässt sich später auf der Projektseite unter **Einstellungen → Projekttyp** ändern.',
      ],
      en: [
        '**Generic**: benchmark or annotation project without exam or card logic. You pick template, models and evaluation methods yourself.',
        '**Exam**: case facts plus model solution, the *Klausurlösung* labeling template (case, notes, outline, solution), AI grading in grade points, immediate evaluation and the model solution revealed after submission. Solvable by students.',
        '**Flashcard deck**: cards with front and back, a spaced-repetition learning schedule, Anki import and export. Learnable by students.',
        'The type can be changed later on the project page under **Settings → Project type**.',
      ],
    },
    tips: {
      de: [
        'Ein Typwechsel ändert nur den Typ. Vorlage, Bewertungsverfahren und Daten bleiben, wie sie sind. Die Hinweise unter dem Typ zeigen, was für Studierende noch fehlt.',
        'Wählen Sie im Schritt *Annotation einrichten* die Vorlage *Karteikarten (leer)*, setzt der Assistent den Typ automatisch auf *Kartenstapel*.',
      ],
      en: [
        'Changing the type only changes the type. Template, evaluation methods and data stay as they are. The hints under the type show what students would still be missing.',
        'Picking the *Karteikarten (leer)* template in the labeling step sets the type to *Flashcard deck* automatically.',
      ],
    },
    links: [{ label: { de: 'Klausur für Studierende freigeben', en: 'Sharing an exam with students' }, href: '/how-to#share-with-students' }],
    keywords: { de: ['Projekttyp', 'Kind', 'Klausur', 'Kartenstapel', 'Generisch'], en: ['project type', 'exam', 'deck', 'generic'] },
  },
  {
    id: 'exam-project-quick',
    category: 'projects',
    title: { de: 'Wie erfasse ich eine Klausur mit Sachverhalt und Musterlösung am schnellsten?', en: 'What is the fastest way to enter an exam with case facts and model solution?' },
    summary: {
      de: 'Über den Tab **Klausur erfassen** im Schritt *Datenimport*. Sie füllen Angabe und Musterlösung als Text aus, optional Gliederung, Bewertungskriterien, Bearbeitervermerk, Zusatzmaterial und Korrekturhinweise. Kein JSON nötig.',
      en: 'Use the **Klausur erfassen** tab in the *Data import* step. Fill in the case facts and model solution as text, optionally an outline, grading criteria, examiner notes, additional material and grading notes. No JSON needed.',
    },
    steps: {
      de: [
        'Projekttyp **Klausur** wählen und **Datenimport** anhaken.',
        'Im Schritt *Datenimport* ist der Tab **Klausur erfassen** vorausgewählt. Klicken Sie auf **Angabe (Sachverhalt)** und fügen Sie den Text ein oder laden Sie eine Datei hoch.',
        'Genauso **Musterlösung** ausfüllen. Sie wird erst nach der Abgabe sichtbar.',
        'Optional über **Inhalt hinzufügen**: *Gliederung / Lösungsskizze*, *Bewertungskriterien* (eigene Rubrik), *Bearbeitervermerk*, *Zusatzmaterial*, *Korrekturhinweise*.',
        'Weiter bis **Projekt erstellen**. Die Klausur wird als eine Aufgabe importiert.',
      ],
      en: [
        'Pick project type **Exam** and tick **Data import**.',
        'In the *Data import* step the **Klausur erfassen** tab is preselected. Click **Angabe (Sachverhalt)** and paste the text or upload a file.',
        'Fill in **Musterlösung** the same way. It is only shown after submission.',
        'Optionally add via **Inhalt hinzufügen**: outline, grading criteria (your own rubric), examiner notes, additional material, grading notes.',
        'Continue to **Create project**. The exam is imported as one task.',
      ],
    },
    tips: {
      de: [
        'Mit eigenen **Bewertungskriterien** bewertet die KI nach Ihrer Rubrik statt nach dem Standard-Schema mit 10 Dimensionen und Notenpunkten.',
        'Mehrere Klausuren in einem Projekt (eine „Klausurensammlung“) legen Sie über eine JSON-Datei mit mehreren Einträgen an, siehe „Welche Felder braucht eine Klausur-Datei?“.',
        'Der **KI-Generator** kann aus einem Vorlesungsskript synthetische Klausuren erzeugen. Er ist als hochexperimentell markiert und nur für ausgewählte Konten sichtbar.',
      ],
      en: [
        'With your own **grading criteria** the AI grades against your rubric instead of the default 10-dimension grade-point scheme.',
        'Several exams in one project (an “exam collection”) are created from a JSON file with several entries, see “Which fields does an exam file need?”.',
        'The **KI-Generator** can produce synthetic exams from a lecture script. It is marked highly experimental and only visible to selected accounts.',
      ],
    },
    links: [{ label: { de: 'Felder einer Klausur-Datei', en: 'Fields of an exam file' }, href: '/how-to#exam-file-fields' }],
    keywords: { de: ['Sachverhalt', 'Musterlösung', 'Rubrik', 'Klausur erfassen', 'strukturiert'], en: ['case', 'model solution', 'rubric', 'structured entry'] },
  },
  {
    id: 'project-page',
    category: 'projects',
    title: { de: 'Wie ist die Projektseite aufgebaut und wo finde ich was?', en: 'How is the project page organized and where do I find what?' },
    summary: {
      de: 'Die Projektseite besteht aus aufklappbaren Karten. Links die Konfiguration (Projektdetails, Annotationskonfiguration, Generierung, Evaluation, Einstellungen, Freigabe), rechts Schnellaktionen, Abrechnung, Statistiken und der Projektbericht. Daten, Meine Aufgaben, Korrektur und Review sind eigene Seiten.',
      en: 'The project page is made of collapsible cards. Configuration on the left (project details, annotation, generation, evaluation, settings, sharing), quick actions, billing, statistics and the project report on the right. Data, My tasks, Korrektur and Review are separate pages.',
    },
    steps: {
      de: [
        '**Projektdetails**: Status, Ersteller, Projekt-ID, Organisationen. Titel und Beschreibung ändern Sie direkt im Kopf der Seite (Stift beim Überfahren).',
        '**Annotationskonfiguration**: Anweisungen für Annotierende, Varianten für A/B-Tests, die Label-Konfiguration (XML) und *Annotationsablauf & -verhalten* (Zuweisungsmodus, Zeitlimit, Zugriffsfenster, Review- und Korrekturphase).',
        '**Generierungskonfiguration** und **Evaluierungskonfiguration**: Modelle, Prompts, Bewertungsverfahren, jeweils mit einem Startknopf.',
        '**Einstellungen**: Projekttyp, Sichtbarkeit der Bereiche (welche Karten es gibt) und die Projekt-Sichtbarkeit (Privat, Organisation, Öffentlich).',
        '**Freigabe**: Auffindbarkeit unter *Entdecken*, Freigabe-Links und Teilnehmende.',
        '**Schnellaktionen** rechts: *Annotation starten*, *Projektdaten* (Aufgaben, Import, Export), *Meine Aufgaben*, *Generierung*, *Evaluierungen*, *Review-Workflow*, *Korrektur*, *Projekt löschen*.',
      ],
      en: [
        '**Project details**: status, creator, project ID, organizations. Change title and description right in the page header (pencil on hover).',
        '**Annotation configuration**: instructions for annotators, A/B variants, the label configuration (XML) and *Annotation workflow & behavior* (assignment mode, time limit, access window, review and grading phase).',
        '**Generation configuration** and **Evaluation configuration**: models, prompts, evaluation methods, each with a start button.',
        '**Settings**: project type, visibility of sections (which cards exist) and project visibility (Private, Organization, Public).',
        '**Sharing**: discoverability under *Entdecken*, share links and participants.',
        '**Quick actions** on the right: *Start annotation*, *Project data* (tasks, import, export), *My tasks*, *Generation*, *Evaluations*, *Review workflow*, *Korrektur*, *Delete project*.',
      ],
    },
    tips: {
      de: [
        'Fehlt eine Karte, ist der Bereich unter **Einstellungen → Sichtbarkeit der Bereiche** ausgeschaltet. Diese Schalter steuern auch die Fortschrittsanzeige.',
        'Die Konfigurationskarten speichern automatisch, sobald Sie ein Feld verlassen. Ein Fehler beim Speichern lässt die Karte im Bearbeitungsmodus.',
      ],
      en: [
        'If a card is missing, that section is switched off under **Settings → Section visibility**. These switches also drive the progress display.',
        'Configuration cards save automatically when you leave a field. A failed save keeps the card in edit mode.',
      ],
    },
    keywords: { de: ['Projektseite', 'Karten', 'Schnellaktionen', 'Statistiken', 'Übersicht'], en: ['project page', 'cards', 'quick actions', 'overview'] },
  },
  {
    id: 'assignment-and-limits',
    category: 'projects',
    title: { de: 'Wie verteile ich Aufgaben an Annotierende und begrenze Annotationen?', en: 'How do I distribute tasks to annotators and limit annotations?' },
    summary: {
      de: 'Über den **Zuweisungsmodus** in *Annotationsablauf & -verhalten*: *Offen* (alle sehen alle Aufgaben), *Manuell* (Sie weisen zu) oder *Automatisch*. Dazu *Max. Annotationen pro Aufgabe* und *Min. Annotationen für Abschluss*.',
      en: 'Via the **assignment mode** in *Annotation workflow & behavior*: *Open* (everyone sees every task), *Manual* (you assign) or *Automatic*. Plus *Max annotations per task* and *Min annotations for completion*.',
    },
    steps: {
      de: [
        'Projektseite → **Annotationskonfiguration → Annotationsablauf & -verhalten**.',
        '**Zuweisungsmodus** wählen. Im Modus *Manuell* oder *Automatisch* sehen Annotierende nur Aufgaben, die ihnen zugewiesen sind.',
        'Zum manuellen Zuweisen: **Projektdaten** öffnen, Aufgaben ankreuzen, Massenaktion **Annotatoren zuweisen**.',
        '**Max. Annotationen pro Aufgabe** (0 = unbegrenzt) und **Min. Annotationen für Abschluss** setzen. Letzteres bestimmt, wann eine Aufgabe als erledigt zählt und wie der Fortschritt berechnet wird.',
        'Optional **Aufgabenreihenfolge zufällig**, Überspringen-Verhalten und **Bestätigung vor dem Absenden**.',
      ],
      en: [
        'Project page → **Annotation configuration → Annotation workflow & behavior**.',
        'Pick the **assignment mode**. In *Manual* or *Automatic* mode annotators only see tasks assigned to them.',
        'To assign manually: open **Project data**, tick tasks, bulk action **Assign annotators**.',
        'Set **Max annotations per task** (0 = unlimited) and **Min annotations for completion**. The latter decides when a task counts as done and how progress is computed.',
        'Optionally **Randomize task order**, skip behavior and **Require confirmation before submit**.',
      ],
    },
    pitfalls: {
      de: [
        'Organisationsadmins und Mitwirkende umgehen die Zuweisung immer. Nur die Rolle *Annotator* ist an Zuweisungen gebunden.',
        'Eine nicht zugewiesene Aufgabe ist für Annotierende unsichtbar (kein Fehler, sie fehlt einfach). Für Klausuren, die Studierende über *Entdecken* lösen sollen, muss der Modus *Offen* sein.',
      ],
      en: [
        'Organization admins and contributors always bypass assignment. Only the *Annotator* role is bound to assignments.',
        'An unassigned task is invisible to annotators (no error, it is simply missing). Exams that students should solve via *Entdecken* need the *Open* mode.',
      ],
    },
    keywords: { de: ['Zuweisung', 'zuweisen', 'Annotatoren', 'Limit', 'Fortschritt'], en: ['assign', 'assignment', 'annotators', 'limit', 'progress'] },
  },
  {
    id: 'timer-and-window',
    category: 'projects',
    title: { de: 'Wie setze ich ein Zeitlimit oder ein Zugriffsfenster?', en: 'How do I set a time limit or an access window?' },
    summary: {
      de: '**Zeitlimit für Annotation** begrenzt die Bearbeitungszeit pro Aufgabe, der **strikte Timer** gibt bei Ablauf automatisch ab. Das **Zeitfenster für den Zugriff** öffnet das Projekt nur zwischen zwei Zeitpunkten.',
      en: '**Time limit for annotation** caps the working time per task, the **strict timer** submits automatically when it runs out. The **access window** opens the project only between two points in time.',
    },
    steps: {
      de: [
        'Im Assistenten unter **Einstellungen** oder später unter *Annotationsablauf & -verhalten*.',
        '**Zeitlimit für Annotation** anhaken und die Minuten eintragen (1 bis 360, Vorgabe 30).',
        'Erst danach **Strikter Timer** anhaken, wenn die Abgabe bei Ablauf automatisch erfolgen soll.',
        '**Zeitfenster für den Zugriff** anhaken und *Öffnet* und *Schließt* setzen. Vor dem Öffnen ist das Projekt gelistet, die Daten bleiben verborgen. Nach dem Schließen ist alles schreibgeschützt.',
      ],
      en: [
        'In the wizard under **Settings** or later under *Annotation workflow & behavior*.',
        'Tick **Time limit for annotation** and enter the minutes (1 to 360, default 30).',
        'Only then tick **Strict timer** if the submission should happen automatically when time runs out.',
        'Tick **Access window** and set *Opens* and *Closes*. Before opening the project is listed but its data hidden. After closing everything is read-only.',
      ],
    },
    pitfalls: {
      de: [
        'Das Ein- oder Ausschalten des Zeitlimits setzt den strikten Timer zurück. Reihenfolge: erst Zeitlimit, dann strikter Timer.',
        'Eigentümer und Admins sind vom Zugriffsfenster nie eingeschränkt. Testen Sie das Fenster mit einem Annotator-Konto.',
        'Bei automatischer Abgabe durch den strikten Timer wird die Bestätigung vor dem Absenden übersprungen.',
      ],
      en: [
        'Toggling the time limit resets the strict timer. Order: time limit first, then strict timer.',
        'Owners and admins are never restricted by the access window. Test it with an annotator account.',
        'When the strict timer submits automatically, the confirmation before submit is skipped.',
      ],
    },
    keywords: { de: ['Timer', 'Zeitlimit', 'Zeitfenster', 'Öffnet', 'Schließt', 'Frist'], en: ['timer', 'time limit', 'window', 'deadline'] },
  },
  {
    id: 'archive-delete-restore',
    category: 'projects',
    title: { de: 'Wie archiviere, lösche oder stelle ich ein Projekt wieder her?', en: 'How do I archive, delete or restore a project?' },
    summary: {
      de: 'Archivieren geht in der Projektliste als Massenaktion. Löschen blendet das Projekt für alle aus, die Daten bleiben erhalten. Nur Superadmins können gelöschte Projekte unter **Mehr → Gelöschte Projekte** wiederherstellen oder endgültig löschen.',
      en: 'Archiving is a bulk action in the project list. Deleting hides the project for everyone, the data is kept. Only superadmins can restore or permanently delete projects under **More → Deleted projects**.',
    },
    steps: {
      de: [
        '**Archivieren**: [Projekte](/projects) → Projekte ankreuzen → **Aktionen → Ausgewählte archivieren**. Archivierte Projekte finden Sie unter **Mehr → Archiviert** und können sie dort dearchivieren.',
        '**Löschen**: Projektseite → Schnellaktionen → **Projekt löschen**. Das Projekt verschwindet für alle, Aufgaben, Abgaben und Bewertungen bleiben gespeichert.',
        '**Wiederherstellen** (Superadmin): **Mehr → Gelöschte Projekte** → *Wiederherstellen* oder *Endgültig löschen*.',
      ],
      en: [
        '**Archive**: [Projects](/projects) → tick projects → **Actions → Archive selected**. Archived projects live under **More → Archived** and can be unarchived there.',
        '**Delete**: project page → quick actions → **Delete project**. The project disappears for everyone, tasks, submissions and evaluations stay stored.',
        '**Restore** (superadmin): **More → Deleted projects** → *Restore* or *Delete permanently*.',
      ],
    },
    tips: {
      de: ['Sichern Sie vor dem endgültigen Löschen einen Export: Projekte ankreuzen → **Aktionen → Ausgewählte Projekte exportieren**.'],
      en: ['Before deleting permanently, keep an export: tick projects → **Actions → Export selected projects**.'],
    },
    keywords: { de: ['archivieren', 'löschen', 'wiederherstellen', 'Papierkorb', 'endgültig'], en: ['archive', 'delete', 'restore', 'trash', 'permanent'] },
  },
]

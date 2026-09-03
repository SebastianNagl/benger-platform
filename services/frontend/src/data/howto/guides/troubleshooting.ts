import type { HowToGuide } from '@/lib/howto'

export const TROUBLESHOOTING_GUIDES: HowToGuide[] = [
  {
    id: 'ts-no-projects',
    category: 'troubleshooting',
    title: { de: '„Ich sehe keine Projekte“ oder „mein Projekt ist verschwunden“', en: '“I see no projects” or “my project has disappeared”' },
    summary: {
      de: 'Fast immer der Kontext: oben rechts im Kontomenü unter **Kontext wechseln** die Organisation wählen. Danach: Ist das Projekt archiviert (*Mehr → Archiviert*) oder auf eine Gruppe beschränkt, der Sie nicht angehören?',
      en: 'Almost always the context: top right in the account menu under **Switch context** pick the organization. Then: is the project archived (*More → Archived*) or restricted to a group you do not belong to?',
    },
    links: [
      { label: { de: 'Privater Kontext vs. Organisation', en: 'Private context vs. organization' }, href: '/how-to#org-context' },
      { label: { de: 'Gruppen', en: 'Groups' }, href: '/how-to#org-groups' },
    ],
    keywords: { de: ['verschwunden', 'nicht sichtbar', 'leer', 'fehlt', 'keine Projekte'], en: ['disappeared', 'not visible', 'empty', 'missing', 'no projects'] },
  },
  {
    id: 'ts-no-models',
    category: 'troubleshooting',
    title: { de: '„Keine API-Schlüssel konfiguriert“ oder es fehlen Modelle in der Auswahl', en: '“No API keys configured” or models are missing from the picker' },
    summary: {
      de: 'Es fehlt der Schlüssel des Anbieters. Eigenen Schlüssel unter [Profil](/profile) → *API-Schlüssel-Verwaltung* hinterlegen, oder die Organisation muss *Organisation stellt API-Schlüssel bereit* einschalten und den Anbieter hinterlegen. Stellt die Organisation Schlüssel bereit, gibt es keinen Rückfall auf Ihren eigenen.',
      en: 'The provider key is missing. Store your own key under [Profile](/profile) → *API key management*, or the organization must switch on *Organization provides API keys* and add the provider. If the organization provides keys, there is no fallback to your own.',
    },
    links: [{ label: { de: 'API-Schlüssel einrichten', en: 'Setting up API keys' }, href: '/how-to#api-keys' }],
    keywords: { de: ['Keine API-Schlüssel', 'Modell fehlt', 'nicht verfügbar', 'Anbieter'], en: ['no api keys', 'model missing', 'unavailable', 'provider'] },
  },
  {
    id: 'ts-generation-fails',
    category: 'troubleshooting',
    title: { de: 'Generierung oder Bewertung schlägt fehl', en: 'Generation or evaluation fails' },
    summary: {
      de: 'Prüfen Sie in dieser Reihenfolge: Schlüssel gültig und mit Guthaben (*Nutzungs- oder Ratenlimit erreicht* heißt kein Guthaben beim Anbieter), Modell noch aktiv im [Modellkatalog](/models), Prompt-Struktur und Verfahren verweisen auf existierende Felder. Details zu jedem Lauf stehen unter [Läufe](/runs), fehlgeschlagene Läufe lassen sich dort erneut starten.',
      en: 'Check in this order: key valid and funded (*usage or rate limit reached* means no credit at the provider), model still active in the [model catalog](/models), prompt structure and methods reference existing fields. Details of every run are under [Runs](/runs), failed runs can be retried there.',
    },
    tips: {
      de: ['Bei *Erneut generieren* wird eine Aufgabe nur neu erzeugt, wenn sich der Prompt geändert hat. Mit *Alle generieren* erzwingen Sie die Neuerzeugung.'],
      en: ['*Regenerate* only re-creates a task when the prompt changed. *Generate all* forces regeneration.'],
    },
    keywords: { de: ['fehlgeschlagen', 'Fehler', 'Generierung fehlgeschlagen', 'Evaluierungsfehler', 'Ratenlimit', 'ungültiger Schlüssel'], en: ['failed', 'error', 'generation failed', 'evaluation error', 'rate limit', 'invalid key'] },
  },
  {
    id: 'ts-import-validation',
    category: 'troubleshooting',
    title: { de: '„Import-Validierungsfehler: These fields are not present in the data“', en: '“Import validation error: These fields are not present in the data”' },
    summary: {
      de: 'Ihre Datei hat andere Spaltennamen als die `$feld`-Platzhalter der Annotationsvorlage. Entweder Spalten umbenennen, die **Feldzuordnung** im Import-Dialog nutzen, oder **Trotzdem importieren** und danach unter *Feldzuordnung & Vorlage* auf der Datenseite die Vorlage aus den Daten erzeugen.',
      en: 'Your file has different column names than the `$field` placeholders of the labeling template. Either rename columns, use the **field mapping** in the import dialog, or **Import anyway** and then generate the template from the data under *Field mapping & template* on the data page.',
    },
    links: [{ label: { de: 'Daten hochladen', en: 'Uploading data' }, href: '/how-to#upload-data' }],
    keywords: { de: ['Validierungsfehler', 'Felder fehlen', 'not present', 'Feldzuordnung', 'Import fehlgeschlagen'], en: ['validation error', 'missing fields', 'field mapping', 'import failed'] },
  },
  {
    id: 'ts-unknown-component',
    category: 'troubleshooting',
    title: { de: 'Ein Feld fehlt in der Annotationsoberfläche oder „Unknown component type“', en: 'A field is missing in the annotation interface or “Unknown component type”' },
    summary: {
      de: 'Der Tag im XML wird nicht erkannt. Tag-Namen sind Groß-/Klein-sensitiv (`TextArea`, nicht `Textarea`). Klausur-Tags wie `Angabe`, `Gliederung` und `Loesung` gibt es nur in der erweiterten Edition. Fehlende Datenfelder (`value="$feld"`) bleiben leer, ohne Fehlermeldung.',
      en: 'The tag in the XML is not recognized. Tag names are case-sensitive (`TextArea`, not `Textarea`). Exam tags such as `Angabe`, `Gliederung` and `Loesung` exist only in the extended edition. Missing data fields (`value="$field"`) stay empty without an error.',
    },
    links: [{ label: { de: 'XML bearbeiten', en: 'Editing the XML' }, href: '/how-to#edit-label-xml' }],
    keywords: { de: ['Unknown component type', 'Feld fehlt', 'leer', 'wird nicht angezeigt', 'XML Fehler'], en: ['unknown component', 'field missing', 'empty', 'not shown', 'xml error'] },
  },
  {
    id: 'ts-import-button',
    category: 'troubleshooting',
    title: { de: '„Wo ist der Import-Knopf?“ und andere verschobene Funktionen', en: '“Where is the import button?” and other moved functions' },
    summary: {
      de: '**Projekt importieren**, **Archiviert**, **Gelöschte Projekte** und **Entdecken** stecken in der Projektliste im Menü **Mehr**. Der Import von Aufgaben in ein Projekt ist auf der Seite *Projektdaten*. Eigene Modelle werden unter [Modelle](/models) verwaltet, eigene API-Schlüssel im [Profil](/profile).',
      en: '**Import project**, **Archived**, **Deleted projects** and **Discover** sit in the project list under the **More** menu. Importing tasks into a project is on the *Project data* page. Custom models are managed under [Models](/models), personal API keys in the [profile](/profile).',
    },
    keywords: { de: ['Import-Knopf', 'Mehr-Menü', 'wo ist', 'finde nicht', 'verschoben'], en: ['import button', 'more menu', 'where is', 'cannot find', 'moved'] },
  },
  {
    id: 'ts-lti-errors',
    category: 'troubleshooting',
    title: { de: 'Start aus Moodle/ILIAS schlägt fehl', en: 'Launch from Moodle/ILIAS fails' },
    summary: {
      de: 'Die Fehlerseite nennt einen Code. *not_linked*: Lehrende haben die Aktivität noch nicht mit einer Klausur verknüpft. *registration_disabled* oder *registration_not_found*: die Anbindung ist deaktiviert oder nicht registriert, Plattform-Administration kontaktieren. *invalid_state* oder *state_unavailable*: Sitzung abgelaufen oder Cookies blockiert, Aktivität aus der Lernplattform neu öffnen, notfalls in einem neuen Tab.',
      en: 'The error page shows a code. *not_linked*: the teacher has not linked the activity to an exam yet. *registration_disabled* or *registration_not_found*: the connection is disabled or not registered, contact the platform administration. *invalid_state* or *state_unavailable*: session expired or cookies blocked, reopen the activity from the learning platform, if needed in a new tab.',
    },
    links: [{ label: { de: 'LTI einrichten', en: 'Setting up LTI' }, href: '/how-to#lti-setup' }],
    keywords: { de: ['LTI Fehler', 'not_linked', 'registration_disabled', 'invalid_state', 'Moodle Start', 'Fehlercode'], en: ['lti error', 'launch failed', 'error code'] },
  },
]

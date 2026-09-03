import type { HowToGuide } from '@/lib/howto'

export const DATA_GUIDES: HowToGuide[] = [
  {
    id: 'upload-data',
    category: 'data',
    title: { de: 'Wie lade ich Daten hoch und welche Formate gehen?', en: 'How do I upload data and which formats work?' },
    summary: {
      de: 'Als **JSON, CSV, TSV oder TXT**, entweder im Projekt-Assistenten (Schritt *Datenimport*) oder später auf der Seite **Projektdaten** über das Import-Symbol. Jede Zeile bzw. jedes Objekt wird eine Aufgabe. Die Feldnamen müssen zu den `$feld`-Platzhaltern der Annotationsvorlage passen.',
      en: 'As **JSON, CSV, TSV or TXT**, either in the project wizard (step *Data import*) or later on the **Project data** page via the import icon. Every row or object becomes a task. Field names must match the `$field` placeholders of the labeling template.',
    },
    steps: {
      de: [
        'Projektseite → Schnellaktion **Projektdaten** → Import-Symbol (Tooltip *Importieren*). Im Assistenten: Schritt **Datenimport**.',
        'Tab **Datei hochladen** (Drag & Drop) oder **Tabelle/JSON einfügen** (Text einfügen, *Daten validieren*). Organisationen mit Speicheranbindung haben zusätzlich **Cloud-Speicher**.',
        'Die Box **Datenanforderungen** zeigt, welche Felder die Vorlage erwartet. Erkannte Spalten Ihrer Datei erscheinen als Chips.',
        'Fehlt ein Feld, bietet der Import **Trotzdem importieren** oder die **Feldzuordnung** an, mit der Sie Spalten auf die erwarteten Felder abbilden.',
        '**Importieren**. Der Import läuft im Hintergrund, der Fortschritt wird angezeigt.',
      ],
      en: [
        'Project page → quick action **Project data** → import icon (tooltip *Import*). In the wizard: step **Data import**.',
        'Tab **Upload file** (drag & drop) or **Paste table/JSON** (paste text, *Validate data*). Organizations with a storage connection also get **Cloud storage**.',
        'The **Data requirements** box shows which fields the template expects. Detected columns of your file appear as chips.',
        'If a field is missing, the import offers **Import anyway** or the **field mapping**, which maps columns to the expected fields.',
        '**Import**. The import runs in the background with a progress display.',
      ],
    },
    tips: {
      de: [
        '**JSON**: ein Array von Objekten `[{"sachverhalt": "…", "musterloesung": "…"}, …]`. Ein Objekt mit `data` darin wird unverändert übernommen.',
        '**CSV/TSV**: erste Zeile sind die Spaltennamen. **TXT**: jede Zeile wird eine Aufgabe mit dem Feld `text`.',
        'Feldnamen werden ohne Rücksicht auf Groß-/Kleinschreibung zugeordnet. `Sachverhalt` in der Datei passt zu `$sachverhalt` in der Vorlage.',
        'Dateien bis 2 GB. Speichern Sie Textdateien als **UTF-8**, sonst erscheinen Umlaute falsch.',
      ],
      en: [
        '**JSON**: an array of objects `[{"sachverhalt": "…", "musterloesung": "…"}, …]`. An object that already has a `data` key is taken as is.',
        '**CSV/TSV**: the first line holds the column names. **TXT**: every line becomes a task with the field `text`.',
        'Field names are matched case-insensitively. `Sachverhalt` in the file matches `$sachverhalt` in the template.',
        'Files up to 2 GB. Save text files as **UTF-8**, otherwise umlauts break.',
      ],
    },
    pitfalls: {
      de: [
        'CSV wird einfach am Komma getrennt. **Kommas oder Zeilenumbrüche innerhalb von Zellen zerreißen die Zeile.** Nutzen Sie für Fließtexte JSON.',
        'Nur Mitwirkende und Admins dürfen importieren. Annotator:innen sehen die Datenseite nicht.',
        'Der Import legt neue Aufgaben an, er aktualisiert keine bestehenden. Ein zweiter Import derselben Datei verdoppelt die Aufgaben.',
      ],
      en: [
        'CSV is split on the comma, plainly. **Commas or line breaks inside cells tear the row apart.** Use JSON for running text.',
        'Only contributors and admins may import. Annotators do not see the data page.',
        'The import creates new tasks, it does not update existing ones. Importing the same file twice doubles the tasks.',
      ],
    },
    links: [{ label: { de: 'Felder einer Klausur-Datei', en: 'Fields of an exam file' }, href: '/how-to#exam-file-fields' }],
    keywords: { de: ['hochladen', 'Upload', 'Import', 'CSV', 'JSON', 'TSV', 'TXT', 'Datei', 'Feldzuordnung', 'Spalten', 'Datenimport'], en: ['upload', 'import', 'csv', 'json', 'file', 'field mapping', 'columns'] },
  },
  {
    id: 'exam-file-fields',
    category: 'data',
    title: { de: 'Welche Felder braucht eine Klausur-Datei (Klausurensammlung)?', en: 'Which fields does an exam file need (exam collection)?' },
    summary: {
      de: 'Pro Klausur ein JSON-Objekt mit `sachverhalt` und `musterloesung`. Optional `muster_gliederung`, `bearbeitervermerk`, `zusatzmaterial` und `korrekturhinweise`. Mehrere Objekte in einem Array ergeben eine Klausurensammlung, die Studierende nacheinander lösen.',
      en: 'One JSON object per exam with `sachverhalt` and `musterloesung`. Optionally `muster_gliederung`, `bearbeitervermerk`, `zusatzmaterial` and `korrekturhinweise`. Several objects in one array form an exam collection students solve one after another.',
    },
    steps: {
      de: [
        '`sachverhalt` (Pflicht): der Fall, während der Klausur sichtbar.',
        '`musterloesung` (Pflicht): die Referenz für die KI-Korrektur, erst nach der Abgabe sichtbar.',
        '`muster_gliederung`: Lösungsskizze, nach der Abgabe sichtbar.',
        '`bearbeitervermerk` und `zusatzmaterial`: während der Klausur sichtbar, erscheinen in der Angabe.',
        '`korrekturhinweise`: Hinweise für Korrigierende, nach der Abgabe sichtbar.',
        'Beispiel: `[{"sachverhalt": "A verkauft B …", "musterloesung": "A. Anspruch …"}, {"sachverhalt": "…", "musterloesung": "…"}]`',
      ],
      en: [
        '`sachverhalt` (required): the case, visible during the exam.',
        '`musterloesung` (required): the reference for AI grading, shown only after submission.',
        '`muster_gliederung`: outline, shown after submission.',
        '`bearbeitervermerk` and `zusatzmaterial`: visible during the exam, shown inside the case panel.',
        '`korrekturhinweise`: notes for graders, shown after submission.',
        'Example: `[{"sachverhalt": "A sells B …", "musterloesung": "A. Claim …"}, {"sachverhalt": "…", "musterloesung": "…"}]`',
      ],
    },
    tips: {
      de: ['Die Hinweise unter **Freigabe** auf der Projektseite prüfen genau diese Felder und melden z.B. *Die Aufgaben enthalten keine Musterlösung.*'],
      en: ['The hints under **Sharing** on the project page check exactly these fields and report e.g. *The tasks contain no model solution.*'],
    },
    keywords: { de: ['Klausurensammlung', 'sachverhalt', 'musterloesung', 'Felder', 'JSON-Struktur', 'mehrere Klausuren'], en: ['exam collection', 'fields', 'json structure', 'multiple exams'] },
  },
  {
    id: 'export-import-project',
    category: 'data',
    title: { de: 'Wie exportiere ich Aufgaben oder ein ganzes Projekt und importiere es wieder?', en: 'How do I export tasks or a whole project and import it again?' },
    summary: {
      de: '**Aufgaben** eines Projekts: Seite *Projektdaten* → Export-Symbol, liefert JSON. **Ganze Projekte** inklusive Konfiguration, Annotationen und Bewertungen: in der Projektliste ankreuzen → **Aktionen → Ausgewählte Projekte exportieren** (ZIP). Wieder einspielen über **Mehr → Projekt importieren**.',
      en: '**Tasks** of a project: *Project data* page → export icon, gives JSON. **Whole projects** including configuration, annotations and evaluations: tick them in the project list → **Actions → Export selected projects** (ZIP). Bring them back via **More → Import project**.',
    },
    steps: {
      de: [
        '**Aufgaben exportieren**: Projektseite → *Projektdaten* → Export-Symbol. Mit aktiven Filtern oder Auswahl wird nur die Teilmenge exportiert. Der Export läuft im Hintergrund, danach erscheint der Download.',
        '**Projekt exportieren**: [Projekte](/projects) → Projekte ankreuzen → **Aktionen → Ausgewählte Projekte exportieren**. Sie erhalten `benger-projects-full-<Datum>.zip`.',
        '**Projekt importieren**: [Projekte](/projects) → **Mehr → Projekt importieren** → `.json` oder `.zip` wählen. Nach dem Import öffnet sich das neue Projekt.',
      ],
      en: [
        '**Export tasks**: project page → *Project data* → export icon. With active filters or a selection only that subset is exported. The export runs in the background, then the download appears.',
        '**Export project**: [Projects](/projects) → tick projects → **Actions → Export selected projects**. You get `benger-projects-full-<date>.zip`.',
        '**Import project**: [Projects](/projects) → **More → Import project** → choose `.json` or `.zip`. The new project opens after the import.',
      ],
    },
    pitfalls: {
      de: [
        'Ein importiertes Projekt ist eine Kopie mit neuen IDs. Nutzer:innen und Organisationen werden nicht mitkopiert, die Sichtbarkeit setzen Sie neu.',
        '*Nicht unterstützte Dateiformatversion* heißt, die Datei stammt aus einer älteren oder fremden Version. Exportieren Sie sie erneut aus der aktuellen Plattform.',
        'Sehr große Aufgaben-Exporte mit Filtern sind gedeckelt. Grenzen Sie enger ein oder exportieren Sie ohne Filter.',
      ],
      en: [
        'An imported project is a copy with new IDs. Users and organizations are not copied, you set the visibility anew.',
        '*Unsupported file format version* means the file comes from an older or foreign version. Export it again from the current platform.',
        'Very large filtered task exports are capped. Narrow the filter or export without filters.',
      ],
    },
    keywords: { de: ['Export', 'exportieren', 'ZIP', 'Backup', 'Sicherung', 'Projekt importieren', 'Anki'], en: ['export', 'zip', 'backup', 'import project', 'anki'] },
  },
]

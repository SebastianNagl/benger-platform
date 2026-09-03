import type { HowToGuide } from '@/lib/howto'

export const ANNOTATION_GUIDES: HowToGuide[] = [
  {
    id: 'labeling-templates',
    category: 'annotation',
    title: { de: 'Welche Annotationsvorlagen gibt es und wann nehme ich welche?', en: 'Which labeling templates exist and when do I use which?' },
    summary: {
      de: 'Im Schritt **Annotation einrichten** wählen Sie aus der Vorlagen-Galerie: *Frage-Antwort*, *Multiple-Choice*, *Span-Annotation*, *Klausurlösung*, *Karteikarten (leer)* oder *Benutzerdefiniert* (eigenes XML). Die Vorlage bestimmt, welche Felder Annotierende sehen und ausfüllen.',
      en: 'In the **Labeling setup** step you choose from the template gallery: *Question answering*, *Multiple choice*, *Span annotation*, *Klausurlösung*, *Flashcards (empty)* or *Custom* (your own XML). The template defines which fields annotators see and fill in.',
    },
    steps: {
      de: [
        '**Frage-Antwort**: Kontext und Frage anzeigen, Freitextantwort erfassen. Daten brauchen `context` und `question`.',
        '**Multiple-Choice**: Frage mit Optionen A bis D, optional Begründung. Daten brauchen `question` und `context`.',
        '**Span-Annotation**: Textstellen markieren und beschriften (Person, Organisation, Norm …). Daten brauchen `text`.',
        '**Klausurlösung**: Angabe, Notizen, Gliederung und Lösung, mit Markierungen im Sachverhalt. Daten brauchen `sachverhalt` und `musterloesung`. Wird bei Projekttyp *Klausur* automatisch gesetzt.',
        '**Karteikarten (leer)**: Vorder- und Rückseite. Daten brauchen `front` und `back`. Setzt den Projekttyp auf *Kartenstapel*.',
        '**Benutzerdefiniert**: eigenes XML, siehe „Wie bearbeite ich das XML der Annotationsoberfläche?“.',
      ],
      en: [
        '**Question answering**: show context and question, capture a free-text answer. Data needs `context` and `question`.',
        '**Multiple choice**: question with options A to D, optional reasoning. Data needs `question` and `context`.',
        '**Span annotation**: mark and label text spans (person, organization, statute …). Data needs `text`.',
        '**Klausurlösung**: case, notes, outline and solution, with highlights in the case text. Data needs `sachverhalt` and `musterloesung`. Set automatically for project type *Exam*.',
        '**Flashcards (empty)**: front and back. Data needs `front` and `back`. Sets the project type to *Flashcard deck*.',
        '**Custom**: your own XML, see “How do I edit the XML of the annotation interface?”.',
      ],
    },
    tips: {
      de: ['Wählen Sie keine Vorlage, bekommt das Projekt eine minimale Vorlage mit einem Textfeld `text` und einer Freitextantwort.'],
      en: ['If you pick no template, the project gets a minimal template with a `text` field and a free-text answer.'],
    },
    keywords: { de: ['Vorlage', 'Template', 'Galerie', 'Frage-Antwort', 'Multiple-Choice', 'Span', 'Klausurlösung', 'Karteikarten'], en: ['template', 'gallery', 'question answering', 'multiple choice', 'span', 'flashcards'] },
  },
  {
    id: 'edit-label-xml',
    category: 'annotation',
    title: { de: 'Wie bearbeite ich das XML der Annotationsoberfläche (Label-Konfiguration)?', en: 'How do I edit the XML of the annotation interface (label configuration)?' },
    summary: {
      de: 'Projektseite → **Annotationskonfiguration → Label-Konfiguration → Konfiguration bearbeiten**. Das XML folgt dem Label-Studio-Schema: ein `<View>` als Wurzel, Anzeige-Tags wie `<Text>` mit `value="$feld"`, Eingabe-Tags wie `<TextArea>` oder `<Choices>` mit `name` und `toName`.',
      en: 'Project page → **Annotation configuration → Label configuration → Edit configuration**. The XML follows the Label Studio schema: a `<View>` root, display tags such as `<Text>` with `value="$field"`, input tags such as `<TextArea>` or `<Choices>` with `name` and `toName`.',
    },
    steps: {
      de: [
        'Öffnen Sie den Editor. Das Panel **Available Task Fields** darüber listet die Felder Ihrer Aufgaben. Ein Klick kopiert `$feldname`.',
        '**Anzeigen**: `<Text name="fall" value="$sachverhalt"/>` zeigt ein Datenfeld. `<Header value="Frage"/>` ist eine Überschrift. `<Image>` zeigt Bilder.',
        '**Eingeben**: `<TextArea name="antwort" toName="fall" rows="6"/>` (Freitext), `<Choices name="wahl" toName="fall"><Choice value="A"/><Choice value="B"/></Choices>` (Auswahl), `<Labels name="marken" toName="fall"><Label value="Norm"/></Labels>` (Textstellen markieren), `<Rating>`, `<Likert>`, `<Number>`.',
        'Jedes Eingabe-Tag braucht ein eindeutiges `name` (wird der Schlüssel der Annotation) und ein `toName`, das auf ein Anzeige-Tag zeigt.',
        '**Konfiguration speichern**. Prüfen Sie das Ergebnis über **Annotation starten**, eine Live-Vorschau gibt es nicht.',
      ],
      en: [
        'Open the editor. The **Available Task Fields** panel above lists the fields of your tasks. One click copies `$fieldname`.',
        '**Display**: `<Text name="fall" value="$sachverhalt"/>` shows a data field. `<Header value="Frage"/>` is a heading. `<Image>` shows images.',
        '**Input**: `<TextArea name="antwort" toName="fall" rows="6"/>` (free text), `<Choices name="wahl" toName="fall"><Choice value="A"/><Choice value="B"/></Choices>` (selection), `<Labels name="marken" toName="fall"><Label value="Norm"/></Labels>` (mark spans), `<Rating>`, `<Likert>`, `<Number>`.',
        'Every input tag needs a unique `name` (becomes the annotation key) and a `toName` pointing at a display tag.',
        '**Save configuration**. Check the result via **Start annotation**, there is no live preview.',
      ],
    },
    tips: {
      de: [
        'Klausur-Tags der erweiterten Edition: `<Angabe value="$sachverhalt" bearbeitervermerk="$bearbeitervermerk" zusatzmaterial="$zusatzmaterial">` mit `<Label>`-Kindern als Markierungsfarben, `<Notizen>`, `<Gliederung>` und `<Loesung linkedTo="gliederung">`. Die Vorlage *Klausurlösung* zeigt das vollständige Beispiel.',
        '`$feld.unterfeld` greift auf verschachtelte Daten zu. Feldnamen werden ohne Groß-/Kleinschreibung zugeordnet.',
        'Die Referenz aller Standard-Tags: [Label Studio Tags](https://labelstud.io/tags/).',
      ],
      en: [
        'Exam tags of the extended edition: `<Angabe value="$sachverhalt" bearbeitervermerk="$bearbeitervermerk" zusatzmaterial="$zusatzmaterial">` with `<Label>` children as highlight colors, `<Notizen>`, `<Gliederung>` and `<Loesung linkedTo="gliederung">`. The *Klausurlösung* template shows the complete example.',
        '`$field.subfield` reaches nested data. Field names are matched case-insensitively.',
        'The reference of all standard tags: [Label Studio tags](https://labelstud.io/tags/).',
      ],
    },
    pitfalls: {
      de: [
        'Ein unbekannter Tag wird ohne Fehlermeldung einfach nicht gerendert. Fehlt ein Feld in der Oberfläche, prüfen Sie den Tag-Namen. Erscheint *Unknown component type: Gliederung*, läuft die Community-Edition ohne die Klausur-Tags.',
        '`required="true"` prüft nur, ob das **Datenfeld** in der Aufgabe vorhanden ist. Es zwingt Annotierende nicht, etwas einzutragen.',
        'Der Editor prüft nur, ob das XML wohlgeformt ist und ein `<View>` enthält. Fehlende `name`/`toName` fallen erst beim Annotieren auf.',
        '**Benennen Sie ein Eingabefeld nicht um, wenn schon Annotationen existieren.** Alte Annotationen und die Bewertungsverfahren (Vorhersagefeld, z.B. `loesung`) verweisen auf den alten Namen.',
      ],
      en: [
        'An unknown tag is silently not rendered. If a field is missing in the interface, check the tag name. *Unknown component type: Gliederung* means the community edition is running without the exam tags.',
        '`required="true"` only checks that the **data field** exists in the task. It does not force annotators to enter something.',
        'The editor only checks that the XML is well-formed and contains a `<View>`. Missing `name`/`toName` only show up when annotating.',
        '**Do not rename an input field once annotations exist.** Old annotations and the evaluation methods (prediction field, e.g. `loesung`) reference the old name.',
      ],
    },
    links: [{ label: { de: 'Label Studio Tag-Referenz', en: 'Label Studio tag reference' }, href: 'https://labelstud.io/tags/' }],
    keywords: { de: ['XML', 'Label-Konfiguration', 'Label Studio', 'View', 'TextArea', 'Choices', 'Labels', 'Angabe', 'Gliederung', 'Loesung', 'Oberfläche anpassen', 'Interface'], en: ['xml', 'label config', 'label studio', 'view', 'textarea', 'choices', 'labels', 'interface', 'customize'] },
  },
  {
    id: 'annotation-instructions',
    category: 'annotation',
    title: { de: 'Wie gebe ich Annotierenden Anweisungen und wie funktioniert das Annotieren?', en: 'How do I give annotators instructions and how does annotating work?' },
    summary: {
      de: 'Anweisungen schreiben Sie im Assistenten (Schritt *Anweisungen*) oder auf der Projektseite unter **Annotationskonfiguration → Annotationsanweisungen**. Annotierende starten über **Annotation starten** oder **Meine Aufgaben**, bearbeiten Aufgabe für Aufgabe und geben mit *Absenden* ab.',
      en: 'Write instructions in the wizard (step *Instructions*) or on the project page under **Annotation configuration → Annotation instructions**. Annotators start via **Start annotation** or **My tasks**, work task by task and submit with *Submit*.',
    },
    steps: {
      de: [
        '**Annotationsanweisungen** (Markdown) werden Annotierenden über der Aufgabe angezeigt.',
        '**Bedingte Anweisungsvarianten** für A/B-Tests: mehrere Varianten mit Gewichten in Prozent, die zusammen 100 ergeben müssen.',
        'Annotierende sehen offene bzw. zugewiesene Aufgaben, können überspringen (wenn erlaubt) und nach der Abgabe ihre eigene Abgabe unter **Meine Aufgaben** einsehen.',
        'Mit **Musterlösung nach Abgabe anzeigen** sehen sie nach dem Absenden auch die Referenzfelder. Ist die **Sofort-Evaluation** aktiv, erscheint direkt das KI-Ergebnis.',
        '**Wiederherstellbare Zwischenstände** speichern alle fünf Minuten einen Stand, den Annotierende zurückholen können.',
      ],
      en: [
        '**Annotation instructions** (Markdown) are shown to annotators above the task.',
        '**Conditional instruction variants** for A/B tests: several variants with percentage weights that must add up to 100.',
        'Annotators see open or assigned tasks, may skip (if allowed) and can review their own submission under **My tasks** afterwards.',
        'With **Show model solution after submission** they also see the reference fields after submitting. If **immediate evaluation** is on, the AI result appears right away.',
        '**Restorable checkpoints** save a snapshot every five minutes that annotators can bring back.',
      ],
    },
    keywords: { de: ['Anweisungen', 'Instruktionen', 'annotieren', 'Absenden', 'Meine Aufgaben', 'Varianten', 'A/B', 'Zwischenstand'], en: ['instructions', 'annotate', 'submit', 'my tasks', 'variants', 'a/b', 'checkpoint'] },
  },
]

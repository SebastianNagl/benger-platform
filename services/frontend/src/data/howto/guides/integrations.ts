import type { HowToGuide } from '@/lib/howto'

export const INTEGRATION_GUIDES: HowToGuide[] = [
  {
    id: 'lti-setup',
    category: 'integrations',
    title: { de: 'Wie binde ich BenGER an Moodle oder ILIAS an (LTI)?', en: 'How do I connect BenGER to Moodle or ILIAS (LTI)?' },
    summary: {
      de: 'Über **LTI 1.3**. Die Plattform-Administration erzeugt für Ihre Organisation einen einmaligen Einladungslink, den die Moodle- oder ILIAS-Administration Ihrer Hochschule als externes Tool einträgt. Danach verknüpfen Lehrende Aktivitäten mit Klausuren, Studierende starten die Klausur aus dem Kurs und Noten fließen zurück.',
      en: 'Via **LTI 1.3**. The platform administration creates a one-time invitation link for your organization, which your university’s Moodle or ILIAS administration enters as an external tool. Afterwards teachers link activities to exams, students start the exam from the course and grades flow back.',
    },
    steps: {
      de: [
        '**Vorbereitung in der Organisation** (Admin): Unter *API-Schlüssel* muss **Organisation stellt API-Schlüssel bereit** eingeschaltet sein und ein Schlüssel für das Bewertungsmodell (OpenAI) vorliegen. Sonst scheitert die KI-Korrektur für Studierende aus der Lernplattform.',
        '**Einladungslink**: Schreiben Sie uns oder bitten Sie Ihre Plattform-Administration. Sie erstellt unter *Benutzer & Organisationen → Ihre Organisation → Lernplattform (LTI)* einen Link (14 Tage gültig) und schickt ihn Ihnen.',
        '**In Moodle** (Administration): *Website-Administration → Plugins → Externes Tool → Tools verwalten* → URL einfügen → **LTI Advantage hinzufügen** → Tool aktivieren. In ILIAS: LTI-Konsument mit der JWKS-URL registrieren, nie mit eingefügtem Schlüssel.',
        '**Anbindung aktivieren**: Nach der Registrierung schaltet die Plattform-Administration die Anbindung in BenGER frei.',
      ],
      en: [
        '**Prepare the organization** (admin): under *API keys* switch on **Organization provides API keys** and store a key for the grading model (OpenAI). Otherwise AI grading fails for students coming from the learning platform.',
        '**Invitation link**: write to us or ask your platform administration. They create a link (valid 14 days) under *Users & organizations → your organization → Learning platform (LTI)* and send it to you.',
        '**In Moodle** (administration): *Site administration → Plugins → External tool → Manage tools* → paste the URL → **Add LTI Advantage** → activate the tool. In ILIAS: register the LTI consumer with the JWKS URL, never with a pasted key.',
        '**Enable the connection**: after registration the platform administration enables the connection in BenGER.',
      ],
    },
    tips: {
      de: [
        'Für Lehrende muss die Lernplattform Name und E-Mail an das Tool übermitteln (*Always*), sonst entsteht beim ersten Start ein anonymes Konto ohne Klausuren.',
        'Das Tool muss in einem **neuen Fenster** starten. Einbettung im Rahmen (iframe) wird nicht unterstützt.',
        'ILIAS zeigt Noten als Lernfortschritt relativ zum Mastery Score. Empfehlung: Mastery Score 22, das entspricht 4 von 18 Notenpunkten.',
      ],
      en: [
        'For teachers the learning platform must send name and email to the tool (*Always*), otherwise the first launch creates an anonymous account without exams.',
        'The tool must open in a **new window**. Embedding in a frame (iframe) is not supported.',
        'ILIAS shows grades as learning progress relative to the mastery score. Recommendation: mastery score 22, which equals 4 of 18 grade points.',
      ],
    },
    links: [{ label: { de: 'Klausur mit einer Aktivität verknüpfen', en: 'Linking an exam to an activity' }, href: '/how-to#lti-teacher' }],
    keywords: { de: ['LTI', 'Moodle', 'ILIAS', 'Lernplattform', 'Integration', 'externes Tool', 'Anbindung', 'Registrierung'], en: ['lti', 'moodle', 'ilias', 'lms', 'integration', 'external tool', 'registration'] },
  },
  {
    id: 'lti-teacher',
    category: 'integrations',
    title: { de: 'Wie verknüpfe ich als Lehrende:r eine Moodle-Aktivität mit einer Klausur?', en: 'How do I, as a teacher, link a Moodle activity to an exam?' },
    summary: {
      de: 'Legen Sie im Kurs eine Aktivität *Externes Tool* mit dem BenGER-Tool an und geben Sie ihr eine Bewertung. Beim **ersten Start** öffnet sich in BenGER die Seite *Aktivität verknüpfen*: Klausur wählen oder neu anlegen, **Verknüpfen**. Studierende landen ab dann direkt in der Klausur.',
      en: 'Create an *External tool* activity in the course with the BenGER tool and give it a grade. On the **first launch** BenGER opens the *Link activity* page: pick an exam or create a new one, **Link**. Students then land directly in the exam.',
    },
    steps: {
      de: [
        'Moodle: *Aktivität anlegen → Externes Tool* → BenGER-Tool wählen → Bewertung aktiv lassen (Maximum 100 ist in Ordnung, BenGER liefert 0 bis 18 Notenpunkte und Moodle rechnet um).',
        'Aktivität als Lehrende:r öffnen. In BenGER erscheint **Aktivität verknüpfen** mit Ihren Klausuren. Nur Klausuren mit KI-Korrektur nach dem Falllösungsschema sind verknüpfbar.',
        '**Verknüpfen**. Die Tabelle *Notenübertragung an die Lernplattform* auf derselben Seite zeigt später jede Abgabe mit Status *Ausstehend*, *Übertragen* oder *Fehlgeschlagen*.',
        'Studierende starten die Aktivität, stimmen einmalig der Datenverarbeitung zu und lösen die Klausur. Die KI-Note wird sofort übertragen, eine spätere menschliche Korrektur überschreibt sie.',
      ],
      en: [
        'Moodle: *Add activity → External tool* → pick the BenGER tool → keep grading on (maximum 100 is fine, BenGER sends 0 to 18 grade points and Moodle rescales).',
        'Open the activity as a teacher. BenGER shows **Link activity** with your exams. Only exams with AI grading on the case-solution scheme can be linked.',
        '**Link**. The table *Grade sync to the learning platform* on the same page later shows every submission with status *Pending*, *Synced* or *Failed*.',
        'Students start the activity, consent once to data processing and solve the exam. The AI grade is synced immediately; a later human grading overwrites it.',
      ],
    },
    pitfalls: {
      de: [
        'Sobald Noten übertragen wurden, lässt sich die Verknüpfung nicht mehr ändern. Legen Sie für eine andere Klausur eine neue Aktivität an.',
        '*Diese Aktivität kann keine Noten empfangen*: Grade Sync ist in der Aktivität nicht aktiv. In Moodle die Bewertung einschalten, in ILIAS *Advanced Grading Services* aktivieren, dann die Aktivität neu öffnen.',
        'Klausuren mit eigener Rubrik (benutzerdefinierter Judge) können derzeit keine Noten zurückgeben.',
      ],
      en: [
        'Once grades have been synced the link cannot be changed. Create a new activity for another exam.',
        '*This activity cannot receive grades*: grade sync is off for the activity. Enable grading in Moodle, or *Advanced Grading Services* in ILIAS, then reopen the activity.',
        'Exams with a custom rubric (custom judge) cannot return grades yet.',
      ],
    },
    keywords: { de: ['Aktivität verknüpfen', 'Notenübertragung', 'Grade Sync', 'Moodle Kurs', 'Bewertung', 'Notenbuch'], en: ['link activity', 'grade sync', 'moodle course', 'gradebook'] },
  },
]

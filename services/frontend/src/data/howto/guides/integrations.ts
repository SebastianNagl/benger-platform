import type { HowToGuide } from '@/lib/howto'

const TECH_REFERENCE_HREF =
  'https://github.com/SebastianNagl/benger-platform/blob/main/docs/lms-integration.md'

const TECH_REFERENCE_LINK = {
  label: {
    de: 'Technische Referenz für Ihre IT (LTI 1.3)',
    en: 'Technical reference for your IT (LTI 1.3)',
  },
  href: TECH_REFERENCE_HREF,
}

export const INTEGRATION_GUIDES: HowToGuide[] = [
  {
    id: 'lti-setup',
    category: 'integrations',
    title: {
      de: 'Wie verbinde ich unsere Organisation mit Moodle oder ILIAS (LTI)?',
      en: 'How do I connect our organization to Moodle or ILIAS (LTI)?',
    },
    summary: {
      de: 'Über **LTI 1.3**. Als **Admin Ihrer Organisation** richten Sie die Anbindung selbst ein: Sie erstellen einen Einladungslink, die Administration der Lernplattform trägt ihn ein, und die Anbindung ist **sofort aktiv**. Gruppen-Admins können das für ihre Gruppen tun.',
      en: 'Via **LTI 1.3**. As an **admin of your organization** you set up the connection yourself: you create an invitation link, the learning platform administration enters it, and the connection is **active at once**. Group admins can do this for their groups.',
    },
    steps: {
      de: [
        '**API-Schlüssel vorbereiten**: [Benutzer & Organisationen](/users-organizations) → Organisation → **API-Schlüssel** → **Organisation stellt API-Schlüssel bereit** einschalten und einen Schlüssel für das Bewertungsmodell hinterlegen. Standard sind Modelle von OpenAI. Ohne Schlüssel gibt es keine KI-Korrektur und keinen Rückfall auf einen anderen Schlüssel.',
        '**Panel öffnen**: [Benutzer & Organisationen](/users-organizations) → Organisation wählen → **Mehr** → **Lernplattform (LTI)**. Oben zeigt **KI-Bewertung und API-Schlüssel**, ob die KI-Korrektur eingerichtet ist.',
        '**Adresse wählen**: Unter **Lernplattform verbinden** wählen Sie die **Adresse für die Lernplattform**. Mit der **Studierenden-Adresse** arbeiten alle in der Studierendenoberfläche, auch Lehrende. Nur die Korrektur öffnet sich in der Expertenoberfläche. Mit der **BenGER-Adresse** arbeiten Studierende in der Studierendenoberfläche und Lehrende in der Expertenoberfläche. Gibt es nur eine Adresse, entfällt die Auswahl.',
        '**Einladungslink erstellen**: Wählen Sie bei Bedarf eine **Gruppe**. Dann treten die Personen aus der Lernplattform dieser Gruppe bei. Klicken Sie auf **Einladungslink erstellen**, kopieren Sie den Link und schicken Sie ihn an die Administration der Lernplattform. Der Link wird nur einmal angezeigt, gilt 14 Tage und funktioniert einmal.',
        '**Lernplattform registriert das Tool**: In Moodle fügt die Administration den Link unter *Website-Administration → Plugins → Aktivitäten → Externes Tool → Tools verwalten* bei **LTI Advantage hinzufügen** ein. Fragt Moodle, ob ein vorhandenes Tool aktualisiert werden soll, wählt sie **Als neues externes Tool registrieren**, außer sie ersetzt bewusst eine frühere Anbindung. Dann aktiviert sie das Tool. ILIAS ab Version 10.9 nimmt den Link beim Anlegen eines LTI-Konsumenten an. Danach aktiviert die ILIAS-Administration beim Provider **Advanced Grading Services**, sonst kommen keine Noten an. Die Anbindung steht im Panel und ist **sofort aktiv**.',
        '**Tool in Moodle einstellen**: Moodle legt jedes per Link registrierte Tool eingebettet, nur als vorkonfiguriertes Tool und mit an Lehrende delegierten Bewertungen an. Das Tool kann das nicht ändern. Die Moodle-Administration öffnet deshalb die Einstellungen des Tools (Symbol *Bearbeiten* auf der Tool-Karte) und setzt *Verwendung der Toolkonfiguration* auf **In Aktivitätsauswahl und als vorkonfiguriertes Tool anzeigen**, *Standard-Startcontainer* auf **Neues Fenster** und *Bewertungen aus dem Tool akzeptieren* auf **Immer**.',
        '**Teststart**: Legen Sie in einem Testkurs eine Aktivität mit Bewertung an. Öffnen Sie sie zuerst als Lehrperson: Nach der Zustimmung verknüpfen Sie eine Klausur. Öffnen Sie sie danach als Studierende: Nach der Zustimmung öffnet sich die Klausur. Ist noch keine Klausur verknüpft, sehen Studierende nur den Hinweis `not_linked`.',
      ],
      en: [
        '**Prepare the API keys**: [Users & organizations](/users-organizations) → organization → **API keys** → switch on **Organization provides API keys** and store a key for the grading model. The default models are from OpenAI. Without a key there is no AI grading and no fallback to another key.',
        '**Open the panel**: [Users & organizations](/users-organizations) → pick the organization → **More** → **Learning platform (LTI)**. At the top, **AI grading and API keys** shows whether AI grading is set up.',
        '**Choose the address**: under **Connect learning platform**, choose the **Address for the learning platform**. With the **Student address** everyone works in the student interface, teachers included. Only the grading view opens in the expert interface. With the **BenGER address** students work in the student interface and teachers in the expert interface. If there is only one address, there is nothing to choose.',
        '**Create the invitation link**: pick a **group** if needed. People from the learning platform then join that group. Click **Create invitation link**, copy the link and send it to the learning platform administration. The link is shown only once, is valid for 14 days and works once.',
        '**The learning platform registers the tool**: in Moodle the administration pastes the link under *Site administration → Plugins → Activity modules → External tool → Manage tools* into **Add LTI Advantage**. If Moodle asks whether to update an existing tool, they choose **Register as a new external tool**, unless they replace an earlier connection on purpose. Then they activate the tool. ILIAS 10.9 and later accepts the link when an LTI consumer is created. The ILIAS administration then switches on **Advanced Grading Services** on the provider, or no grades arrive. The connection shows up in the panel and is **active at once**.',
        '**Adjust the tool in Moodle**: Moodle creates every tool registered by link as embedded, as a preconfigured tool only, and with grades delegated to teachers. The tool cannot change that. So the Moodle administration opens the tool settings (the *Edit* icon on the tool card) and sets *Tool configuration usage* to **Show in activity chooser and as a preconfigured tool**, *Default launch container* to **New window** and *Accept grades from the tool* to **Always**.',
        '**Test launch**: create an activity with a grade in a test course. Open it first as a teacher: after the consent page, link an exam. Then open it as a student: after the consent page, the exam opens. If no exam is linked yet, students only see the `not_linked` notice.',
      ],
    },
    tips: {
      de: [
        'Ohne Einladungslink legt **Neue Anbindung** die Anbindung von Hand an. Das Formular zeigt die drei Tool-URLs schon vor dem Speichern. Schicken Sie sie an die Administration der Lernplattform. Sie meldet Ihnen nach dem Speichern des Tools die Client-ID und die Deployment-ID (ILIAS: Provider-ID). Tragen Sie dann die URLs der Lernplattform, die Client-ID und die Deployment-IDs ein und speichern Sie. Die Tool-URLs stehen später auch unter **Tool-Konfiguration**. Auch diese Anbindung ist sofort aktiv.',
        'Die Lernplattform muss Name und E-Mail-Adresse übermitteln. In Moodle müssen beide auf **Immer** stehen. Der Einladungslink fordert das an. Prüfen Sie die Einstellung nach der Registrierung in den Tool-Einstellungen. In ILIAS wählen Sie auch nach der Registrierung per Link die Identifizierung per E-Mail-Adresse und den vollständigen Namen.',
        'Für Moodle empfiehlt sich bei *IMS LTI Aufgaben und Bewertung* die Einstellung **Service für die Synchronisation von Bewertungen und die Verwaltung der Spalten nutzen**. Dann erhält Moodle neben der Endnote auch eine Spalte **KI-Bewertung**. Der Einladungslink fordert das an. Lehrende nehmen diese Spalte aus der Kursgesamtbewertung heraus, siehe [Noten aus der Lernplattform](/how-to#lti-grades).',
        'Das Tool muss in einem **neuen Fenster** starten. In Moodle entscheidet das der *Standard-Startcontainer* des Tools, nicht die einzelne Aktivität.',
        'ILIAS zeigt Noten als Lernfortschritt. Empfehlung: Mastery Score 22, das entspricht 4 von 18 Notenpunkten.',
        'Gruppen-Admins erstellen Einladungen und Anbindungen nur für ihre Gruppen. **Organisation stellt API-Schlüssel bereit** kann nur ein Org-Admin einschalten.',
      ],
      en: [
        'Without an invitation link, **New connection** creates the connection by hand. The form shows the three tool URLs before anything is saved. Send them to the learning platform administration. After saving the tool, they send you the client ID and the deployment ID (ILIAS: provider ID). Then enter the learning platform URLs, the client ID and the deployment IDs, and save. The tool URLs are also shown later under **Tool configuration**. This connection is active at once as well.',
        'The learning platform must send name and email address. In Moodle both must be set to **Always**. The invitation link requests this. Check the tool settings after the registration. In ILIAS, choose identification by email address and the full name, also after a registration by link.',
        'For Moodle, set *IMS LTI Assignment and Grade Services* to **Use this service for grade sync and column management**. Moodle then gets a **KI-Bewertung** column next to the final grade. The invitation link requests this. Teachers take this column out of the course total, see [Grades and the learning platform](/how-to#lti-grades).',
        'The tool must open in a **new window**. In Moodle the tool’s *Default launch container* decides this, not the single activity.',
        'ILIAS shows grades as learning progress. Recommendation: mastery score 22, which equals 4 of 18 grade points.',
        'Group admins create invitations and connections for their groups only. Only an org admin can switch on **Organization provides API keys**.',
      ],
    },
    pitfalls: {
      de: [
        'Die Anbindung ist aktiv, sobald die Lernplattform den Link einlöst. Schließen Sie den Vertrag mit uns vorher ab und erstellen Sie den Link erst danach.',
        'Einen Link, den Sie nicht mehr brauchen, entwerten Sie unter **Offene Einladungen** mit **Widerrufen**.',
        'Startet das Tool eingebettet im Kurs (iframe), landen Personen auf der Anmeldeseite statt in der Klausur. Nach einer Registrierung per Link ist das in Moodle voreingestellt. Stellen Sie den *Standard-Startcontainer* des Tools auf **Neues Fenster**.',
        'Haben Moodle-Aktivitäten keine Bewertung, delegiert *Bewertungen aus dem Tool akzeptieren* noch an die Lehrenden. Stellen Sie es auf **Immer**. Sonst müssen Lehrende in jeder Aktivität den Haken *… erlauben, Bewertungen hinzuzufügen* setzen.',
      ],
      en: [
        'The connection is active as soon as the learning platform redeems the link. Sign the contract with us first and create the link only after that.',
        'Revoke a link you no longer need under **Pending invitations** with **Revoke**.',
        'If the tool starts embedded in the course (iframe), people land on the login page instead of the exam. After a registration by link, Moodle presets exactly that. Set the tool’s *Default launch container* to **New window**.',
        'If Moodle activities have no grade, *Accept grades from the tool* still delegates to teachers. Set it to **Always**. Otherwise teachers must tick *Allow … to add grades in the gradebook* in every activity.',
      ],
    },
    links: [
      {
        label: {
          de: 'Anbindung verwalten',
          en: 'Managing a connection',
        },
        href: '/how-to#lti-manage',
      },
      {
        label: {
          de: 'Klausur mit einer Aktivität verknüpfen',
          en: 'Linking an exam to an activity',
        },
        href: '/how-to#lti-teacher',
      },
      {
        label: {
          de: 'Datenschutz bei der Anbindung',
          en: 'Data protection for the integration',
        },
        href: '/how-to#lti-privacy',
      },
      {
        label: {
          de: 'Start aus Moodle oder ILIAS schlägt fehl',
          en: 'Launch from Moodle or ILIAS fails',
        },
        href: '/how-to#ts-lti-errors',
      },
      TECH_REFERENCE_LINK,
    ],
    keywords: {
      de: [
        'LTI',
        'Moodle',
        'ILIAS',
        'Lernplattform',
        'Integration',
        'externes Tool',
        'Anbindung',
        'Registrierung',
        'Einladungslink',
        'Dynamic Registration',
        'Studierenden-Adresse',
        'BenGER-Adresse',
        'Tools verwalten',
        'Standard-Startcontainer',
        'Aktivitätsauswahl',
        'Bewertungen aus dem Tool akzeptieren',
      ],
      en: [
        'lti',
        'moodle',
        'ilias',
        'lms',
        'integration',
        'external tool',
        'registration',
        'invitation link',
        'dynamic registration',
        'student address',
        'benger address',
        'manage tools',
        'default launch container',
        'activity chooser',
        'accept grades from the tool',
      ],
    },
  },
  {
    id: 'lti-manage',
    category: 'integrations',
    title: {
      de: 'Wie verwalte ich eine Anbindung an Moodle oder ILIAS?',
      en: 'How do I manage a connection to Moodle or ILIAS?',
    },
    summary: {
      de: 'Im Panel **Lernplattform (LTI)** hat jede Anbindung eine eigene Karte. Dort schalten Sie die Anbindung und ihre Deployments ein und aus, legen die Rolle der Lehrenden fest und sehen Aktivitäten, LMS-Konten, Notenübertragungen und den Verlauf. Das Panel steht Org-Admins offen, Gruppen-Admins für die Anbindungen ihrer Gruppen.',
      en: 'In the **Learning platform (LTI)** panel every connection has its own card. There you switch the connection and its deployments on and off, set the role of teachers and see activities, LMS accounts, grade transfers and the history. The panel is open to org admins, and to group admins for their groups’ connections.',
    },
    steps: {
      de: [
        '**Ein- und ausschalten**: **Anbindung deaktivieren** sperrt sofort alle Starts, die Seiten der Anbindung in der App und die Notenübertragung für diese Lernplattform. **Anbindung aktivieren** hebt das wieder auf.',
        '**Deployments**: Deployment-IDs hinzufügen oder entfernen und einzeln mit **Deployment ausschalten** sperren. Die anderen Deployments laufen weiter. In ILIAS ist die Deployment-ID die numerische Provider-ID.',
        '**Bearbeiten**: Die **Org-Rolle für Lehrende** ist Mitwirkender (contributor), Org-Admin (org_admin) oder keine Org-Rolle (none). Bei einer Gruppen-Anbindung wird Org-Admin zu Mitwirkender plus Gruppen-Admin. Gruppen-Admins vergeben höchstens Mitwirkender, und nur, wenn sie selbst mindestens Mitwirkende sind. Hier ändern Sie auch Adresse, Gruppe, **Org-Rolle für Studierende** und **Verknüpfung mit bestehenden Konten anbieten**.',
        '**Aktivitäten**: jede Aktivität mit Kurs, verknüpfter Klausur, Teilnehmenden, Stand der Übertragungen und dem Stand der Spalte **KI-Bewertung**. **Notenübersicht öffnen** führt zur Aktivitätsübersicht.',
        '**LMS-Konten**: alle Personen der Anbindung mit Name, E-Mail-Adresse, Pseudonym, Rolle, Einwilligung und letztem Start, mit Suche. **Verknüpfung lösen** trennt die Kennung der Lernplattform vom Konto. Konten, die die Lernplattform angelegt hat, lassen sich mit **Anonymisieren** anonymisieren.',
        '**Notenübertragungen**: alle, fehlgeschlagene oder ausstehende Übertragungen mit Person, Kurs, Aktivität, Klausur und Fehlertext. Bei fehlgeschlagenen und ausstehenden Übertragungen schickt **Erneut versuchen** die Note sofort.',
        '**Verlauf**: jede Änderung an der Anbindung mit Zeit und handelnder Person. Ruft die Lernplattform das Tool über die andere Adresse auf, zeigt die Karte eine Warnung. **Verlauf aller Anbindungen anzeigen** unten im Panel zeigt zusätzlich Einladungslinks und gelöschte Anbindungen.',
        '**KI-Bewertung und API-Schlüssel**: Oben im Panel steht, ob die Organisation und jede Gruppe mit Anbindung die KI-Korrektur bezahlen kann und welcher Schlüssel fehlt.',
        '**Löschen**: Deaktivieren Sie die Anbindung zuerst. **Löschen** fragt dann, ob die angelegten Konten bestehen bleiben oder anonymisiert werden. Aktivitäten, LMS-Verknüpfungen und alle Teilnahmen und Notenübertragungen samt Übertragungsstand verschwinden. Abgaben und Bewertungen bleiben erhalten. Bereits übertragene Noten bleiben in der Lernplattform. Behaltene Konten bleiben pseudonymisiert. Ihre Namen sehen danach nur noch die Admins Ihrer Organisation und die Administration der Plattform.',
      ],
      en: [
        '**Switch on and off**: **Disable connection** immediately blocks all launches, the connection’s pages in the app and the grade transfer for this learning platform. **Enable connection** lifts that again.',
        '**Deployments**: add or remove deployment IDs and block single ones with **Turn deployment off**. The other deployments keep working. In ILIAS the deployment ID is the numeric provider ID.',
        '**Edit**: the **Org role for teachers** is contributor, org admin (org_admin) or no org role (none). On a group connection, org admin becomes contributor plus group admin. Group admins grant at most contributor, and only if they are at least contributors themselves. Here you also change the address, the group, the **Org role for students** and **Offer linking to existing accounts**.',
        '**Activities**: every activity with course, linked exam, participants, transfer counts and the state of the **KI-Bewertung** column. **Open grade overview** leads to the activity overview.',
        '**LMS accounts**: everyone on the connection with name, email address, pseudonym, role, consent and last launch, with search. **Unlink** separates the learning platform identity from the account. Accounts the learning platform created can be anonymized with **Anonymize**.',
        '**Grade transfers**: all, failed or pending transfers with person, course, activity, exam and error text. For failed and pending transfers, **Retry** sends the grade at once.',
        '**History**: every change to the connection with time and acting person. If the learning platform calls the tool through the other address, the card shows a warning. **Show the history of all connections** at the bottom of the panel also lists invitation links and deleted connections.',
        '**AI grading and API keys**: the top of the panel shows whether the organization and each group with a connection can pay for AI grading, and which key is missing.',
        '**Delete**: disable the connection first. **Delete** then asks whether the accounts it created stay or are anonymized. Activities, LMS links and all participation and grade transfer records, including their transfer state, go away. Submissions and grades are kept. Grades already sent stay in the learning platform. Kept accounts stay pseudonymized. Afterwards only your organization’s admins and the platform administration see their names.',
      ],
    },
    tips: {
      de: [
        'Nach **Verknüpfung lösen** bleiben Konto, Abgaben und Bewertungen bestehen. Die Teilnahme an den Aktivitäten und die Notenübertragungen dieser Anbindung werden entfernt. In der Notenübersicht erscheint die Person erst nach dem nächsten Start wieder. Beim nächsten Start fragt die Anbindung wieder nach Zustimmung. Das Konto wird dabei nur angeboten, wenn es noch die Adresse hat, die die Lernplattform sendet. Sonst, etwa bei einer Platzhalter-Adresse, entsteht ein neues, separates Konto, und die bisherigen Bewertungen bleiben beim alten Konto.',
        'Entfernen Sie eine Person aus der Gruppe einer Anbindung, fügt ein Start sie nicht wieder hinzu. Auch entzogene Gruppen-Admin-Rechte bleiben entzogen. Ein Start von Lehrenden hebt aber eine Annotator-Rolle wieder auf die **Org-Rolle für Lehrende** an.',
        '**Anonymisieren** löscht Name, E-Mail-Adresse, Passwort und die Kennung der Lernplattform und sperrt die Anmeldung. Abgaben und Bewertungen bleiben unter einem neuen Pseudonym für Auswertungen erhalten. Bereits übertragene Noten bleiben in der Lernplattform. Vor dem Anonymisieren zeigt eine Vorschau, was gelöscht wird und was bleibt.',
        'Nicht anonymisieren lassen sich Konten der Plattform-Administration, Ihr eigenes Konto, Konten, die es vor der Verknüpfung schon gab, Konten mit Bezug zu anderen Organisationen oder Gruppen und Konten mit Zahlungsdaten. Gruppen-Admins können keine Org-Admins anonymisieren.',
        'Als Admin sehen Sie die Klarnamen der Personen Ihrer Anbindungen. Andere Mitglieder sehen in Listen das Pseudonym.',
      ],
      en: [
        'After **Unlink** the account, its submissions and its grades stay. The person’s activity participation and grade transfers on this connection are removed, so the person shows up in the grade overview again only after the next launch. On the next launch the connection asks for consent again. It offers the account only if it still has the address the learning platform sends. Otherwise, for example with a placeholder address, a new, separate account is created and the earlier grades stay with the old account.',
        'If you remove a person from a connection’s group, a launch does not add them back. Group admin rights you took away stay removed too. A teacher launch does raise an annotator back to the **Org role for teachers**, though.',
        '**Anonymize** deletes name, email address, password and the learning platform identity and locks the sign-in. Submissions and grades stay for analysis under a new pseudonym. Grades already transferred stay in the learning platform. Before anonymizing, a preview shows what is deleted and what stays.',
        'These accounts cannot be anonymized: accounts of the platform administration, your own account, accounts that existed before the link, accounts tied to other organizations or groups, and accounts with payment records. Group admins cannot anonymize org admins.',
        'As an admin you see the real names of the people on your connections. Other members see the pseudonym in lists.',
      ],
    },
    pitfalls: {
      de: [
        'Fehlt in Moodle die Spalte **KI-Bewertung**, erlaubt Moodle dem Tool keine eigene Spalte. Die Moodle-Administration stellt beim Tool *IMS LTI Aufgaben und Bewertung* auf **Service für die Synchronisation von Bewertungen und die Verwaltung der Spalten nutzen**. Danach die Aktivität erneut öffnen.',
        'Den Privacy-Modus in ILIAS nach dem Start nicht mehr ändern. Er bestimmt die Kennung der Personen, ein Wechsel trennt alle Verknüpfungen.',
        'Anonymisieren lässt sich nicht rückgängig machen. Startet die Person die Aktivität erneut, entsteht ein neues, leeres Konto.',
        'Ändern Sie die Adresse einer Anbindung, passen Sie auch die Tool-URLs in der Lernplattform an. Bis dahin funktionieren die Starts weiter, und der Verlauf zeigt eine Warnung.',
      ],
      en: [
        'If the **KI-Bewertung** column is missing in Moodle, Moodle does not let the tool add a column. The Moodle administration sets the tool’s *IMS LTI Assignment and Grade Services* to **Use this service for grade sync and column management**. Then open the activity again.',
        'Do not change the privacy mode in ILIAS after go-live. It decides how people are identified, and a change detaches every link.',
        'Anonymizing cannot be undone. If the person opens the activity again, a new, empty account is created.',
        'If you change a connection’s address, update the tool URLs in the learning platform too. Until then launches keep working, and the history shows a warning.',
      ],
    },
    links: [
      {
        label: {
          de: 'Anbindung einrichten',
          en: 'Setting up a connection',
        },
        href: '/how-to#lti-setup',
      },
      {
        label: {
          de: 'Noten aus der Lernplattform',
          en: 'Grades and the learning platform',
        },
        href: '/how-to#lti-grades',
      },
      {
        label: {
          de: 'Datenschutz bei der Anbindung',
          en: 'Data protection for the integration',
        },
        href: '/how-to#lti-privacy',
      },
      {
        label: {
          de: 'Start aus Moodle oder ILIAS schlägt fehl',
          en: 'Launch from Moodle or ILIAS fails',
        },
        href: '/how-to#ts-lti-errors',
      },
    ],
    keywords: {
      de: [
        'Anbindung verwalten',
        'Anbindung deaktivieren',
        'Deployment',
        'LMS-Konten',
        'Verknüpfung lösen',
        'Anonymisieren',
        'Notenübertragungen',
        'Erneut versuchen',
        'Verlauf',
        'Org-Rolle für Lehrende',
        'Anbindung löschen',
      ],
      en: [
        'manage connection',
        'disable connection',
        'deployment',
        'lms accounts',
        'unlink',
        'anonymize',
        'grade transfers',
        'retry',
        'history',
        'teacher role',
        'delete connection',
      ],
    },
  },
  {
    id: 'lti-teacher',
    category: 'integrations',
    title: {
      de: 'Wie verknüpfe ich eine Moodle- oder ILIAS-Aktivität mit einer Klausur?',
      en: 'How do I link a Moodle or ILIAS activity to an exam?',
    },
    summary: {
      de: 'Legen Sie im Kurs eine Aktivität *Externes Tool* (Moodle) oder einen *LTI-Konsumenten* (ILIAS) mit Bewertung an und öffnen Sie sie. Beim **ersten Start** stimmen Sie einmal zu und wählen dann die Klausur. Danach öffnet die Aktivität die **Aktivitätsübersicht** mit allen Abgaben und Noten.',
      en: 'Create an *External tool* activity (Moodle) or an *LTI consumer* (ILIAS) with a grade in your course and open it. On the **first launch** you consent once and then pick the exam. After that the activity opens the **activity overview** with all submissions and grades.',
    },
    steps: {
      de: [
        'Moodle: *Aktivität anlegen* → das Tool in der Aktivitätsauswahl wählen → Bewertung aktiv lassen. Zeigt die Aktivität keine Bewertung, setzen Sie zuerst den Haken **… erlauben, Bewertungen hinzuzufügen** (vorne steht der Name des Tools). Ohne den Haken hat die Aktivität keine Bewertung. Ein Maximum von 100 ist in Ordnung, das Tool liefert 0 bis 18 Notenpunkte und Moodle rechnet um. Den Startcontainer legt in Moodle die Administration für das Tool fest. ILIAS: *LTI-Konsument* mit dem Provider anlegen und als Startoption **Neues Fenster** wählen.',
        'Aktivität öffnen. Beim ersten Start bittet die Anbindung um Ihre Zustimmung, auch zur Forschungsnutzung. Gibt es schon ein Konto mit Ihrer E-Mail-Adresse, verknüpfen Sie es durch Anmelden oder über einen Link per E-Mail. Oder Sie wählen **Mit separatem Konto fortfahren**.',
        'Die Auswahl trägt den Titel Ihrer Aktivität. Sie zeigt Ihre eigenen Klausuren (*Eigene*) und die Klausuren der Mitwirkenden und Admins Ihrer Organisation, jeweils mit Autorin oder Autor. Bei einer Gruppen-Anbindung zählen nur die Mitwirkenden der Gruppe, die Gruppen-Admins und die Org-Admins. Auch private Klausuren lassen sich verknüpfen. Unter der Liste legen Sie mit **Oder neue Klausur anlegen** eine neue an. Gibt es noch keine Klausur, heißt die Schaltfläche **Neue Klausur anlegen**.',
        'Verknüpfbar sind Klausuren mit Falllösung und Klausuren mit aktivem Bewertungsbogen. Klausuren ohne Aufgabe, mit mehreren Aufgaben oder ohne aktiven Bewertungsbogen lassen sich nicht wählen. Der Grund steht dabei.',
        '**Verknüpfen**. Damit ist die menschliche Korrektur für die Klausur eingeschaltet, und die Mitarbeitenden Ihrer Organisation können die Abgaben ansehen und korrigieren.',
        'Studierende öffnen die Aktivität, stimmen einmal zu und landen direkt in der Klausur.',
        'Öffnen Sie die Aktivität später erneut, landen Sie in der **Aktivitätsübersicht**. Mit der BenGER-Adresse ist das die Expertenoberfläche. **Korrektur öffnen** führt immer in die Expertenoberfläche, auch mit der Studierenden-Adresse. Was die Übersicht zeigt, steht unter [Noten aus der Lernplattform](/how-to#lti-grades).',
        '**Moodle: KI-Bewertung aus der Kursgesamtbewertung nehmen**. Moodle legt die Spalte **KI-Bewertung** als normale Bewertung an und zählt sie in *Kurs gesamt* mit. Sobald die Spalte mit der ersten KI-Note erscheint, öffnen Sie im Kurs *Bewertungen* → *Setup für Bewertungen*. Haken Sie in der Zeile KI-Bewertung das Kästchen in der Spalte *Gewichtungen* an, tragen Sie 0 ein und klicken Sie auf *Änderungen speichern*. Dann zählt nur die Aktivitätsspalte.',
      ],
      en: [
        'Moodle: *Add an activity* → pick the tool in the activity chooser → keep grading on. If the activity shows no grade settings, first tick **Allow … to add grades in the gradebook** (the tool’s name fills the gap). Without the tick the activity has no grade. A maximum of 100 is fine, the tool sends 0 to 18 grade points and Moodle rescales. In Moodle the administration sets the launch container for the tool. ILIAS: create an *LTI consumer* with the provider and choose **New window** as launch option.',
        'Open the activity. On the first launch the connection asks for your consent, including research use. If an account with your email address already exists, link it by signing in or through a link sent by email. Or choose **Continue with a separate account**.',
        'The picker carries your activity’s title. It lists your own exams (*Own*) and the exams of your organization’s contributors and admins, each with its author. On a group connection only the group’s contributors, the group admins and the org admins count. Private exams can be linked too. Below the list, **Or create a new exam** creates a new one. If there is no exam yet, the button reads **Create new exam**.',
        'Exams with a case solution (Falllösung) and exams with an active grading sheet (Bewertungsbogen) can be linked. Exams without a task, with several tasks or without an active grading sheet cannot be chosen. The reason is shown next to them.',
        '**Link**. This switches on human grading for the exam, and your organization’s staff can view and grade the submissions.',
        'Students open the activity, consent once and land directly in the exam.',
        'When you open the activity again later, you land in the **activity overview**. With the BenGER address this is the expert interface. **Open grading** always leads to the expert interface, also with the Student address. What the overview shows is described under [Grades and the learning platform](/how-to#lti-grades).',
        '**Moodle: take the KI-Bewertung out of the course total**. Moodle creates the **KI-Bewertung** column as a normal grade item and counts it in the *Course total*. Once the column appears with the first AI grade, open *Grades* → *Gradebook setup* in the course. In the KI-Bewertung row, tick the box in the *Weights* column, enter 0 and click *Save changes*. Then only the activity column counts.',
      ],
    },
    tips: {
      de: [
        'Die Zustimmung gilt je Anbindung. Weitere Kurse und Aktivitäten derselben Lernplattform fragen nicht erneut.',
        'Auf der Projektseite der Klausur zeigt **Einstellungen** → **Einzel-Freigabe** die **Lernplattform-Aktivitäten** mit einem Link zur Übersicht.',
        'Die KI-Korrektur bezahlt die Organisation der Anbindung. Fehlt ihr ein Schlüssel, zeigen die Auswahl und die Übersicht einen Hinweis.',
      ],
      en: [
        'Consent applies per connection. Further courses and activities of the same learning platform do not ask again.',
        'On the exam’s project page, **Settings** → **Individual sharing** lists the **Learning platform activities** with a link to the overview.',
        'The organization of the connection pays for AI grading. If it lacks a key, the picker and the overview show a notice.',
      ],
    },
    pitfalls: {
      de: [
        'Sobald eine Note an die Lernplattform übertragen wurde, lässt sich die Verknüpfung nicht mehr ändern. Legen Sie für eine andere Klausur eine neue Aktivität an.',
        '*Diese Aktivität kann keine Noten empfangen*: Die Notenübertragung ist nicht aktiv. Schalten Sie in Moodle die Bewertung ein, bei Bedarf mit dem Haken *… erlauben, Bewertungen hinzuzufügen*, oder in ILIAS *Advanced Grading Services*. Öffnen Sie die Aktivität dann neu.',
        'Klausuren mit mehreren Aufgaben lassen sich noch nicht verknüpfen, und eine verknüpfte Klausur nimmt keine zweite Aufgabe an.',
        'Startet das Tool eingebettet (iframe), landen Sie auf der Anmeldeseite. In Moodle 4.5 ändern Sie das nicht in der Aktivität. Die Moodle-Administration stellt den *Standard-Startcontainer* des Tools auf **Neues Fenster**. In ILIAS wählen Sie beim Objekt **Neues Fenster**.',
        'Finden Sie das Tool nicht in der Moodle-Aktivitätsauswahl, bitten Sie die Moodle-Administration, beim Tool *Verwendung der Toolkonfiguration* auf **In Aktivitätsauswahl und als vorkonfiguriertes Tool anzeigen** zu stellen.',
      ],
      en: [
        'Once a grade has been sent to the learning platform, the link cannot be changed. Create a new activity for another exam.',
        '*This activity cannot receive grades*: grade sync is off. Turn on grading in Moodle, if needed with the tick *Allow … to add grades in the gradebook*, or *Advanced Grading Services* in ILIAS. Then open the activity again.',
        'Exams with several tasks cannot be linked yet, and a linked exam does not accept a second task.',
        'If the tool starts embedded (iframe), you land on the login page. In Moodle 4.5 you cannot change this in the activity. The Moodle administration sets the tool’s *Default launch container* to **New window**. In ILIAS, choose **New window** on the object.',
        'If you cannot find the tool in the Moodle activity chooser, ask the Moodle administration to set the tool’s *Tool configuration usage* to **Show in activity chooser and as a preconfigured tool**.',
      ],
    },
    links: [
      {
        label: {
          de: 'Noten aus der Lernplattform',
          en: 'Grades and the learning platform',
        },
        href: '/how-to#lti-grades',
      },
      {
        label: {
          de: 'Anbindung einrichten',
          en: 'Setting up a connection',
        },
        href: '/how-to#lti-setup',
      },
      {
        label: {
          de: 'Datenschutz bei der Anbindung',
          en: 'Data protection for the integration',
        },
        href: '/how-to#lti-privacy',
      },
      TECH_REFERENCE_LINK,
    ],
    keywords: {
      de: [
        'Aktivität verknüpfen',
        'Externes Tool',
        'LTI-Konsument',
        'Klausur verknüpfen',
        'Bewertungsbogen',
        'Falllösung',
        'Aktivitätsübersicht',
        'Moodle Kurs',
        'Bewertung',
        'Kurs gesamt',
        'Setup für Bewertungen',
      ],
      en: [
        'link activity',
        'external tool',
        'lti consumer',
        'link exam',
        'grading sheet',
        'activity overview',
        'moodle course',
        'gradebook',
        'course total',
        'gradebook setup',
      ],
    },
  },
  {
    id: 'lti-grades',
    category: 'integrations',
    title: {
      de: 'Wie kommen die Noten in die Lernplattform?',
      en: 'How do grades get into the learning platform?',
    },
    summary: {
      de: 'Nach der Abgabe korrigiert die KI, und die Note geht sofort an die Lernplattform. Korrigieren Sie die Abgabe selbst, wird Ihre Note zur Endnote. Die KI-Note bleibt erhalten. Die **Aktivitätsübersicht** zeigt beide Noten und was die Lernplattform erhalten hat.',
      en: 'After submission the AI grades the solution, and the grade goes to the learning platform right away. If you grade the submission yourself, your grade becomes the final grade. The AI grade is kept. The **activity overview** shows both grades and what the learning platform received.',
    },
    steps: {
      de: [
        'Öffnen Sie die Aktivität in der Lernplattform. Die Übersicht erreichen Sie auch über **Notenübersicht öffnen** im Panel der Anbindung oder über **Übersicht öffnen** bei den Lernplattform-Aktivitäten der Klausur.',
        'Die Tabelle **Abgaben und Noten** zeigt je Person den Namen, die Abgabe, die **KI-Note**, die **Korrektur** und was die Aktivitätsspalte und die Spalte KI-Bewertung erhalten haben. Dazu kommt der Status (*Übertragen*, *Wird übertragen*, *Noch keine Note*, *Übersprungen* oder *Fehlgeschlagen*) mit Fehlertext.',
        '**Korrektur öffnen** führt direkt zur Abgabe in der Korrektur. Sie öffnet sich in der Expertenoberfläche, auch mit der Studierenden-Adresse. Ihre Note ersetzt in der Aktivitätsspalte die KI-Note.',
        'Hat eine Übertragung einen Fehler, bietet die Zeile **Erneut senden** an. Das gilt für fehlgeschlagene Übertragungen und für ausstehende nach einem Fehlversuch. **Erneut senden** schickt die Note sofort noch einmal. **Fehlgeschlagene erneut senden** macht das für alle Übertragungen mit Fehler auf einmal.',
        'Unter **Spalten in der Lernplattform** sehen Sie, ob die Spalte **KI-Bewertung** aktiv ist. Wurde sie in Moodle gelöscht, legt **Spalte neu anlegen** sie wieder an.',
      ],
      en: [
        'Open the activity from the learning platform. You also reach the overview through **Open grade overview** in the connection panel, or **Open overview** in the exam’s learning platform activities.',
        'The table **Submissions and grades** shows for each person the name, the submission, the **AI grade**, the **Human grade** and what the activity column and the KI-Bewertung column received. It also shows the status (*Transferred*, *Being transferred*, *No grade yet*, *Skipped* or *Failed*) with the error text.',
        '**Open grading** takes you straight to the submission in the grading view. It opens in the expert interface, also with the Student address. Your grade replaces the AI grade in the activity column.',
        'If a transfer has an error, the row offers **Send again**. This covers failed transfers and pending ones after a failed attempt. **Send again** sends the grade once more, right away. **Send failed ones again** does this for all transfers with an error at once.',
        'Under **Columns in the learning platform** you see whether the **KI-Bewertung** column is active. If it was deleted in Moodle, **Create column again** brings it back.',
      ],
    },
    tips: {
      de: [
        'Moodle erhält zwei Spalten. Die Aktivitätsspalte hat die Endnote (die Korrektur, sonst die KI-Note), umgerechnet auf das Maximum der Aktivität. Die Spalte **KI-Bewertung** hat immer die KI-Note auf der Skala 0 bis 18. Dafür muss beim Tool *IMS LTI Aufgaben und Bewertung* auf **Service für die Synchronisation von Bewertungen und die Verwaltung der Spalten nutzen** stehen, sonst erhält Moodle nur die Endnote.',
        'ILIAS erhält je Person einen Wert, die Endnote. Den Kommentar zur Note zeigt ILIAS nicht an.',
        'Eine Korrektur löscht nichts. Die KI-Note bleibt in der Übersicht und in der Spalte KI-Bewertung. Bei mehreren Korrekturen gilt die zuletzt bearbeitete.',
        'Ändert sich eine Note nachträglich, etwa durch einen neuen Notenschlüssel, geht der neue Wert spätestens nach etwa einer Stunde an die Lernplattform.',
        'Während der Korrektur ist die KI-Note standardmäßig ausgeblendet, bis Sie Ihre eigene Note abgegeben haben.',
        'Klarnamen sehen hier die Lehrenden der Kurse, die diese Klausur verknüpfen, Mitarbeitende, die diese Klausur bewerten dürfen, die Admins der Organisation und die Administration der Plattform. Anonymisierte Konten erscheinen als *Anonymisiert*.',
      ],
      en: [
        'Moodle gets two columns. The activity column holds the final grade (the human grade, otherwise the AI grade), rescaled to the activity’s maximum. The **KI-Bewertung** column always holds the AI grade on the 0 to 18 scale. This needs the tool’s *IMS LTI Assignment and Grade Services* set to **Use this service for grade sync and column management**, otherwise Moodle gets the final grade only.',
        'ILIAS gets one value per person, the final grade. ILIAS does not show the comment on the grade.',
        'Grading deletes nothing. The AI grade stays in the overview and in the KI-Bewertung column. With several human grades, the most recently edited one counts.',
        'If a grade changes later, for example through a new grading key, the new value reaches the learning platform within about an hour.',
        'By default the AI grade is hidden while you grade, until you have submitted your own grade.',
        'Real names are shown here to the teachers of the courses that link this exam, to staff who may grade this exam, to the organization’s admins and to the platform administration. Anonymized accounts show as *Anonymized*.',
      ],
    },
    pitfalls: {
      de: [
        'Stellt die Organisation keine API-Schlüssel bereit oder fehlt ein passender Schlüssel, läuft keine KI-Korrektur. Studierende sehen den Grund: Ihre Organisation bezahlt die KI-Korrektur noch nicht, oder ihr fehlt ein API-Schlüssel für das Bewertungsmodell. Die Abgabe bleibt gespeichert. Die Übersicht zeigt *Wartet auf einen API-Schlüssel der Organisation*. Sobald der Schlüssel hinterlegt ist, wird die Abgabe bei der nächsten stündlichen Prüfung korrigiert, also spätestens nach etwa einer Stunde.',
        'Moodle legt die Spalte **KI-Bewertung** als normale Bewertung an und zählt sie in *Kurs gesamt* mit, auch wenn eine Korrektur die Endnote bestimmt. Setzen Sie ihre Gewichtung auf 0: im Kurs *Bewertungen* → *Setup für Bewertungen*, in der Zeile KI-Bewertung das Kästchen in der Spalte *Gewichtungen* anhaken, 0 eintragen und *Änderungen speichern*. Wird die Spalte neu angelegt, wiederholen Sie das.',
        'Eine fehlgeschlagene Übertragung wird von selbst wiederholt. War die Lernplattform nicht erreichbar oder hatte sie einen Serverfehler, geht die Note nach 10, 30 und 90 Sekunden erneut hinaus. Danach wachsen die Abstände bis zu sechs Stunden. Nach zehn Versuchen gilt die Übertragung als fehlgeschlagen und wird weiter alle sechs Stunden versucht.',
        'Ist die Anbindung deaktiviert, gehen keine Noten hinaus, und die Aktivitätsübersicht zeigt nur einen Hinweis. Übertragungen aus dieser Zeit gelten als fehlgeschlagen. Nach dem Einschalten schickt **Erneut senden** sie sofort. Sonst versucht das Tool sie etwa sechs Stunden nach dem Fehlschlag von selbst erneut.',
      ],
      en: [
        'If the organization does not provide API keys or has no matching key, no AI grading runs. Students see the reason: their organization does not pay for AI grading yet, or it has no API key for the grading model. The submission stays saved. The overview shows *Waiting for an API key of the organization*. Once the key is in place, the submission is graded at the next hourly check, so within about an hour.',
        'Moodle creates the **KI-Bewertung** column as a normal grade item and counts it in the *Course total*, even when a human grade decides the final grade. Set its weight to 0: in the course, *Grades* → *Gradebook setup*, tick the box in the *Weights* column of the KI-Bewertung row, enter 0 and click *Save changes*. If the column is created again, repeat this.',
        'A failed transfer is retried automatically. If the learning platform was unreachable or had a server error, the grade goes out again after 10, 30 and 90 seconds. After that the intervals grow up to six hours. After ten attempts the transfer counts as failed and is still retried every six hours.',
        'While the connection is disabled, no grades go out, and the activity overview only shows a notice. Transfers from that time count as failed. After enabling the connection, **Send again** sends them at once. Otherwise the tool retries them by itself about six hours after the failure.',
      ],
    },
    links: [
      {
        label: {
          de: 'Klausur mit einer Aktivität verknüpfen',
          en: 'Linking an exam to an activity',
        },
        href: '/how-to#lti-teacher',
      },
      {
        label: {
          de: 'Menschliche Korrektur',
          en: 'Human grading',
        },
        href: '/how-to#korrektur-review',
      },
      {
        label: {
          de: 'Anbindung verwalten',
          en: 'Managing a connection',
        },
        href: '/how-to#lti-manage',
      },
      {
        label: {
          de: 'Datenschutz bei der Anbindung',
          en: 'Data protection for the integration',
        },
        href: '/how-to#lti-privacy',
      },
    ],
    keywords: {
      de: [
        'Notenübertragung',
        'Noten',
        'KI-Bewertung',
        'KI-Note',
        'Endnote',
        'Notenbuch',
        'Spaltenverwaltung',
        'Erneut senden',
        'Grade Sync',
        'Notenschlüssel',
        'Kurs gesamt',
        'Gewichtung',
      ],
      en: [
        'grade transfer',
        'grades',
        'ai grade',
        'final grade',
        'gradebook',
        'column management',
        'send again',
        'grade sync',
        'grading key',
        'course total',
        'weight',
      ],
    },
  },
  {
    id: 'lti-privacy',
    category: 'integrations',
    title: {
      de: 'Was muss ich zum Datenschutz der Lernplattform-Anbindung wissen?',
      en: 'What do I need to know about data protection for the LMS integration?',
    },
    summary: {
      de: 'Die Anbindung bittet **vor jedem Konto um Zustimmung**, einmal je Anbindung, bei Studierenden und Lehrenden. Konten tragen Name und E-Mail-Adresse aus der Lernplattform, in der App erscheint ein Pseudonym. Die KI-Korrektur läuft nur auf den Schlüsseln Ihrer Organisation. Gehostet wird in **Deutschland**. Wir sind Auftragsverarbeiter und erfüllen die Anforderungen Ihrer Datenschutzstelle. Sagen Sie uns bitte konkret, was Sie brauchen.',
      en: 'The integration asks for **consent before any account exists**, once per connection, from students and teachers. Accounts carry name and email address from the learning platform, and the app shows a pseudonym. AI grading runs only on your organization’s keys. Hosting is in **Germany**. We act as processor and will meet the requirements your data protection office sets. Please tell us specifically what you need.',
    },
    steps: {
      de: [
        '**Zustimmung zuerst**: Beim ersten Start sieht die Person, was die Lernplattform übermittelt hat, und stimmt zwei Punkten zu. Das sind die Verarbeitung (Konto mit Name und E-Mail-Adresse, Pseudonym, Notenübertragung) und die Forschungsnutzung. Vorher entsteht kein Konto. Der geprüfte Start wartet höchstens 30 Minuten auf dem Server. Fordert die Person einen Bestätigungslink an, bleibt eine Kopie des Starts mit dem Link bis zu 24 Stunden gespeichert.',
        '**Forschungsnutzung ist Pflicht**: Ohne diese Zustimmung lässt sich das Tool aus der Lernplattform nicht nutzen. Ein Zugang, der von einer Einwilligung abhängt, wirft die Frage nach Art. 7 Abs. 4 DSGVO auf. Ob das für Ihren Kurs passt, beurteilt Ihre Datenschutzstelle.',
        '**Klarname und Pseudonym**: Konten tragen Name und E-Mail-Adresse aus der Lernplattform. In der App erscheint das Pseudonym. Klarnamen sehen die Admins der Organisation, Gruppen-Admins für ihre Gruppe, die Lehrenden des Kurses, Mitarbeitende, die die verknüpfte Klausur bewerten dürfen, und die Administration der Plattform. Lehrende des Kurses sind die Lehrenden jedes Kurses der Anbindung, der die Klausur verknüpft. Bewerten dürfen standardmäßig auch die Lehrenden der Anbindung, weil sie in der Organisation Mitwirkende werden.',
        '**Anforderungen nennen**: AVV nach Ihrer Vorlage oder unserer, TOM-Anlage, Eintrag für Ihr Verarbeitungsverzeichnis, Zuarbeit für eine DSFA, Unterauftragsverarbeiter, Löschfristen. Die vollständige Abfrageliste steht in der technischen Referenz.',
        '**Vertrag vor dem Einladungslink**: Eine Anbindung ist aktiv, sobald die Lernplattform den Link einlöst. Schließen Sie den Vertrag deshalb ab, bevor Ihr Organisations-Admin den Link erstellt. Darauf zu achten, ist Aufgabe der Hochschule.',
        '**Ansprechpersonen benennen**: je eine Person für die rechtliche Seite (meist Justiziariat oder Datenschutzkoordination, nicht die einzelne Lehrkraft) und für die Moodle- oder ILIAS-Administration.',
      ],
      en: [
        '**Consent first**: on the first launch the person sees what the learning platform sent and agrees to two points. These are the processing (an account with name and email address, the pseudonym, the grade transfer) and research use. No account exists before that. The checked launch waits on the server for at most 30 minutes. If the person requests a confirmation link, a copy of the launch is kept with the link for up to 24 hours.',
        '**Research use is required**: without this consent the tool cannot be used from the learning platform. Access that depends on consent raises the question of Art. 7(4) GDPR. Whether this fits your course is for your data protection office to assess.',
        '**Real name and pseudonym**: accounts carry name and email address from the learning platform. The app shows the pseudonym. Real names are visible to the organization’s admins, to group admins for their group, to the course teachers, to staff who may grade the linked exam and to the platform administration. Course teachers are the teachers of any course on the connection that links the exam. By default the connection’s teachers may grade too, because they become contributors in the organization.',
        '**State your requirements**: a data processing agreement on your template or ours, a TOMs annex, an entry for your record of processing, input for a DPIA, subprocessors, retention periods. The full prompt list is in the technical reference.',
        '**Contract before the invitation link**: a connection is active as soon as the learning platform redeems the link. Sign the contract before your organization admin creates the link. Making sure of this is the university’s task.',
        '**Name the contacts**: one for the legal side (usually the legal office or data protection coordination, not the individual teacher) and one for the Moodle or ILIAS administration.',
      ],
    },
    tips: {
      de: [
        'Die KI-Korrektur verknüpfter Klausuren läuft nur auf den **API-Schlüsseln Ihrer Organisation**, nie auf einem Schlüssel von uns. Fehlt der Schlüssel, wird nicht korrigiert. Sie entscheiden also, welcher Anbieter Lösungstexte verarbeitet.',
        'Es wird kein Teilnehmerverzeichnis gelesen. Die Anbindung nutzt höchstens drei notenbezogene Berechtigungen (bei ILIAS zwei) und kein Names and Role Provisioning.',
        'Ein bestehendes Konto wird nur verknüpft, wenn sich die Person anmeldet oder einen Link per E-Mail bestätigt. Konten der Plattform-Administration werden nie verknüpft.',
        'Neue Konten mit zustellbarer Adresse erhalten nach der Zustimmung eine E-Mail zum Festlegen eines Passworts.',
        'Die Admins Ihrer Organisation anonymisieren Konten, die die Lernplattform angelegt hat. Name, E-Mail-Adresse und die Kennung der Lernplattform werden gelöscht, Abgaben und Noten bleiben ohne Personenbezug erhalten. Die vollständige Löschung eines Kontos gibt es auf Anfrage.',
        'KI-Note und Korrektur stehen nebeneinander, und die Korrektur ist die Endnote. Bis zur Korrektur steht die KI-Note in der Lernplattform.',
      ],
      en: [
        'AI grading of linked exams runs only on **your organization’s API keys**, never on one of ours. Without a key nothing is graded. So you decide which provider processes solution text.',
        'No course roster is read. The integration uses at most three grade-related permissions (two on ILIAS) and no Names and Role Provisioning.',
        'An existing account is linked only when the person signs in or confirms a link sent by email. Accounts of the platform administration are never linked.',
        'New accounts with a deliverable address get an email to set a password after consent.',
        'Your organization’s admins anonymize accounts the learning platform created. Name, email address and the learning platform identity are deleted, while submissions and grades stay without personal reference. Full deletion of an account is available on request.',
        'The AI grade and the human grade are kept side by side, and the human grade is the final grade. Until a teacher grades, the AI grade is the value in the learning platform.',
      ],
    },
    pitfalls: {
      de: [
        'Wählen Sie den **Privacy-Modus in ILIAS** vor dem Start so, dass Name und E-Mail-Adresse übertragen werden, und ändern Sie ihn danach nicht mehr. Ein Wechsel ändert die Kennung jeder Person und trennt alle Verknüpfungen.',
        'Ob eine Datenschutz-Folgenabschätzung nötig ist und wie die KI-Note vor der Korrektur rechtlich einzuordnen ist, entscheidet die Hochschule als Verantwortliche. Wir liefern die Verarbeitungsbeschreibung als Zuarbeit.',
        'Noten, die schon an die Lernplattform übertragen wurden, bleiben dort, auch nach einer Anonymisierung. Sie löschen sie in der Lernplattform.',
      ],
      en: [
        'Choose the **ILIAS privacy mode** so that name and email address are sent before go-live, and do not change it afterwards. A change alters every person’s identifier and detaches every link.',
        'Whether a data protection impact assessment is needed, and how the AI grade before human grading is to be assessed legally, is for the university as controller to decide. We supply the processing description as input.',
        'Grades already sent to the learning platform stay there, also after anonymization. You delete them in the learning platform.',
      ],
    },
    links: [
      {
        label: {
          de: 'Vollständige Datenschutz- und Technikreferenz',
          en: 'Full data protection and technical reference',
        },
        href: TECH_REFERENCE_HREF,
      },
      {
        label: {
          de: 'Anbindung einrichten',
          en: 'Setting up a connection',
        },
        href: '/how-to#lti-setup',
      },
      {
        label: {
          de: 'Anbindung verwalten',
          en: 'Managing a connection',
        },
        href: '/how-to#lti-manage',
      },
      {
        label: {
          de: 'Datenschutzerklärung',
          en: 'Privacy policy',
        },
        href: '/about/data-protection',
      },
    ],
    keywords: {
      de: [
        'Datenschutz',
        'DSGVO',
        'AVV',
        'Auftragsverarbeitung',
        'TOM',
        'DSFA',
        'Verarbeitungsverzeichnis',
        'Pseudonym',
        'Klarname',
        'Einwilligung',
        'Forschungsnutzung',
        'Anonymisierung',
        'Hosting',
        'Löschung',
      ],
      en: [
        'data protection',
        'gdpr',
        'dpa',
        'processor',
        'dpia',
        'record of processing',
        'pseudonym',
        'real name',
        'consent',
        'research use',
        'anonymization',
        'hosting',
        'deletion',
      ],
    },
  },
]

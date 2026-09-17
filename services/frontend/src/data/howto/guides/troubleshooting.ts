import type { HowToGuide } from '@/lib/howto'
import { LTI_LAUNCH_ERROR_CODES } from '@/lib/lti/launchErrors'

export const TROUBLESHOOTING_GUIDES: HowToGuide[] = [
  {
    id: 'ts-no-projects',
    category: 'troubleshooting',
    title: {
      de: '„Ich sehe keine Projekte“ oder „mein Projekt ist verschwunden“',
      en: '“I see no projects” or “my project has disappeared”',
    },
    summary: {
      de: 'Fast immer der Kontext: oben rechts im Kontomenü unter **Kontext wechseln** die Organisation wählen. Danach: Ist das Projekt archiviert (*Mehr → Archiviert*) oder auf eine Gruppe beschränkt, der Sie nicht angehören?',
      en: 'Almost always the context: top right in the account menu under **Switch context** pick the organization. Then: is the project archived (*More → Archived*) or restricted to a group you do not belong to?',
    },
    links: [
      {
        label: {
          de: 'Privater Kontext vs. Organisation',
          en: 'Private context vs. organization',
        },
        href: '/how-to#org-context',
      },
      { label: { de: 'Gruppen', en: 'Groups' }, href: '/how-to#org-groups' },
    ],
    keywords: {
      de: ['verschwunden', 'nicht sichtbar', 'leer', 'fehlt', 'keine Projekte'],
      en: ['disappeared', 'not visible', 'empty', 'missing', 'no projects'],
    },
  },
  {
    id: 'ts-no-models',
    category: 'troubleshooting',
    title: {
      de: '„Keine API-Schlüssel konfiguriert“ oder es fehlen Modelle in der Auswahl',
      en: '“No API keys configured” or models are missing from the picker',
    },
    summary: {
      de: 'Es fehlt der Schlüssel des Anbieters. Eigenen Schlüssel unter [Profil](/profile) → *API-Schlüssel-Verwaltung* hinterlegen, oder die Organisation muss *Organisation stellt API-Schlüssel bereit* einschalten und den Anbieter hinterlegen. Stellt die Organisation Schlüssel bereit, gibt es keinen Rückfall auf Ihren eigenen.',
      en: 'The provider key is missing. Store your own key under [Profile](/profile) → *API key management*, or the organization must switch on *Organization provides API keys* and add the provider. If the organization provides keys, there is no fallback to your own.',
    },
    links: [
      {
        label: { de: 'API-Schlüssel einrichten', en: 'Setting up API keys' },
        href: '/how-to#api-keys',
      },
    ],
    keywords: {
      de: [
        'Keine API-Schlüssel',
        'Modell fehlt',
        'nicht verfügbar',
        'Anbieter',
      ],
      en: ['no api keys', 'model missing', 'unavailable', 'provider'],
    },
  },
  {
    id: 'ts-generation-fails',
    category: 'troubleshooting',
    title: {
      de: 'Generierung oder Bewertung schlägt fehl',
      en: 'Generation or evaluation fails',
    },
    summary: {
      de: 'Prüfen Sie in dieser Reihenfolge: Schlüssel gültig und mit Guthaben (*Nutzungs- oder Ratenlimit erreicht* heißt kein Guthaben beim Anbieter), Modell noch aktiv im [Modellkatalog](/models), Prompt-Struktur und Verfahren verweisen auf existierende Felder. Details zu jedem Lauf stehen unter [Läufe](/runs), fehlgeschlagene Läufe lassen sich dort erneut starten.',
      en: 'Check in this order: key valid and funded (*usage or rate limit reached* means no credit at the provider), model still active in the [model catalog](/models), prompt structure and methods reference existing fields. Details of every run are under [Runs](/runs), failed runs can be retried there.',
    },
    tips: {
      de: [
        'Bei *Erneut generieren* wird eine Aufgabe nur neu erzeugt, wenn sich der Prompt geändert hat. Mit *Alle generieren* erzwingen Sie die Neuerzeugung.',
      ],
      en: [
        '*Regenerate* only re-creates a task when the prompt changed. *Generate all* forces regeneration.',
      ],
    },
    keywords: {
      de: [
        'fehlgeschlagen',
        'Fehler',
        'Generierung fehlgeschlagen',
        'Evaluierungsfehler',
        'Ratenlimit',
        'ungültiger Schlüssel',
      ],
      en: [
        'failed',
        'error',
        'generation failed',
        'evaluation error',
        'rate limit',
        'invalid key',
      ],
    },
  },
  {
    id: 'ts-import-validation',
    category: 'troubleshooting',
    title: {
      de: '„Import-Validierungsfehler: These fields are not present in the data“',
      en: '“Import validation error: These fields are not present in the data”',
    },
    summary: {
      de: 'Ihre Datei hat andere Spaltennamen als die `$feld`-Platzhalter der Annotationsvorlage. Entweder Spalten umbenennen, die **Feldzuordnung** im Import-Dialog nutzen, oder **Trotzdem importieren** und danach unter *Feldzuordnung & Vorlage* auf der Datenseite die Vorlage aus den Daten erzeugen.',
      en: 'Your file has different column names than the `$field` placeholders of the labeling template. Either rename columns, use the **field mapping** in the import dialog, or **Import anyway** and then generate the template from the data under *Field mapping & template* on the data page.',
    },
    links: [
      {
        label: { de: 'Daten hochladen', en: 'Uploading data' },
        href: '/how-to#upload-data',
      },
    ],
    keywords: {
      de: [
        'Validierungsfehler',
        'Felder fehlen',
        'not present',
        'Feldzuordnung',
        'Import fehlgeschlagen',
      ],
      en: [
        'validation error',
        'missing fields',
        'field mapping',
        'import failed',
      ],
    },
  },
  {
    id: 'ts-unknown-component',
    category: 'troubleshooting',
    title: {
      de: 'Ein Feld fehlt in der Annotationsoberfläche oder „Unknown component type“',
      en: 'A field is missing in the annotation interface or “Unknown component type”',
    },
    summary: {
      de: 'Der Tag im XML wird nicht erkannt. Tag-Namen sind Groß-/Klein-sensitiv (`TextArea`, nicht `Textarea`). Klausur-Tags wie `Angabe`, `Gliederung` und `Loesung` gibt es nur in der erweiterten Edition. Fehlende Datenfelder (`value="$feld"`) bleiben leer, ohne Fehlermeldung.',
      en: 'The tag in the XML is not recognized. Tag names are case-sensitive (`TextArea`, not `Textarea`). Exam tags such as `Angabe`, `Gliederung` and `Loesung` exist only in the extended edition. Missing data fields (`value="$field"`) stay empty without an error.',
    },
    links: [
      {
        label: { de: 'XML bearbeiten', en: 'Editing the XML' },
        href: '/how-to#edit-label-xml',
      },
    ],
    keywords: {
      de: [
        'Unknown component type',
        'Feld fehlt',
        'leer',
        'wird nicht angezeigt',
        'XML Fehler',
      ],
      en: [
        'unknown component',
        'field missing',
        'empty',
        'not shown',
        'xml error',
      ],
    },
  },
  {
    id: 'ts-import-button',
    category: 'troubleshooting',
    title: {
      de: '„Wo ist der Import-Knopf?“ und andere verschobene Funktionen',
      en: '“Where is the import button?” and other moved functions',
    },
    summary: {
      de: '**Projekt importieren**, **Archiviert**, **Gelöschte Projekte** und **Entdecken** stecken in der Projektliste im Menü **Mehr**. Der Import von Aufgaben in ein Projekt ist auf der Seite *Projektdaten*. Eigene Modelle werden unter [Modelle](/models) verwaltet, eigene API-Schlüssel im [Profil](/profile).',
      en: '**Import project**, **Archived**, **Deleted projects** and **Discover** sit in the project list under the **More** menu. Importing tasks into a project is on the *Project data* page. Custom models are managed under [Models](/models), personal API keys in the [profile](/profile).',
    },
    keywords: {
      de: ['Import-Knopf', 'Mehr-Menü', 'wo ist', 'finde nicht', 'verschoben'],
      en: ['import button', 'more menu', 'where is', 'cannot find', 'moved'],
    },
  },
  {
    id: 'ts-lti-errors',
    category: 'troubleshooting',
    title: {
      de: 'Start aus Moodle oder ILIAS schlägt fehl',
      en: 'Launch from Moodle or ILIAS fails',
    },
    summary: {
      de: 'Die Fehlerseite nennt einen **Fehlercode**, bei unerwarteten Serverfehlern auch eine **Referenz**. Suchen Sie den Code in der Liste unten. Jeder Eintrag nennt Ursache, Lösung und wer helfen kann. Studierende wenden sich an ihre Lehrenden, Lehrende an die Admins ihrer Organisation. Einige Fehler zeigt die Zustimmungs- oder Bestätigungsseite selbst, nur mit einer Überschrift. Die Liste nennt diese Überschriften.',
      en: 'The error page shows an **error code**, and a **reference** for unexpected server errors. Find the code in the list below. Each entry gives the cause, the fix and who can help. Students contact their teachers, teachers contact the admins of their organization. The consent or confirmation page shows some errors itself, with a heading only. The list names these headings.',
    },
    steps: {
      de: [
        '`invalid_request`: Die Lernplattform hat eine unvollständige Startanfrage geschickt. Öffnen Sie die Aktivität erneut. Kommt der Fehler jedes Mal, prüft die Administration der Lernplattform die Tool-Einstellungen.',
        '`registration_not_found`: Zur Lernplattform passt keine Anbindung. Meist stimmen Plattform-ID (Issuer) oder Client-ID in den Tool-Einstellungen nicht mit der Anbindung überein, oder die Anbindung wurde gelöscht. Auch zwei aktive Anbindungen, die sich nicht unterscheiden lassen, führen zu diesem Code. Die Admins Ihrer Organisation prüfen die Anbindung, die Administration der Lernplattform prüft die Tool-Einstellungen.',
        '`registration_disabled`: Die Organisation hat die Anbindung abgeschaltet. Eine abgeschaltete Anbindung zeigt bei jedem Start diesen Code. Im Panel trägt ihre Karte das Zeichen **Ausgeschaltet**, und der Schalter zeigt **Anbindung aus**. Die Admins Ihrer Organisation schalten sie mit einem Klick auf den Schalter wieder ein.',
        '`org_inactive`: Die Organisation, der die Anbindung gehört, ist deaktiviert. Das kann nur der Betreiber der Plattform ändern. Lehrende wenden sich an ihn.',
        '`unknown_deployment`: Die Lernplattform schickt eine Deployment-ID, die in der Anbindung nicht eingetragen ist. In ILIAS ist die Deployment-ID die Provider-ID. Die Administration der Lernplattform nennt die ID, die Admins Ihrer Organisation tragen sie in der Anbindung unter **Deployments** ein.',
        '`deployment_disabled`: Die Deployment-ID ist in der Anbindung eingetragen, aber abgeschaltet. Neben der ID zeigt der Schalter **Deployment aus**. Die Admins Ihrer Organisation schalten sie unter **Deployments** mit einem Klick auf den Schalter wieder ein.',
        '`tool_not_configured`: Der Signaturschlüssel des Tools lässt sich auf dem Server nicht laden. Das behebt nur der Betreiber der Plattform. Lehrende wenden sich an ihn.',
        '`state_unavailable`: Ein vorübergehendes Serverproblem. Der Server konnte die Anmeldung nicht speichern oder lesen. Das liegt nicht am Browser. Versuchen Sie es in ein paar Minuten erneut. Hält es an, geben Lehrende den Code an den Betreiber der Plattform weiter.',
        '`invalid_state`: Die Anmeldung war älter als 5 Minuten oder wurde schon verwendet, etwa nach *Zurück*, nach dem Neuladen oder nach doppeltem Absenden. Öffnen Sie die Aktivität erneut in der Lernplattform.',
        '`invalid_token`: Die Anmeldedaten der Lernplattform ließen sich nicht prüfen. Mögliche Ursachen sind eine falsche Schlüssel-URL (JWKS) oder Client-ID in der Anbindung, neue Schlüssel der Lernplattform oder eine falsch gehende Serveruhr. Öffnen Sie die Aktivität erneut. Kommt der Fehler jedes Mal, prüft die Administration der Lernplattform die Tool-Einstellungen gemeinsam mit den Admins Ihrer Organisation.',
        '`nonce_mismatch`: Die Antwort der Lernplattform passt nicht zur begonnenen Anmeldung. Öffnen Sie die Aktivität erneut in der Lernplattform.',
        '`nonce_reused`: Dieselbe Anmeldung kam ein zweites Mal an. Öffnen Sie die Aktivität erneut in der Lernplattform.',
        '`unsupported_message`: Die Lernplattform schickt eine Anfrage, die das Tool nicht unterstützt, zum Beispiel Deep Linking. Die Administration der Lernplattform schaltet Deep Linking in den Tool-Einstellungen ab.',
        '`not_linked`: Die Aktivität ist noch mit keiner Klausur verknüpft. Lehrende öffnen die Aktivität selbst in der Lernplattform und wählen eine Klausur aus. Studierende wenden sich an ihre Lehrenden.',
        '`exam_unavailable`: Die verknüpfte Klausur wurde gelöscht. Lehrende öffnen die Aktivität und verknüpfen eine andere Klausur. Wurden schon Noten übertragen, legen sie in der Lernplattform eine neue Aktivität an. Studierende wenden sich an ihre Lehrenden.',
        '`user_inactive`: Das Konto der Person ist in dieser Plattform deaktiviert. Nur der Betreiber der Plattform kann es wieder freischalten. Lehrende wenden sich an ihn. Ein anonymisiertes Konto kommt nicht zurück. Beim Anonymisieren verliert es die Verknüpfung mit der Lernplattform, deshalb entsteht beim nächsten Start nach der Zustimmung ein neues Konto.',
        '`membership_removed`: Ein Admin hat die Person aus der Organisation oder der Gruppe der Anbindung entfernt. Ein Start aus der Lernplattform stellt die Mitgliedschaft nicht wieder her. Soll die Person wieder Zugang haben, laden die Admins Ihrer Organisation sie mit **Mitglied einladen** an die E-Mail-Adresse ihres Kontos ein. Nimmt die Person die Einladung angemeldet an, ist die Mitgliedschaft wieder aktiv. Hat das Konto noch kein Passwort, legt die Person vorher mit **Passwort vergessen?** eines fest. Hat das Konto nur eine Platzhalter-Adresse (die Lernplattform hat keine oder eine schon vergebene Adresse geschickt), kommen weder Einladung noch Passwort-Mail an. Dann stellt der Betreiber der Plattform die Mitgliedschaft mit **Bestehenden Benutzer hinzufügen** wieder her. Eine Gruppenmitgliedschaft stellen die Admins wieder her, indem sie die Person der Gruppe hinzufügen.',
        '`launch_expired`: Auf der Zustimmungsseite und der Kontoauswahl erscheint dieser Fall ohne Code als **Anmeldung abgelaufen**. Der Start ist abgelaufen oder schon abgeschlossen. Das passiert, wenn die Zustimmungsseite oder die Kontoauswahl länger als 30 Minuten offen war, oder wenn der Start in einem anderen Tab schon abgeschlossen wurde. Öffnen Sie die Aktivität erneut in der Lernplattform.',
        '`launch_mismatch`: Auf der Zustimmungsseite und der Kontoauswahl erscheint dieser Fall ohne Code als **Anmeldung passt nicht**. Die Seite gehört zu einem anderen Start, oder der Browser hat das Cookie dieses Starts nicht. Das passiert, wenn die Adresse in einem anderen Browser geöffnet wird oder das Tool eingebettet startet. Öffnen Sie die Aktivität erneut und schließen Sie alle Schritte im selben Browser ab.',
        '`link_proof_failed`: Auf der Bestätigungsseite erscheint dieser Fall ohne Code als **Bestätigung fehlgeschlagen**. Der Bestätigungslink aus der E-Mail ist ungültig, älter als 24 Stunden oder schon benutzt. Öffnen Sie die Aktivität erneut und fordern Sie einen neuen Link an.',
        '`account_not_linkable`: Dieses Konto darf nicht mit einer Lernplattform verknüpft werden, zum Beispiel ein Konto mit Administrationsrechten für die ganze Plattform. Die Admins Ihrer Organisation lösen die bestehende Verknüpfung unter **LMS-Konten** mit **Verknüpfung lösen**. Öffnen Sie die Aktivität danach erneut und stimmen Sie zu. Die Seite **Eigenes Konto** bietet dann nur **Weiter** an. Damit entsteht ein separates Konto.',
        '`internal`: Ein unerwarteter Fehler auf dem Server. Die Fehlerseite zeigt dazu eine **Referenz**. Versuchen Sie es in ein paar Minuten erneut. Hält der Fehler an, geben Lehrende Fehlercode und Referenz an den Betreiber der Plattform weiter. Mit der Referenz findet er den Fehler im Server-Protokoll.',
      ],
      en: [
        '`invalid_request`: the learning platform sent an incomplete launch request. Open the activity again. If the error comes every time, the learning platform administration checks the tool settings.',
        '`registration_not_found`: no connection matches the learning platform. Usually the platform ID (issuer) or client ID in the tool settings does not match the connection, or the connection was deleted. Two active connections that cannot be told apart also lead to this code. The admins of your organization check the connection, the learning platform administration checks the tool settings.',
        '`registration_disabled`: the organization has switched off the connection. A switched-off connection shows this code on every launch. In the panel its card shows the badge **Switched off**, and the switch reads **Connection off**. The admins of your organization switch it back on with a click on the switch.',
        '`org_inactive`: the organization that owns the connection is deactivated. Only the operator of the platform can change that. Teachers contact the operator.',
        '`unknown_deployment`: the learning platform sends a deployment ID that is not registered in the connection. In ILIAS the deployment ID is the provider ID. The learning platform administration provides the ID, and the admins of your organization add it to the connection under **Deployments**.',
        '`deployment_disabled`: the deployment ID is registered in the connection but switched off. Next to the ID the switch reads **Deployment off**. The admins of your organization switch it back on under **Deployments** with a click on the switch.',
        '`tool_not_configured`: the tool signing key cannot be loaded on the server. Only the operator of the platform can fix this. Teachers contact the operator.',
        '`state_unavailable`: a temporary server problem. The server could not store or read the sign-in. This is not caused by the browser. Try again in a few minutes. If it persists, teachers pass the code on to the operator of the platform.',
        '`invalid_state`: the sign-in was older than 5 minutes or was already used, for example after going back, reloading or submitting twice. Open the activity again from the learning platform.',
        '`invalid_token`: the sign-in data from the learning platform could not be verified. Possible causes are a wrong key URL (JWKS) or client ID in the connection, new keys on the learning platform, or a server clock that is off. Open the activity again. If the error comes every time, the learning platform administration checks the tool settings together with the admins of your organization.',
        '`nonce_mismatch`: the response of the learning platform does not match the sign-in that was started. Open the activity again from the learning platform.',
        '`nonce_reused`: the same sign-in arrived a second time. Open the activity again from the learning platform.',
        '`unsupported_message`: the learning platform sends a request the tool does not support, for example Deep Linking. The learning platform administration switches Deep Linking off in the tool settings.',
        '`not_linked`: the activity is not linked to an exam yet. Teachers open the activity themselves from the learning platform and pick an exam. Students contact their teachers.',
        '`exam_unavailable`: the linked exam was deleted. Teachers open the activity and link another exam. If grades were already sent, they create a new activity in the learning platform. Students contact their teachers.',
        '`user_inactive`: the account of the person is deactivated on this platform. Only the operator of the platform can activate it again. Teachers contact the operator. An anonymized account does not come back. Anonymizing removes its link to the learning platform, so the next launch creates a new account after consent.',
        '`membership_removed`: an admin removed the person from the organization or the group of the connection. A launch from the learning platform does not restore the membership. If the person should have access again, the admins of your organization send an invitation with **Invite Member** to the email address of their account. Once the person accepts it while signed in, the membership is active again. If the account has no password yet, the person first sets one with **Forgot your password?**. If the account only has a placeholder address (the learning platform sent no address or one that is already in use), neither the invitation nor the password mail arrives. The operator of the platform then restores the membership with **Add Existing User**. The admins restore a group membership by adding the person to the group again.',
        '`launch_expired`: on the consent page and the account choice this case appears without a code as **Sign-in expired**. The launch has expired or was already completed. This happens when the consent page or the account choice was open for more than 30 minutes, or when the launch was already completed in another tab. Open the activity again from the learning platform.',
        '`launch_mismatch`: on the consent page and the account choice this case appears without a code as **Sign-in does not match**. The page belongs to another launch, or the browser does not have the cookie of this launch. This happens when the address is opened in another browser or the tool starts embedded. Open the activity again and finish all steps in the same browser.',
        '`link_proof_failed`: on the confirmation page this case appears without a code as **Confirmation failed**. The confirmation link from the email is invalid, older than 24 hours or already used. Open the activity again and request a new link.',
        '`account_not_linkable`: this account may not be linked to a learning platform, for example an account with administration rights for the whole platform. The admins of your organization remove the existing link under **LMS accounts** with **Unlink**. Then open the activity again and consent. The page **Separate account** then offers only **Continue**. This creates a separate account.',
        '`internal`: an unexpected error on the server. The error page shows a **reference** for it. Try again in a few minutes. If the error persists, teachers pass the error code and reference on to the operator of the platform. With the reference the operator finds the error in the server log.',
      ],
    },
    tips: {
      de: [
        'Die Admins Ihrer Organisation verwalten die Anbindung unter [Benutzer & Organisationen](/users-organizations) → Organisation → **Mehr** → **Lernplattform (LTI)**. Dort schalten sie Anbindung und Deployments ein und aus, tragen Deployment-IDs ein und lösen Verknüpfungen von LMS-Konten.',
        'Tool-Einstellungen wie Startcontainer und Annahme von Bewertungen, Deployment-ID, Datenschutz (in Moodle die Übermittlung von Name und E-Mail, in ILIAS die *Identifikation der Person*) sowie die Notenübertragung (in Moodle *IMS LTI Aufgaben und Bewertung*, in ILIAS *Erweiterte Benotungsdienste*) ändert nur die Administration der Lernplattform.',
      ],
      en: [
        'The admins of your organization manage the connection under [Users & organizations](/users-organizations) → organization → **More** → **Learning platform (LTI)**. There they switch the connection and its deployments on and off, add deployment IDs and unlink LMS accounts.',
        'Only the learning platform administration changes the tool settings such as the launch container and accepting grades, the deployment ID, privacy (in Moodle sending name and email, in ILIAS the *User identification*) and the grade transfer (in Moodle *IMS LTI Assignment and Grade Services*, in ILIAS *Advanced Grading Services*).',
      ],
    },
    pitfalls: {
      de: [
        'Startet das Tool eingebettet im Kurs (iframe), landen Personen auf der Anmeldeseite statt in der Klausur oder sehen **Anmeldung passt nicht** (`launch_mismatch`). Der Browser gibt die Anmelde-Cookies im eingebetteten Rahmen nicht weiter. Stellen Sie das Tool in der Lernplattform auf **Neues Fenster**. Moodle stellt nach einer Registrierung per Link „eingebettet“ ein. Dort ändert die Moodle-Administration den *Standard-Startcontainer* des Tools. Lehrende können das in Moodle 4.5 nicht je Aktivität ändern.',
        '`state_unavailable` hat nichts mit Cookies oder dem Browser zu tun. Ein anderer Browser hilft nicht, ein neuer Versuch nach einigen Minuten schon.',
        '*Zurück*, Neuladen oder ein Lesezeichen auf eine Seite des Starts führen zu `invalid_state`. Starten Sie immer aus der Lernplattform.',
        '`unknown_deployment` und `deployment_disabled` sind nicht dasselbe. Im ersten Fall fehlt die ID in der Anbindung, im zweiten ist sie eingetragen und abgeschaltet.',
      ],
      en: [
        'If the tool starts embedded in the course (iframe), people land on the login page instead of the exam, or see **Sign-in does not match** (`launch_mismatch`). The browser does not pass the sign-in cookies into the embedded frame. Set the tool to **New window** in the learning platform. After a registration by link, Moodle presets embedded. There the Moodle administration changes the tool’s *Default launch container*. Teachers cannot change it per activity in Moodle 4.5.',
        '`state_unavailable` has nothing to do with cookies or the browser. Another browser does not help, a new attempt after a few minutes does.',
        'Going back, reloading or a bookmark on a launch page leads to `invalid_state`. Always start from the learning platform.',
        '`unknown_deployment` and `deployment_disabled` are not the same. In the first case the ID is missing from the connection, in the second it is registered and switched off.',
      ],
    },
    links: [
      {
        label: { de: 'Anbindung einrichten', en: 'Setting up a connection' },
        href: '/how-to#lti-setup',
      },
      {
        label: { de: 'Anbindung verwalten', en: 'Managing a connection' },
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
          de: 'Noten kommen nicht in der Lernplattform an',
          en: 'Grades do not arrive in the learning platform',
        },
        href: '/how-to#ts-lti-grades',
      },
    ],
    keywords: {
      de: [
        'LTI Fehler',
        'Fehlercode',
        'Fehlerseite',
        'Referenz',
        'Start fehlgeschlagen',
        'Moodle Start',
        'ILIAS Start',
        'Anbindung deaktiviert',
        'Deployment-ID',
        'Provider-ID',
        'iframe',
        'eingebettet',
        'Standard-Startcontainer',
        'Anmeldeseite',
        'Anmeldung abgelaufen',
        'Anmeldung passt nicht',
        'Bestätigung fehlgeschlagen',
        ...LTI_LAUNCH_ERROR_CODES,
      ],
      en: [
        'lti error',
        'error code',
        'error page',
        'reference',
        'launch failed',
        'moodle launch',
        'ilias launch',
        'connection disabled',
        'deployment id',
        'provider id',
        'iframe',
        'embedded',
        'default launch container',
        'login page',
        'sign-in expired',
        'sign-in does not match',
        'confirmation failed',
        ...LTI_LAUNCH_ERROR_CODES,
      ],
    },
  },
  {
    id: 'ts-lti-grades',
    category: 'troubleshooting',
    title: {
      de: 'Noten kommen nicht in Moodle oder ILIAS an',
      en: 'Grades do not arrive in Moodle or ILIAS',
    },
    summary: {
      de: 'Öffnen Sie die **Aktivitätsübersicht** oder im Panel der Anbindung die **Notenübertragungen**. Dort stehen Status und Fehlertext jeder Übertragung. Die häufigsten Ursachen sind eine Aktivität ohne Bewertung, eine ausgeschaltete Notenübertragung in der Lernplattform, ein fehlender API-Schlüssel und in ILIAS die *Identifikation der Person* per *E-Mail-Adresse*. Dann meldet ILIAS „User not available“.',
      en: 'Open the **activity overview**, or **Grade transfers** in the connection panel. They show the status and the error text of every transfer. The most common causes are an activity without a grade, grade sync switched off in the learning platform, a missing API key and, in ILIAS, the *User identification* set to *E-Mail Address*. ILIAS then answers “User not available”.',
    },
    steps: {
      de: [
        '**ILIAS: „ILIAS kennt die Person nicht“ oder „User not available“**: Der ILIAS-Provider identifiziert die Personen per *E-Mail-Adresse*. In ILIAS 10.9 scheitert in diesem Modus jede Notenübertragung. Die Karte der Anbindung warnt dann mit **Notenübertragung nach ILIAS scheitert**. Die ILIAS-Administration stellt beim Provider *Identifikation der Person* auf **ID des ILIAS-Kontos …** um. Danach ändert sich die Kennung jeder Person. Beim nächsten Start stimmt jede Person erneut zu, erhält ein neues Konto und wird einmal nach ihrer E-Mail-Adresse gefragt. Bisherige Abgaben bleiben beim alten Konto.',
        '**ILIAS: kein Wert kommt an**: Beim Provider muss *Erweiterte Benotungsdienste* eingeschaltet sein. Öffnen Sie die Aktivität danach neu.',
        '**ILIAS: bestandene Klausur steht auf „in Bearbeitung“**: Der *Mastery Score* des Objekts steht noch auf 80. Setzen Sie ihn unter *Optionen für den Lernfortschritt* auf **22**. Fehlt das Feld, hakt die ILIAS-Administration beim Provider *Provider unterstützt Outcome Service* an. Den Lernfortschritt zeigt ILIAS nur, wenn er in der ILIAS-Administration eingeschaltet ist.',
        '**Moodle: die Aktivität hat keine Bewertung**: Ohne Bewertung gibt es keine Notenspalte. Schalten Sie die Bewertung in der Aktivität ein, bei Bedarf mit dem Haken *… erlauben, Bewertungen hinzuzufügen*.',
        '**Status Fehlgeschlagen mit 400, 401, 403 oder 404**: Die Lernplattform lehnt die Note endgültig ab. Das Tool versucht es deshalb nicht sofort erneut. Beheben Sie die Ursache aus dem Fehlertext und klicken Sie dann auf **Erneut senden** oder im Panel auf **Erneut versuchen**.',
        '**Status Wird übertragen oder Ausstehend mit Fehlertext**: Die Lernplattform war kurz nicht erreichbar oder hatte einen Serverfehler. Das Tool versucht es nach 10, 30 und 90 Sekunden erneut, danach in wachsenden Abständen bis zu sechs Stunden.',
        '**Noch keine Note**: Die KI-Korrektur läuft noch oder konnte nicht starten. Fehlt der Organisation ein API-Schlüssel, zeigt die Übersicht *Wartet auf einen API-Schlüssel der Organisation*.',
        '**Anbindung ausgeschaltet**: Während der Schalter **Anbindung aus** zeigt, gehen keine Noten hinaus. Schalten Sie die Anbindung ein und klicken Sie auf **Alle Noten erneut senden** oder in der Zeile auf **Erneut senden**.',
        '**Lernplattform war ausgefallen oder die Notenübertragung war dort aus**: Klicken Sie danach auf **Alle Noten erneut senden**. Die Aktivitätsübersicht bietet das je Aktivität an, das Panel der Anbindung unter **Notenübertragungen** für alle Aktivitäten einer Anbindung. Ohne diesen Klick gehen die Noten mit den automatischen Wiederholungen hinaus. Das kann bis zu sechs Stunden dauern.',
      ],
      en: [
        '**ILIAS: “ILIAS kennt die Person nicht” or “User not available”**: the ILIAS provider identifies people by *E-Mail Address*. In ILIAS 10.9 every grade transfer fails in this mode. The connection card then warns with **Grade transfer to ILIAS fails**. The ILIAS administration switches the provider’s *User identification* to **ILIAS user id …**. After that, the identifier of every person changes. On the next launch each person consents again, gets a new account and is asked once for their email address. Earlier submissions stay with the old account.',
        '**ILIAS: no value arrives**: *Advanced Grading Services* must be switched on for the provider. Then open the activity again.',
        '**ILIAS: a passed exam shows as “in progress”**: the object’s *Mastery Score* is still 80. Set it to **22** under *Options for Learning Progress*. If the field is missing, the ILIAS administration ticks *Provider supports Outcome Service* on the provider. ILIAS shows learning progress only when it is switched on in the ILIAS administration.',
        '**Moodle: the activity has no grade**: without a grade there is no grade column. Switch on grading in the activity, if needed with the tick *Allow … to add grades in the gradebook*.',
        '**Status Failed with 400, 401, 403 or 404**: the learning platform refuses the grade for good. So the tool does not try again right away. Fix the cause from the error text, then click **Send again**, or **Retry** in the panel.',
        '**Status Being transferred or Pending with an error text**: the learning platform was briefly unreachable or had a server error. The tool tries again after 10, 30 and 90 seconds, then at growing intervals of up to six hours.',
        '**No grade yet**: the AI grading is still running or could not start. If the organization lacks an API key, the overview shows *Waiting for an API key of the organization*.',
        '**Connection switched off**: while the switch reads **Connection off**, no grades go out. Switch the connection on and click **Send all grades again**, or **Send again** in the row.',
        '**The learning platform was down, or grade transfer was off there**: afterwards click **Send all grades again**. The activity overview offers it per activity, the connection panel under **Grade transfers** for all activities of a connection. Without this click the grades go out with the automatic retries. That can take up to six hours.',
      ],
    },
    tips: {
      de: [
        'Ändert sich eine Note nachträglich, etwa durch eine Korrektur oder einen neuen Notenschlüssel, geht der neue Wert spätestens nach etwa einer Stunde an die Lernplattform.',
        'ILIAS erhält je Person nur die Endnote. Eine Spalte **KI-Bewertung** gibt es nur in Moodle.',
        'Zeigt Moodle nach **Alle Noten erneut senden** weiter einen anderen Wert, wurde die Note im Moodle-Notenbuch überschrieben oder gesperrt. Moodle ändert solche Noten nicht. Heben Sie das Überschreiben in Moodle auf, dann zeigt Moodle den gesendeten Wert.',
      ],
      en: [
        'If a grade changes later, for example through a human grade or a new grading key, the new value reaches the learning platform within about an hour.',
        'ILIAS gets only the final grade per person. A **KI-Bewertung** column exists in Moodle only.',
        'If Moodle still shows another value after **Send all grades again**, the grade was overridden or locked in the Moodle gradebook. Moodle does not change such grades. Remove the override in Moodle, and Moodle shows the value sent.',
      ],
    },
    pitfalls: {
      de: [
        'Ändern Sie die *Identifikation der Person* in ILIAS nur, um den Modus *E-Mail-Adresse* zu verlassen. Jeder Wechsel trennt alle bestehenden Verknüpfungen.',
      ],
      en: [
        'Change the *User identification* in ILIAS only to leave the mode *E-Mail Address*. Every change detaches all existing links.',
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
        label: { de: 'Anbindung verwalten', en: 'Managing a connection' },
        href: '/how-to#lti-manage',
      },
      {
        label: { de: 'Anbindung einrichten', en: 'Setting up a connection' },
        href: '/how-to#lti-setup',
      },
    ],
    keywords: {
      de: [
        'Noten kommen nicht an',
        'Notenübertragung fehlgeschlagen',
        'User not available',
        'ILIAS kennt die Person nicht',
        'Identifikation der Person',
        'E-Mail-Adresse',
        'Mastery Score',
        'Lernfortschritt',
        'Erweiterte Benotungsdienste',
        'Erneut senden',
        'Alle Noten erneut senden',
        'Ausfall',
      ],
      en: [
        'grades missing',
        'grade transfer failed',
        'user not available',
        'user identification',
        'email address',
        'mastery score',
        'learning progress',
        'advanced grading services',
        'send again',
        'send all grades again',
        'outage',
      ],
    },
  },
]

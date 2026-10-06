import type { HowToGuide } from '@/lib/howto'

export const ORGANIZATION_GUIDES: HowToGuide[] = [
  {
    id: 'org-context',
    category: 'organizations',
    title: {
      de: 'Warum sehe ich keine Projekte? Privater Kontext vs. Organisation',
      en: 'Why do I see no projects? Private context vs. organization',
    },
    summary: {
      de: 'Projekte gehören zu Organisationen. Im Kontext **Privat** sehen Sie nur Ihre privaten Projekte. Wechseln Sie oben rechts im Kontomenü unter **Kontext wechseln** zur Organisation.',
      en: 'Projects belong to organizations. In the **Private** context you only see your private projects. Switch to the organization top right in the account menu under **Switch context**.',
    },
    steps: {
      de: [
        'Klicken Sie oben rechts auf Ihren Namen. In Klammern steht der aktuelle Kontext, z.B. *(Privat)* oder *(Lehrstuhl X)*.',
        'Unter **Kontext wechseln** die Organisation anklicken. Die Seite lädt neu unter der Adresse der Organisation (`organisation.what-a-benger.net`).',
        'Zurück zu Ihren privaten Projekten über **Privat**.',
      ],
      en: [
        'Click your name top right. The current context is shown in brackets, e.g. *(Private)* or *(Chair X)*.',
        'Under **Switch context** click the organization. The page reloads under the organization’s address (`organization.what-a-benger.net`).',
        'Back to your private projects via **Private**.',
      ],
    },
    tips: {
      de: [
        'Der zuletzt gewählte Kontext wird gemerkt. Lesezeichen auf die Organisationsadresse führen direkt in den richtigen Kontext.',
      ],
      en: [
        'The last chosen context is remembered. Bookmarks on the organization address lead straight into the right context.',
      ],
    },
    keywords: {
      de: [
        'Kontext',
        'Privat',
        'Organisation',
        'keine Projekte',
        'leer',
        'Subdomain',
        'Organisationswechsler',
      ],
      en: [
        'context',
        'private',
        'no projects',
        'empty',
        'subdomain',
        'org switcher',
      ],
    },
  },
  {
    id: 'org-roles',
    category: 'organizations',
    title: {
      de: 'Welche Rollen gibt es in einer Organisation und was dürfen sie?',
      en: 'Which roles exist in an organization and what can they do?',
    },
    summary: {
      de: 'Drei Rollen: **Admin** verwaltet die Organisation, lädt ein und sieht alles. **Mitwirkender** legt Projekte an, importiert Daten, startet Generierung und Evaluation. **Annotator** annotiert zugewiesene oder offene Aufgaben und löst Klausuren. Jedes Mitglied hat eine Rolle in der Organisation und in jeder seiner Gruppen eine eigene Rolle in der Gruppe.',
      en: 'Three roles: **Admin** manages the organization, invites and sees everything. **Contributor** creates projects, imports data, starts generation and evaluation. **Annotator** annotates assigned or open tasks and solves exams. Every member has one role in the organization and, in each of their groups, a separate role in the group.',
    },
    steps: {
      de: [
        '**Admin**: Mitglieder und Rollen, Gruppen, API-Schlüssel der Organisation, Einladungen, Projekt-Sichtbarkeit und [Lernplattform-Anbindungen](/how-to#lti-manage) (Moodle, ILIAS). Sieht die Klarnamen der Personen aus den eigenen Anbindungen. Umgeht Zuweisungen und Zugriffsfenster. Gruppen-Admins verwalten die Anbindungen ihrer Gruppe.',
        '**Mitwirkender**: Alles rund um Projekte und Daten (Import, Export, Generierung, Evaluation, Berichte), aber keine Mitgliederverwaltung. Sieht und korrigiert auch private Klausuren anderer, die mit einer Lernplattform der Organisation verknüpft sind. Personen aus einer Lernplattform erscheinen in Listen unter ihrem Pseudonym, außer bei Klausuren, die der Mitwirkende bewerten darf.',
        '**Annotator**: Sieht Projekte der Organisation als Annotierende:r, keine Datenseite, keine Mitgliederliste. Bei Klausuren nur die Teilnehmer-Sicht ohne Musterlösung vor der Abgabe.',
        '**Rolle in der Organisation und Rolle in der Gruppe**: Die Rolle in der Organisation gilt für organisationsweite Projekte und für alles auf Ebene der Organisation. Auf einem Projekt einer [Gruppe](/how-to#org-groups) zählt die Rolle in dieser Gruppe; sie darf höher oder niedriger sein. Beispiel: In der Organisation Annotator, im Lehrstuhl A Annotator (dort Klausuren nur als Teilnehmer:in), im Lehrstuhl B Admin (dort Projekte anlegen und betreuen). Organisationsadmins sind in jeder Gruppe Admin.',
        'Rollen ändern: [Benutzer & Organisationen](/users-organizations) → Tab *Organisationen* → Organisation wählen → Mitgliederliste. Admins können andere Admins nicht ändern. Rollen in einer Gruppe ändern Sie unter **Gruppen** → **Mitglieder**.',
      ],
      en: [
        '**Admin**: members and roles, groups, the organization’s API keys, invitations, project visibility and [learning platform connections](/how-to#lti-manage) (Moodle, ILIAS). Sees the real names of the people on the organization’s own connections. Bypasses assignments and access windows. Group admins manage their group’s connections.',
        '**Contributor**: everything around projects and data (import, export, generation, evaluation, reports), but no member management. Also sees and grades other people’s private exams that are linked to a learning platform of the organization. People from a learning platform appear in lists under their pseudonym, except on exams the contributor may grade.',
        '**Annotator**: sees organization projects as an annotator, no data page, no member list. On exams only the participant view without the model solution before submission.',
        '**Organization role and group role**: the organization role applies to organization-wide projects and to everything at the organization level. On a project of a [group](/how-to#org-groups) the role in that group counts; it may be higher or lower. Example: annotator in the organization, annotator in chair A (exams there only as a participant), admin in chair B (creates and runs projects there). Organization admins are admin in every group.',
        'Change roles: [Users & organizations](/users-organizations) → tab *Organizations* → pick the organization → member list. Admins cannot change other admins. Group roles are changed under **Groups** → **Members**.',
      ],
    },
    tips: {
      de: [
        'Neue Organisationen legt nur die Plattform-Administration (Superadmin) an. Schreiben Sie uns, wenn Sie eine brauchen.',
      ],
      en: [
        'New organizations are created by the platform administration (superadmin) only. Write to us if you need one.',
      ],
    },
    keywords: {
      de: [
        'Rolle',
        'Rollen',
        'Admin',
        'Mitwirkender',
        'Annotator',
        'Rechte',
        'Berechtigung',
        'Gruppenrolle',
      ],
      en: [
        'role',
        'roles',
        'admin',
        'contributor',
        'annotator',
        'permissions',
        'group role',
      ],
    },
  },
  {
    id: 'invite-members',
    category: 'organizations',
    title: {
      de: 'Wie lade ich jemanden in meine Organisation ein?',
      en: 'How do I invite someone to my organization?',
    },
    summary: {
      de: 'Unter [Benutzer & Organisationen](/users-organizations) → *Organisationen* → **Mitglied einladen** (oder **Mehrere einladen**). Die Person erhält eine E-Mail mit einem Link, der 7 Tage gültig ist, und tritt beim Annehmen mit der gewählten Rolle bei.',
      en: 'Under [Users & organizations](/users-organizations) → *Organizations* → **Invite member** (or **Invite several**). The person gets an email with a link valid for 7 days and joins with the chosen role on accepting.',
    },
    steps: {
      de: [
        'Organisation in der linken Liste wählen, Abschnitt **Mitglieder**.',
        '**Mitglied einladen**: E-Mail, optional **Gruppe** (sonst *Keine (ganze Organisation)*) und die **Rolle** (Admin, Mitwirkender, Annotator). Mit Gruppe wählen Sie die **Rolle in der Gruppe** und die **Rolle in der Organisation** (Vorgabe Annotator). Für mehrere Adressen **Mehrere einladen**, getrennt durch Komma, Semikolon oder Zeilenumbruch.',
        'Gruppen-Admins laden nur in ihre eigenen Gruppen ein, mit beliebiger Rolle in der Gruppe. In der Organisation werden die Eingeladenen Annotator; nur Organisationsadmins können das ändern.',
        '**Einladung senden**. Offene Einladungen stehen unter *Ausstehende Einladungen* und lassen sich dort zurückziehen.',
        'Die Person klickt den Link: Mit bestehendem Konto **Anmelden zum Annehmen**, sonst **Einladung annehmen & Konto erstellen**. Neue Konten sind sofort verifiziert.',
      ],
      en: [
        'Pick the organization in the left list, section **Members**.',
        '**Invite member**: email, optionally a **group** (otherwise *None (whole organization)*) and the **role** (Admin, Contributor, Annotator). With a group you pick the **role in the group** and the **role in the organization** (default Annotator). For several addresses use **Invite several**, separated by comma, semicolon or line break.',
        'Group admins invite only into their own groups, with any group role. In the organization the invitees become annotators; only organization admins can change that.',
        '**Send invitation**. Open invitations are listed under *Pending invitations* and can be cancelled there.',
        'The person clicks the link: with an existing account **Sign in to accept**, otherwise **Accept & create account**. New accounts are verified immediately.',
      ],
    },
    pitfalls: {
      de: [
        'Die Einladung ist an die eingeladene E-Mail-Adresse gebunden. Wer mit einem anderen Konto angemeldet ist, sieht einen Hinweis und muss sich mit der eingeladenen Adresse anmelden.',
        'Für eine Adresse, die bereits Mitglied ist oder eine offene Einladung hat, wird keine zweite Einladung angelegt. Ist eine Gruppe gewählt, kommen bestehende Mitglieder der Organisation direkt mit der gewählten Rolle in die Gruppe. Die Rückmeldung nennt jede übersprungene Adresse mit Grund.',
        'Einen Beitritt über die E-Mail-Domain gibt es nicht. Jedes Mitglied kommt über eine Einladung, eine Lernplattform-Anbindung (LTI) oder die Plattform-Administration.',
      ],
      en: [
        'The invitation is bound to the invited email address. Someone signed in with another account sees a notice and must sign in with the invited address.',
        'No second invitation is created for an address that is already a member or has an open invitation. With a group chosen, existing organization members are added straight to the group with the chosen role. The result names every skipped address with its reason.',
        'There is no joining by email domain. Every member comes in through an invitation, a learning-platform connection (LTI) or the platform administration.',
      ],
    },
    keywords: {
      de: [
        'einladen',
        'Einladung',
        'Mitglied',
        'E-Mail',
        'beitreten',
        'Link abgelaufen',
      ],
      en: ['invite', 'invitation', 'member', 'join', 'expired link'],
    },
  },
  {
    id: 'org-groups',
    category: 'organizations',
    title: {
      de: 'Wie lege ich Gruppen (z.B. Lehrstühle) an und wer verwaltet sie?',
      en: 'How do I create groups (e.g. chairs) and who manages them?',
    },
    summary: {
      de: 'Gruppen teilen eine Organisation auf: Projekte und API-Schlüssel können auf eine Gruppe beschränkt werden, und Gruppenmitglieder sehen nur ihre Gruppenprojekte. Jedes Gruppenmitglied hat eine eigene **Rolle in der Gruppe** (Admin, Mitwirkender, Annotator). Organisationsadmins legen Gruppen unter **Gruppen** an. Wer in einer Gruppe Admin ist, verwaltet Mitglieder, Rollen und Schlüssel dieser Gruppe, ohne organisationsweite Rechte.',
      en: 'Groups split an organization: projects and API keys can be restricted to a group, and group members only see their group’s projects. Every group member has their own **role in the group** (Admin, Contributor, Annotator). Organization admins create groups under **Groups**. Whoever is admin of a group manages that group’s members, roles and keys without organization-wide rights.',
    },
    steps: {
      de: [
        '[Benutzer & Organisationen](/users-organizations) → *Organisationen* → Organisation wählen → Button **Gruppen**.',
        '**Neue Gruppe**: Name (z.B. *Lehrstuhl für Zivilrecht*) und Beschreibung, dann **Gruppe erstellen**. Nur Organisationsadmins können Gruppen anlegen, umbenennen, deaktivieren und löschen.',
        '**Mitglieder** einer Gruppe: **Mitglied hinzufügen** aus den bestehenden Organisationsmitgliedern mit der **Rolle in der Gruppe** (Vorgabe Annotator). Die Rolle lässt sich je Mitglied in der Liste ändern. Neue Personen laden Sie direkt in die Gruppe ein (Einladung mit gesetzter *Gruppe* und Rolle in der Gruppe).',
        '**Projekte auf eine Gruppe beschränken**: Beim Anlegen unter *Sichtbarkeit → Organisation* je Organisation die **Gruppe** wählen (Vorgabe *Gesamte Organisation*), später auf der Projektseite unter *Projekt-Sichtbarkeit*. Angeboten werden die Gruppen, in denen Sie Mitwirkender oder Admin sind; *Gesamte Organisation* nur mit der Rolle Mitwirkender oder Admin in der Organisation.',
        '**Schlüssel je Gruppe**: Im Dialog *API-Schlüssel* der Organisation den **Geltungsbereich** auf die Gruppe stellen. Gruppenprojekte nutzen zuerst den Gruppenschlüssel, sonst den der Organisation.',
      ],
      en: [
        '[Users & organizations](/users-organizations) → *Organizations* → pick the organization → button **Groups**.',
        '**New group**: name (e.g. *Chair of Civil Law*) and description, then **Create group**. Only organization admins can create, rename, deactivate and delete groups.',
        '**Members** of a group: **Add member** from the existing organization members with their **role in the group** (default Annotator). The role can be changed per member in the list. New people are invited straight into the group (invitation with the *Group* and group role set).',
        '**Restrict projects to a group**: when creating, under *Visibility → Organization* pick the **group** per organization (default *Whole organization*), later on the project page under *Project visibility*. Offered are the groups where you are contributor or admin; *Whole organization* only with the role contributor or admin in the organization.',
        '**Keys per group**: in the organization’s *API keys* dialog set the **scope** to the group. Group projects use the group key first, else the organization’s.',
      ],
    },
    tips: {
      de: [
        'Ohne Gruppen ändert sich nichts. Alles, was nicht auf eine Gruppe beschränkt ist, gilt weiter für die gesamte Organisation.',
        'Gruppenmitgliedschaft steuert die Sichtbarkeit, die Rolle in der Gruppe die Rechte auf den Gruppenprojekten. Auf organisationsweiten Projekten gilt die Rolle in der Organisation.',
        'Organisationsadmins sehen alle Gruppenprojekte und sind in jeder Gruppe Admin. Gruppen-Admins haben Admin-Rechte nur auf Projekten ihrer Gruppe, auch wenn sie in der Organisation Annotator sind.',
      ],
      en: [
        'Without groups nothing changes. Everything not restricted to a group keeps applying to the whole organization.',
        'Group membership drives visibility, the group role drives rights on the group’s projects. On organization-wide projects the organization role applies.',
        'Organization admins see every group project and are admin in every group. Group admins have admin rights only on their group’s projects, even when they are annotators in the organization.',
      ],
    },
    pitfalls: {
      de: [
        'Eine Gruppe lässt sich erst löschen, wenn keine Projekte, Schlüssel oder Lernplattform-Anbindungen mehr auf sie zeigen. Deaktivieren (*Gruppe ist aktiv* aus) geht immer und blockiert nur neue Zuordnungen.',
        'Ein Gruppen-Admin ändert keine Rollen in der Organisation, lädt nur als Annotator der Organisation ein und legt keine neuen Gruppen an.',
      ],
      en: [
        'A group can only be deleted once no projects, keys or learning-platform registrations point at it. Deactivating (*Group is active* off) always works and only blocks new attachments.',
        'A group admin does not change organization roles, invites only as organization annotator and cannot create new groups.',
      ],
    },
    keywords: {
      de: [
        'Gruppe',
        'Gruppen',
        'Lehrstuhl',
        'Gruppen-Admin',
        'Geltungsbereich',
        'Untergruppe',
      ],
      en: ['group', 'groups', 'chair', 'group admin', 'scope', 'department'],
    },
  },
]

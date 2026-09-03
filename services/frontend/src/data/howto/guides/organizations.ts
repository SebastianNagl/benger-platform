import type { HowToGuide } from '@/lib/howto'

export const ORGANIZATION_GUIDES: HowToGuide[] = [
  {
    id: 'org-context',
    category: 'organizations',
    title: { de: 'Warum sehe ich keine Projekte? Privater Kontext vs. Organisation', en: 'Why do I see no projects? Private context vs. organization' },
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
      de: ['Der zuletzt gewählte Kontext wird gemerkt. Lesezeichen auf die Organisationsadresse führen direkt in den richtigen Kontext.'],
      en: ['The last chosen context is remembered. Bookmarks on the organization address lead straight into the right context.'],
    },
    keywords: { de: ['Kontext', 'Privat', 'Organisation', 'keine Projekte', 'leer', 'Subdomain', 'Organisationswechsler'], en: ['context', 'private', 'no projects', 'empty', 'subdomain', 'org switcher'] },
  },
  {
    id: 'org-roles',
    category: 'organizations',
    title: { de: 'Welche Rollen gibt es in einer Organisation und was dürfen sie?', en: 'Which roles exist in an organization and what can they do?' },
    summary: {
      de: 'Drei Rollen: **Admin** verwaltet die Organisation, lädt ein und sieht alles. **Mitwirkender** legt Projekte an, importiert Daten, startet Generierung und Evaluation. **Annotator** annotiert zugewiesene oder offene Aufgaben und löst Klausuren.',
      en: 'Three roles: **Admin** manages the organization, invites and sees everything. **Contributor** creates projects, imports data, starts generation and evaluation. **Annotator** annotates assigned or open tasks and solves exams.',
    },
    steps: {
      de: [
        '**Admin**: Mitglieder und Rollen, Gruppen, API-Schlüssel der Organisation, Einladungen, Projekt-Sichtbarkeit. Umgeht Zuweisungen und Zugriffsfenster.',
        '**Mitwirkender**: Alles rund um Projekte und Daten (Import, Export, Generierung, Evaluation, Berichte), aber keine Mitgliederverwaltung.',
        '**Annotator**: Sieht Projekte der Organisation als Annotierende:r, keine Datenseite, keine Mitgliederliste. Bei Klausuren nur die Teilnehmer-Sicht ohne Musterlösung vor der Abgabe.',
        'Rollen ändern: [Benutzer & Organisationen](/users-organizations) → Tab *Organisationen* → Organisation wählen → Mitgliederliste. Admins können andere Admins nicht ändern.',
      ],
      en: [
        '**Admin**: members and roles, groups, the organization’s API keys, invitations, project visibility. Bypasses assignments and access windows.',
        '**Contributor**: everything around projects and data (import, export, generation, evaluation, reports), but no member management.',
        '**Annotator**: sees organization projects as an annotator, no data page, no member list. On exams only the participant view without the model solution before submission.',
        'Change roles: [Users & organizations](/users-organizations) → tab *Organizations* → pick the organization → member list. Admins cannot change other admins.',
      ],
    },
    tips: {
      de: ['Neue Organisationen legt nur die Plattform-Administration (Superadmin) an. Schreiben Sie uns, wenn Sie eine brauchen.'],
      en: ['New organizations are created by the platform administration (superadmin) only. Write to us if you need one.'],
    },
    keywords: { de: ['Rolle', 'Rollen', 'Admin', 'Mitwirkender', 'Annotator', 'Rechte', 'Berechtigung'], en: ['role', 'roles', 'admin', 'contributor', 'annotator', 'permissions'] },
  },
  {
    id: 'invite-members',
    category: 'organizations',
    title: { de: 'Wie lade ich jemanden in meine Organisation ein?', en: 'How do I invite someone to my organization?' },
    summary: {
      de: 'Unter [Benutzer & Organisationen](/users-organizations) → *Organisationen* → **Mitglied einladen** (oder **Mehrere einladen**). Die Person erhält eine E-Mail mit einem Link, der 7 Tage gültig ist, und tritt beim Annehmen mit der gewählten Rolle bei.',
      en: 'Under [Users & organizations](/users-organizations) → *Organizations* → **Invite member** (or **Invite several**). The person gets an email with a link valid for 7 days and joins with the chosen role on accepting.',
    },
    steps: {
      de: [
        'Organisation in der linken Liste wählen, Abschnitt **Mitglieder**.',
        '**Mitglied einladen**: E-Mail, **Rolle** (Admin, Mitwirkender, Annotator) und optional **Gruppe** (sonst *Keine (ganze Organisation)*). Für mehrere Adressen **Mehrere einladen**, getrennt durch Komma, Semikolon oder Zeilenumbruch.',
        '**Einladung senden**. Offene Einladungen stehen unter *Ausstehende Einladungen* und lassen sich dort zurückziehen.',
        'Die Person klickt den Link: Mit bestehendem Konto **Anmelden zum Annehmen**, sonst **Einladung annehmen & Konto erstellen**. Neue Konten sind sofort verifiziert.',
      ],
      en: [
        'Pick the organization in the left list, section **Members**.',
        '**Invite member**: email, **role** (Admin, Contributor, Annotator) and optionally a **group** (otherwise *None (whole organization)*). For several addresses use **Invite several**, separated by comma, semicolon or line break.',
        '**Send invitation**. Open invitations are listed under *Pending invitations* and can be cancelled there.',
        'The person clicks the link: with an existing account **Sign in to accept**, otherwise **Accept & create account**. New accounts are verified immediately.',
      ],
    },
    pitfalls: {
      de: [
        'Die Einladung ist an die eingeladene E-Mail-Adresse gebunden. Wer mit einem anderen Konto angemeldet ist, sieht einen Hinweis und muss sich mit der eingeladenen Adresse anmelden.',
        'Für eine Adresse, die bereits Mitglied ist oder eine offene Einladung hat, wird keine zweite Einladung angelegt.',
        'Einen Beitritt über die E-Mail-Domain gibt es nicht. Jedes Mitglied kommt über eine Einladung, eine Lernplattform-Anbindung (LTI) oder die Plattform-Administration.',
      ],
      en: [
        'The invitation is bound to the invited email address. Someone signed in with another account sees a notice and must sign in with the invited address.',
        'No second invitation is created for an address that is already a member or has an open invitation.',
        'There is no joining by email domain. Every member comes in through an invitation, a learning-platform connection (LTI) or the platform administration.',
      ],
    },
    keywords: { de: ['einladen', 'Einladung', 'Mitglied', 'E-Mail', 'beitreten', 'Link abgelaufen'], en: ['invite', 'invitation', 'member', 'join', 'expired link'] },
  },
  {
    id: 'org-groups',
    category: 'organizations',
    title: { de: 'Wie lege ich Gruppen (z.B. Lehrstühle) an und wer verwaltet sie?', en: 'How do I create groups (e.g. chairs) and who manages them?' },
    summary: {
      de: 'Gruppen teilen eine Organisation auf: Projekte und API-Schlüssel können auf eine Gruppe beschränkt werden, und Gruppenmitglieder sehen nur ihre Gruppenprojekte. Organisationsadmins legen Gruppen unter **Gruppen** an. Ein **Gruppen-Admin** verwaltet Mitglieder und Schlüssel seiner Gruppe, ohne organisationsweite Rechte.',
      en: 'Groups split an organization: projects and API keys can be restricted to a group, and group members only see their group’s projects. Organization admins create groups under **Groups**. A **group admin** manages the members and keys of their group without organization-wide rights.',
    },
    steps: {
      de: [
        '[Benutzer & Organisationen](/users-organizations) → *Organisationen* → Organisation wählen → Button **Gruppen**.',
        '**Neue Gruppe**: Name (z.B. *Lehrstuhl für Zivilrecht*) und Beschreibung, dann **Gruppe erstellen**. Nur Organisationsadmins können Gruppen anlegen, umbenennen, deaktivieren und löschen.',
        '**Mitglieder** einer Gruppe: **Mitglied hinzufügen** aus den bestehenden Organisationsmitgliedern, optional **Als Gruppen-Admin**. Neue Personen laden Sie direkt in die Gruppe ein (Einladung mit gesetzter *Gruppe*).',
        '**Projekte auf eine Gruppe beschränken**: Beim Anlegen unter *Sichtbarkeit → Organisation* je Organisation die **Gruppe** wählen (Vorgabe *Gesamte Organisation*), später auf der Projektseite unter *Projekt-Sichtbarkeit*.',
        '**Schlüssel je Gruppe**: Im Dialog *API-Schlüssel* der Organisation den **Geltungsbereich** auf die Gruppe stellen. Gruppenprojekte nutzen zuerst den Gruppenschlüssel, sonst den der Organisation.',
      ],
      en: [
        '[Users & organizations](/users-organizations) → *Organizations* → pick the organization → button **Groups**.',
        '**New group**: name (e.g. *Chair of Civil Law*) and description, then **Create group**. Only organization admins can create, rename, deactivate and delete groups.',
        '**Members** of a group: **Add member** from the existing organization members, optionally **As group admin**. New people are invited straight into the group (invitation with the *Group* set).',
        '**Restrict projects to a group**: when creating, under *Visibility → Organization* pick the **group** per organization (default *Whole organization*), later on the project page under *Project visibility*.',
        '**Keys per group**: in the organization’s *API keys* dialog set the **scope** to the group. Group projects use the group key first, else the organization’s.',
      ],
    },
    tips: {
      de: [
        'Ohne Gruppen ändert sich nichts. Alles, was nicht auf eine Gruppe beschränkt ist, gilt weiter für die gesamte Organisation.',
        'Gruppenmitgliedschaft steuert die Sichtbarkeit, die Organisationsrolle die Rechte. Ein Annotator in einer Gruppe bleibt Annotator.',
        'Organisationsadmins sehen alle Gruppenprojekte. Gruppen-Admins haben Admin-Rechte nur auf Projekten ihrer Gruppe.',
      ],
      en: [
        'Without groups nothing changes. Everything not restricted to a group keeps applying to the whole organization.',
        'Group membership drives visibility, the organization role drives rights. An annotator in a group stays an annotator.',
        'Organization admins see every group project. Group admins have admin rights only on their group’s projects.',
      ],
    },
    pitfalls: {
      de: [
        'Eine Gruppe lässt sich erst löschen, wenn keine Projekte, Schlüssel oder Lernplattform-Anbindungen mehr auf sie zeigen. Deaktivieren (*Gruppe ist aktiv* aus) geht immer und blockiert nur neue Zuordnungen.',
        'Ein Gruppen-Admin kann niemanden als Organisationsadmin einladen und keine neuen Gruppen anlegen.',
      ],
      en: [
        'A group can only be deleted once no projects, keys or learning-platform registrations point at it. Deactivating (*Group is active* off) always works and only blocks new attachments.',
        'A group admin cannot invite anyone as organization admin and cannot create new groups.',
      ],
    },
    keywords: { de: ['Gruppe', 'Gruppen', 'Lehrstuhl', 'Gruppen-Admin', 'Geltungsbereich', 'Untergruppe'], en: ['group', 'groups', 'chair', 'group admin', 'scope', 'department'] },
  },
]

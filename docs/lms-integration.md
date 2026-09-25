# LMS integration (LTI 1.3) for Moodle and ILIAS

BenGER connects to a university's learning management system (LMS) as an
**LTI 1.3 Advantage tool**. Students open an exam from a course activity, and
grades go back to the LMS gradebook.

**Setting it up?** Start with the short step-by-step guides in
[`lms-setup/`](lms-setup/README.md) (German): one each for organization
admins, the ILIAS administration, the Moodle administration and teachers.
This document is the reference behind them.

This document is for the people who evaluate and run the integration: LMS
administrators, university IT, organization admins in BenGER and data
protection officers. It describes what the tool does on the wire, what it
stores and what it needs from your LMS. German setup sheets for the LMS
administration are in [Appendix A](#appendix-a-ilias-setup-sheet-german) and
[Appendix B](#appendix-b-moodle-setup-sheet-german).

**The data protection review in brief.**

- Hosting is in Germany.
- Nobody gets an account before they consent. Students and teachers consent
  once per connection.
- Consent to research use is required. See [§8.4](#84-consent).
- Accounts carry the name and email address that the LMS sends. From ILIAS
  they carry the name only, because ILIAS has to identify people by their
  ILIAS user id (see [§3](#ilias-limitations-to-plan-around)). Such
  accounts are asked once, right after consent, for an email address. The
  step can be skipped. The app shows a pseudonym. Real names are visible to the organization's admins, to
  the course teachers, to the staff who may grade the linked exam and to the
  platform administrators.
- The AI grade and the human grade are kept side by side. The human grade is
  the final grade.
- AI grading runs only on your organization's own API key. There is no
  fallback to a key of ours. It sends the solution text, without name or
  email, to that key's model provider (OpenAI with the default models).
- Organization admins can anonymize the accounts that the LMS created.
- We act as processor. Tell us what your data protection officer needs, using
  the list in [§8.8](#88-compliance-tell-us-what-you-need).

## 1. Edition boundary (read this first)

BenGER follows an open-core model. The LMS integration is split across the two
editions.

| Part | Edition | Where |
|---|---|---|
| Database schema for all LTI state: eight tables, migrations `079`, `083`, `084`, `085`, `089`, `097`, `105` and `106` | Community (Apache-2.0) | `services/api/alembic/versions/` |
| Connection management API (`/api/admin/lti/*`) for superadmins, org admins and group admins: connections, invites, deployments, tool sheet, activities, LMS accounts with unlink and anonymization, grade transfers with retry and "send all grades again" (the sending needs the extended edition), history | Community (Apache-2.0) | `services/api/routers/lti_admin.py` |
| Account anonymization | Community (Apache-2.0) | `services/api/services/user_anonymization.py` |
| Hiding LMS users' names in member lists, task lists and exports. The rule who may see a name comes from the commercial edition. | Community (Apache-2.0) | `services/api/services/member_privacy.py`, `services/shared/lms_name_masking.py` |
| Page routes for consent, account choice, email confirmation, exam picker, activity overview and the error page, plus the list of launch error codes. Most pages show content from the commercial edition. | Community (Apache-2.0) | `services/frontend/src/app/lti/`, `services/frontend/src/lib/lti/launchErrors.ts` |
| Admin panel for connections, consent page, account choice, exam picker, activity overview | **Commercial (BenGER Extended)** | not in this repository |
| **LTI protocol and rules**: OIDC login, `id_token` validation, launch, consent and account linking, JWKS, grade transfer (AGS), Dynamic Registration, billing of linked exams | **Commercial (BenGER Extended)** | not in this repository |

The eight tables are `lti_platform_registrations`, `lti_deployments`,
`lti_resource_links`, `lti_user_links` and `lti_grade_syncs` (migration 079),
`lti_registration_invites` (083), and `lti_resource_link_users` and
`lti_admin_events` (105). The other migrations add columns:

| Migration | Adds |
|---|---|
| `084` | the organization role for LMS students |
| `085` | a parked activation address on `users` |
| `089` | the LMS type of a connection (Moodle, ILIAS) |
| `097` | the group scope of connections and invites |
| `105` | the tool address of connections and invites, the research consent, link method and unlink marker of LMS identities, the AI grade column of activities, one grade transfer row per column |
| `106` | the anonymization marker and the email state of LMS accounts, the change time of gradings, the origin of an exam's organization attachment |

The routes an LMS talks to (`/api/lti/login`, `/api/lti/launch`,
`/api/lti/jwks`, `/api/lti/register/init`) are served by the commercial
edition. **A deployment built from this repository alone has the admin API but
cannot accept a launch.** The community edition is a complete benchmarking and
annotation platform. It is not an LTI tool.

If you are evaluating BenGER for LMS use, a review of the open repository
covers the data model, the tenant and role model, the admin API and the
storage of every LTI record. It does not cover the protocol handling. For that
half, this document is the specification, and a source review can be arranged
under NDA. Contact details are in [§12](#12-support-and-contact).

## 2. What the integration does

1. An organization admin connects the LMS in BenGER. The connection is active
   at once. See [§6](#6-registering-your-lms).
2. A teacher adds an external tool activity to a course and opens it. On the
   first launch the teacher consents and then picks the exam behind the
   activity. Later launches open the exam's page, which links the activity
   overview with all submissions and grades.
3. A student opens the activity. On the first launch the student consents.
   Only then is an account created. The student then lands in the exam.
   Returning students go straight to the exam.
4. After submission, the AI grades the solution on the organization's API key.
   The grade goes to the LMS through **Assignment and Grade Services (AGS)**.
5. A teacher can grade the submission as well. The human grade becomes the
   final grade in the LMS. The AI grade is kept, and Moodle shows it in a
   second column, "KI-Bewertung: <activity title>".

Grades are sent as German *Notenpunkte*, 0 to 18, with `scoreMaximum: 18`.
The LMS rescales the activity column to the activity's maximum grade. An
activity graded out of 100 shows 12 of 18 points as 66.67.

## 3. Supported systems

| LMS | Version | Status |
|---|---|---|
| Moodle | 4.5 | Validated end to end on 4.5.12, including Dynamic Registration |
| Moodle | 5.x | Reviewed against the 5.2 source. Not validated on a live system. |
| ILIAS | 10 | Validated end to end on 10.9 |
| ILIAS | 9 | Expected to work. Not validated on a live system. |

ILIAS 8 reached end of life on 2025-12-31 and is not supported. ILIAS 11 is
expected to change AGS behaviour and will be validated when it ships.

Other LTI 1.3 certified platforms may work, because nothing in the tool is
Moodle or ILIAS specific on the wire. They are not validated and not
supported. See [§10](#10-conformance) for what has been tested.

### ILIAS limitations to plan around

These are properties of ILIAS 10, not of BenGER.

- **Identify people by their ILIAS user id.** The provider's privacy
  setting *Identifikation der Person* (English ILIAS: *User
  identification*) decides how ILIAS names a person to the tool. Choose
  *ID des ILIAS-Kontos kombiniert mit einer eindeutigen
  ILIAS-Plattform-ID, die als E-Mail-Adresse formatiert ist* (*ILIAS user
  id combined with a unique ILIAS platform id formatted as an E-Mail
  address*). This is the supported setting for every ILIAS connection.

  Set *Anmeldename* (*User name*) to *Vollständiger Name* (*Entire name*).
  Do not choose *E-Mail-Adresse* (*E-Mail Address*). In ILIAS 10.9 the
  grade service cannot find the person in that mode and refuses every
  grade with `404 User not available`. This is an ILIAS issue. Choose the
  mode before go-live and do not change it afterwards (see
  [§6](#6-registering-your-lms)).
- **No email address from ILIAS.** In this mode ILIAS sends only a pseudo
  address that ends in `.ilias`, and the tool ignores it. Accounts from
  ILIAS therefore start with the full name but no email address, so there
  is no automatic activation mail and no linking to an existing account.
  Right after consent, students and teachers are asked once for an email
  address. The step can be skipped. The confirmation link sent to that
  address is the activation mail (see [§8.1](#81-accounts-and-names)).
- **ILIAS has no AGS line item service.** The tool works only with the
  `lineitem` URL from the launch. ILIAS therefore gets one value per student,
  the final grade. There is no "KI-Bewertung" column. The activity must carry
  a grade. Every launch refreshes the `lineitem` URL. If the grade is added
  later, open the activity once. Waiting grades then go out at the next
  hourly sweep. Transfers already marked `failed` are retried about six hours
  after their last attempt; **Send again** in the activity overview or
  **Retry** in the admin panel sends them at once. **Send all grades again**
  sends every grade of an activity or a connection at once.
- **The score comment is discarded.** ILIAS stores the score but not the
  comment. Written feedback is visible only inside BenGER.
- **Grades appear as learning progress, not as a gradebook column.** ILIAS
  compares the score with the object's *Mastery Score*, which defaults to
  80 %. A passing law exam is 4 of 18 points, about 22 %. With the default, a
  passed exam shows as "in progress". Set the Mastery Score to **22**:
  - The field appears only when the provider has *Provider unterstützt
    Outcome Service* (*Provider supports Outcome Service*) ticked. Tick it
    and set *Voreinstellung Mastery Score* (*Default Mastery Score*) to 22
    before teachers create objects. An object copies the value when it is
    created.
  - Objects created earlier keep their value. Change it in the object's
    settings under *Optionen für den Lernfortschritt* (*Options for Learning
    Progress*).
  - The learning progress view needs learning progress switched on for the
    whole installation: *Administration → Lernerfolge → Zugriffsstatistiken
    und Lernfortschritt → Einstellungen*, *Lernfortschritt* (English ILIAS:
    *Achievements → Statistics and Learning Progress*).
- **No Names and Role Provisioning Service (NRPS)** before ILIAS 12. Accounts
  are created at launch only. Moodle is used the same way.

## 4. Architecture and data flow

```
  Person in the LMS course
        │ 1. opens the external tool activity
        ▼
  LMS ──POST /api/lti/login──────────────▶ tool
                                            stores the login state with its
                                            nonce on the server (5 min,
                                            deleted on use)
        ◀──302 to the LMS authorization endpoint
        │ 2. the LMS signs an id_token
        ▼
  LMS ──POST /api/lti/launch─────────────▶ tool
                                            checks the signature (LMS JWKS),
                                            iss, aud, exp, nonce, deployment
                                            marks the nonce as used (10 min)
                                            records the activity (course and
                                            activity title, no personal data)
        known LMS identity with current consent?
          yes ─▶ opens the session, go to 4
          no  ─▶ holds the checked launch on the server (30 min),
                 sets a launch cookie, shows the consent page
        │ 3. the person consents. If one account already has the same
        │    email address: sign in, confirm by email, activate that
        │    account first, or choose a separate account.
        ▼
                                            creates or links the account,
                                            adds memberships and exam access,
                                            sends the activation mail,
                                            opens the session
        │ 3a. no address that can receive mail (ILIAS, or an LMS that
        │     withholds it): the page asks once for one (skippable)
        │ 4. teacher: exam picker or the exam's page
        │    student: the exam
        ▼
  submission ─▶ AI grading on the organization's API key
        │ 5. grade transfer
        ▼
  tool ──client_credentials + private_key_jwt──▶ LMS token endpoint
  tool ──score to the activity line item───────▶ final grade
  tool ──score to the "KI-Bewertung" item──────▶ AI grade (Moodle with column
                                                 management)
```

Server to server calls use HTTPS. The tool never runs inside an LMS iframe.
See [§9](#9-requirements-on-your-lms).

## 5. Tool endpoints and scopes

| Purpose | URL |
|---|---|
| Login initiation (OIDC third-party login) | `https://<tool-host>/api/lti/login` |
| Launch and redirect URI | `https://<tool-host>/api/lti/launch` |
| Public keyset (JWKS) | `https://<tool-host>/api/lti/jwks` |
| Dynamic Registration | `https://<tool-host>/api/lti/register/init?token=<token>` (one-time invite link) |

`<tool-host>` is the address chosen for the connection (see
[§6](#6-registering-your-lms)). The tool sheet in the admin panel always shows
the URLs of the connection's address, never the address of the browser.

There is **no deep-linking URL**, on purpose. The tool rejects
`LtiDeepLinkingRequest` launches. The exam is bound through the teacher's
picker instead ([§7](#7-course-setup-teacher)). Do not configure deep linking
in your LMS.

### Scopes requested

| Scope | Why |
|---|---|
| `https://purl.imsglobal.org/spec/lti-ags/scope/score` | Send a grade to a line item |
| `https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly` | Read line items |
| `https://purl.imsglobal.org/spec/lti-ags/scope/lineitem` | Create one extra column per activity, "KI-Bewertung: <activity title>" |

The tool uses `lineitem` only to find or create its own "KI-Bewertung" column.
It never changes or deletes the activity's own column, and it never deletes a
line item. Dynamic Registration asks Moodle for all three scopes and ILIAS for
`score` and `lineitem.readonly` only. When the LMS does not grant `lineitem`,
the tool sends the final grade only, and the activity overview and the admin
panel say why.

The tool does not request `result.readonly` and does not use NRPS. It never
reads course rosters.

Token exchange uses the `client_credentials` grant with `private_key_jwt`
client authentication, signed RS256. Access tokens are cached for their stated
lifetime and refreshed five minutes before they expire.

## 6. Registering your LMS

Organization admins set up connections themselves. Group admins can do the
same for their groups. The panel is under **Users & organizations**, select the
organization, then **More** and **Learning platform (LTI)**. In the German
interface this is *Benutzer & Organisationen → Organisation → Mehr →
Lernplattform (LTI)*.

**API keys first.** AI grading of linked exams runs only on your
organization's keys. In the **API keys** dialog, switch on **Organization
provides API keys** and add a key for the provider of the grading model. The
default grading models are OpenAI models. The top of the panel shows whether
AI grading is ready. Group admins can add a key for their group, but only an
org admin can switch on that option. See [§8.5](#85-where-the-data-lives-and-who-pays).

**Tool address.** Every connection has an address that its tool URLs use. A
deployment can offer two addresses.

| Address | Who works where |
|---|---|
| Student host | Everyone works in the student interface, teachers included. Only the Korrektur opens in the expert interface. |
| BenGER host | Students work in the student interface, teachers in the expert interface |

The invite link, Dynamic Registration and the tool sheet all use the chosen
address. Where both are offered, the student host is the default, and
connections created before the choice existed use it. If you change the
address later, update the tool URLs in the LMS as well. Until then, launches
through the old address still work, and the panel's history shows a warning.

**One assistant per LMS.** **Connect learning platform** in the panel first
asks which LMS you use and then shows only the steps for it:

| Choice | Way | See |
|---|---|---|
| Moodle | one-time invite link | [§6a](#6a-one-link-registration-dynamic-registration) |
| ILIAS | global provider, entered by hand (3 steps) | [§6b](#6b-manual-registration) |
| ILIAS, one course only | invite link (*Only testing one course?*) | [§6a](#6a-one-link-registration-dynamic-registration) |
| Other | the full form with all fields | [§6b](#6b-manual-registration) |

An invite link alone connects nothing. Until the LMS redeems it, the panel
shows it as a card **Waiting for the learning platform**, with its expiry
date and **Revoke**. Only then does the connection card appear.

**Active at once.** Both ways below create a connection that works
immediately. It can be switched off in the panel at any time. Because of
this, the contract with us must be in place before your organization admin
creates the invite (see [§8.8](#88-compliance-tell-us-what-you-need)).

### 6a. One-link registration (Dynamic Registration)

1. In the panel, click **Connect learning platform** and choose **Moodle**
   (for a single ILIAS course: **ILIAS**, then *Only testing one course?
   Create invitation link*). Choose the address and, if you like, a group.
   Then click **Create invitation link**. The link is shown once. It works
   once, is stored only as a SHA-256 hash and is valid for 14 days. Until
   the LMS redeems it, it stays as a **Waiting for the learning platform**
   card in the panel, where you can revoke it.
2. Send the link to the LMS administration.
3. **Moodle**: Site administration → Plugins → Activity modules → External
   tool → Manage tools (German Moodle: *Website-Administration → Plugins →
   Aktivitäten → Externes Tool → Tools verwalten*). Paste the link into
   **Add LTI Advantage**.
   - If a tool with the same domain exists already, Moodle asks whether to
     update it. Choose **Register as a new external tool** (*Als neues
     externes Tool registrieren*). Choose **Update** only if you replace an
     earlier connection on purpose.
   - Moodle shows the tool's result page inside its own page and closes it
     when the registration is done.
   - Moodle and the tool exchange issuer, endpoints, client ID and deployment
     ID. The tool appears as *Pending* (*Wartend*). Click **Activate**
     (*aktivieren*).
4. **Moodle, tool settings.** Open the tool's settings with the edit icon on
   its card and change three values. Moodle 4.5 gives every tool registered
   by link the same values, and the tool cannot change them.

   | Setting (German Moodle) | Value after the registration | Set it to |
   |---|---|---|
   | Tool configuration usage (*Verwendung der Toolkonfiguration*) | Show as preconfigured tool when adding an external tool | **Show in activity chooser and as a preconfigured tool** (*In Aktivitätsauswahl und als vorkonfiguriertes Tool anzeigen*) |
   | Default launch container (*Standard-Startcontainer*) | Embed, without blocks (*Eingebettet ohne Blöcke*) | **New window** (*Neues Fenster*) |
   | Accept grades from the tool (*Bewertungen aus dem Tool akzeptieren*) | As specified in Deep Linking definition or Delegate to teacher | **Always** (*Immer*) |

   Without these changes, teachers do not find the tool in the activity
   chooser, the tool opens embedded, which does not work (see
   [§9](#9-requirements-on-your-lms)), and an activity has no grade unless
   the teacher allows grades in the activity settings.
5. **ILIAS** (10.9 and later): create an LTI consumer object, open
   *Eigene Tool-Einstellungen mit dynamischer Registrierung anlegen (LTI
   1.3)* (English ILIAS: *Create Own Settings for Tool with Dynamic
   Registration (LTI 1.3)*), paste the link and add it. ILIAS fills in all
   tool URLs, including the JWKS key type. Then open the provider settings
   and change these by hand:
   - tick *Erweiterte Benotungsdienste* (*Advanced Grading Services*), or no
     grade is sent;
   - set the identification and the name as described in
     [§3](#ilias-limitations-to-plan-around);
   - tick *Provider unterstützt Outcome Service* and set the Mastery Score
     to 22.

   ILIAS creates a provider bound to that one object, so for a campus-wide
   rollout the manual way in
   [Appendix A](#appendix-a-ilias-setup-sheet-german) is better.
6. The connection now appears in the panel and is active.

Further rules:

- Dynamic Registration asks the LMS to send name and email for every user.
  Check the tool's privacy settings in Moodle after the registration. ILIAS
  does not apply this request: set its identification and name by hand (see
  the end of this section).
- The LMS lists the tool under the product name of the chosen address, with
  a short description. On a deployment whose address contains `staging.`,
  the name ends with "(Staging)", so a shared test LMS can tell the tools
  apart.
- An invite works only while its creator may still manage its organization or
  group. An invite for a group that was switched off fails.
- A group admin's invite always creates a connection for that group.
- LMS teachers of the new connection get the contributor role in the
  organization if the invite's creator may grant it. Otherwise they get no
  organization role.
- The registration endpoint validates the IMS origin rules and blocks calls
  into internal networks.
- If the registration fails, the LMS shows a German error page with the
  reason. An unexpected failure also shows a reference that matches the
  server log. Send it to the platform operator.

### 6b. Manual registration

The LMS issues the client ID only after the tool, including its URLs, is
saved there. So the order is:

**ILIAS** (the assistant's three steps):

1. In the panel, click **Connect learning platform** and choose **ILIAS**.
   Choose the address and, if you like, a group. Step 1 shows the three tool
   URLs (login, launch and JWKS).
2. Send these URLs, or the setup sheet in
   [Appendix A](#appendix-a-ilias-setup-sheet-german), to the ILIAS
   administration. It creates a global provider (English ILIAS: *Extending
   ILIAS → LTI → ILIAS as LTI Consumer → Add Global Provider for all Users*;
   set *Availability* to *For Creating Objects* and *LTI Version* to 1.3,
   both are preset differently) and reports the client ID
   and the deployment ID, which is the numeric **Provider ID**. ILIAS shows
   both in the saved provider, in the box *Hinweise* (*Hints*).
3. Step 2: enter the ILIAS address, the client ID and the deployment ID and
   click **Connect**. The tool fills in the endpoints from the address and
   uses the default settings below. Change them later under **Edit**.
4. Step 3 confirms the connection. Teachers can now add LTI consumer objects
   with this provider to their courses.

**Other LMSs** (choice **Other**): the form shows the three tool URLs before
anything is saved. Once the LMS reports client ID and deployment ID, enter
the issuer, the endpoints, the client ID and the deployment ID and save.

Later, **Tool configuration** on the connection shows the same URLs.

| Field | Moodle | ILIAS |
|---|---|---|
| Issuer | `https://moodle.uni-x.de` (`$CFG->wwwroot`, no trailing slash) | `https://ilias.uni-x.de` (base URL, no trailing slash) |
| Authorization endpoint | `{issuer}/mod/lti/auth.php` | `{issuer}/ltiauth.php` |
| Token endpoint | `{issuer}/mod/lti/token.php` | `{issuer}/ltitoken.php` |
| Platform JWKS | `{issuer}/mod/lti/certs.php` | `{issuer}/lticerts.php` |
| Client ID, deployment ID | shown in the tool details after saving | the client ID and the numeric **Provider ID**, which is the deployment ID |

ILIAS also publishes `{issuer}/lticonfig.php`, which helps to check these
values. Deployment IDs can be added later under **Deployments**.

### Connection settings

| Setting | Default | Effect |
|---|---|---|
| Address (`tool_host`) | student host where offered | See above. |
| Group (`group_id`) | none | People who launch join this group, and linked exams are visible to the group only. Group admins create group connections only. Changing the group later moves the linked exams' visibility and key pool along. A launch does not add someone back whom an admin removed from the group, and does not make a teacher group admin again after an admin took that right away. |
| Org role for teachers (`instructor_org_role`) | `contributor` | `contributor`, `org_admin` or `none`. On a group connection, `org_admin` becomes contributor plus group admin. A group admin can grant at most `contributor`, and only if they hold that role themselves. A launch never lowers an existing role, but a teacher launch raises an annotator to this role. |
| Org role for students (`student_org_role`) | `annotator` | `annotator` makes students members of the organization, so they also see its shared exams. `none` adds no membership in your organization. Students reach the linked exam through the launch. On the hosted service, every account a launch creates also joins the operator's shared student organization (see [§8.1](#81-accounts-and-names)). |
| Offer linking to existing accounts (`link_existing_users_by_email`) | on | If exactly one account has the address the LMS sends, the person may link it after signing in or confirming by email. When off, the launch always creates a separate account. ILIAS sends no address, so there is nothing to link. |
| Connection status | active | The switch on the connection's card reads **Connection on** (German *Anbindung aktiv*). Switched off, it reads **Connection off** (*Anbindung aus*), and the card shows the badge **Switched off** (*Ausgeschaltet*). A switched-off connection blocks every login, launch, LTI page in the app and grade transfer for this LMS. |
| Deployment status | active | The switch next to each deployment ID reads **Deployment on** (*Deployment aktiv*) or **Deployment off** (*Deployment aus*). A switched-off deployment rejects launches. The other deployments of the connection keep working. |

**ILIAS privacy settings.** Set them in the provider before go-live:

- *Identifikation der Person* (*User identification*): *ID des
  ILIAS-Kontos …* (*ILIAS user id …*).
- *Anmeldename* (*User name*): *Vollständiger Name* (*Entire name*).

Do not choose *E-Mail-Adresse*. In ILIAS 10.9 every grade transfer fails in
that mode (see [§3](#ilias-limitations-to-plan-around)). If an ILIAS
connection launches in that mode, the connection's card in the panel shows a
warning with the fix. Do not change the identification after go-live. It
decides the `sub` value, so a change detaches every account from its LMS
identity. Each person then consents again and gets a new account, and the
earlier submissions stay with the old one. The old account keeps its email
address, so that address counts as taken when the new account is asked for
one, until the old account is anonymized.

## 7. Course setup (teacher)

1. Add an External Tool (Moodle) or LTI consumer (ILIAS) activity to the
   course. In Moodle, pick the tool by its name in the activity chooser.
   **Make sure the activity carries a grade.** Without a grade there is no
   line item, and no grade can be returned. Moodle's default of 100 is fine.
   If the Moodle tool still delegates grades to the teacher, the grade
   settings stay hidden until you tick **Allow <tool name> to add grades in
   the gradebook** (German: *<Toolname> erlauben, Bewertungen
   hinzuzufügen*). Without the tick the activity has no grade.
2. The tool must open in a **new window** (see
   [§9](#9-requirements-on-your-lms)). In Moodle 4.5 teachers cannot choose
   this per activity. The activity uses the tool's default launch container,
   which the Moodle administration sets (see [§6a](#6a-one-link-registration-dynamic-registration)).
   In ILIAS, set the object's launch option to **New window**.
3. Open the activity. On the first launch the teacher consents, as students
   do. If an account with the same email address exists, the teacher can
   link it by signing in or by email, or continue with a separate account.
4. The picker carries the activity's title as its heading. It lists the
   teacher's own exams and the exams created by staff of the connection's
   organization. Staff means contributors and org admins. On a group
   connection it means the group's contributors, the group's admins and the
   org admins. Exams of any visibility can be linked. Archived and deleted
   exams are not listed. The teacher can also create a new exam from the
   picker: **Or create a new exam** below the list, or **Create new exam**
   when the list is empty.
5. Falllösung exams and Bewertungsbogen exams with an active sheet can be
   linked. The picker shows other exams with the reason: no task yet, more
   than one task, a grading that gives no Notenpunkte, or no active
   Bewertungsbogen. **Exams with more than one task cannot be linked yet.**
6. Click **Link**. Human Korrektur is switched on for the exam. The exam is
   attached to the connection's organization (or group), so its staff can
   open the exam and grade it.
7. After linking, and on every later launch, the teacher lands on the
   exam's page: the project page on the BenGER host, the exam page in the
   student interface on the student host. Its card **Learning platform
   activities** lists every linked activity with participants, submissions
   and transfer errors, and links its **activity overview**.
8. The activity overview lists every student who consented, with real name,
   submission time, AI grade, human grade, what each LMS column received,
   and the transfer status and error. From there the teacher opens the
   Korrektur or the exam. A transfer with an error (failed, or waiting after
   a failed attempt) can be sent again with **Send again**. **Open grading**
   always opens the Korrektur in the expert interface, also on the student
   host.
9. **Moodle: keep the AI grade out of the course total.** Moodle adds the
   "KI-Bewertung" column as a normal manual grade item. Its name is
   "KI-Bewertung: <activity title>", so the columns of several linked
   activities in one course can be told apart. Columns created by earlier
   versions keep the plain name "KI-Bewertung". Unless the teacher
   changes it, the AI grade counts in the course total next to the final
   grade in the activity column. The column appears with the first AI grade.
   Then open the course's **Grades** and choose **Gradebook setup** (German
   Moodle: *Bewertungen → Setup für Bewertungen*). In the row of the
   "KI-Bewertung" column, tick the box in the **Weights** column
   (*Gewichtungen*), enter 0 and click **Save changes** (*Änderungen
   speichern*). This applies to Moodle's default aggregation, *Natural*
   (German: *Summe*). With another aggregation that uses weights, set the
   weight of this column to 0 as well. Repeat it if the column is created
   again.

The activity can point to another exam until the first grade reached the LMS.
After that, create a new activity. A linked exam does not accept a second
task.

The activity overview is open to the course teachers, the organization's
admins, group admins of a group connection, and the staff who may grade the
linked exam. Linking and relinking is for the course teachers and the admins.
The exam's project page lists its LMS activities in the sidebar, below the
quick actions.

## 8. Identity, data protection and what is stored

### 8.1 Accounts and names

- **Name and email.** After consent, a new account gets the name and email
  address from the LMS and a pseudonym. Dynamic Registration asks Moodle to
  send both. An account from ILIAS gets the full name only. In the
  identification mode that ILIAS needs (see
  [§3](#ilias-limitations-to-plan-around)), ILIAS sends no real address.
- **Unconfirmed address.** The address counts as unconfirmed until the person
  activates the account or resets the password.
- **Placeholders.** If the LMS withholds the address, or another account
  already uses it, the account gets a placeholder address. A later launch
  with a free address fills it in. A withheld name is filled in the same way.
  An account with a placeholder address gets no automatic activation mail,
  and no later launch can offer it for linking.
- **Asked once for an address.** A new or re-consenting account without a
  password and without an address that can receive mail is asked right
  after consent for an email address, before the page moves on. This covers
  every ILIAS account and Moodle accounts whose address is withheld.
  Students and teachers see it alike. The person can skip the step. An
  entered address is kept aside and adopted only when the person opens the
  confirmation link sent to it. That link is the activation mail: it
  confirms the address and sets the first password. An address that another
  account already uses is refused with a clear message. The step appears
  only on the consent page, so it comes once per connection, and again only
  when the consent version changes or after an unlink. Later the person can
  add an address in the app (*Zugang ohne Lernplattform einrichten*, in the
  student navigation and in the profile).
- **Pseudonym.** The app shows the pseudonym. Real names are visible to
  superadmins, to the admins of the connection's organization, to group
  admins for their group's connections, to the course teachers and to the
  staff who may grade the linked exam in that organization. Course teachers
  are the teachers of any course on the connection that links the exam.
  Grading staff are the organization's contributors and admins in the
  connection's scope, so by default also the connection's LMS teachers
  (see the teacher role in [§6](#6-registering-your-lms)). In an
  organization whose connections only superadmins run, its contributors see
  the names that its admins see. Everyone else, other students included,
  sees the pseudonym. A person who switches off the pseudonym in their
  profile is shown by name. An account the LMS created stays pseudonymous
  after an unlink and after its connection is deleted.
- **Linking an existing account.** An LMS identity is linked to an existing
  account only after proof. The person either signs in with that account's
  password or opens a confirmation link sent to that account's address. The
  link is valid for 24 hours, works once and also works on another device.
  If an LMS created that account and it has no password yet, neither is
  possible. The person is then offered the activation mail for that account
  instead. They set a password with it, open the activity again and sign in.
  Linking is offered only when exactly one account has the address and the
  connection offers linking. Accounts of platform administrators are never
  linked. A separate new account is always possible. Accounts are never
  merged.
- **Activation mail.** New accounts with a deliverable address get an
  activation mail after consent. Accounts without one get it for the
  address they enter. It is in German, and its link is valid for 7 days.
  With it the person sets a password and can also sign in without the LMS.
- **Operator membership.** On the hosted service, every account a launch
  creates, for students and teachers alike, also joins the operator's shared
  student organization as a plain member, whatever the connection's roles.
  This has a technical reason: the membership decides how the platform
  classifies and bills the account's gradings outside linked exams. The
  account sees that organization's shared exams, and that organization's
  admins and contributors see only its pseudonym. Existing accounts linked
  by proof do not join.
- **Removed memberships.** A launch never reactivates an organization
  membership that an admin removed, and never re-adds someone an admin
  removed from the connection's group. The person sees `membership_removed`.
  A launch also leaves a group admin right alone once an admin took it away.
  - To restore an organization membership, an org admin invites the person
    again with **Invite Member**, using the email address of their account.
    Once the person accepts the invitation while signed in, the membership
    is active again. An account without a password needs one first
    (**Forgot your password?** on the login page).
  - This needs a deliverable address on the account. An account with a
    placeholder address can receive neither the invitation nor a password
    reset mail, and it cannot sign in without the LMS. A platform
    administrator restores its membership with **Add Existing User**. If the
    person set up access without the LMS before the removal, the account has
    a real address and the invitation works.
  - To restore a group membership, a group admin or org admin adds the
    person to the group again.
  - Roles work differently: a teacher launch raises an annotator back to
    the connection's teacher role. To keep someone out, remove their
    organization membership, or unlink or anonymize their LMS account. To
    limit teachers, change **Org role for teachers**.
  - Unlinking an account the LMS created keeps the record of its group
    membership. Unlinking an account linked by proof removes that record, so
    that person's next consent adds them to the group again.

ILIAS notes: the `sub` value comes from the provider's identification mode
(*Identifikation der Person*). ILIAS sends a withheld name as a literal `"-"`
and, in the user id mode, a pseudo address like
`<user id>@<installation id>.ilias`. The tool treats both as not sent. It
also ignores addresses on reserved top-level domains such as `.invalid` or
`.local`.

### 8.2 Claims consumed

From the `id_token`: `sub`, `iss`, `aud`, `exp`, `iat`, `nonce`, the LTI
`message_type`, `version`, `deployment_id`, `resource_link`, `context`,
`roles`, `name`, `email` and the AGS endpoint claim. `name` and `email` are
expected. ILIAS sends no usable `email` in the user id mode. The `custom` claim is not used.

Roles are mapped narrowly. The instructor, content developer and
administrator role markers make a person a teacher. Everyone else counts as a
student. On ILIAS 10, course admins and course tutors are teachers, and course
members are students.

### 8.3 What is persisted

**Before consent**, the tool stores only the activity record (course and
activity title, AGS URLs, no personal data). The checked launch (identity,
name, email, roles, course) waits in Redis for at most 30 minutes after the
last step. The browser holds only a random secret in an httponly cookie.
The OIDC login state lives in Redis for 5 minutes and is deleted on use. The
launch then keeps the nonce for 10 minutes as a replay marker.

**After consent**, these tables hold LTI data. All of them are in the open
repository.

| Table | Contents | Personal data |
|---|---|---|
| `lti_platform_registrations` | issuer, client ID, endpoint URLs, address, role policy, status | none |
| `lti_deployments` | deployment IDs and their status | none |
| `lti_registration_invites` | hash of the invite token, organization, group, address, expiry, creator | the creator's account ID |
| `lti_resource_links` | activity to exam, course and activity title, AGS URLs and scopes, state of the "KI-Bewertung" column | course titles only |
| `lti_user_links` | `sub` to account, consent time and version, research consent time, how the account was linked, unlink marker, last launch, a snapshot of name, email and roles | name, email and roles from the LMS |
| `lti_resource_link_users` | who took part in which activity, as teacher or student, first and last launch. Written only after consent. | account IDs |
| `lti_grade_syncs` | one row per activity, student and column (final grade or AI grade): status, attempts, last sent score and its source, last error | links an account to a score |
| `lti_admin_events` | history of connection changes: action, time, changed settings | the acting admin's account ID and affected account IDs, never names or emails |

The `users` table holds name, email, pseudonym and the email state. The
`organization_memberships` table holds the memberships a launch grants: in
the connection's organization and group, as the connection's roles say, and
on the hosted service in the operator's shared student organization (see
[§8.1](#81-accounts-and-names)). No raw `id_token` is kept. An email
confirmation token lives in Redis for 24 hours, stored under its hash
together with a copy of the waiting launch.

### 8.4 Consent

- Consent is asked once per connection and LMS identity, from students and
  teachers, before any account or membership exists.
- The consent page shows what the LMS sent. It has two required checkboxes:
  the processing (an account with name and email from the LMS, the pseudonym
  in the app, who sees the name, the grade transfer) and research use. The
  teacher version names the organization role instead of the grade transfer.
- Consent is asked again only when the consent version changes, or after an
  admin unlinked the identity.
- The time and version are stored with the LMS identity. The research consent
  time is also stored on the account.

**Research use is required.** This consent is required. Without it the tool
cannot be used from the LMS. Access that depends on consent raises the
question of Art. 7(4) GDPR. Whether this setup fits your course is for your
data protection officer to assess.

### 8.5 Where the data lives and who pays

- **Hosting is in Germany.** AI grading sends the solution text, without
  name or email, to the model provider of your organization's key. With the
  default grading models this is OpenAI. Whether that is a transfer to a
  third country depends on the provider's contract and where it processes
  data, so include the provider in your transfer assessment.
- **Grades go to your own LMS and nowhere else.**
- **The connection's organization pays for AI grading of a linked exam.**
  This covers the gradings of its LMS students and its own staff, including
  batch evaluation runs they start on the exam. A batch run a platform
  administrator starts is billed to the first connection's organization.
  Other people who start a batch run keep the normal billing rules. A
  group's key is used before the organization's key.
- **No key, no grading.** The organization must have **Organization provides
  API keys** switched on and a key for the provider of the grading model.
  Otherwise the grading does not run. Students see the reason: their
  organization does not pay for AI grading yet, or it has no API key for the
  grading model. Teachers and admins see what is missing. The submission
  stays saved. Once the key is in place, it is graded at the next hourly
  check, so within about an hour. There is never a fallback to another key,
  ours included.
- **Teacher AI helpers** on a linked exam, for example an AI proposal for a
  Bewertungsbogen, are billed the same way. They are refused without a key,
  and also when the billing check itself fails.
- **You choose the model provider.** The university decides which provider
  processes solution text and can name it in its own record of processing.
  Custom model endpoints, including self-hosted ones, are supported. If you
  want grading to stay inside your own infrastructure, raise it during
  onboarding.
- People who reach a linked exam without the LMS, for example through a
  share link, keep the normal billing rules.

### 8.6 Privacy by design and by default (Art. 25 GDPR)

| Property | Effect |
|---|---|
| Consent first | Nothing about the person is stored before consent. The checked launch waits on the server for at most 30 minutes. See [§8.4](#84-consent). |
| Names only where needed | The app shows a pseudonym. Real names are for admins, course teachers and grading staff. See [§8.1](#81-accounts-and-names). |
| Data minimisation on the wire | At most three AGS scopes (two on ILIAS), all about grades. No Names and Role Provisioning, so course rosters are never read. See [Scopes requested](#scopes-requested). |
| Minimal storage | Eight tables, [itemised](#83-what-is-persisted). No raw `id_token`. The login state expires after 5 minutes, the nonce marker after 10. |
| Linking only with proof | An existing account is linked only after sign-in or email confirmation. Platform administrator accounts are never linked. |
| Purpose limitation | Grades go to your LMS only. Nothing is shared with third parties to run the integration. |
| Tenant isolation | Every connection belongs to one organization, and optionally one group. Only its admins manage it. |
| Human in the loop | The human grade is the final grade. Nothing is deleted. See [§8.7](#87-automated-assessment). |
| Fail closed | Unknown or switched-off connections and deployments reject launches. Without the organization's key no AI grading runs, and there is no fallback. |
| Revocable | Organization admins anonymize LMS accounts. Full deletion on request. See [§8.9](#89-retention-anonymization-and-deletion). |

### 8.7 Automated assessment

- Until a teacher grades a submission, the AI grade is the value in the
  activity's LMS column.
- A human grade replaces it there. Moodle keeps the AI grade in the
  "KI-Bewertung" column. Nothing is deleted.
- Moodle treats "KI-Bewertung" as a normal grade item. It counts in the
  course total until the teacher sets its weight to 0 (see
  [§7](#7-course-setup-teacher)). Otherwise the AI grade weighs on the course
  total even after a human grade replaced it in the activity column.
- With several human grades, the most recently edited one is final.
- Human Korrektur is switched on for every linked exam. By default, graders
  do not see the AI grade until they have submitted their own. The activity
  overview shows both grades.

Whether a data protection impact assessment is needed, and how the AI grade
before human review fits a graded examination under Art. 22 GDPR, is for the
university as controller to decide. We supply the processing description as
input.

### 8.8 Compliance: tell us what you need

We act as processor, and the university acts as controller. **We will meet
the documentation and contractual requirements your data protection office
sets.** That includes signing your own data processing agreement, or
supplying ours as a draft.

We cannot guess which documents your DPO wants. It differs by institution and
by whether the use is a practice exercise or a graded examination. **Please
tell us specifically what you need.** The list below is a prompt, not a
limit.

- **Contract**: your AVV/DPA template, or ours as a starting point? Any
  framework agreement it has to sit under?
- **Technical and organisational measures**: a TOMs annex in your format, or
  free form? Any controls you must see evidenced?
- **Record of processing**: a ready-made entry for your VVT, or only the
  processing description as input?
- **DPIA**: are you running one? What do you need from us, and by when?
- **Research consent**: the consent to research use is required (see
  [§8.4](#84-consent)). Does your DPO accept that for your course?
- **Name and email**: every Moodle launch carries name and email, every
  ILIAS launch the name. Does your processing description cover that?
- **Subprocessors**: do you need a subprocessor list? Do you want to name the
  model provider yourself through your own API key?
- **Retention**: a fixed deletion period for accounts and grades, or deletion
  on request?
- **Hosting evidence**: should the hosting location be documented in the
  contract?
- **Security review**: a source review of the protocol half under NDA, a
  security questionnaire, or both?

Two practical notes. First, name a contact for the legal side and one for the
LMS administration early. The AVV is usually signed by the legal office or the
faculty's data protection coordination, not by the individual teacher.
Second, **connections are live at once**, and your organization admin creates
the invite. Sign the contract before the invite is created. Making sure of
this is the university's task.

Send your requirements to the address in [§12](#12-support-and-contact).

### 8.9 Retention, anonymization and deletion

**Anonymization.** Org admins, and group admins for their group's
connections, anonymize the accounts that an LMS launch created. In the panel
this is **LMS accounts**, then **Anonymize**. A preview shows what will be
removed and kept. It cannot be undone.

- **Removed**: name, email address, password, parked address, reset and
  verification tokens, research profile answers, personal API keys, the LMS
  identity links with their name and email snapshot and consent fields, the
  account's grade transfer rows, all stored sign-in sessions (open and
  ended ones), group memberships, and notifications that name the person.
  The preview names how many LMS links, grade transfers and sessions go and
  how many memberships end.
- **Changed**: the account is locked, its organization memberships are
  deactivated, and a new pseudonym replaces the old one.
- **Kept as anonymous records**: submissions, grades, created exams, the
  activity participation rows (IDs and times only) and the research consent
  time.
- **Refused** for platform administrator accounts, for your own account, for
  accounts that existed before the link (those can only be unlinked), for
  accounts with LMS links or active memberships outside your scope, and for
  accounts with payment records or a running subscription. Group admins
  cannot anonymize org admins.
- A later launch by the same person creates a new, empty account.

**Unlinking** detaches the LMS identity from the account. The account, its
submissions and grades stay. Its grade transfer rows, including their
history, and its activity participation on this connection are removed, so
the person shows up in the activity overview again only after the next
launch. The next launch asks for consent again. It offers the account for
linking only if the connection offers linking and the account still has the
address the LMS sends. Otherwise, for example with a placeholder address,
the launch creates a new, separate account. The earlier submissions and
grades stay with the old account and no longer go to the LMS. An account the
LMS created stays recognizable and pseudonymous, so it can still be
anonymized later.

**Deleting a connection.** Switch the connection off first. Then choose
whether the accounts it created are kept or anonymized. Deleting removes the
connection's deployments, activities, LMS identity links, participation rows
and all grade transfer rows. Kept accounts, and accounts that could not be
anonymized, stay pseudonymous. Their names are then visible only to the
admins of the connection's organization and to platform administrators. Org
admins can no longer anonymize them through the connection; the platform
operator does that on request. Exams that no other connection of the organization
links lose the attachment that linking created. LMS access to those exams
ends, unless another connection still grants it. Submissions and grades
stay. The organization's history (`GET /api/admin/lti/events`) keeps the
deletion, the accounts anonymized with it and the invites; group admins see
the entries of their groups.

**Grades already in the LMS** stay there. Deleting them is up to you.

**Full deletion** of an account is available on request to us. If you want a
fixed retention period instead, name it and we record it in the contract.

## 9. Requirements on your LMS

- **Reachability.** Your LMS must reach the tool's JWKS URL on **port 443**.
  Moodle's outbound curl security blocks other ports by default, and a keyset
  on another port fails the token exchange with a null-JWKS error. Behind an
  egress proxy, `curlsecurityblockedhosts` may need a review.
- **JWKS by URL, never a pasted key.** On ILIAS in particular, set *Typ des
  öffentlichen Schlüssels* (*Public Key Type*) to *URL (Json Web Token)* and
  enter the keyset URL. ILIAS checks our client assertion only through the
  keyset URL. A pasted RSA key passes the launch and then breaks the grade
  transfer.
- **New window.** Embedded iframe launches are not supported. The session
  cookies need a top-level window. Inside an iframe, people land on the login
  page or see *Sign-in does not match* (`launch_mismatch`). Moodle: set the
  tool's *Default launch container* to **New window**. Moodle 4.5 sets
  *Embed, without blocks* for every tool registered by link, and teachers
  cannot change it per activity.
- **Tool visible to teachers.** Moodle: set *Tool configuration usage* to
  **Show in activity chooser and as a preconfigured tool**. A tool
  registered by link is only a preconfigured tool at first.
- **Grades accepted.** Moodle: set *Accept grades from the tool* to
  **Always**. A tool registered by link delegates this to the teacher, and
  an activity then has no grade unless the teacher allows it.
- **Name and email.** Moodle: share the launcher's name and email with the
  tool **Always**, for every role (German Moodle: *Anwendername an Tool
  übergeben* and *E-Mail des Anwenders an Tool übergeben* → *Immer*).
  Dynamic Registration requests this. Check the setting after the
  registration. ILIAS: identify people by the ILIAS user id, never by
  *E-Mail-Adresse*, and send the full name (see
  [§3](#ilias-limitations-to-plan-around)). ILIAS then sends the name
  only, and each person is asked once for an address after consent.
- **Grade sync with column management.** Moodle: set the tool's *IMS LTI
  Assignment and Grade Services* to **Use this service for grade sync and
  column management** (German Moodle: *IMS LTI Aufgaben und Bewertung* →
  **Service für die Synchronisation von Bewertungen und die Verwaltung der
  Spalten nutzen**). Dynamic Registration requests it. With *Use this
  service for grade sync only* (*Service nur für Bewertungen nutzen*),
  Moodle gets the final grade only. ILIAS: tick *Erweiterte
  Benotungsdienste* (*Advanced Grading Services*) in the provider.
- **ILIAS learning progress.** Tick *Provider unterstützt Outcome Service*
  and set the Mastery Score to 22, and switch on learning progress for the
  installation (see [§3](#ilias-limitations-to-plan-around)).
- **Clock sync.** Moodle `id_token`s live 60 seconds, and ILIAS checks our
  client assertions with zero leeway. Keep NTP tight on both sides. AGS also
  needs strictly increasing score timestamps, so clock skew between our
  workers shows up as a `409` on the score POST.
- **Exact redirect URI.** The redirect URI must match the registered entry
  character for character.

## 10. Conformance

- The tool was tested against the **saLTIre** LTI conformance emulator
  (`saltire.lti.app`): launch acceptance, account and activity creation, and
  negative cases. `alg:none` tokens, broken tokens and missing parameters all
  lead to a clean error page and no server error.
- End-to-end validation was done on Moodle 4.5.12 and ILIAS 10.9, each through
  the full loop: launch, consent, account, submission, correction, grade
  transfer, grade visible in the LMS.
- **BenGER is not 1EdTech certified.** If certification is a procurement
  requirement, raise it early.

**Replay protection.** A replayed launch POST gets `invalid_state`, because
the state is used up on the first launch. A replayed `id_token` sent with a
fresh login gets `nonce_mismatch`, because every login creates a new nonce.
As a second guard, the launch marks each nonce as used for 10 minutes (an
atomic set-if-absent) and rejects a second use with `nonce_reused`.

## 11. Operating the tool (self-hosted deployments)

This section matters only if you run BenGER yourself. The LTI routes need the
commercial edition ([§1](#1-edition-boundary-read-this-first)).

**Signing key.** The tool signs client assertions with an RSA key (RS256).
Generate a 4096-bit key and supply it through `LTI_TOOL_PRIVATE_KEY` (PEM) or
`LTI_TOOL_PRIVATE_KEY_FILE`, named by `LTI_TOOL_KID`. Without a configured key
the process creates a temporary key in memory and logs a warning. That is
fine for tests and useless in production, because the published JWKS changes
on every restart. A key that cannot be loaded at all gives
`tool_not_configured`.

**Rotation.** Install the new key as the active pair and move the old one to
`LTI_TOOL_PRIVATE_KEY_PREVIOUS` and `LTI_TOOL_KID_PREVIOUS`, then restart. The
JWKS serves both keys during the window, and LMSs fetch it again on an
unknown `kid`. Drop the previous pair after about an hour. Every JWK carries
`kid` and `alg`, which Moodle requires.

**Tool addresses.** The BenGER host is `FRONTEND_URL`. A second,
student-only host is optional and comes with the commercial edition. Without
it, the panel offers the BenGER host only.

Connections created before the address choice use the student host. On a
deployment without one, their tool sheet and their older unused invites
answer `tool_host_unavailable`, and teachers land in the student interface
(launches still work). Move such a connection to the BenGER host under
**Edit** in the panel, which then offers the BenGER address, or with
`PUT /api/admin/lti/registrations/{id}` and the body
`{"tool_host": "main"}` (organization admins may call it for their own
connections). Then create new invites. Check that the tool URLs in the LMS
use the BenGER host.

**Organization API key.** AI grading of a linked exam is billed to the
connection's organization. The organization must provide keys
(`require_private_keys: false`) and hold a key for the provider of the grading
model. Otherwise the grading is refused with a reason, and no other key is
used. See [API key resolution](./features/api-key-resolution.md).

**Redis is required.** OIDC state and nonce, waiting launches, email
confirmation tokens and the limits on sign-in attempts and mails live in
Redis. Without Redis the tool fails closed with `state_unavailable`.

**Grade transfer is an outbox.**

- A transfer is queued as soon as an AI grade or a human grade is saved.
- There is one row per activity, student and column.
- Transfers for one student in one course run one at a time. Moodle keeps
  one course total per student, and two first grades sent at the same moment
  can fail. A transfer that finds another one running waits a few seconds
  and tries again. This does not count as an attempt.
- A transfer that fails because the LMS is unreachable, times out or
  answers with a server error (5xx, or 408, 409, 425, 429) is sent again
  after 10, 30 and 90 seconds.
- A score that the LMS refuses for good (400, 401, 403, 404 or another 4xx
  status that is not listed above) makes the row `failed` at once. The
  activity overview and the admin panel show it right away. Sending the same
  score again does not help until someone changes the setup. On ILIAS, a
  `404` is stored with a hint to check the identification mode.
- After the quick retries, and after other failures such as a refused token
  request, the row becomes due again after a wait. The wait is 60 seconds
  after the first attempt and doubles with each attempt, up to 6 hours.
  After 10 attempts the row is `failed`.
- The stored error is short plain text: the status code and a short reason.
  An HTML error page from the LMS is cut off. An error that was only such a
  page shows as "Die Lernplattform hat mit einer Fehlerseite geantwortet"
  with its HTTP status, so it still counts as an error.
- An hourly sweep (minute 45) sends the rows that are due, so a retry after
  a wait goes out at the first sweep after that wait. It retries `failed`
  rows every 6 hours without limit. It also sends grades that changed in place
  (Notenschlüssel recomputes, revised human grades) and creates missing rows.
  In addition, it compares sent grades with the grade the exam picks now,
  and sends the ones that differ. This covers a pick that changed without a new
  grading, for example a Bewertungsbogen judge added after the transfer. It
  compares at most 1000 transfers per run, a different share every hour.
  The activity overview data flags such transfers (`differs`).
- A row with nothing to send (no grade yet, grading not possible) becomes
  `idle` instead of `failed`.
- The same score, comment and column are never sent twice, except on a
  manual retry or **Send all grades again**.
- A manual retry resets the row and queues the transfer at once. It always
  sends, also when score and comment did not change. It is
  available as **Retry** in the admin panel (for failed and pending
  transfers), as **Send again** in the activity overview (for transfers
  with an error) and as `POST /api/admin/lti/grade-syncs/{id}/retry`. If the
  queue cannot be reached, the next hourly sweep sends it.
- **Send all grades again** sends every current grade once more, also
  unchanged ones: per activity in the activity overview, and per connection
  in the **Grade transfers** section of the admin panel
  (`POST /api/admin/lti/registrations/{id}/grade-syncs/resend-all`, same
  scope rules as the retry, recorded in the history with counts). Both ask
  for a confirmation first. Use it after an LMS outage, after changing the
  column settings in the LMS and after a Notenschlüssel change. It covers
  every learner with consent and a grade, in the activity column and, where
  it is in use, the KI-Bewertung column. Learners without a grade or
  consent and anonymized accounts are skipped and counted. The request only
  checks and counts; a background task marks the transfers and sends them
  in small batches (two every two seconds, at most one hour in total), so
  a big course does not flood the LMS. A marked transfer stays due, so the
  hourly sweep sends it if its push gets lost. If the queue cannot be
  reached, the transfers are marked right away and the sweep sends them.
  A switched-off connection, deployment or organization is refused with
  `409`. Two clicks before the first round has run send each grade once; a
  click after that round sends the grades again. In the community edition
  the endpoint answers `501`.
- **Values changed by hand in the LMS.** Moodle does not change a grade
  that was overridden or locked in its gradebook; a new score only updates
  the raw value behind it. The KI-Bewertung column is a manual grade item
  in Moodle, so a value typed into it is replaced by the next transfer.
  ILIAS stores the last value sent.
- A switched-off connection fails its transfers at once, and the activity
  overview only answers with a notice (`409`) while it is off. After switching
  it on, use **Send again**, **Retry** or **Send all grades again**. Otherwise
  the sweep sends the failed rows again about six hours after the failure.

**Switching off.** A switched-off connection blocks everything for that LMS.
A switched-off deployment blocks launches through that deployment. Unknown
deployments are rejected.

**Framing of the registration page.** Moodle shows
`/api/lti/register/init` inside an iframe of its admin page. A reverse proxy
in front of the tool must not add `X-Frame-Options` on this path. The tool
answers it with `Content-Security-Policy: frame-ancestors` set to the origin
of the LMS that started the registration. Every other path keeps
`X-Frame-Options: DENY`.

### Validation checklist before onboarding a university

1. `GET https://<tool-host>/api/lti/jwks` returns 200, and every key carries
   `kid` and `alg`.
2. An org admin creates an invite, the LMS registers, and the connection is
   active. The result page shows inside the LMS. The tool URLs in the LMS
   use the chosen address. On Moodle, the three tool settings from
   [§6a](#6a-one-link-registration-dynamic-registration) are changed.
3. A teacher launch shows the consent page once. The picker lists own and
   colleagues' exams, and a Bewertungsbogen exam can be linked.
4. A student launch in a clean browser shows the consent page, and no
   account exists before consent. After consent the account has a pseudonym.
   On Moodle the activation mail arrives. On ILIAS the account carries the
   full name, and the page asks once for an address. A link sent to it
   arrives and activates the account. Skipping opens the exam as well. A
   relaunch goes straight to the exam.
5. After a submission, the final grade lands in the activity column with the
   right rescaling. On Moodle with column management, the AI grade lands in
   "KI-Bewertung: <activity title>". On ILIAS the grade shows as learning
   progress, and a passed exam counts as completed.
6. A human grade changes the activity column and leaves "KI-Bewertung"
   unchanged. After the teacher set the weight of "KI-Bewertung" to 0, the
   Moodle course total counts the activity column only.
7. A Notenschlüssel recompute reaches the LMS within about an hour.
8. In an organization without a key, the grading does not run, and the
   student, teacher and admin see a message.
9. A short LMS outage makes the outbox back off and then recover.
10. A replayed launch POST gets `invalid_state`.

### Launch error codes

The error page shows a code, and a reference for unexpected server errors.
The in-app guide "Launch from Moodle or ILIAS fails" explains each code in
more detail. The consent page and the account choice show `launch_expired`
and `launch_mismatch` themselves, without the code, as *Sign-in expired* and
*Sign-in does not match*. The email confirmation page shows
`link_proof_failed` as *Confirmation failed*. JSON calls of these pages that
fail unexpectedly carry the reference in their message.

| Code | Meaning | Who acts |
|---|---|---|
| `invalid_request` | The LMS sent an incomplete launch request. | Reopen the activity. If it repeats, the LMS admin checks the tool settings. |
| `registration_not_found` | No connection matches the LMS (issuer or client ID differ, the connection was deleted, or two active connections cannot be told apart). | Org admin checks the connection, LMS admin the tool settings. |
| `registration_disabled` | The organization switched the connection off. | Org admin switches it on. |
| `org_inactive` | The organization that owns the connection is deactivated. | Platform operator. |
| `unknown_deployment` | The deployment ID is not registered in the connection. On ILIAS it is the Provider ID. | LMS admin gives the ID, org admin adds it. |
| `deployment_disabled` | The deployment ID is registered but switched off. | Org admin switches it on. |
| `tool_not_configured` | The tool's signing key cannot be loaded. | Platform operator. |
| `state_unavailable` | A temporary server problem. The sign-in could not be stored or read. It is not a browser or cookie problem. | Try again in a few minutes. |
| `invalid_state` | The sign-in was older than 5 minutes or already used (back button, reload, double submit). | Reopen the activity. |
| `invalid_token` | The LMS sign-in could not be verified (JWKS URL, client ID, new LMS keys, clock). | Reopen. If it repeats, LMS admin and org admin check the settings. |
| `nonce_mismatch` | The LMS answer does not match the started sign-in. | Reopen the activity. |
| `nonce_reused` | The same sign-in arrived twice. | Reopen the activity. |
| `unsupported_message` | The LMS sent a request type the tool does not support, for example Deep Linking. | LMS admin switches Deep Linking off. |
| `not_linked` | The activity is not linked to an exam yet. | Teacher opens the activity and picks an exam. |
| `exam_unavailable` | The linked exam was deleted. | Teacher links another exam, or creates a new activity if grades were sent. |
| `user_inactive` | The account is deactivated. An anonymized account never comes back: anonymizing removes its LMS link, so a later launch creates a new account. | Platform operator. |
| `membership_removed` | An admin removed the person from the connection's organization or group. A launch does not restore it. | Org admin invites the person again; accepting the invitation restores the membership. For an account with a placeholder address a platform administrator uses **Add Existing User**. A group membership is restored by adding the person to the group. |
| `launch_expired` | The consent page or account choice was open longer than 30 minutes, or the launch finished in another tab. | Reopen the activity. |
| `launch_mismatch` | The page belongs to another launch, or the browser lacks this launch's cookie (another browser, embedded launch). | Reopen and finish in one browser, in a new window. |
| `link_proof_failed` | The email confirmation link is invalid, older than 24 hours or already used. | Reopen and request a new link. |
| `account_not_linkable` | This account may not be linked, for example a platform administrator account. | The org admin removes the existing link under **LMS accounts** with **Unlink**. Then reopen the activity. The page *Separate account* offers only **Continue**, which creates a separate account. |
| `internal` | An unexpected server error. The page shows a reference. | Try again later. If it repeats, send code and reference to the platform operator. |

### Troubleshooting

| Symptom | Cause |
|---|---|
| Moodle gets only the final grade, no "KI-Bewertung" column | The tool's AGS setting is *Use this service for grade sync only*. Set it to **Use this service for grade sync and column management** (see [§9](#9-requirements-on-your-lms)), then open the activity again. A teacher who deleted the column can create it again in the activity overview. ILIAS never gets this column. |
| Grading does not run, students see that their organization does not pay for AI grading yet or has no API key for the grading model | The organization does not provide keys, or has no key for the grading model's provider. Switch on **Organization provides API keys** and add the key. Waiting submissions are graded at the next hourly check, so within about an hour. |
| The Moodle course total also counts the AI grade | Moodle treats "KI-Bewertung" as a normal grade item. The teacher sets its weight to 0 in **Gradebook setup** (see [§7](#7-course-setup-teacher)). |
| An existing account was not offered for linking | The connection does not offer linking, the LMS sent no address, several accounts share the address, or the account is a platform administrator account or deactivated. If the person chose a separate account, an org admin can unlink it. The next launch then offers the choice again, as long as the existing account still has the address the LMS sends. |
| A teacher's picker is empty | The teacher and the organization's staff have no exams yet, or all of them are archived. Create an exam from the picker. |
| Teachers do not find the tool in the Moodle activity chooser | The tool's *Tool configuration usage* is still *Show as preconfigured tool*. Set it to **Show in activity chooser and as a preconfigured tool** (see [§6a](#6a-one-link-registration-dynamic-registration)). |
| A Moodle activity has no grade settings | The tool's *Accept grades from the tool* delegates to the teacher, and the teacher did not tick *Allow ... to add grades in the gradebook*. Set the tool to **Always**, or tick the box in the activity. |
| The Moodle registration window stays empty or shows a browser error | A proxy in front of the tool sends `X-Frame-Options` on `/api/lti/register/init` (see [§11](#11-operating-the-tool-self-hosted-deployments)). The connection may exist anyway. Check the panel before you try again. |
| Moodle `invalidrequest` at `auth.php` | The redirect URI is not registered character for character, or the `lti_message_hint` was changed. |
| Token call fails with `"kid" invalid` | The LMS cannot match our JWKS: wrong or unreachable keyset URL, a rotated key without the previous pair, or API and workers signing with different keys. |
| Token call fails with a null-JWKS error | The LMS's outbound curl security blocks the keyset URL. Serve it on port 443. |
| ILIAS token endpoint returns `ERROR_OPEN_SSL_CONF` | A misleading catch-all for any error, including an unknown `kid` or a failed JWKS fetch. The real error is only in the ILIAS log. Check that the ILIAS server reaches the JWKS URL and that the right `kid` is used. |
| A grade never appears | The activity has no grade, so there is no line item. Or the exam cannot give Notenpunkte. Or, on ILIAS, *Erweiterte Benotungsdienste* (*Advanced Grading Services*) is off. The activity overview shows the transfer status and error. |
| ILIAS refuses every grade with `404 User not available` | The provider identifies people by *E-Mail-Adresse*. ILIAS 10.9 cannot find the person in that mode. Choose *ID des ILIAS-Kontos …* (see [§3](#ilias-limitations-to-plan-around)). The identifier of every person changes with it: each person consents again and gets a new account, and earlier submissions stay with the old one. The panel shows a warning while a connection launches in that mode. |
| `409` on the score POST | AGS needs increasing timestamps. Clock skew between workers. |
| ILIAS shows a passed exam as "in progress" | The Mastery Score is still 80 %. Set it to 22 in the object's *Optionen für den Lernfortschritt*. If the field is missing, tick *Provider unterstützt Outcome Service* in the provider first. |
| ILIAS accounts have no email address | Expected until the person enters one. In the user id mode ILIAS sends no real address (see [§3](#ilias-limitations-to-plan-around)). The consent page asks once for an address. A person who skipped it uses *Zugang ohne Lernplattform einrichten* in the app. |

## 12. Support and contact

- Teachers and students contact their organization admin first. Org admins
  manage connections in the panel.
- Issues with the open platform:
  <https://github.com/SebastianNagl/benger-platform/issues>
- LMS onboarding, the commercial edition, data protection requirements
  ([§8.8](#88-compliance-tell-us-what-you-need)) and source review under NDA:
  <sebastian.nagl@tum.de>

When you write about data protection, the most useful thing to send is the
list from [§8.8](#88-compliance-tell-us-what-you-need) with your answers. Then
we can reply with the documents instead of another round of questions.

---

## Appendix A: ILIAS setup sheet (German)

> **Das Tool als LTI-1.3-Tool in ILIAS einbinden**
>
> Die Bezeichnungen folgen der deutschen Oberfläche von ILIAS 10.9.
>
> 1. **Globalen Provider anlegen:** Administration → ILIAS erweitern → LTI →
>    Reiter „ILIAS als LTI-Konsument“ → „Globalen Provider für alle Benutzer
>    hinzufügen“.
> 2. **Felder ausfüllen.** Die URLs schickt Ihnen Ihr Organisations-Admin.
>    Das Panel zeigt sie unter **Lernplattform verbinden** → **ILIAS** und später
>    unter **Tool-Konfiguration**. Zwei Voreinstellungen des Formulars
>    passen nicht und müssen geändert werden: Verfügbarkeit und LTI-Version.
>    - „Verfügbarkeit“: **„in neuen und bestehenden Objekten“**. Die
>      Voreinstellung „nicht verfügbar“ verhindert neue Objekte.
>    - „LTI Version“: **„Version 1.3“**. Voreingestellt ist Version 1.1.
>    - „Login URL“: `https://<tool-host>/api/lti/launch`
>    - „Initiate Login URL“: `https://<tool-host>/api/lti/login`
>    - „Redirection URI“: `https://<tool-host>/api/lti/launch`
>    - „Typ des öffentlichen Schlüssels“: **„URL (Json Web Token)“**, im
>      Feld „URL“ `https://<tool-host>/api/lti/jwks`. Bitte unbedingt die
>      URL-Variante wählen und **keinen RSA-Schlüssel einfügen**, sonst
>      scheitert die Notenübertragung.
>    - „Unterstützung für Deep Linking“: **aus**
>    - „Erweiterte Benotungsdienste“: **aktivieren**
> 3. **Datenschutzeinstellungen:**
>    - „Identifikation der Person“: **„ID des ILIAS-Kontos kombiniert mit
>      einer eindeutigen ILIAS-Plattform-ID, die als E-Mail-Adresse
>      formatiert ist“**.
>    - Bitte **nicht** „E-Mail-Adresse“ wählen. In ILIAS 10.9 lehnt ILIAS in
>      diesem Modus jede Note mit „User not available“ ab. Die Ursache
>      liegt in ILIAS.
>    - „Anmeldename“: **„Vollständiger Name“**
>    - Folge: ILIAS übermittelt den vollständigen Namen, aber keine echte
>      E-Mail-Adresse. Direkt nach der Zustimmung werden Studierende und
>      Lehrende deshalb einmal nach ihrer E-Mail-Adresse gefragt. Der
>      Schritt lässt sich überspringen. Der Bestätigungslink an diese
>      Adresse ist zugleich die Aktivierungsmail. Eine Verknüpfung mit
>      bestehenden Konten gibt es nicht. In der Anwendung erscheint ein
>      Pseudonym.
>    - Die Identifikation nach der Inbetriebnahme **nicht mehr ändern**.
>      Jeder Wechsel trennt alle bestehenden Kontoverknüpfungen.
> 4. **Lernfortschritt:** Unter „Optionen für den Lernfortschritt“
>    „Provider unterstützt Outcome Service“ **anhaken** und „Voreinstellung
>    Mastery Score“ auf **22** setzen (4 von 18 Punkten gelten als
>    bestanden). Erst mit dem Haken erscheint der Mastery Score. Setzen Sie
>    den Wert, bevor Lehrende Objekte anlegen. Jedes Objekt übernimmt ihn
>    beim Anlegen.
> 5. Nach dem Speichern führt ILIAS zurück zur Provider-Liste. Öffnen Sie
>    den Provider erneut über seinen Titel. Unter „Erweiterte
>    Benotungsdienste“ stehen im Feld „Hinweise“ die Zeilen
>    **„Client ID“** und **„Deployment ID“**. Die Deployment-ID ist die
>    numerische Provider-ID. Melden Sie beide Werte an Ihren
>    **Organisations-Admin**.
> 6. **Lernfortschritt für die Installation einschalten**, falls noch nicht
>    geschehen: Administration → Lernerfolge → Zugriffsstatistiken und
>    Lernfortschritt → „Einstellungen“ → bei „Tracking aktivieren“
>    „Lernfortschritt“ anhaken. Sonst zeigt ILIAS den Lernfortschritt nicht
>    an.
> 7. **Im Kurs:** „Neues Objekt hinzufügen“ → „LTI-Konsument“ → Provider
>    wählen → online schalten. „Optionen für den Start“: **„Neues
>    Fenster“** (Pflicht). Unter „Optionen für den Lernfortschritt“ prüfen:
>    „Mastery Score“ **22**. Objekte, die vor Schritt 4 entstanden sind,
>    passen Sie dort an.
> 8. **Noten:** ILIAS erhält je Person einen Wert, die Endnote. Das ist die
>    Korrektur der Lehrenden, sonst die KI-Note. ILIAS zeigt sie als
>    Lernfortschritt. Eine eigene Spalte für die KI-Note gibt es in ILIAS
>    nicht, und Kommentare zur Note zeigt ILIAS nicht an.
> 9. **Voraussetzungen:** ILIAS 10 auf aktuellem Patchlevel. Getestet ist
>    ILIAS 10.9, ILIAS 9 ist nicht live getestet. Die JWKS-URL muss vom
>    ILIAS-Server aus über Port 443 erreichbar sein.

## Appendix B: Moodle setup sheet (German)

> **Das Tool als LTI-1.3-Tool in Moodle einbinden**
>
> **Variante 1, ein Link (empfohlen):**
>
> 1. Website-Administration → Plugins → Aktivitäten → Externes Tool → Tools
>    verwalten → den **Registrierungslink Ihres Organisations-Admins** in das
>    Feld **„LTI Advantage hinzufügen“** einfügen.
> 2. Fragt Moodle, ob ein vorhandenes Tool aktualisiert werden soll, wählen
>    Sie **„Als neues externes Tool registrieren“**. „Aktualisierung“ nur
>    dann, wenn Sie eine frühere Anbindung bewusst ersetzen.
> 3. Moodle und das Tool tauschen alle weiteren Werte aus. Das Tool erscheint
>    als *Wartend*. Ein Klick auf **aktivieren** schaltet es frei. Die
>    Anbindung ist sofort aktiv.
> 4. Öffnen Sie die Einstellungen des Tools (Symbol „Bearbeiten“ auf der
>    Tool-Karte) und setzen Sie:
>    - „Verwendung der Toolkonfiguration“: **„In Aktivitätsauswahl und als
>      vorkonfiguriertes Tool anzeigen“**
>    - „Standard-Startcontainer“: **„Neues Fenster“**
>    - „Bewertungen aus dem Tool akzeptieren“: **„Immer“**
>
>    Moodle legt jedes per Link registrierte Tool mit „Als vorkonfiguriertes
>    Tool anzeigen …“, „Eingebettet ohne Blöcke“ und „… an Dozierende
>    delegieren“ an. Das Tool kann das nicht ändern. Ohne die Änderung finden
>    Lehrende das Tool nicht in der Aktivitätsauswahl, das Tool startet
>    eingebettet, und Aktivitäten erhalten nur dann eine Bewertung, wenn
>    Lehrende das in jeder Aktivität erlauben.
> 5. Prüfen Sie in denselben Einstellungen auch:
>    - „Anwendername an Tool übergeben“ und „E-Mail des Anwenders an Tool
>      übergeben“: **„Immer“**, für alle Personen
>    - „IMS LTI Aufgaben und Bewertung“: **„Service für die Synchronisation
>      von Bewertungen und die Verwaltung der Spalten nutzen“**
>
>    Die Registrierung fordert beides an.
>
> **Variante 2, manuell:**
> Website-Administration → Plugins → Aktivitäten → Externes Tool → Tools
> verwalten → „Tool manuell konfigurieren“. Die URLs schickt Ihnen Ihr
> Organisations-Admin. Das Panel zeigt sie beim Anlegen einer **Neuen
> Anbindung** und später unter **Tool-Konfiguration**.
>
> - Tool-URL: `https://<tool-host>/api/lti/launch`
> - Initiate-Login-URL: `https://<tool-host>/api/lti/login`
> - Redirection-URI(s): `https://<tool-host>/api/lti/launch`
>   (zeichengenau identisch)
> - Öffentliches Schlüsselset: `https://<tool-host>/api/lti/jwks`
> - LTI-Version: **1.3**
> - Verwendung der Toolkonfiguration: **In Aktivitätsauswahl und als
>   vorkonfiguriertes Tool anzeigen**
> - Standard-Startcontainer: **Neues Fenster** (Pflicht, kein iframe)
> - Bewertungen aus dem Tool akzeptieren: **Immer**
> - IMS LTI Aufgaben und Bewertung: **Service für die Synchronisation von
>   Bewertungen und die Verwaltung der Spalten nutzen**
> - Deep Linking: **aus**
> - Datenschutz: „Anwendername an Tool übergeben“ und „E-Mail des Anwenders
>   an Tool übergeben“ auf **Immer**, für alle Personen. Die Konten tragen
>   Name und E-Mail-Adresse aus Moodle, in der Anwendung erscheint ein
>   Pseudonym.
>
> Anschließend die Tool-Details öffnen, **Client-ID** und **Deployment-ID**
> auslesen und an Ihren **Organisations-Admin** melden.
>
> **Bestehende Tools:** Beide Einstellungen stehen in der Konfiguration des
> Tools unter „Tools verwalten“. Steht „IMS LTI Aufgaben und Bewertung“ dort
> auf „Service nur für Bewertungen nutzen“, stellen Sie es auf **„Service für
> die Synchronisation von Bewertungen und die Verwaltung der Spalten
> nutzen“** um. Öffnen Sie danach die Aktivität einmal. Das Tool legt die
> Spalte „KI-Bewertung“ dann bei der nächsten Notenübertragung an,
> spätestens beim stündlichen Abgleich, sobald eine Note vorliegt.
>
> **Im Kurs:** Aktivität anlegen → das Tool in der Aktivitätsauswahl wählen
> → sicherstellen, dass die Aktivität **eine Bewertung besitzt** (Standard
> 100 genügt). Ohne Bewertung gibt es kein Line Item, und es kann keine Note
> zurückgeschrieben werden. Steht das Tool noch auf „… an Dozierende
> delegieren“, erscheint die Bewertung erst nach dem Haken bei **„<Toolname>
> erlauben, Bewertungen hinzuzufügen“**. Den Startcontainer wählen Lehrende
> in Moodle 4.5 nicht selbst. Er kommt aus den Einstellungen des Tools.
>
> **Noten:** Die Spalte der Aktivität erhält die Endnote. Das ist die
> Korrektur der Lehrenden, sonst die KI-Note, umgerechnet auf das Maximum der
> Aktivität. Die Spalte **KI-Bewertung** erhält immer die KI-Note auf der
> Skala 0 bis 18. Sie heißt „KI-Bewertung: <Titel der Aktivität>“. Spalten
> aus früheren Versionen heißen nur „KI-Bewertung“. Eine Korrektur löscht
> nichts.
>
> **Kursgesamtbewertung:** Moodle legt „KI-Bewertung“ als normalen
> manuellen Bewertungsaspekt an. Ohne Änderung zählt die KI-Note daher in
> „Kurs gesamt“ neben der Endnote mit. Die Spalte erscheint mit der ersten
> KI-Note. Danach nehmen Lehrende sie heraus: im Kurs „Bewertungen“ →
> „Setup für Bewertungen“ → in der Zeile der Spalte „KI-Bewertung“ das
> Kästchen in der Spalte „Gewichtungen“ anhaken, **0** eintragen,
> „Änderungen speichern“. Das gilt für die Standard-Berechnung „Summe“. Bei einer anderen Berechnung mit
> Gewichtung setzen Sie die Gewichtung dieser Spalte ebenfalls auf 0. Wird
> die Spalte neu angelegt, wiederholen Sie den Schritt.
>
> **Voraussetzungen:** Getestet ist Moodle 4.5. Moodle 5 ist anhand des
> Quellcodes geprüft, aber nicht live getestet. Die JWKS-URL muss vom
> Moodle-Server aus über Port 443 erreichbar sein. Moodles ausgehende
> curl-Sicherheit blockiert andere Ports standardmäßig.

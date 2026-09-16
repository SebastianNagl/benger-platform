# LMS integration (LTI 1.3) — Moodle and ILIAS

BenGER connects to a university's learning management system as an **LTI 1.3
Advantage tool**. Students launch from a course activity straight into an
exam, and grades flow back into the LMS gradebook automatically.

This document is written for the people who have to evaluate and operate that
integration: LMS administrators, university IT, and data-protection officers.
It describes what the tool does on the wire, what it stores, and what it asks
of your LMS. Ready-to-forward German setup sheets for the two supported
systems are in [Appendix A](#appendix-a-ilias-setup-sheet-german) and
[Appendix B](#appendix-b-moodle-setup-sheet-german).

**For the data protection review in one paragraph:** hosting is in Germany, a
student launch is pseudonymous by default and needs no name or email, consent
is captured in-product before any processing, grades go to your own LMS and
nowhere else, and the AI grade is always overridable by a human. We act as
processor and will meet the contractual and documentation requirements your
DPO sets. Tell us what you need and we will produce it, using the prompt list
in [§8.8](#88-compliance-tell-us-what-you-need).

## 1. Edition boundary (read this first)

BenGER follows an open-core model, and the LMS integration is split across the
two halves:

| Part | Edition | Where |
|---|---|---|
| Database schema for all LTI state (5 tables, migrations `079`/`083`/`084`) | Community (Apache-2.0) | this repository |
| Registration management API (`/api/admin/lti/*`), tool-config echo, grade-sync outbox reads and retry | Community (Apache-2.0) | `services/api/routers/lti_admin.py` |
| Admin UI for registrations, invites and the failed-sync queue | Community (Apache-2.0) | `services/frontend/src/app/admin/lti/` |
| **LTI protocol implementation** — OIDC third-party login, `id_token` validation, launch handling, JWKS, AGS grade passback, Dynamic Registration | **Commercial (BenGER Extended)** | not in this repository |

The routes an LMS actually talks to (`/api/lti/login`, `/api/lti/launch`,
`/api/lti/jwks`) are served by the commercial edition. **A deployment built
from this repository alone exposes the LTI admin surface but cannot accept a
launch.** The community edition is a complete benchmarking and annotation
platform; it is not an LTI tool.

If you are evaluating BenGER for LMS use, this means the code review you can
do on the open repository covers the data model, the tenant and role model,
the admin API and the storage of every LTI record, but not the protocol
handling. For the protocol half, this document is the specification, and a
source review can be arranged under NDA. Contact details are in
[§12](#12-support-and-contact).

## 2. What the integration does

1. An instructor places an **External Tool / LTI consumer** activity in a
   course and, on first launch, picks which BenGER exam it points at.
2. Students launch the activity. First-time users pass a consent gate, then
   land directly in the exam. No separate account creation, no password.
3. When a solution is graded, the grade is pushed back to the LMS gradebook
   via **Assignment and Grade Services (AGS)**. The AI grade appears right
   after submission and is overwritten by the human corrected grade and any
   later revision.

Grades are transmitted as German *Notenpunkte*, 0 to 18, with
`scoreMaximum: 18`. Your LMS rescales to whatever maximum the activity
carries, so an activity graded out of 100 shows 12/18 as 66.67.

## 3. Supported systems

| LMS | Versions | Status |
|---|---|---|
| Moodle | 4.5 and 5.x (verified against the 4.5 and 5.2 sources) | Validated end to end, including Dynamic Registration |
| ILIAS | 9 and 10, current patch level | Validated end to end against 10.9 |

ILIAS 8 reached end of life on 2025-12-31 and is not supported. ILIAS 11 is
expected to change AGS behaviour (LineItem CRUD, key validation) and will be
re-validated when it ships.

Any other LTI 1.3 certified platform is likely to work, because nothing in
the tool is Moodle- or ILIAS-specific on the wire. It has not been validated
and is not supported. See [§10](#10-conformance) for what has been tested.

### ILIAS limitations to plan around

These are properties of ILIAS 10, not of BenGER:

- **AGS LineItem and Results endpoints are not implemented** in ILIAS. The
  tool works exclusively from the `lineitem` URL supplied in the launch
  claim and never attempts LineItem discovery or creation. This is
  sufficient, but it means the activity must be configured to carry a grade
  before the first launch.
- **The score comment is discarded.** ILIAS stores the numeric score but not
  the `comment` field of the score POST. Written feedback and the overall
  assessment are visible only inside BenGER. Set expectations with your
  teaching staff accordingly.
- **Grades surface as Lernfortschritt, not as a gradebook column.** ILIAS
  compares `scoreGiven/scoreMaximum` against the object's *Mastery Score*,
  which defaults to 80 %. A passing law exam is 4 of 18 points, roughly
  22 %, so with the default a passed exam is reported as "in progress". Set
  the Mastery Score to **22**.
- **No Names and Role Provisioning Service (NRPS)** before ILIAS 12.
  Accounts are provisioned at launch time only. Moodle is used the same way,
  so this is not a functional difference between the two.

## 4. Architecture and data flow

```
  Student in LMS course
        │
        │  1. clicks the External Tool activity
        ▼
  LMS  ──POST /api/lti/login──────────────▶  BenGER
                                              mints state + nonce (server-side,
                                              single-use, 5 / 10 min TTL)
        ◀──302 to the LMS authorization endpoint──
        │
        │  2. LMS authenticates the user, signs an id_token
        ▼
  LMS  ──POST /api/lti/launch (form_post)─▶  BenGER
                                              verifies RS256 signature against
                                              the LMS JWKS, checks iss/aud/exp/
                                              nonce, consumes the nonce once
                                              provisions or links the account
                                              starts a session, redirects to the
                                              exam (or the consent gate)
        │
        │  3. student solves and submits; grading happens in BenGER
        ▼
  BenGER ──POST client_credentials + private_key_jwt──▶ LMS token endpoint
  BenGER ──POST score to the lineitem URL (AGS)───────▶ LMS gradebook
```

Everything is server-to-server over HTTPS. The tool never embeds itself in an
LMS iframe; see [§9](#9-requirements-on-your-lms).

## 5. Tool endpoints

Three endpoints, all on the public base URL of the BenGER deployment:

| Purpose | URL |
|---|---|
| Initiate login (OIDC third-party init) | `https://<benger-host>/api/lti/login` |
| Launch / redirection URI | `https://<benger-host>/api/lti/launch` |
| Public keyset (JWKS) | `https://<benger-host>/api/lti/jwks` |

There is **no deep-linking URL**, deliberately. The tool rejects
`LtiDeepLinkingRequest` launches; content is bound through the instructor
launch picker instead ([§7](#7-course-setup-instructor)). Do not configure
deep linking in your LMS.

A superadmin can read the exact values for a given deployment from
`GET /api/admin/lti/registrations/{id}/tool-config?base_url=https://<host>`.

### Scopes requested

The tool requests exactly two AGS scopes when it exchanges a client assertion
for an access token, and no others:

| Scope | Why |
|---|---|
| `https://purl.imsglobal.org/spec/lti-ags/scope/score` | Post a grade to the activity's line item |
| `https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly` | Read the line item to confirm it exists and its maximum |

Note that `lineitem` (read-write) is **not** requested: the tool never
creates, modifies or deletes line items. It also does not request
`result.readonly`, and it does not use the Names and Role Provisioning
Service, so it never enumerates your course rosters.

Token exchange uses the `client_credentials` grant with `private_key_jwt`
client authentication, signed RS256. Access tokens are cached in process for
their stated lifetime, refreshed five minutes before expiry.

## 6. Registering your LMS

Two paths. Both end with a registration that is **disabled until a BenGER
superadmin enables it**, so an accidental or premature registration cannot
process student data.

### 6a. Dynamic Registration (recommended)

BenGER mints a one-time, organization-bound invite link of the form
`https://<benger-host>/api/lti/register/init?token=<token>`. The token is
single-use, stored only as a SHA-256 hash, and expires after a configurable
period (14 days by default, 1 to 90 allowed).

- **Moodle**: Site administration → Plugins → External tool → Manage tools →
  paste the link into the **"Add LTI Advantage"** box. Moodle and BenGER
  exchange issuer, endpoints, `client_id` and `deployment_id` automatically
  via IMS Dynamic Registration. The tool appears as *Pending*; click
  **Activate**.
- **ILIAS** (10.9 and later): create an LTI consumer object → section
  *Create Own Settings for Tool with Dynamic Registration (LTI 1.3)* → paste
  the link → Add. ILIAS fills in all tool URLs correctly, including the JWKS
  URL key type. Two caveats: **"Advanced Grading Services" is left
  unchecked** and must be enabled manually or no grade will ever transmit;
  and the result is an object-bound user provider rather than a global
  provider, so for a campus-wide rollout the manual route in
  [Appendix A](#appendix-a-ilias-setup-sheet-german) is preferable.

The registration endpoint is SSRF-guarded and validates the IMS origin.

### 6b. Manual registration

Supply the LMS site URL. Everything else is derived:

| Field | Moodle | ILIAS |
|---|---|---|
| Issuer | `https://moodle.uni-x.de` (`$CFG->wwwroot`, no trailing slash) | `https://ilias.uni-x.de` (base URL, no trailing slash) |
| Authorization endpoint | `{issuer}/mod/lti/auth.php` | `{issuer}/ltiauth.php` |
| Token endpoint | `{issuer}/mod/lti/token.php` | `{issuer}/ltitoken.php` |
| Platform JWKS | `{issuer}/mod/lti/certs.php` | `{issuer}/lticerts.php` |
| `client_id`, `deployment_id` | read from the tool details after saving | Client ID plus the numeric **Provider ID**, which is the deployment id |

ILIAS also publishes `{issuer}/lticonfig.php`, which is useful for verifying
the above.

### Per-registration policy

| Setting | Default | Effect |
|---|---|---|
| `link_existing_users_by_email` | `true` | A launch email attaches to an existing BenGER account only if that account's address is **verified**. Otherwise a pseudonymous account is created. Linking never elevates privileges and is audit-logged. |
| `instructor_org_role` | `contributor` | Organization role granted to launching instructors. `org_admin` and `none` are also available. |
| `student_org_role` | `annotator` | Organization role granted to launching students. Set to `none` for a privacy-strict tenant that wants entitlement-only students. |
| `group_id` | unset | Optionally scopes the registration to one group inside the organization. |
| `status` | `disabled` on creation | Kill switch. `disabled` blocks every launch for that LMS. |

**Identity mapping is sticky.** The decision between email linking and
pseudonymous provisioning is made on the *first* launch for a given
`(registration, sub)` pair and recorded. Changing your LMS privacy settings
afterwards has no effect until the stale mapping row is removed. Decide the
privacy mode before go-live.

## 7. Course setup (instructor)

1. Add an External Tool (Moodle) or LTI consumer (ILIAS) activity to the
   course and pick the BenGER tool.
2. **Make sure the activity carries a grade.** Without a grade there is no
   AGS line item and no grade can ever be returned. Moodle's default of 100
   is fine.
3. Set the launch container to **New window**. This is required; see
   [§9](#9-requirements-on-your-lms).
4. The instructor's first launch opens an exam picker. Pick one of their
   BenGER exams. Only exams using the *Falllösung* grading family are
   linkable; free-form custom judge rubrics are not yet syncable.
5. Students launching afterwards see the consent gate once, then the exam.

Re-pointing an activity at a different exam is blocked once grades have
synced. Create a new activity instead.

## 8. Identity, data protection and what is stored

### 8.1 The default is pseudonymous

BenGER works **fully pseudonymously on the `sub` claim alone**. No name and
no email claim is required for a student launch. This is the recommended
configuration for German universities and usually shortens the DPO review.
Instructors are the exception: without an email claim, an instructor's first
launch creates a fresh pseudonymous account whose exam picker is empty, so
they can never bind their own exams. Set name and email sharing to *always*
for instructors.

ILIAS note: the `sub` value is derived from the provider's **privacy mode**
(user id, login, SHA-256 or email). Changing the privacy mode after go-live
changes every `sub` and detaches every existing account link. ILIAS also
sends suppressed name claims as a literal `"-"` rather than omitting them,
and a default pseudo-email of the form `<ident>@<installation-uuid>.ilias`
which is syntactically valid but undeliverable. BenGER normalises both away.

### 8.2 Claims consumed

From the `id_token`: `sub`, `iss`, `aud`, `exp`, `iat`, `nonce`, the LTI
`message_type`, `version`, `deployment_id`, `resource_link`, `context`,
`roles`, `custom`, and the AGS endpoint claim. Optionally `name` and `email`
when your LMS is configured to share them.

Roles are mapped narrowly: any instructor-shaped role marker grants the
configured instructor role, everything else is treated as a learner. On
ILIAS 10, course admin and course tutor both map to instructor, course
member maps to learner.

### 8.3 What is persisted

Five tables, all in the open repository so you can inspect the schema
directly in `services/api/alembic/versions/079_add_lti_tables.py`:

| Table | Contents | Personal data |
|---|---|---|
| `lti_platform_registrations` | Your LMS issuer, client id, endpoint URLs, policy flags | none |
| `lti_deployments` | Known deployment ids under a registration | none |
| `lti_resource_links` | Activity to exam mapping, course id and title, AGS line item URLs and scopes | course titles only |
| `lti_user_links` | `sub` to BenGER user mapping, the consent timestamp and version, last launch time, and a small claims snapshot | `name`, `email` and `roles` **only if your LMS shares them**; otherwise `sub` alone |
| `lti_grade_syncs` | Grade passback outbox: status, attempt count, last synced score and hash, last error | links a user to a score |

No raw `id_token` is retained. State and nonce live in Redis with 5 and 10
minute TTLs respectively and are deleted on use.

### 8.4 Consent

Every student passes a consent gate on first launch, before any exam content
is shown, and the outcome is recorded in `lti_user_links` with a version
stamp. It captures:

- **Required**: processing consent covering the link between the LMS
  identity and the BenGER account, and transmission of the grade back to the
  LMS.
- **Optional**: consent to research use of the data, declinable without
  losing access.

### 8.5 Where the data lives

- **Hosting is in Germany.** No transfer to a third country is involved in
  running the integration, so no Art. 44 et seq. transfer mechanism is
  required for it.
- **Grade data transits to the university's own LMS and nowhere else.**
- **You choose the model provider.** LLM grading for an LTI cohort runs on
  the API key held by *your* organization in BenGER, never on a BenGER-owned
  key. That means the university decides which provider processes solution
  text, and can name that provider in its own record of processing. Custom
  model endpoints, including self-hosted ones, are supported; if you want
  grading to stay inside your own infrastructure, raise it during onboarding
  so we can size it with you.

### 8.6 Privacy by design and by default (Art. 25 GDPR)

The integration was built privacy-first rather than retrofitted, and the
individual properties are documented above. Consolidated, so a DPO can
assess them in one place:

| Property | Effect |
|---|---|
| Pseudonymous by default | A student launch needs only the `sub` claim. No name, no email, no matriculation number. See [§8.1](#81-the-default-is-pseudonymous). |
| Data minimisation on the wire | Two AGS scopes only, both grade-related. No Names and Role Provisioning, so course rosters are never read. See [Scopes requested](#scopes-requested). |
| Minimal storage | Five tables, [itemised](#83-what-is-persisted). Name, email and roles are stored **only if your LMS chooses to send them**. Raw `id_token`s are never retained; OIDC state and nonce expire in 5 and 10 minutes. |
| Consent before processing | Captured in-product on first launch, version-stamped, with research use separately optional and declinable. See [§8.4](#84-consent). |
| Purpose limitation | Grades flow to your LMS only. Nothing is shared with third parties for the operation of the integration. |
| Tenant isolation | Every registration is bound to one organization; students never enumerate rosters; member listing requires an elevated role. |
| Human in the loop | The AI grade is always overridable by a human correction. See [§8.7](#87-automated-assessment). |
| Fail-closed controls | Registrations are created disabled, deployment checks reject unknown deployments, and disabling a registration stops every launch. |
| Revocable | Deletion on request through the organization administrator. See [§8.9](#89-retention-and-deletion). |

### 8.7 Automated assessment

Automated assessment of examinations is the trigger for the questions German
university DPOs typically raise, so the position is stated plainly:

- The AI grade is **always human-overridable**. The correction workflow
  overwrites it and pushes the revised grade.
- No fully automated individual decision within the meaning of Art. 22 GDPR
  is made.
- Per-student consent is captured before any processing.

Whether a data protection impact assessment is required is the university's
decision as controller. We supply the processing description as input rather
than arguing the question either way.

### 8.8 Compliance: tell us what you need

We act as processor, the university acts as controller, and **we will meet
the documentation and contractual requirements your data protection office
sets.** That includes signing your own data processing agreement if you have
a standard one, or supplying ours if you would rather start from a draft.

What we cannot do is guess which of the many possible artefacts your DPO
actually wants, because it differs by institution and by whether the use is a
practice exercise or a graded examination. **Please tell us specifically what
you need.** The list below is a prompt, not a menu we are limited to:

- **Contract**: your AVV/DPA template, or ours as a starting point? Any
  framework agreement it has to sit under?
- **Technical and organisational measures**: a TOMs annex in your format, or
  free-form? Any specific controls you must see evidenced?
- **Record of processing**: do you want a ready-made entry for your VVT, or
  only the processing description as input to your own drafting?
- **DPIA**: are you running one? If so, what do you need from us and by when?
- **Claim scope**: pseudonymous `sub` only, which is the default and the
  shortest review, or do you want name and email in launches? This changes
  the processing description on both sides.
- **Subprocessors**: do you need a subprocessor list, and do you want to
  name the model provider yourself via your own API key?
- **Retention**: a fixed deletion period for accounts and grades, or
  deletion on request?
- **Hosting evidence**: do you need the hosting location and arrangement
  documented in the contract?
- **Security review**: do you want a source review of the protocol half
  under NDA, a completed security questionnaire, or both?

Two practical notes from earlier onboardings. First, get a named contact for
both the legal side and the LMS administration early; the AVV is normally
signed by the Justiziariat or the faculty's data protection coordination
rather than by the individual instructor. Second, the contract should be in
place before the registration is enabled, because an enabled registration
processes real student data. We therefore leave every new registration
disabled until you tell us to switch it on.

Send requirements to the address in [§12](#12-support-and-contact).

### 8.9 Retention and deletion

Accounts provisioned through a launch, and their grades, are deleted on
request through the organization administrator. If you want a fixed retention
period rather than deletion on request, name it and we will record it in the
contract.

## 9. Requirements on your LMS

- **Reachability.** Your LMS must be able to reach the BenGER JWKS URL over
  **port 443**. Moodle's outbound curl security blocks non-80/443 ports by
  default, and a keyset on an exotic port fails the token exchange with a
  null-JWKS error. On-premise installations behind an egress proxy may need
  `curlsecurityblockedhosts` reviewed.
- **JWKS by URL, never a pasted key.** On ILIAS in particular, choose the
  *JWK keyset URL* key type. ILIAS validates our client assertion only via
  the keyset URL, refetching per request. A pasted RSA key will pass the
  launch and then silently break grade transmission.
- **New window launches.** Embedded iframe launches are not supported. The
  session cookie design requires a top-level browsing context.
- **Clock sync.** Moodle `id_token`s live 60 seconds and ILIAS validates our
  client assertions with zero leeway. Keep NTP tight on both sides. AGS also
  requires strictly increasing score timestamps, so skew between our own
  workers surfaces as a `409` on score POST.
- **Exact redirect URI.** The redirection URI must match the registered
  entry character for character, line by line.

## 10. Conformance

- The tool has been exercised against the **saLTIre** LTI conformance
  emulator (`saltire.lti.app`), covering launch acceptance, JIT user and
  resource-link provisioning, and negative cases: `alg:none` tokens, garbage
  tokens and missing parameters all produce a clean error redirect with no
  server error.
- End-to-end validation has been performed against a real Moodle and a real
  ILIAS 10.9 instance, in each case through the full loop: launch,
  provisioning, consent, submission, correction, AGS push, grade visible in
  the LMS.
- **BenGER is not currently 1EdTech certified.** If formal certification is
  a procurement requirement, raise it early.

Replay protection is verified as part of every validation run: re-posting a
previously used `id_token` is rejected, because the nonce is consumed
exactly once per registration inside its TTL using an atomic set-if-absent.

## 11. Operating the tool (self-hosted deployments)

Only relevant if you run BenGER yourself rather than using the hosted
service. The LTI routes require the commercial edition
([§1](#1-edition-boundary-read-this-first)).

**Signing key.** The tool signs client assertions with an RSA key, RS256.
Generate a 4096-bit key and supply it through `LTI_TOOL_PRIVATE_KEY` (PEM) or
`LTI_TOOL_PRIVATE_KEY_FILE`, naming it with `LTI_TOOL_KID`. Without a
configured key the process generates an ephemeral in-memory keypair and logs
a warning; that is fine for tests and useless in production, because the
published JWKS goes stale on every restart.

**Rotation.** Install the new key as the active pair and move the old one to
`LTI_TOOL_PRIVATE_KEY_PREVIOUS` / `LTI_TOOL_KID_PREVIOUS`, then restart. The
JWKS serves both keys during the window and platforms refetch on a `kid`
miss. Drop the previous pair after about an hour. Every JWK served carries
both `kid` and `alg`, which Moodle requires.

**Organization API key.** LLM grading for an LTI cohort bills to the
organization that owns the registration, never to the student. The
organization must hold a judge provider key, and its `require_private_keys`
setting must be `false`. With `require_private_keys: true` the resolver falls
through to the launching user's personal key, which LTI students do not have,
and grading fails. See [API key resolution](./features/api-key-resolution.md).

**Redis is required.** OIDC state and nonce storage is in Redis and fails
closed. If Redis is unavailable, launches are rejected rather than accepted
without CSRF binding.

**Grade passback is an outbox.** Failed pushes are retried with exponential
backoff from 60 seconds, doubling, capped at 6 hours, up to 10 attempts. A
periodic sweep heals the queue after an LMS outage. Administrators can
inspect the queue and force a retry from the admin UI or via
`POST /api/admin/lti/grade-syncs/{id}/retry`.

**Kill switches.** Setting a registration to `disabled` blocks everything for
that LMS. Disabling its deployment row blocks launches too; the deployment
check fails closed, so an empty active-deployment set rejects every launch.

### Validation checklist before onboarding a new university

1. `GET https://<benger-host>/api/lti/jwks` returns 200 and every key carries
   `kid` and `alg`.
2. Instructor launch reaches the picker and an exam can be linked.
3. Student launch in a clean browser shows the consent gate exactly once;
   re-launch goes straight to the exam.
4. Submit an attempt and confirm the grade lands in the LMS gradebook with
   the correct rescaling.
5. Revise the grade through the correction workflow and confirm the gradebook
   entry is overwritten.
6. Interrupt LMS connectivity briefly and confirm the outbox backs off and
   then heals.
7. Replay a launch POST with the same `id_token` and confirm it is rejected.

### Troubleshooting

| Symptom | Cause |
|---|---|
| Instructor lands in an empty account, picker shows no exams | LMS tool privacy withholds name and email, so a pseudonymous account was provisioned. Set both to *always* **and** clear the stale `lti_user_links` row, because the first-launch mapping is sticky. |
| Student sees a `not_linked` error | Expected before linking. The instructor has not bound an exam to the activity yet. |
| Moodle `invalidrequest` at `auth.php` | Redirect URI not registered character for character, or a mangled `lti_message_hint`. |
| Token call fails with `"kid" invalid` | The LMS cannot match our JWKS: wrong or unreachable keyset URL, a key rotated without the previous pair configured, or API and workers signing with different keys. |
| Token call fails with a null-JWKS error | LMS outbound curl security is blocking the keyset URL. Serve it on 443. |
| ILIAS token endpoint returns `ERROR_OPEN_SSL_CONF` | A misleading catch-all for any exception, including an unknown `kid` or a failed JWKS fetch. The real exception is only in the ILIAS log. Check that the JWKS URL is reachable from the ILIAS server and that the correct `kid` is in use. |
| Grade never appears | The activity was created without a grade, so there is no line item; or the exam's evaluation config is not in the Falllösung family; or, on ILIAS, "Advanced Grading Services" was never enabled. |
| `409` on score POST | AGS requires strictly increasing timestamps. Clock skew between workers. |
| ILIAS shows a passed exam as "in progress" | Mastery Score left at the 80 % default. Set it to 22. |

## 12. Support and contact

- Issues with the open platform: <https://github.com/SebastianNagl/benger-platform/issues>
- LMS onboarding, the commercial edition, data protection requirements
  ([§8.8](#88-compliance-tell-us-what-you-need)), and source review under
  NDA: <sebastian.nagl@tum.de>

When you write in about data protection, the single most useful thing you can
send is the list from [§8.8](#88-compliance-tell-us-what-you-need) with your
answers filled in. It lets us come back with the actual documents instead of
another round of questions.

---

## Appendix A: ILIAS setup sheet (German)

*Zum Weiterleiten an die ILIAS-Administration.*

> **BenGER als LTI-1.3-Tool in ILIAS einbinden**
>
> 1. **Globalen Provider anlegen:** Administration → Erweiterung von ILIAS →
>    LTI → Tab „ILIAS als LTI-Konsument" → „Add Global Provider for all
>    Users".
> 2. **Felder ausfüllen** (Werte liefert das BenGER-Team):
>    - LTI-Version: **LTI 1.3**
>    - Tool-URL: `https://<benger-host>/api/lti/launch`
>    - Initiate-Login-URL: `https://<benger-host>/api/lti/login`
>    - Redirection-URI(s): `https://<benger-host>/api/lti/launch`
>    - Schlüsseltyp: **JWK-Keyset-URL** = `https://<benger-host>/api/lti/jwks`
>      — bitte unbedingt die URL-Variante wählen und **keinen Schlüssel
>      einfügen**, sonst schlägt die Notenübertragung fehl.
>    - „Advanced Grading Services" (Grade Synchronization): **aktivieren**
>    - Deep Linking: **aus**
>    - Privacy: Modus frei wählbar, aber **nach Inbetriebnahme nicht mehr
>      ändern** (jeder Moduswechsel trennt alle bestehenden Kontoverknüpfungen).
> 3. Nach dem Speichern **Client-ID** und **Provider-ID** (numerisch) an das
>    BenGER-Team melden. Die Provider-ID ist unsere Deployment-ID.
> 4. **Im Kurs:** „Neues Objekt hinzufügen" → LTI-Konsument → Provider wählen
>    → Online schalten. „Optionen für den Start": **Neues Fenster** (Pflicht).
>    Mastery Score: **22** (4 von 18 Punkten entspricht „bestanden").
> 5. **Voraussetzungen:** ILIAS 9 oder 10 auf aktuellem Patchlevel; die
>    BenGER-JWKS-URL muss vom ILIAS-Server aus über Port 443 erreichbar sein.

## Appendix B: Moodle setup sheet (German)

*Zum Weiterleiten an die Moodle-Administration.*

> **BenGER als LTI-1.3-Tool in Moodle einbinden**
>
> **Variante 1 — Dynamische Registrierung (empfohlen, ein Link):**
> Website-Administration → Plugins → Externes Tool → Tools verwalten → den
> vom BenGER-Team erhaltenen Registrierungslink in das Feld
> **„LTI Advantage hinzufügen"** einfügen. Moodle und BenGER tauschen alle
> weiteren Werte automatisch aus. Das Tool erscheint als *Ausstehend*, ein
> Klick auf **Aktivieren** schließt die Moodle-Seite ab.
>
> **Variante 2 — manuell:**
> Website-Administration → Plugins → Externes Tool → Tools verwalten → „Tool
> manuell konfigurieren":
>
> - Tool-URL: `https://<benger-host>/api/lti/launch`
> - Initiate-Login-URL: `https://<benger-host>/api/lti/login`
> - Redirection-URI(s): `https://<benger-host>/api/lti/launch`
>   (zeilengenau identisch)
> - Öffentliches Schlüsselset: `https://<benger-host>/api/lti/jwks`
> - LTI-Version: **1.3**
> - Standard-Startcontainer: **Neues Fenster** (Pflicht, kein iframe)
> - IMS LTI Assignment and Grade Services: **nur Notensynchronisation**
> - Deep Linking: **aus**
> - Datenschutz: für **Studierende** optional — BenGER arbeitet vollständig
>   pseudonym allein auf Basis der `sub`-Kennung. Für **Lehrende** bitte Name
>   und E-Mail auf *Immer* stellen, sonst kann die Lehrkraft ihre eigenen
>   Klausuren nicht zuordnen.
>
> Anschließend die Tool-Details öffnen, **Client-ID** und **Deployment-ID**
> auslesen und an das BenGER-Team melden.
>
> **Im Kurs:** Aktivität anlegen → Externes Tool → BenGER-Tool wählen →
> sicherstellen, dass die Aktivität **eine Bewertung besitzt** (Standard 100
> genügt). Ohne Bewertung existiert kein Line Item und es kann keine Note
> zurückgeschrieben werden.
>
> **Voraussetzung:** Die BenGER-JWKS-URL muss vom Moodle-Server aus über
> Port 443 erreichbar sein. Moodles ausgehende curl-Sicherheit blockiert
> andere Ports standardmäßig.

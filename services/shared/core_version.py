"""Single source of truth for the open-core extension handshake.

CORE_API_VERSION is the contract version the platform exposes to the
proprietary benger_extended overlay. The extended package declares
COMPATIBLE_CORE_VERSIONS; every loader (services/api/extensions.py,
services/workers/ml_evaluation/__init__.py, services/workers/tasks.py)
checks this constant against that list at startup.

This module lives in /shared so the api and the workers import the exact
same value — it was previously hand-copied into all three loaders with
"keep in sync" comments, which is how versions drift.

The extended repo's tests/test_version_handshake.py string-parses this file
(it deliberately avoids importing platform modules), so keep the assignment
on a single line in the form: CORE_API_VERSION = "<version>". The parser
takes the first line that starts with the constant's name, so no line of
this docstring may start with it either.

What each version added (the symbols the extended overlay imports; bump
whenever one is added, renamed or removed):

- 2.8: task_rubrics table + llm_judge_rubric worker routing + TaskRubricPanel
  slot (Bewertungsbogen feature).
- 2.9: participant access tier (get_project_access_tier) + share governance
  (check_user_can_manage_shares) + projects.icon — benger Entdecken wave.
- 2.10: org_resolution + project_consumers + the org_billing_authorized
  consumer-inheritance flag.
- 2.11: organization groups (shared/org_groups: attachment_group_clause,
  ProjectOrganization.group_id, group-scoped org API keys) — the extended
  student arms and worker key threading reference them.
- 2.12: grading_feedback table (project_models.GradingFeedback) — solver
  thumbs/comment feedback on LLM and human gradings; the extended write
  router upserts into it.
- 2.13: Bewertungsbogen as a grading mode — task_rubrics.structure/grade_scale
  + float total_points (migration 100), the shared pure module
  ``rubric_structure`` (validate/normalize/criteria projection/grade
  tables/task.data mirror) and the async ``task_rubric_service``
  (create/edit-with-clone/activate/archive), platform task-rubrics writes +
  stateless parse, judge rows carrying grade_points/passed, optional
  generator keys on llm_judge_rubric configs. The extended routers/worker
  import both shared modules.
- 2.14: the Notenschlüssel audit trail — the shared pure module
  ``grade_scale_history`` (append_grade_scale_change / mark_recomputed /
  latest_grade_scale_change / carry_grade_scale_history) that BOTH writers
  of ``evaluation_config.grade_scale`` append through. The extended exam
  router imports it at module level: without it the Vertretbar exam modal
  would write the key and record nothing, so the handshake has to fail
  loudly rather than degrade.
- 2.15: REMOVES the Falllösung judge's prompt versioning: the bulk fan-out no
  longer forwards ``metric_parameters.prompt_version`` (the extended compute
  hook no longer takes it) and migration 101 strips the dead key from stored
  evaluation configs. One judge prompt, one Notenschlüssel, for every exam.
  Also widens the rubric importer to .csv/.md/.json and adds
  ``rubric_import.rubric_document_text``, which the extended AI-structuring
  fallback reads its document with.
- 2.16: the Bewertungsbogen fix train (platform #375/#376, extended #118):
  ``model_defaults.DEFAULT_JUDGE_MODEL_ID`` (the judge a config grades with
  when it names none; the extended exam/flashcard defaults follow it),
  ``eval_field_classification.bare_field_name`` / ``same_field`` /
  ``unprefixed_is_human`` (one authority for the role-prefix rule; migration
  102 re-files human rubric gradings under the field they grade), the
  evidence-quoted rubric judge (per-step evidence verified against the
  step's own part, ``reasoning_effort`` forwarded; the extended
  ``rubric_judge_backfill`` maintenance script rewrites stored judge
  configs to it), ``import_jobs.organization_id`` (migration 103) and
  Bewertungsbogen rows carried through full project export/import.
- 2.17: ``rubric_structure.order_criteria_keys`` (the one ordering of flat
  criteria both grading surfaces use), ``model_defaults.RUBRIC_JUDGE_MAX_TOKENS``
  / ``METRIC_MAX_TOKENS_FLOOR`` (the rubric judge's output budget the builder
  and the worker floor respect), and creator access to an unattached
  (private) project under a foreign org context — the extended task-rubric
  reads route to the platform endpoints instead of re-implementing it.
- 2.18: the ``evaluation_received_*`` notification types (migration 104) and
  ``notification_service.notify_evaluation_received`` /
  ``annotator_ids_for_annotations``, which the extended Korrektur grade
  endpoints call when a new human grading lands. The workers also look for an
  optional ``benger_extended.workers.get_notification_brand_host_fn`` to brand
  notification emails.
- 2.19: the attempted access tier — ``routers.projects.helpers.TIER_ATTEMPTED``
  (an own non-cancelled annotation keeps read access to the submission
  through window / archive / privacy / membership / share changes; only the
  soft delete removes it), ``user_attempted_project(_async)``,
  ``get_attempted_project_ids(_async)``, ``tier_allows_writes`` /
  ``require_write_tier`` and the ``tier=`` kwarg of
  ``enforce_project_read_window(_async)`` (attempted exempt). The extended
  student list/detail, own-review and Korrektur reads honour it; the timer
  and flashcard writes refuse it.
- 2.20: LMS (LTI) connections run by org admins and group admins, consent
  before any account, proof-based account linking, co-existing AI and human
  grades, connection-org billing, staff access to linked exams, LMS name
  masking and anonymization (one bundled release with the extended overlay).
  Schema: migration 105 (``tool_host`` on registrations and invites;
  ``lti_user_links.research_consent_at`` / ``link_method`` / ``unlinked_at``;
  ``lti_resource_links.ai_lineitem_*``; ``lti_grade_syncs.kind`` /
  ``last_synced_source`` / ``last_checked_at`` with ``uq_lti_grade_sync`` on
  (resource_link_id, user_id, kind); the new ``lti_resource_link_users``
  and ``lti_admin_events`` tables) and migration 106
  (``task_evaluations.updated_at``, ``users.anonymized_at``,
  ``ix_users_email_lower``, the ``lti_claim`` email method of provisioned
  accounts (the verified flag is left alone so older pods keep working),
  ``users.lms_provisioned_at`` / ``users.lms_origin_org_id`` (the LMS
  origin of an account a launch created; the extended provisioning sets
  both, deleting a connection stamps them, migration 106 backfills them),
  ``project_organizations.attached_via``); the activation and
  password-reset confirm paths verify an unproven routable address,
  including a verified one still marked ``lti_claim``
  (``account_activation.verify_email_by_link``). ``lti_admin_events`` has a
  ``group_id`` (SET NULL; a row with a registration and no group gets the
  registration's group on insert). Modules: ``public_hosts``
  (tool host key to base URL), ``user_display`` (real name or pseudonym label),
  ``auth_module.org_scope`` (``OrgAdminScope``, ``require_scope_admin`` and
  its sync twin). API hooks the extended ``get_hooks()`` registers:
  ``dispatch_lti_grade_sync``, ``privacy_protected_member_ids`` (an LMS
  user has a provisioned link, a link that is not unlinked, or the LMS
  origin marker; an org call counts marked accounts of that origin org once
  no provisioned link is left; with the keyword ``group_ids``: only the
  org's connections scoped to those groups, markers do not count; a hook
  without it reveals nobody to group admins),
  ``project_real_name_viewer``, ``lti_anonymization_policy``,
  ``lti_protected_org_ids`` and ``projects_real_name_user_ids(db, viewer,
  {project_id: user_ids}) -> {project_id: set}`` (the bulk form the project
  list uses; the wrapper loops the single hook when it is missing). Hooks
  that query run inside a savepoint, so a failed query leaves the caller's
  transaction usable. Billing contract: the grading dispatch policy
  may return a 4-tuple ``(org_id, configs, authorized, block)``; a block
  marks the immediate run failed via
  ``_mark_immediate_run_failed(extra_metadata=)`` and runs no judge; the
  shared ``immediate_eval_dispatch.record_blocked_immediate_run`` /
  ``latest_blocked_run`` keep one blocked run per annotation, and the
  submit, endpoint and sweep paths consult the optional worker hook
  ``benger_extended.workers.get_grading_block_fn``. Like
  ``get_grading_dispatch_policy_fn`` that hook is NOT in ``get_hooks()``:
  the workers never load ``extensions.py``, and the handshake test only
  scans that file. The same holds for the optional worker hook
  ``benger_extended.workers.get_batch_evaluation_policy_fn``:
  ``run_evaluation`` asks it for ``(org_id, block[, authorized])`` before any
  judge run, fails a refused batch run with ``billing_blocked:<reason>``
  (the block under ``eval_metadata.billing_block``), and every evaluation
  cell asks it again for the authorization instead of reading a payload.
  ``GradingPayer`` (``schemas/billing_schemas.py``) gains ``block_reason``
  and ``missing_providers``. Imports refuse a second task on an exam an LMS
  activity points at (``multi_task_unsupported``, API and import drivers).
  Admin API: ``/api/admin/lti`` is scoped to org and group admins, with
  ``GET /tool-hosts``, ``DELETE /registrations/{id}``
  (``accounts=keep|anonymize``),
  ``PATCH .../deployments/{pk}``, ``GET .../resource-links``,
  ``GET|DELETE .../user-links``, ``GET .../events``, the organization
  history ``GET /api/admin/lti/events`` (``organization_id``,
  ``registration_id``, ``deleted_only``; also invites and deleted
  connections, group admins see their groups' entries), grade transfers with
  context and a retry that dispatches through ``dispatch_lti_grade_sync``,
  and ``POST /registrations/{id}/grade-syncs/resend-all`` (202, "resend all
  grades" of a connection, a ``grades_resend_all`` event with counts) through
  the optional API hook ``resend_all_lti_grades(db, registration_id) ->
  dict`` (``status`` queued, scheduled, nothing or refused with ``code``,
  ``message`` and ``http_status``; may commit ``db`` when its queue is down;
  501 ``grade_transfer_unavailable`` without it). Its Celery task
  ``tasks.lti_resend_all_grades`` is routed to ``interactive`` in
  ``celery_queues``.
  Moving a connection to another group or org, and deleting one, re-derives
  the org's LMS-linking attachments of its exams
  (``org_groups.sync_lti_attachments(_async)``, ``collapse_linking_groups``,
  ``plan_lti_attachment_sync``, ``lti_sync_changed``); the update event
  lists them under ``resynced_project_ids``. Deleting a connection with
  ``accounts=anonymize`` runs set-based
  (``user_anonymization.anonymize_users(_sync)``, ``AnonymizationOutcome``).
  Consent first and proof linking (the extended overlay parks a launch until
  consent and links an existing account only after proof):
  ``account_activation`` gains ``EMAIL_METHOD_LMS_CLAIM``,
  ``UNPROVEN_EMAIL_METHODS``, ``ACCOUNT_LINK_TOKEN_EXPIRY`` (the proof-token
  TTL), ``email_ownership_proven``, ``mask_email``,
  ``build_account_link_url``, ``account_link_mail_eligibility``,
  ``mail_language_for`` and ``clean_display_name``; the platform mail task
  ``emails.send_account_link_confirmation(user_id, token, host,
  connection_name, organization_name)`` runs on the EMAILS queue (not an
  extended task). Public standalone host routes (no login, no app shell):
  ``/lti/consent`` (slot ``LtiConsentGate``), ``/lti/link-account`` (slot
  ``LtiIdentityChoice``), ``/lti/link-confirm/[token]`` (slot
  ``LtiLinkConfirm``, prop ``token``) and ``/lti/error``. The Next
  ``/api/lti`` proxy passes the ``lti_pending`` cookie (``Path=/api/lti``)
  through in both directions.
  Staff access to linked exams (D13): ``org_groups.lti_staff_role``
  (``protected_org_ids``: on an org whose connections stay superadmin-run
  only its admins count), ``get_lti_attachment_map(_async)`` (only
  ``attached_via='lti'`` rows whose org still has an activity linked to the
  project) and ``non_lti_attachment``; the three deciders
  (``check_project_accessible``, ``get_project_access_tier``,
  ``AuthorizationService``, both lanes) give eligible staff of such an org
  the full tier on a PRIVATE exam under any org context, the participant
  tier is unchanged; under the ``private`` context (the LMS landing pages)
  the same rule opens someone else's NON-private exam to staff of an org
  that links it (``org_groups.linked_attachment_map``,
  ``get_linking_org_ids(_async)``: that org's row of any ``attached_via``);
  ``extensions.lti_protected_org_subset`` resolves the protected orgs
  fail-closed. On someone else's NON-private exam the same
  deciders, the edit and effective-role checks and the org project list drop
  the ``attached_via='lti'`` rows (stale ones included) of protected orgs
  for everyone but those orgs' admins and the row group's admins
  (``org_groups.drop_protected_lti_attachments``,
  ``get_lti_row_org_ids(_async)``). ``get_effective_project_role(_async)``
  applies the private rule too (someone else's private project: only the
  staff role of a live, unprotected LMS link, else the participant
  fallback). Share management stays with the creator
  unless a manual org row exists. The visibility PATCH keeps linking rows,
  turns a manual row of a linked org into one (with the connection's group),
  drops linking rows whose org no longer links the exam and answers 409
  ``lti_attachment_conflict`` to a group-aware re-scope of a linked org;
  ``ProjectResponse.organizations[]`` carries ``attached_via``. The project
  lists agree with those deciders: ``routers.projects.helpers.
  get_lti_staff_project_ids(_async)`` returns the LMS-linked private exams a
  user may open as such staff (the extended student exam list imports the
  async twin). ``check_user_can_edit_project(_async)`` applies the same
  private rule itself (only a live LMS link opens someone else's private
  exam, protected orgs count only their admins), and
  ``get_soft_deletable_project_ids_async`` is the one delete rule (a private
  project is its creator's alone; only manual org rows count, an LMS link
  never hands deletion to anyone) behind ``DELETE /projects/{id}``, bulk
  delete and the extended student list/detail ``can_delete`` flag.
  Accepting an organization invitation, also through email verification,
  reactivates a removed membership.
  Host route ``/lti/activity`` (slot ``LtiActivityView``, props
  ``resourceLinkId``, ``expectedUserId``, ``requestedUiMode``) is the teacher
  view.
  Names (D8): ``/auth/me``, ``/auth/me/contexts`` and the login user carry
  ``pseudonym``, ``use_pseudonym`` and ``is_lms_account`` (there: a launch
  created the account; a proof-linked account keeps its header); shared
  modules ``lms_name_masking`` (``NameVisibility``, ``lms_link_exists``,
  ``is_lms_account(_sync)``, ``is_lms_provisioned_account(_sync)``) and
  ``user_display.masked_name`` /
  ``prefers_pseudonym``; ``services/member_privacy`` masks the org member
  list, ``/organizations/manage/users``, the group roster, project members,
  the task listing, task assignments, ``created_by_name`` (list, detail,
  edit and visibility responses; ``project_name_masks`` for a whole page)
  and the export ``users`` block (a masked record carries ``"masked": true``
  and is imported by id when the account exists). Group admins see real
  names through ``reveal_group_accounts`` (their groups' connections). New API hook ``project_real_name_user_ids(db, viewer,
  project_id, user_ids)`` (the people a viewer may see by name on a project;
  project lists unmask only those). The workers (and exports in the API
  process, while the extension loader accepted the package) read the
  optional worker hook ``benger_extended.workers.get_name_visibility_fns``,
  which returns ``(privacy_protected_member_ids,
  project_real_name_user_ids)``; like the other worker hooks it is NOT in
  ``get_hooks()``. Anonymization (D16): ``services/user_anonymization``
  (``anonymize_user(_sync)``, ``anonymization_check(_sync)``,
  ``anonymization_footprint(_sync)``, ``revoke_lms_link_tokens``,
  ``is_reserved_username``; a fresh ``Anonym-<hex>`` pseudonym replaces the
  old one), the endpoints ``GET /api/admin/lti/registrations/{id}/
  anonymization``, ``GET .../user-links/{id}/anonymization``,
  ``POST .../user-links/{id}/anonymize`` and the superadmin
  ``GET|POST /api/users/{id}/anonymization|anonymize``; reactivating an
  anonymized account answers 400 ``account_anonymized``; signup refuses the
  ``lti-`` and ``anon-`` username prefixes. ``get_current_user`` returns
  None for inactive accounts (the handlers that use it answer 401), and the
  progress WebSockets refuse inactive accounts.
  Frontend contract (the extended overlay imports these): ``lib/lti/
  launchErrors`` (``LTI_LAUNCH_ERROR_CODES``, the action categories,
  ``isLtiLaunchErrorCode``, ``ltiLaunchErrorPath``; the code list mirrors the
  extended ``lti/errors.py`` page codes, and a parity test in each repo
  compares them) with the ``lti.error`` locale namespace that the host
  route ``/lti/error`` renders, and ``lib/utils/displayName``
  (``getUserDisplayName``). ``StudentModeRedirect`` honours the one-shot
  ``lti_ui=student|expert`` parameter next to ``lti_u`` / ``rl``, and
  ``AuthContext`` skips the last-org subdomain redirect while ``lti_u``,
  ``rl`` or ``lti_ui`` is in the URL. Worker-side,
  ``immediate_eval_dispatch`` exports ``BILLING_BLOCK_KEY`` and
  ``normalize_billing_block``, and ``auth_module.org_scope`` exports
  ``load_org_admin_scope_sync``.
- 2.21: project read access is context-free. ``check_project_accessible``,
  ``get_project_access_tier`` and ``AuthorizationService`` (both lanes)
  decide from every active org membership; the ``org_context`` parameter
  stays for call-site symmetry and is ignored (the selected organization
  used to be a read boundary and demoted staff of a started exam to the
  participant tier from the private context). ``get_accessible_project_ids
  (_async)`` returns the union over all memberships (``_pick_member_org_
  projects``: eligibility, foreign-private, ANNOTATOR exam and archive
  carve-outs, protected LMS orgs) and never raises for the header org; the
  project list sets ``effective_role`` per row and both list and detail
  carry the new ``ProjectResponse.can_edit`` (``resolve_project_roles_
  batch_async``). Removed: ``org_groups.linked_attachment_map``,
  ``get_linking_org_ids(_async)`` and the private-context deciders. A
  generation run resolves the org whose keys it spends from the project
  (``org_resolution.resolve_dispatch_org_for_project_async``), not from the
  header.

2.22 (2026-09-22): the selected organization of the client is retired.
  ``POST /api/projects/`` takes the target ``organization_id`` in the body
  (private when absent); ``/api/users/api-keys/available-models`` takes
  ``project_id`` (dispatch org of that project) or ``organization_id``
  (creation target) as query parameters; ``require_org_admin`` /
  ``require_org_contributor`` need an explicit org id; the
  ``OrgContextMiddleware`` (``request.state.organization_context``) is
  gone. ``X-Organization-Context`` is still accepted and ignored.

2.23 (2026-09-23): the inert ``org_context`` parameters are removed.
  ``check_project_accessible(_async)``, ``get_project_access_tier(_async)``,
  ``get_accessible_project_ids(_async)``,
  ``AuthorizationService.check_project_access(_async)`` and
  ``org_groups.lti_staff_role`` no longer take it, ``ProjectAccess`` drops
  its ``org_context`` attribute, and ``get_org_context_from_request`` is
  gone. ``X-Organization-Context`` is no longer in the CORS
  ``allow_headers``. ``POST /api/projects/project-imports`` takes the target
  ``organization_id`` in the body (org-less imports are private). Extended
  callers must stop passing the argument.

2.24 (2026-09-24): the legacy ``project_members`` table is dropped
  (migration 108) and ``project_models.ProjectMember`` is removed. Project
  roles come from organization memberships only. Project export no longer
  writes members (``statistics.total_members`` stays 0), import skips the
  rows of older exports (``"project_members": 0`` in the result), and
  ``stream_io.serialize_project_member_row`` is gone. Extended code must not
  import ``ProjectMember``.

2.25 (2026-09-24): Safe Exam Browser support. ``Project.seb_required`` and
  ``Project.seb_config`` (migration 109), the pure verifier ``/shared/seb.py``
  and the guards ``enforce_seb`` / ``enforce_seb_async`` in
  ``routers.projects.helpers`` (called by the platform exam endpoints; the
  extended timer and student-exam routes call them too).
  ``ProjectResponse.seb_required`` is exposed read-only; the extended edition
  owns the settings endpoint that writes both columns.

2.26 (2026-10-02): monitoring hooks (extended issue #125). The optional
  package-level ``benger_extended.configure_app(app)`` is called once after
  the extended routers are included (``extensions.configure_app``; for
  middleware such as HTTP metrics). The optional API hook
  ``on_ops_event(event, **labels)`` receives ``mail_outcome`` (``mail_type``
  verification or password_reset, ``outcome`` sent or failed) from the
  API's inline mail and ``health_check_failed`` (``dependency`` redis,
  database or celery) from ``/health``, through
  ``extensions.emit_ops_event``. Worker mail is observed through Celery
  signals. The api image carries ``prometheus-client`` for the extended
  metrics endpoint.

2.27 (2026-10-02): the feature flag system moves to the extended edition.
  ``feature_flags`` gets ``state`` (``off``, ``everyone`` or ``allowlist``)
  in place of ``is_enabled``, loses ``configuration`` and has a nullable
  ``created_by`` (``ON DELETE SET NULL``); the new ``feature_flag_targets``
  table holds the allowlist (exactly one of ``user_id`` and
  ``organization_id`` per row). Models ``FeatureFlag`` and
  ``FeatureFlagTarget`` (migration 110, which also deletes the retired core
  flags). The platform ``/api/feature-flags`` router,
  ``FeatureFlagService``, ``init_feature_flags`` and
  ``Permission.FEATURE_FLAG_MANAGE`` are removed; the extended edition
  serves ``/api/ext/feature-flags``. ``EmailService()`` no longer takes
  ``check_feature_flag``. The frontend drops its flag context and gates;
  ``/admin/feature-flags`` renders the ``FeatureFlagsAdmin`` slot.

2.28 (2026-10-06): per-group roles. ``OrganizationGroupMembership.role``
  (OrganizationRole, NOT NULL) replaces ``is_group_admin`` and
  ``Invitation.group_role`` (nullable, set iff ``group_id``) replaces
  ``invited_as_group_admin`` (migration 111, backfill keeps every effective
  right; ``ImportJob.organization_group_id`` added). In
  ``shared/org_groups``: ``get_user_group_context(_async)`` return
  ``{group_id: 'ORG_ADMIN'|'CONTRIBUTOR'|'ANNOTATOR'}``; the new pure
  ``attachment_role(group_id, org_role, user_groups)`` is the one rule (org
  role on an org-wide attachment, ORG_ADMIN for org admins, else the group
  role, else None); ``attachment_eligible`` keeps its signature;
  ``grants_full_tier(project_kind, role)`` takes the attachment role (two
  arguments); ``ROLE_RANK``, ``best_role``, ``role_at_least``;
  ``build_select_admin_group_ids(user_id, organization_id=None)`` is the
  group-admin scope of every gate (group role ORG_ADMIN, active group,
  active org membership) and ``build_select_group_admin_ids(group_id)``;
  ``lti_staff_role`` / ``drop_protected_lti_attachments`` keep their
  signatures on the new ``user_groups`` shape. The best role over all
  eligible attachments wins everywhere. HTTP: group list items carry
  ``my_role``; group member rows ``role`` (POST ``{user_id, role}``, PATCH
  ``{role}``); org roster ``groups[].role``; ``/auth/me/contexts``
  ``organizations[].groups[].role``; invitations take ``group_role`` with
  ``group_id`` (group admins invite with org role ANNOTATOR only) and an
  existing member of a group-scoped invite is added to the group
  (``added_to_group`` / ``already_in_group``, bulk ``added_to_group``
  count); the create-new import takes ``organization_group_id``; removing
  an org member deletes their group rows in that org. ``lti_admin``: a
  group admin may grant up to ``org_admin`` (group Admin) on a group-scoped
  connection.

2.29 (2026-10-06): LTI links bound to single tasks or to a whole
  collection (issue #122), migration 112.
  ``LtiResourceLink.task_id`` (nullable FK ``tasks.id`` ON DELETE SET NULL,
  index ``ix_lti_resource_links_task``; links on exams with exactly one task
  are backfilled). ``LtiResourceLink.grade_scope`` (String(16) NOT NULL,
  default ``'exam'``, CHECK ``ck_lti_resource_links_grade_scope`` in
  ``exam | task | collection``; backfilled ``'task'`` where ``task_id`` is
  set): ``exam`` is the legacy whole-exam link (only valid while the exam
  has one task), ``task`` grades ``task_id`` only (NULL ``task_id`` there
  means the task was deleted), ``collection`` has one gradebook column per
  task and NULL ``task_id``. ``LtiGradeSync.task_id`` (nullable FK
  ``tasks.id`` ON DELETE CASCADE, index ``ix_lti_grade_syncs_task``): the
  task column a row feeds, NULL for the activity's own column.
  ``uq_lti_grade_sync`` keeps its name and becomes ``UNIQUE NULLS NOT
  DISTINCT (resource_link_id, user_id, kind, task_id)``; upserts target it
  with ``on_conflict_do_*(constraint="uq_lti_grade_sync")``. New
  ``LtiTaskLineitem`` (``lti_task_lineitems``: resource_link_id and task_id
  FKs ON DELETE CASCADE, ``kind`` final | ai, ``lineitem_url``, ``status``
  ready | unavailable | error | deleted, ``error``; unique
  ``uq_lti_task_lineitem`` on (resource_link_id, task_id, kind), indexes
  ``ix_lti_task_lineitems_resource_link`` and ``ix_lti_task_lineitems_task``).
  Schemas: ``LtiResourceLinkTaskRead{id, inner_id}``; ``LtiResourceLinkRead``
  and ``LtiResourceLinkAdminRead`` carry ``grade_scope``, ``task_id`` and
  ``task``; the admin ``GET /registrations/{id}/resource-links`` rows fill
  them. ``LtiGradeSyncRead`` carries ``task_id``; the admin ``GET
  /grade-syncs`` rows (and the retry answer) carry ``task {id, inner_id}``.
  The import block (``linked_exam_stmt``, ``_enforce_linked_exam_task_limit``,
  the API's 422 ``multi_task_unsupported``) applies only to exams with at
  least one ``grade_scope = 'exam'`` link; task and collection links accept
  imports.

2.30 (2026-10-07): uploaded solution files (extended issue #149), migration
  113. New ``SubmissionFile`` (``submission_files``: ``project_id``,
  ``task_id``, ``user_id`` FKs ON DELETE CASCADE; ``uploaded_by`` and
  ``annotation_id`` FKs ON DELETE SET NULL; ``storage_key``,
  ``original_filename``, ``content_type``, ``size_bytes``, ``sha256``,
  ``source_format`` pdf | docx | text, ``extracted_chars``,
  ``replaced_result`` JSONB, ``created_at``; indexes
  ``ix_submission_files_task_user`` (task_id, user_id, created_at) and
  ``ix_submission_files_project``). New
  ``routers.projects.annotations.persist_annotation_submission(db, *, task,
  project, user_id, annotation)``: the persistence half of the annotation
  POST (duplicate guard, limits, counters, draft cleanup,
  ``on_annotation_created``, assignment completion, report refresh) without
  its access, window and SEB checks.

2.31 (2026-10-07): scores-by-project views. New
  ``GET /api/leaderboards/llm-models/{model_id:path}/projects?period=``
  (one model across the caller's readable projects; the per-model routes
  accept slashes in ids); ``aggregate_summaries.aggregate_model_project_rows``
  and the ``_leaderboard_src_sql`` / ``_leaderboard_bucket_stats_sql`` /
  ``_leaderboard_rollup_sql`` builders. Frontend: shared
  ``components/shared/ProjectScoresDialog`` (``ProjectScoreRow``,
  ``ProjectScoreCell``, ``ScoresPeriod``), the project x metric dialog the
  model catalog uses and the extended annotator leaderboard reuses.

2.32 (2026-10-08): first-visit onboarding + exam Bundesland. Migration 114
  adds ``users.exam_bundesland`` (two-letter state code, written through
  ``PUT /api/auth/profile``, validated by the ``Bundesland`` Literal) and
  ``users.onboarding_state`` (JSON). New ``PUT /api/auth/me/onboarding``
  (``OnboardingStateUpdate``: ``setup_completed_at``, ``setup_skipped``,
  ``tours`` {tier: version}, ``reset_tours``; deep-merged). Both fields ride
  on /auth/me[/contexts]. Frontend: the ``GlobalOnboarding`` slot (rendered in
  both shells by ``Layout``), ``data-tour`` anchors on the expert navigation
  links (``nav-<path>``) and the account menu (``account-menu``),
  ``apiClient.setOnboardingState``, the ``BUNDESLAENDER``
  codebook (``lib/profile/bundeslaender.ts``) and the ``driver.js`` dependency.

2.33 (2026-10-08): who pays per group. Migration 115 adds
  ``organization_groups.require_private_keys`` (nullable Boolean; NULL =
  follow the org's ``settings.require_private_keys``). New ``org_groups``
  helpers ``effective_require_private_keys(org_settings, group_override)``,
  ``require_private_keys_for[_async](db, org_id, group_id=None)`` and
  ``org_pays_for_project(db, org_id, project=None)``; key resolution, provider
  availability, the BYOM org-credential fallback and the extended billing
  policy read the effective value for the project's attachment group. A
  paying group spends its own key, then the org-wide key.
  ``GET/PUT /api/organizations/{id}/api-keys/settings`` take ``group_id``
  (group scope: org admins and that group's admins; ``null`` = follow the
  org). ``get_available_providers_for_context[_async]`` and
  ``resolve_custom_model_credentials_async`` take ``project_id``.

2.34 (2026-10-09): grading steps after submit, separate from the reference.
  Migration 116 adds ``projects.annotator_step_detail_after_submit``
  (nullable Boolean; NULL = follow ``annotator_full_visibility_after_submit``)
  on ProjectUpdate/ProjectResponse and the project export/import. New shared
  module ``solution_reveal`` (``reference_revealed(project)``,
  ``step_detail_revealed(project)``) and the pure
  ``rubric_structure.structure_without_guidance`` /
  ``criteria_without_guidance`` (a sheet without step hints and section
  notes). ``blinding.step_detail_task_ids_async`` /
  ``submitted_task_ids_async``; the task-rubrics reads serve a submitter the
  bare outline when only the steps are revealed. The extended student,
  Korrektur and immediate-evaluation reads import both shared modules.

2.35 (2026-10-09): the result of each task in "Meine Aufgaben". New hook
  ``task_grade_summaries_for_user(db, project_id, user_id, task_ids)``
  (``extensions.task_grade_summaries_for_user``; ``{}`` in the community
  edition and when the hook fails); ``GET /projects/{id}/my-tasks`` returns
  it per row as ``grade_summary`` (headline values only, null without a
  submission). The frontend slot ``MyTaskRowResult`` renders it in the row;
  the ``MyTasksResultCard`` slot is gone.

2.36 (2026-10-10): writing-page presence. Migration 117 adds
  ``task_work_presence`` (model ``project_models.TaskWorkPresence``: one row
  per task and user with ``started_at``, ``last_seen_at``, ``visible``,
  ``ended_at``; written by the extended edition only). Frontend extension
  point ``registerWritingPresenceReporter(fn)`` (``lib/extensions``):
  ``useServerDraftSync`` calls the reporter on ticks without a change, on
  mount and on tab hide/show; none is registered in the community edition.
  New slots ``project-editor-actions`` (Quick Actions for the project's
  editors only) and ``ProjectLivePage`` (``/projects/[id]/live``). The draft
  and checkpoint endpoints run in the threadpool and the draft save is one
  upsert; ``on_draft_saved`` now runs after that upsert's commit.

2.37 (2026-10-13): N-package extension registry. New shared module
  ``extension_registry`` (``services/shared/extension_registry.py``) loads
  every package named in ``BENGER_EXTENSIONS`` (ordered, default
  ``benger_extended``) in order; ``BENGER_REQUIRE_EXTENSIONS`` names the
  packages that must load (unset: the legacy ``BENGER_REQUIRE_EXTENDED``
  requires all of them). Per package: namespace guard,
  ``COMPATIBLE_CORE_VERSIONS`` handshake, then the ``REQUIRES_EXTENSIONS``
  check (``{package: [EXTENSION_API_VERSION, ...]}``; the dependency must be
  loaded earlier). New optional overlay attributes: ``EXTENSION_ID`` (short
  id, default name without ``benger_``), ``EXTENSION_API_VERSION``,
  ``REQUIRES_EXTENSIONS``, ``get_task_queues()`` (``{task: queue}``, fed into
  ``celery_queues.register_task_queue`` with the package as owner; new
  packages own ``<EXTENSION_ID>.*`` task names), ``get_api_scopes()`` and
  ``get_v1_routers()`` (collected by ``extensions.get_api_scopes_all`` /
  ``get_v1_routers_all``, no platform caller yet). ``extensions.HOOK_SPECS``
  publishes every hook key with its merge policy (CALL_ALL,
  CALL_ALL_ISOLATED, UNION, DICT_FIRST_WINS, SINGLE_OWNER); the keys
  ``on_submission_finalized`` (CALL_ALL), ``assessment_transition`` and
  ``external_run_policy`` (SINGLE_OWNER) are reserved without a caller
  (``extensions.PENDING_HOOK_KEYS``). ``extensions.load_extended()`` loads
  all packages (``_extended`` stays the alias of ``benger_extended``),
  ``extensions.include_extension_routers(app)`` mounts their routers:
  packages other than ``benger_extended`` must mount under
  ``/api/ext/<EXTENSION_ID>``, a route two packages claim fails startup for
  a required package (``BENGER_EXTENSION_ROUTE_POLICY=error``, the
  default). ``extensions.is_loaded(name)`` replaces peeking at
  ``_extended``. The workers loop over the loaded packages
  (``register_evaluators`` / ``register_metric_handlers`` /
  ``register_tasks`` under ``extension_registry.owner``), and the worker
  getters (``get_grading_dispatch_policy_fn``, ``get_batch_evaluation_policy_fn``,
  ``get_grading_finalize_fn``, ``get_notification_brand_host_fn``,
  ``get_grading_block_fn``, ``get_name_visibility_fns``) are resolved through
  ``extension_registry.worker_attrs`` / ``first_worker_attr``. The LLM
  catalog loader merges every package's ``get_llm_models_yaml_path()``. The
  classifier-rule, metric-handler and evaluator registries record the
  registering package and log replacements. Helm: ``overlays.<name>``
  (``enabled``, ``package``, ``required``, ``order``, ``api.env``,
  ``workers.env``) renders the two env vars and the per-overlay env.
  API keys (benger-compliance #3). Migration 118 adds ``api_keys``
  (``models.ApiKey``: hashed ``bgr_<live|test>_<kid>_<secret>`` keys owned by
  a user or an organisation, scopes, project allowlist, expiry, revocation,
  per-key limits), ``api_key_usage_events`` (``models.ApiKeyUsageEvent``,
  append-only usage log, retention via ``tasks.cleanup_api_key_usage_events``)
  and ``users.is_service_account`` (one hidden service-account user per org
  key; excluded from people lists, notifications and login). Keys are
  accepted only on ``/api/v1/*`` and health (``auth_module.principal``,
  ``services.api_key_service``); ``require_user`` / ``get_current_user`` /
  ``optional_user`` resolve them first and set ``request.state.principal``;
  ``require_superadmin`` refuses key principals. Scope vocabulary in
  ``app.core.scopes`` (``register_scopes`` is fed from every package's
  ``get_api_scopes()`` by ``extensions.load_extended``); ``routers/v1/_deps``
  provides ``require_scope`` / ``v1_project_access`` and the startup audit
  ``assert_v1_routes_scoped``. Management routes under
  ``/api/organizations/{org_id}/access-keys``, ``/api/users/me/access-keys``,
  ``/api/admin/access-keys`` and ``GET /api/access-keys/scopes``. New
  settings: ``API_KEY_PEPPER``, ``API_KEY_ENVIRONMENT``,
  ``API_KEY_DEFAULT_RPM`` / ``_RPD``, ``API_USAGE_RETENTION_DAYS``,
  ``API_USAGE_IP_MODE``, ``SERVICE_ACCOUNT_EMAIL_HOST``.

2.38 (2026-10-14): French UI and the shared translation catalog. Frontend
  module ``@/lib/i18n/locales`` (``Locale`` = de | en | fr, ``LOCALES``,
  ``intlTag``, ``dateFnsLocale``) and ``@/lib/i18n/catalog``
  (``registerTranslations(source, {de, en, fr})`` merges an overlay's locale
  trees into the catalog, ``TranslationBundle``, ``lookup``,
  ``translateKey``). ``t(key, vars?)`` no longer takes an inline default:
  every string lives in a locale catalog. How-to guides and changelog
  entries carry ids only; their copy lives under ``howToGuides.<id>`` /
  ``howToCategories.<id>`` and ``changelogEntries.<id>``.
  Access keys and ``/api/v1`` are gated (unreleased): the SINGLE_OWNER
  hook ``public_api_enabled(db: AsyncSession, user, *, organization_id)``
  (sync or async) decides per caller, ``PUBLIC_API_ENABLED`` (default off)
  without an implementation; key management, the platform and overlay v1
  routers answer 404 ``feature_disabled`` while it is closed, and
  ``GET /api/access-keys/availability`` returns ``{"enabled": bool}`` for
  the frontend's entry points.

2.39 (2026-10-18): state-specific exam interfaces. ``ExamLayoutPrefs``
  (``users.exam_layout_prefs``, ``PUT /auth/me/exam-layout``) gains mode
  ``"state"`` with ``state_code`` (a Bundesland, required for that mode) and
  ``state_ui`` (``align``, ``hide_time``, ``theme``, ``spellcheck``). The
  frontend contract (``@/lib/labelConfig/examLayout``) adds ``ExamChrome`` /
  ``HostExamChrome``: in state mode ``useModernExamLayout`` reports
  ``state: true``, hosts hide their own header and pass ``examChrome``
  (``renderTimer(variant)``, ``onLeave``, ``extra``, ``title``) to
  ``DynamicAnnotationInterface``, which drops its action bar and hands the
  ModernExamLayout slot ``chrome`` incl. ``onSubmit``. The TimerIntegration
  slot receives ``variant: "default" | "state"``.

2.40 (2026-10-19): Korrektur reservations. New table
  ``korrektur_reservations`` (migration 119, model
  ``project_models.KorrekturReservation``): one row per (user, metric,
  target) while a grader has that annotation or generation open in the
  grading modal, with a heartbeat-refreshed ``last_seen_at``. Written by the
  overlay to keep a second grader away from the last free slot of a target
  with a grader cap; the platform only owns the schema.

2.41 (2026-10-19): jurisdiction-specific project types and score-less judges.
  ``organizations.settings.jurisdiction`` (``"DE"`` | ``"FR"``, default DE;
  shared ``org_jurisdiction``) is reported per organization by
  ``/auth/me/contexts`` and set via ``PUT /organizations/{id}/jurisdiction``.
  Frontend: ``registerWizardProjectType({id, kind, icon, nameKey,
  descriptionKey, templateId?, jurisdictions?, preset?})`` adds options to
  the wizard's project-type picker next to the three base kinds;
  ``RegisteredWizardTemplate.jurisdictions`` limits a template the same
  way (``@/lib/jurisdiction``). Workers: ``benger_extended.workers.
  get_inline_judge(metric)`` returns a judge with ``compute`` /
  ``build_row`` / ``evaluate_single`` that the bulk cells and the
  immediate lane call instead of the generic score parser
  (``evaluation/inline_judges.py``). A score-less result carries
  ``value: None`` and ``details.feedback_only: true``; the evaluation
  planner counts it as evaluated (``_row_has_score``).

2.42 (2026-10-19): runtime switch for extension packages. The flag engine
  is back in the platform: ``services/shared/feature_flags`` (``registry``:
  ``FlagDefinition``, ``STATE_*``, ``register_flags(owner, flags)``,
  ``all_flags``, ``flag``, ``flag_owner``, ``PLATFORM_OWNER``,
  ``register_master_flag``; ``service``: ``load_snapshot[_sync]``,
  ``evaluate_all_for[_sync]``, ``is_enabled_for[_sync]``,
  ``public_api_enabled``; ``worker``: ``flag_enabled_sync``,
  ``feature_disabled_result``) and ``services/api/feature_flags/deps.py``
  (``require_feature_flag``, ``feature_disabled_error``,
  ``require_extension_active``). Routes ``/api/feature-flags`` (``GET /me``
  answers anonymous callers with ``{flags, extensions}``; superadmin list,
  PUT, targets and ``DELETE /{name}`` for unregistered rows) plus the old
  ``/api/ext/feature-flags`` for one release. ``public_api`` is a platform
  flag (default from ``PUBLIC_API_ENABLED``); the hook stays as an override.
  The registry sync no longer deletes rows nobody registered (admin GET marks
  them ``registered: false``); Redis key ``feature_flags:snapshot``. Every
  loaded package gets a master flag ``extension.<EXTENSION_ID>`` (owner: the
  package; default ``DEFAULT_RUNTIME_STATE``, else ``everyone`` for
  benger_extended and ``off`` for the others), and a flag owned by a
  package evaluates as master AND flag. ``extension_activation`` decides per
  request/task context (``ExtContext``, ``use_context``,
  ``extension_active``, ``package_active``) with gating classes ALWAYS /
  POLICY_GLOBAL / GATED: ``extensions.HOOK_GATING`` (every hook key) and
  ``extension_registry.WORKER_ATTR_GATING`` (worker getters); package
  routers and v1 routers answer 404 ``{"code": "feature_disabled", "flag":
  "extension.<id>"}`` while inactive, except the ``(METHOD, path)`` pairs in
  the optional package attribute ``UNGATED_ROUTES`` (an unknown entry fails
  startup for a required package). Metrics registered while a package
  imports carry it as owner (``register_extended_metrics``); the API lists
  and the workers run them only while the owner is active. Celery messages
  carry the header ``benger_ext_ctx`` = ``{user_id, project_id}``.

2.43 (2026-10-23): margin notes move to the extended edition. The rubric
  judge asks the worker getter ``<package>.workers.get_judge_notes()``
  (gating class gated, ``ml_evaluation/judge_notes.py``) for a notes
  provider (``enabled``, ``schema``, ``schema_cost``, ``rubric_rules``,
  ``finalize``) and writes ``annotations`` only with one; the platform no
  longer ships ``ml_evaluation/margin_notes.py`` nor registers the
  ``margin_notes`` flag (the overlay does, the row keeps its state).

2.44 (2026-10-30): ``korrektur_feedback``, the human Korrektur of the
  French exam types on the barème /20, is a human-graded metric:
  ``HUMAN_GRADED_METRICS`` lists it (so ``get_or_create_human_eval_run``
  accepts it and the results read endpoints accept its runs) and migration
  122 adds its partial unique index
  ``uq_human_eval_run_per_project_metric_feedback``. Its note /20 lives in
  ``details.grade`` (never ``grade_points``), so the Notenschlüssel
  recompute leaves it alone; ``report_snapshot`` names it.

2.45 (2026-10-30): access keys on the full API. Besides ``/api/v1``, every
  route now accepts access keys through its rule in
  ``services/api/app/core/key_routes.py`` (``KeyRule``: pattern, methods,
  scopes or never, ``neutral``, ``bind``), checked by
  ``middleware/key_gate.py``; the auth dependencies read the gate's user
  from ``request.state.key_gate_user``. Platform routes without a rule fail
  startup (``assert_key_routes_covered``). Overlays declare rules for their
  own routes with the optional package attribute ``get_key_route_rules()``
  (``KeyRule`` objects or dicts ``{pattern, scopes, methods?, neutral?,
  bind?}``) and may map extra path parameters to project resolvers with
  ``get_key_project_params()`` (``{param: kind}``, for its own routes only, kinds ``project``,
  ``task``, ``annotation``, ``evaluation_run``, ``response_generation``,
  ``report``, or one added via ``middleware.key_gate.
  register_project_resolver``); routes of an overlay without rules stay
  closed to keys. New scopes ``account:read/write``, ``org:manage``,
  ``projects:write``, ``tasks:write``, ``annotations:read/write``,
  ``models:read/manage``, ``files:read/write``, ``admin:platform`` (grantable
  values ``org_admin_role``, ``superadmin``); organization keys may carry
  the role ORG_ADMIN; a key keeps its owner's superadmin rights only with
  ``admin:platform``. ``GET /api/v1/reference`` documents the full API.

2.46 (2026-10-31): hook key ``before_annotation_write`` (CALL_ALL, gating
  class ALWAYS, ``extensions.before_annotation_write(db, task_id, user_id,
  project_id, annotation_id=None, is_update=False)``, the last two passed as
  keyword arguments). The annotation routers call it for HTTP clients
  BEFORE a write, after their access, assignment, window and SEB checks:
  ``POST /tasks/{task_id}/annotations`` (``create_annotation``, sync
  session, ``annotation_id`` None) and ``PATCH /annotations/{id}``
  (``update_annotation``, a sync session via ``AsyncSession.run_sync``,
  ``is_update`` True), inside ``use_context(project_id=...)``. An
  implementation refuses by raising ``extensions.AnnotationWriteRejected(
  detail, status_code=409)``, which the routers answer as an HTTP error with
  that status and detail; any other exception propagates and fails the
  write. The server-side timer auto-submit and other callers of
  ``persist_annotation_submission`` do not call it.

2.47 (2026-11-02): project setting ``allow_external_paste`` (migration 123,
  ``projects.allow_external_paste`` NOT NULL, default TRUE; on
  ``ProjectResponse`` / ``ProjectUpdate`` and in project export/import).
  False forbids pasting text copied outside BenGER while annotating. The
  frontend hook ``@/hooks/useExternalPasteGuard`` (``useExternalPasteGuard(
  enabled, onBlocked)``) enforces it; the labeling interface mounts it, and
  overlays with their own answer surfaces mount it there. Also project
  setting ``allow_solution_upload`` (migration 124, NOT NULL, default TRUE,
  same schemas and round trip): persistence only, the overlay that offers
  answer uploads enforces it. Slot ``project-settings-interface-extra``
  (props ``settings``, ``onSettingsChange``, ``editing``) renders overlay
  checkboxes directly below the paste switch in Annotationsablauf &
  -verhalten.

2.48 (2026-11-02): handwritten solution uploads (migration 125).
  - ``shared.ai_services.attachments``: ``Attachment(mime_type, data,
    filename)`` and ``generate_with_attachments(service, prompt, attachments,
    *, model_name, ...)``. Anthropic, OpenAI (chat completions) and Google
    read images and PDFs (``SUPPORTS_ATTACHMENTS``); any other provider is
    refused with ``UnsupportedAttachmentError`` instead of silently dropping
    the pages.
  - ``shared.page_documents``: ``sniff_page_format``, ``classify_pdf_pages``
    (text-layer vs scanned pages), ``pdf_subset``, ``pdf_page_count``,
    ``normalize_photo`` (HEIC, EXIF rotation, downsizing). Workers now ship
    pdfplumber, pypdfium2, Pillow and pillow-heif.
  - Table ``submission_ocr_jobs`` (model ``SubmissionOcrJob``; mode own |
    on_behalf | pending, ``user_id`` NULL only for pending; ordered
    ``page_keys``), ``submission_files.ocr_job_id`` + ``page_index``, and
    ``projects.handwriting_ocr_enabled`` (NOT NULL, default FALSE) +
    ``projects.handwriting_ocr_model`` (override, NULL = the organization's
    default); both on ``ProjectResponse`` / ``ProjectUpdate`` and in
    export/import.
  - ``shared.org_ocr``: the organization default lives in
    ``organizations.settings.handwriting_ocr_model``, set by
    ``PUT /organizations/{id}/ocr-model`` (org admins; active official
    multimodal model or null); ``effective_ocr_model(db, project)``.
  - ``shared.annotation_submission``: ``persist_submission(db, *, task,
    project, user_id, fields, was_cancelled=False, auto_submitted=None)``,
    the persistence core of ``persist_annotation_submission`` (advisory
    lock, update in place, maximum-annotations limit as
    ``MaximumAnnotationsReached``, counters, draft cleanup, race fallback),
    now usable from workers; ``complete_assignment(...)``.
  - Frontend slot ``OrgOcrModelPanel`` (props ``organizationId``,
    ``organizationName``, ``settings``, ``open``, ``onOpenChange``,
    ``onSaved``), opened from the organization's "Mehr" menu for org admins.
  - ``project_models.attach_ocr_job_to_user(db, job, user_id)`` gives a
    pending job its person (creates the ``submission_files`` rows, mode
    becomes on_behalf; does not commit or persist the annotation).
  - Celery: new queue ``ocr`` (own worker pool ``workerPools.ocr``, compose
    ``worker-ocr``) for ``tasks.ocr_handwritten_submission`` and
    ``tasks.ocr_finalize_submission``, 600/660 s.

2.49 (2026-11-02): solutions for people who are not on BenGER yet.
  Migration 126 adds ``pending_submission_uploads``
  (``project_models.PendingSubmissionUpload``, ``PENDING_UPLOAD_OPEN_STATUSES``):
  an upload parked until the invitee joins. Hook key
  ``after_invitation_accepted`` (CALL_ALL_ISOLATED, gating class ALWAYS,
  ``extensions.after_invitation_accepted(db, invitation, user_id)``), called
  after the commit on every invitation consumption path (accept endpoint,
  signup with token, automatic acceptance on verification); implementations
  own their commit, failures are logged and rolled back. Invitation helpers
  in ``routers.invitations``: ``invite_or_reuse(db, *, inviter,
  organization, email, group_id=None, host=None) -> (Invitation, created)``,
  ``add_existing_user(db, *, actor, organization, user_id, group_id=None)
  -> 'member' | 'added_to_group' | 'added_to_org' | 'needs_invitation'``,
  ``pending_invitation(db, organization_id, email)``,
  ``queue_invitation_mail(...)``; invitations are valid for
  ``INVITATION_VALIDITY_DAYS`` = 90 days (was 7).

2.50 (2026-11-02): exam tools (Hilfsmittel), tool providers, synced content.
  Migration 127 adds ``projects.exam_tools`` (JSONB, NULL = never chosen;
  read-only on ``ProjectResponse``; travels through export/import via
  ``exam_tools.portable_exam_tools``, which drops ``connection_id`` at any
  depth) and the tables ``tool_providers`` (``models.ToolProvider``, incl.
  OAuth client columns and ``supports_student_links``),
  ``org_tool_provider_connections`` (``models.OrgToolProviderConnection``,
  Fernet ``encrypted_credential``, ``last_sync_*``),
  ``user_tool_provider_links`` (``models.UserToolProviderLink``, Fernet OAuth
  tokens, ``last_sync_*``), ``tool_bundles`` / ``tool_bundle_items``
  (``models.ToolBundle`` / ``models.ToolBundleItem``, deduplicated by content
  hash, GIN full-text index ``ix_tool_bundle_items_search``),
  ``tool_entitlements`` (``models.ToolEntitlement``, exactly one owner: link,
  org connection or built-in provider), ``exam_tool_pins``
  (``models.ExamToolPin``) and ``exam_tool_notes``
  (``project_models.ExamToolNote``, one per task and user, not exported).
  ``ExamLayoutPrefs.tool_placements`` (per tool id: zone left / right /
  float / hidden, order, float box in viewport percent).
  Frontend: ``ExamChrome.renderTools(variant)`` (host-supplied like
  ``renderTimer``; the classic render shows the 'default' variant, the
  modern layout renders the 'modern' variant inside its own layout context,
  a state interface places the 'state' variant itself). Slots:
  ``ExamToolDock`` (props ``variant``, ``projectId``, ``taskId``,
  ``examTools``), ``project-exam-tools`` (props ``project``, ``onRefresh``;
  project page after ``project-exam-security``), ``OrgToolProvidersPanel``
  (same props as ``OrgOcrModelPanel``, behind flag ``exam_tools``) and
  ``profile-tools-extended`` (profile page). Celery tasks
  ``tasks.exam_tools_sync_law_texts``, ``tasks.exam_tools_sync_link``,
  ``tasks.exam_tools_sync_org_connection``, ``tasks.exam_tools_nightly_sync``
  and ``tasks.exam_tools_gc_bundles`` route to maintenance.

2.51 (2026-11-11): requirements of a step, and grading per requirement.
  A step node of a Bewertungsbogen structure may list ``requirements``
  (``{text, points, standard, element}``; half-point BE that add up to the
  step's ``max_score``; ``standard`` null or ``"folgerichtig"``, ``element``
  null or ``"definition"``). ``rubric_structure``: ``step_requirements``,
  ``requirement_lines``, ``has_requirements``,
  ``checklist_spec_from_structure``, ``stored_checklist_spec``,
  ``rubric_checklist_spec``,
  ``REQUIREMENT_STANDARD_RULE`` / ``REQUIREMENT_DEFINITION_RULE`` (the
  closing sentences of an outline rendering) and
  ``rubric_prompt_text(..., alternatives="branch" | "replace")``. The
  Bewertungsbogen judge grades a sheet per requirement in every lane when
  every step of its outline lists requirements
  (``LLMJudgeEvaluator.bind_task_rubric(rubric, margin_notes, score_unit)``;
  ``metric_parameters.rubric_score_unit``: ``"binary"`` by default,
  ``"bullet"``, or ``"step"`` for one number per step). The scoring data is
  the generator's own (``generation_metadata.checklist_spec``) while the row
  still carries the text it was rendered with, else the one built from the
  outline; a sheet without requirements in its outline keeps one number per
  step. ``ml_evaluation.checklist_scoring`` gains the score unit
  ``"binary"`` (states ``erfuellt``, ``nicht_erfuellt``,
  ``nicht_einschlaegig``, ``unsicher``; ``zitat_nicht_belegt`` set by code;
  a status word that names no state reads as ``unsicher``),
  ``binary_state``, ``requirement_worth``, ``build_schema_within`` and
  ``mock_judgment``; the judge's notes
  (``judge_notes``) and the end-to-end test mode now cover that lane too.
  Evaluation rows of such a grading carry ``details.checklist`` (with
  ``unsettled_be`` and ``not_applicable_be``; either can set
  ``assessment_status`` to ``review_required``) and
  ``details.assessment``, and each step of ``details.scores`` its
  ``anforderungen``. A row without scores keeps ``details.assessment`` when
  the judge wrote one. An edit of a generated sheet's outline drops
  ``generation_metadata.checklist_spec`` and ``rendered_text_replace``
  together with ``rendered_text``; an edit that leaves the outline as it is
  keeps them, and every new version keeps ``contract_version`` and
  ``review``. The requirement lane owns its prompts
  (the grading template of a project's config is not used there);
  ``rubric_judge_prompts.requirement_judge_prompts()`` serves them to
  readers outside the worker from ``rubric_requirement_prompts.json``, a
  file written from the worker code
  (``services/workers/scripts/write_rubric_requirement_prompts.py``, pinned
  by the workers suite).

2.52 (2026-11-11): OpenOlat, deep linking and the course roster (LTI).
  ``lti_platform_registrations.lms_family`` may be ``'openolat'`` and
  ``lti_resource_links`` gains ``context_memberships_url`` (the NRPS URL of
  the launch; migration 129). ``LMS_FAMILY_PATTERN`` allows ``openolat``.
  ``GET /api/admin/lti/registrations/{id}/tool-config`` returns
  ``deep_link_url`` (the launch URL; the extended edition answers
  ``LtiDeepLinkingRequest`` there). The frontend proxy and the Helm ingress
  let an LMS frame ``/api/lti/launch`` and ``/api/lti/deep-link`` (besides
  ``/api/lti/register/init``); the API limits framing with CSP
  ``frame-ancestors``. How-to guide ``lti-setup-openolat``.

2.53 (2026-11-16): production-ready rubric grading: generation job records,
  the check step and the edit log of grading sheets, the app version.
  - Generation jobs: table ``rubric_generation_jobs`` (migration 136;
    ``project_models.RubricGenerationJob``,
    ``RUBRIC_GENERATION_JOB_STATUSES``, ``RUBRIC_GENERATION_JOB_ENTRY_POINTS``;
    every FK ``SET NULL``, ``celery_task_id`` unique), the serializer
    ``rubric_generation_jobs.serialize_rubric_generation_job(job, *,
    project_title, task_inner_id, user_label, organization_name)``, the
    superadmin read ``GET /api/admin/rubric-generation-jobs`` (filters,
    ``total``, ``items``, ``facets``) and the slot
    ``RubricGenerationJobsAdmin`` on ``/admin/rubric-generation-jobs``.
  - Check step (migration 137): ``projects.rubric_review_required``
    (``ProjectResponse.rubric_review_required``, read-only),
    ``task_rubrics.review_state`` / ``reviewed_at`` / ``reviewed_by`` (in
    ``TaskRubricResponse``), the append-only table
    ``task_rubric_review_events`` (``project_models.TaskRubricReviewEvent``;
    a ``BEFORE UPDATE`` trigger allows only the two SET NULL actions).
    ``task_rubric_service``: ``RubricReviewRequired`` (code
    ``rubric_review_required``), raised by ``activate_task_rubric`` before
    any write when the project requires the check and the sheet is not
    ``"confirmed"`` (so also by ``create_task_rubric(status="active")`` and
    the clone of an edited active sheet; ``ensure_activation_allowed`` is
    the rule itself); the clone keeps the review fields;
    ``create_task_rubric(..., origin=)`` stores ``generation_metadata
    ["origin"]`` (an object of at most 4 KB). The platform routes answer a
    refusal with 422 ``{"code": "rubric_review_required", "rubric_id",
    "message"}``; ``TaskRubricCreate.origin``. Project export and import
    carry the new columns and the events (``rubrics`` /
    ``rubric_review_events`` per task, flat ``task_rubric_review_events`` /
    NDJSON ``task_rubric_review_event``). Slot ``ProjectRubricReviewPage``
    on ``/projects/[id]/rubric-review``.
  - ``app_version.app_version()``: the image tag from ``BENGER_APP_VERSION``
    (set by the Helm chart on the api, every worker, the beat and the
    migration job), ``None`` when unset.

2.54 (2026-11-17): exam readiness seams (no grading without a usable sheet).
  - Exam not open yet: optional worker attribute
    ``<package>.workers.get_exam_open_block_fn`` (gating class ``gated``)
    returning ``fn(db, *, project, user_id) -> None | dict | str``. The
    platform asks it in ``enforce_project_read_window(_async)`` after the
    window rule and in the ``/api/data`` scope, never on writes; editors,
    superadmins and the attempted tier pass. The guards now return the tier
    the caller must apply from then on; with the keyword
    ``allow_attempted=True`` a blocked non-editor with an own submission is
    demoted to ``TIER_ATTEMPTED`` (own submissions only) instead of refused.
    Opt in only where the attempted tier's scoping is applied to the
    returned tier; without it every blocked non-editor is refused, an own
    submission included. A block answers 403
    ``{"code": "exam_not_ready", "reason", "message", "project_id"}``
    (``helpers.EXAM_NOT_READY_CODE``; ``exam_open_block(_async)`` is the
    rule itself). A failing hook counts as open. Without a package nothing
    changes.
  - ``task_rubric_resolution`` (sync): ``resolve_grading_rubric(db, task,
    metric_parameters, *, review_required=None)`` is the one sheet lookup of
    the judge cells, the immediate grading and the dispatch
    (``evaluation.cell_evaluator._resolve_task_rubric`` delegates to it);
    ``split_held_rubric_judges``, ``RUBRIC_JUDGE_METRIC``,
    ``RUBRIC_MISSING`` (``"rubric_missing"``), ``NoUsableRubricError``.
    ``metric_parameters.rubric_selector`` picks only a sheet with
    ``review_state == "confirmed"`` when the project has
    ``rubric_review_required``.
  - Immediate dispatch: a sheet judge on a task without a usable sheet is
    not dispatched; the other configs run and the run lists the held ones in
    ``eval_metadata.held_configs``. With nothing else to grade the grading
    is blocked (``billing_block`` with ``code``/``reason``
    ``rubric_missing``, ``task_id``, ``held_configs``; error
    ``billing_blocked:rubric_missing``), which the hourly sweep retries
    without the attempt cap. ``immediate_eval_dispatch``:
    ``split_held_configs(db, project, task, configs)`` for dispatchers that
    build their own run, ``dispatch_waiting_gradings(db, task_id)`` grades
    the held answers of a task (trigger ``rubric_ready``),
    ``queue_waiting_gradings(task_id)`` queues it as the worker task
    ``tasks.dispatch_waiting_gradings`` (``interactive``), and
    ``grading_retry_state(db, project, annotation)`` says whether an
    ungraded answer is ``held``, ``retrying``, ``exhausted`` or
    ``none``.
  - Worker: the immediate grading skips a sheet judge without a usable sheet
    (``skipped_configs[].reason == "rubric_missing"``, also
    ``nothing_to_grade.reason`` when nothing else ran) instead of writing
    an error row; an error row that still says the sheet is missing (bulk
    cells, a sheet removed mid-grading) carries
    ``metrics[<metric>].error_code == "rubric_missing"``.

2.55 (2026-11-17): creation-wizard drafts (migration 141).
  - ``projects.is_wizard_draft`` (``ProjectResponse.is_wizard_draft``,
    read-only) and the table ``project_wizard_drafts``
    (``project_models.ProjectWizardDraft``: ``project_id``, ``created_by``,
    ``client_key`` unique per creator, ``target_organization_id`` /
    ``target_group_id`` (SET NULL), ``state`` JSONB with ``state_version``,
    ``step_id``, ``touched_at``, ``created_at``, ``finished_at``). A draft is
    private and has no organization rows until its finish.
  - ``project_models.project_listable()`` (not deleted and not a draft: the
    predicate of every list, count and aggregate) and
    ``project_is_wizard_draft(project)``. ``get_accessible_project_ids``
    (sync and async), the project list, the dashboard counts, the aggregate
    summaries, the v1 project list and ``/api/data`` leave drafts out; the
    per-project deciders do not, so the creator opens the draft.
  - Routes ``POST|GET /api/projects/wizard-drafts``, ``GET|PUT|DELETE
    /api/projects/{id}/wizard-draft``, ``POST .../wizard-draft/finish``,
    ``GET .../wizard-draft/tasks`` and ``PUT .../wizard-draft/tasks/{task_id}``
    (``routers/projects/wizard_drafts.py``; ``discard_wizard_draft``). The
    visibility PATCH and share-link creation answer 409 ``{"code":
    "wizard_draft"}`` on a draft (``wizard_drafts.wizard_draft_refusal``),
    ``DELETE /api/projects/{id}`` discards it, and a draft's share links do
    not resolve.
  - Key scope: while a draft has no organization rows, its target
    organization counts as the project's organization for its creator in
    ``org_resolution`` (``resolve_dispatch_org_for_project`` and
    ``billing_org_options``, sync and async; same membership and
    ``min_role`` rules), and its target group is the scope group of
    ``org_groups.resolve_project_group_for_org`` (sync and async) while the
    creator may create a project there (``user_may_scope_to_group`` and its
    new twin ``user_may_scope_to_group_async``). ``org_groups.
    wizard_draft_target(_async)`` reads the target.
  - ``project_purge.enqueue_purge_job_async`` / ``enqueue_purge_job_sync``
    (with ``active_purge_job_*``, ``supersede_if_stale_*``,
    ``PurgeQueueUnavailable``): queueing a purge, shared by the purge and
    discard routes and the worker.
  - ``wizard_drafts``: ``WIZARD_DRAFT_RETENTION`` (30 days since the last
    change), ``draft_expires_at``, ``purge_stale_wizard_drafts`` and the
    daily beat task ``tasks.purge_stale_wizard_drafts`` (queue
    ``maintenance``).
  - Frontend: ``registerWizardDraftPolicy({ applies, describeDiscard? })``
    and the draft hooks ``registerWizardDraftHook('created' |
    'tasksSynced' | 'configSynced', fn)`` (``@/lib/extensions/wizardDraft``).
    ``created`` runs once after the draft was created; ``tasksSynced`` after
    every task sync (moving past the data step, and on "Create");
    ``configSynced`` after title, label config and evaluation configs were
    written into the draft and before they are read back, every time the
    user moves to the rubric step and once more on "Create" (before the
    post-create hooks and the finish route). Draft mode applies only while a
    registered policy applies or a draft is open; otherwise the wizard
    navigates and creates as before. The policy's ``applies(wizardData)``
    is asked when the user leaves step 1; ``describeDiscard({ projectId })``
    returns extra lines for the confirmation before a draft is discarded
    (wizard footer or unfinished-drafts list), e.g. how many generated or
    checked grading sheets will be lost, and is ignored when it fails. The
    stale-draft sweep also discards a draft whose ``project_wizard_drafts``
    row is gone (it cascades away when the creator is hard-deleted).
    The rubric step slot
    ``ProjectWizardRubricStep`` gets ``draftProjectId``; post-create hooks
    get ``draft: true`` in draft mode.
  - Frontend: the policy's awaited guard ``beforeLeaveStep?({ projectId,
    fromStepId, toStepId, skippedStepIds, wizardData, confirm })``, the only
    member that can hold the wizard. In draft mode it is asked for each
    applying policy on every forward move (Next and step-dot jumps forward,
    which pass ``skippedStepIds`` without opening them; after the draft
    exists, before the move's syncs) and on "Create" (``toStepId`` null,
    before the final syncs). Resolving false keeps the user on the current
    step; a guard that throws shows its message and keeps the user there.
    ``confirm(WizardConfirmRequest)`` opens the wizard's own confirmation
    dialog. Backward moves and the wizard outside draft mode are never
    guarded; ``getApplyingWizardDraftPolicies(wizardData)`` lists the
    applying policies.

2.56 (2026-11-18): system key of a generation (no migration).
  - ``services/shared/system_profile.py``: ``parameter_profile(params)``
    (temperature, top_p, max_tokens and the reasoning knobs
    ``reasoning_effort``, ``thinking_budget``, ``thinking_token_budget``,
    ``prompt_mode``, ``enable_thinking``; never seed or run index),
    ``parameter_profile_sha256`` (SHA-256 of the sorted compact JSON) and
    ``system_key(model_id, profile)`` = ``"<model_id>@<first 12 hex>"``. A
    reasoning arm of one model is a system of its own; its repeats are not.
    The profile holds the parameters as sent for DeepInfra and as
    configured for other providers until they report what they sent.
  - ``generations.response_metadata.system`` and the run's
    ``parameters.system``: ``{key, model_id, provider, provider_model_id,
    response_model, parameter_profile, parameter_profile_sha256}``. Answers
    generated before 2.56 carry no ``system`` block.
  - Reasoning knob ``enable_thinking`` (``"on"`` / ``"off"``, a
    ``reasoning_config`` select) in a model's run config. DeepInfra sends a
    model's declared ``reasoning_effort`` or ``enable_thinking`` (as
    ``chat_template_kwargs``) with the run value or the declared default,
    and reports ``reasoning_params_sent``, ``provider_model_id`` and
    ``response_model`` in its response metadata; the worker records the
    reported knob in the run's ``parameters``.
    ``provider_capabilities.model_reasoning_config(model_id)`` reads the
    catalog declaration.

2.57 (2026-11-18): compliance records (migration 145).
  - Tables ``compliance_assessments``, ``compliance_suite_runs`` and
    ``compliance_findings`` (``models.ComplianceAssessment``,
    ``ComplianceSuiteRun``, ``ComplianceFinding``). A finding carries
    ``requirement_ref``, ``metric``, ``system_key``, ``scope``, counts,
    ``value`` / ``ci_low`` / ``ci_high`` / ``ci_level`` in double precision,
    ``ci_method``, ``threshold``, ``verdict``, ``baseline``, ``details`` and
    the ids of the analysis run and estimate it was derived from
    (``analysis_run_id``, ``analysis_estimate_id``; plain indexed ids without
    a foreign key, like ``compliance_suite_runs.analysis_run_ids`` and
    ``compliance_assessments.release_id``, until those tables exist). The
    composite key ``(suite_run_id, assessment_id)`` ties a finding to its run.
  - ``compliance_records`` (shared, pure): the assessment statuses and the
    static ``ASSESSMENT_TRANSITIONS`` table with ``transition_assessment``
    (stamps ``registered_at`` and ``thresholds_hash``, ``attested_at``), the
    suite-run statuses with ``SUITE_RUN_TRANSITIONS`` and
    ``transition_suite_run``, ``VERDICTS``, ``REGISTRATION_LOCKED_FIELDS``,
    the ``check_*`` guards (terminal assessments and finished suite runs are
    read-only, only drafts are deleted) raising
    ``ComplianceRecordConflict(code, detail)``, and ``canonical_json`` /
    ``canonical_sha256``. The overlay's workflow and workers write through
    these rules; the platform routes never change an assessment's status.
  - Routes ``GET|POST /api/compliance/assessments``, ``GET|PATCH|DELETE
    /api/compliance/assessments/{id}``, ``GET|POST
    .../assessments/{id}/suite-runs``, ``GET|PATCH|DELETE
    /api/compliance/suite-runs/{id}``, ``GET|POST
    .../suite-runs/{id}/findings``, ``GET /api/compliance/findings``
    (by assessment, suite run, analysis run or estimate) and ``GET|PATCH|DELETE
    /api/compliance/findings/{id}`` (``routers/compliance_records.py``):
    ORG_ADMIN and CONTRIBUTOR members of the assessment's organization,
    deletes ORG_ADMIN only, 409 ``{"code", "message"}`` from the guards.
    Access keys are refused (``key_routes``).

2.58 (2026-11-18): uniform retryability of a failed provider call (no
migration).
  - Every provider's error response (OpenAI, Anthropic, Google, Mistral,
    Cohere, Grok, DeepInfra, Custom endpoints) carries a boolean
    ``metadata.retryable``: whether the same call can succeed when tried
    again. It comes from one shared classifier,
    ``ai_services.base_service.classify_retryable(exc)``, on the original
    exception: False for an invalid or missing key, any 4xx other than
    408/409/429 (unknown model 404, bad request, content filter, context
    length), an exhausted quota or billing limit sent as 429
    (``insufficient_quota`` / ``billing_hard_limit_reached``, where the
    provider names it), an unresolvable host and the url_guard rejection;
    True for 408/409/429, 5xx, timeouts, connection failures, a stream
    whose connection drops midway (httpx ``ReadError`` or
    ``RemoteProtocolError``) and a model answer that did not parse. Only a
    4xx or 5xx counts as an HTTP status: an Anthropic stream that fails
    after HTTP 200 is True when its error event's ``error.type`` is
    ``overloaded_error``, ``api_error``, ``rate_limit_error`` or
    ``timeout_error``. Google's own empty-answer error is False for a
    safety block and True otherwise. Callers that repeat a failed
    generation read this flag instead of ``error_type`` or
    ``retry_attempts[-1].retryable``. ``error_type`` and each provider's
    own retry behaviour are unchanged; ``base_service`` also exports
    ``is_transient_upstream_error``, the DeepInfra / Custom backoff
    predicate.

2.59 (2026-11-18): variant designs, the declared and freezable design of a
  variant experiment (counterfactual and robustness tests), migration 142.
  - Table ``variant_designs`` (``project_models.VariantDesign``: ``key``
    unique per project, ``spec`` JSONB, ``version``, ``status``
    draft|frozen, ``content_hash``, ``frozen_at/by``, ``provenance``). The
    spec follows ``shared/schemas/variant_design.schema.json`` (factors with
    typed levels, ``role`` and ``source`` task|structure|system|run, the
    unit, optional slots, outcome, gold and invariance bindings).
  - ``task.meta.variant`` is a reserved key (``variant_designs.META_KEY``,
    ``shared/schemas/task_variant.schema.json``: ``design``, ``unit``,
    ``factors``, ``slots``, ``spans``, ``provenance``) and the single source
    of each task's place in a design. ``tasks.variant_design`` /
    ``variant_unit`` / ``variant_cell`` are derived from it by the trigger
    ``trg_tasks_variant_sync`` (``project_models.TASKS_VARIANT_DDL``); never
    write them. ``variant_cell`` is the design cell (the within-unit task
    factors of the assignment), and ``uq_tasks_variant_cell`` allows one
    task per cell and unit,
    ``fk_tasks_variant_design`` requires the design (a writer flushes a
    new design before its tasks).
  - Every ORM flush validates the ``meta.variant`` it writes against its
    design (``variant_design_guard.check_session_tasks``, a ``before_flush``
    listener on every Session). Refusals raise
    ``variant_design_guard.VariantDesignError`` (``status_code``, ``code``,
    ``detail``); the API answers them, and the database guards'
    errors (``error_from_db``), with 422/409 ``{"detail": {"code",
    "message", "problems"?}}``; the importers raise ``ImportValidationError``.
  - A frozen design makes its tasks' ``data`` and ``meta.variant``
    read-only and takes no new tasks (the trigger; SQLSTATE 23001, message
    ``variant_design_frozen``), and their bulk delete answers 409. An
    overlay that writes task data must expect that refusal.
  - Pure rules in ``variant_designs`` (``validate_spec``, ``DesignView``,
    ``validate_task_variant``, ``DesignCheck``/``check_design`` for the
    assignment, balance and span-invariance checks, ``content_hash``);
    service functions in ``variant_design_guard`` (``run_checks``,
    ``freeze_design``, ``update_design_spec``, ``serialize_design``,
    ``export_document``, ``iter_design_records``).
  - Routes under ``/api/projects/{id}/variant-designs`` (list, create,
    ``import``, get, ``export``, PUT spec, DELETE draft, ``check``,
    ``freeze``); reads need the full-data tier, writes edit rights.
  - Exports carry ``variant_designs`` (JSON and comprehensive, only when
    the project has any) and ``variant_design`` records (NDJSON); every
    importer creates them before the tasks and freezes them again (same
    content hash) before its commit. A flat import row may carry
    ``meta.variant`` as JSON in a column of that name. The v1 task reads
    never carry ``meta.variant``.

2.60 (2026-11-19): per-slot label configs (Label Studio ``<Repeater>``; no
migration).
  - Label configs may contain ``<Repeater on="$array" indexFlag="{{idx}}">``.
    It is expanded against each task's data exactly as Label Studio's
    ``Tree.tsx`` expands it (children once per array element, the index flag
    replaced by the 0-based element index in every attribute, the Repeater
    becoming a ``<View>``), so results are stored under plain indexed control
    names (``risk_0``, ``risk_1``, ...). BenGER attributes ``answerKey`` and
    ``answerKeyStart`` (default 1) name the key that identifies an item in an
    array answer. Rules (``label_config_repeater.repeater_errors``, enforced
    by ``LabelConfigValidator``): ``on`` is a ``$`` binding (looked up
    exactly, case-sensitive), no nesting, every named control carries the
    flag in its name, at most once per attribute, no expanded name equals an
    outside control's name or another template's expansion, and answer keys
    are unique.
  - ``shared/label_config_repeater.py``: ``expand_repeaters(config,
    task_data)`` (a config without a Repeater comes back unchanged),
    ``expand_repeaters_with_counts`` (to given counts, e.g. the longest
    array), ``repeater_blocks`` (``RepeaterBlock`` / ``RepeaterControl``
    with ``answer_property``, ``item_key``, ``item_count``),
    ``map_array_answers`` (``ArrayAnswerError``), ``repeater_answer_schema``,
    ``repeater_answer_example``, ``derive_slot_map(config, task_data,
    patterns)`` (slot index to control names, from a Repeater or from
    ``{idx}`` name patterns for hand-written indexed controls) and
    ``control_targets``.
  - ``ResponseParser.parse(..., task_data=None)``: required for a Repeater
    config; an array answer (top-level list for the only block, or an object
    keyed by ``answer_property``) is mapped onto the indexed names, by
    ``answerKey`` or by position, and a misfitting array is a
    ``validation_error``; only blocks with answer controls take array
    answers. ``generate_json_schema_from_label_config(...,
    task_data=None)`` and ``generate_format_instructions(...,
    task_data=None)`` describe a Repeater block as one array of objects,
    pinned to the task's item count when ``task_data`` is given. The
    generation worker and the reparse route pass the task's data.
  - ``LabelConfigParser.extract_fields``: a field inside a Repeater keeps
    its template name with a ``repeater`` entry (expand the config first for
    indexed names); ``bound_data_fields`` includes a Repeater's ``on`` array
    instead of the bindings into its items, and blinding reads ``$a[i].b``
    as the top-level key ``a``.
  - ``services/label_config/project_expansion.expanded_project_label_config_async``
    (longest array per Repeater, one SQL aggregate each), used by evaluation
    field detection, the multi-field field list and the ``answer_fields`` of
    the v1 project view (``serialize_project_public`` takes
    ``expanded_label_config``). The stored evaluation config of a Repeater
    project keeps the ``repeater_item_counts`` it was expanded to and is
    regenerated on read when the tasks' counts change.
  - ``ResponseParser`` JSON extraction: a JSON boolean answering a Choices
    field with "true"/"false" choices is stored as that choice; a closing
    code fence may follow the JSON directly; when neither a fenced block nor
    the whole text decodes, the last JSON object or array in the text is
    read; a ``<Choices choice="multiple">`` (or ``"multiple-dropdown"``)
    answer may be a list of choices, stored as ``value.choices``; the
    structured-output schema asks for a list of the choice values there,
    also inside a Repeater block.
  - Routes ``GET /api/projects/{id}/label-config/label-studio`` (the config
    expanded for Label Studio, with ``item_counts``) and ``GET
    /api/projects/{id}/label-config/slots?task_id=&pattern=`` (slot map).
  - The Label Studio task export fills a result's missing or dangling
    ``to_name`` from its control's ``toName`` in the task's expanded config
    (``convert_to_label_studio_format(results, targets)``); stored results are
    unchanged.
  - Frontend: ``parseLabelConfig(xml, taskData?)`` expands Repeaters
    (``@/lib/labelConfig/repeater``, exact path lookup like the backend),
    data bindings resolve ``[n]`` indexes, and
    ``extractFieldsFromLabelConfig(xml, tasksData)`` (project creation
    wizard) lists a Repeater's indexed names to the longest array of the
    imported tasks, none without data.

2.61 (2026-11-19): generation fidelity (migration 143).
  - ``generations.request_record`` (JSONB), ``request_sha256``,
    ``first_response_content`` and ``retried`` (``models.Generation``). The
    record holds every request the provider client sent for the generation
    (``ai_services.request_capture``: ``capture_requests()`` scope,
    ``record_request(provider, api, body, capture=...)`` called by every
    provider service right before its send, ``build_request_record``,
    ``request_sha256``, ``normalized_view``); for SDK clients the body is
    replaced by the JSON the SDK hands to httpx / httpx2 inside the scope
    (``capture: "http_body"``, with ``path``). A provider service added by
    an overlay records its requests the same way, or the worker stores the
    call it made marked ``capture: "worker_call"``.
  - Provider services take ``continuation=[{role, content}, ...]`` on
    ``generate`` / ``generate_structured``: turns sent after the first user
    prompt (``base_service.continuation_turns``).
  - Prompt structures take ``append_schema_instruction``,
    ``structured_output`` (``auto`` / ``off``), ``format_retry``,
    ``answer_schema`` and ``refusal_heuristic`` (``generation_fidelity``:
    ``answer_format(structure)``, ``answer_skeleton(label_config,
    task_data, answer_keys)`` and ``schema_instruction``,
    ``render_answer_schema`` / ``AnswerKeys``, ``refusal_matches``,
    ``MAX_GENERATION_RUNS_PER_TASK`` = 100). The appended skeleton lists the
    flat answer fields under their rendered answer keys plus one example
    object per item for each Repeater block; a config without a Repeater
    appends the same text as before. ``ResponseParser`` takes
    ``answer_keys`` (kept by the per-task Repeater parser);
    ``ParseResult.mapped_values``; ``answer_controls(task_data)`` names the
    indexed controls the format retry checks a parse against.
  - ``GET /api/runs/generations/{id}`` children carry
    ``has_request_record``, ``request_sha256``, ``retried`` and
    ``first_response_preview``; ``GET /api/runs/generations/{id}/trials/
    {trial_id}/request`` returns one trial's ``request_record`` and
    ``request_sha256`` (same access rules, 404 for a trial of another run).
  - Exports carry every generation column in both modes (``data`` also
    names the job's ``structure_key``); the task-level import keeps them,
    groups jobs by model and structure and keeps each row's ``run_index``.
  - The ``system`` block's ``parameter_profile`` is read from the first
    request the client sent (``system_profile.parameters_sent(entry)``, per
    API: chat.completions, openai.responses, anthropic.messages,
    google.generate_content, mistral.chat, cohere.chat), so filled-in and
    coerced values count; a ``worker_call`` entry or a body without those
    parameters falls back to the run config as in 2.56.

2.62 (2026-11-19): the analysis engine for variant experiments (migration 146).
  - ``services/shared/analysis`` (``import analysis``; importing the package
    pulls in no numeric library): ``analysis.spec`` (``validate_spec``,
    ``normalize_spec``, ``spec_hash``, ``SpecError``, ``DEFAULT_CONVENTIONS``,
    ``BASE_COLUMNS``; the JSON Schema ``schemas/analysis_spec.schema.json``,
    spec format 1), ``analysis.expression`` (``parse_expression``, grammar 1),
    ``analysis.observations`` (``Observation``, ``variant_of_task_meta``,
    ``typed_field_values``, ``observations_from_records``),
    ``analysis.db_source.iter_observations(db, project_id, inputs, counts)``
    (the seam to ``tasks.meta.variant``; the frame's ``system`` column is
    the generation's system key ``response_metadata.system.key``, see 2.56,
    read from the metadata as stored (a JSON object or its JSON text), and
    falls back to the model id for answers generated before 2.56; its
    ``retried`` column is ``generations.retried``, see 2.61),
    ``analysis.frame``
    (``build_frame``, ``frame_hash``, ``to_parquet``, ``from_parquet``),
    ``analysis.runner.run_spec(frame, spec)`` (estimates in a fixed order with
    the keys of ``ESTIMATE_KEYS``), ``analysis.multiplicity.adjust`` and
    ``analysis.version.ENGINE_VERSION`` (1.0.0). Estimators ``fe_ols``,
    ``mean_rate``, ``paired_within``; variances iid, HC1, one- and two-way
    cluster with ``ssc`` ``statsmodels`` | ``fixest`` | ``none``; inference
    normal or t; linear and ratio contrasts, TOST, Holm, Bonferroni,
    Benjamini-Hochberg (exploratory families only), MDE.
  - Tables ``analysis_runs`` (``models.AnalysisRun``) and
    ``analysis_estimates`` (``models.AnalysisEstimate``), cascading with the
    project and the run.
  - Queue ``analysis`` (``celery_queues.ANALYSIS``, served by the bulk pool)
    and the worker task ``tasks.run_analysis(run_id)``; frame snapshots under
    the durable storage prefix ``analysis/``.
  - Routes ``GET /api/analysis/engine``, ``POST /api/analysis/specs/validate``,
    ``POST|GET /api/projects/{project_id}/analysis-runs``,
    ``GET /api/analysis-runs/{analysis_run_id}``, ``.../estimates`` and
    ``.../frame`` (``routers.analysis``: ``create_run``,
    ``load_run_for_read``, ``serialize_run``, ``serialize_estimate``,
    ``build_select_estimates``), and the v1 reads
    ``GET /api/v1/projects/{project_id}/analysis-runs``,
    ``GET /api/v1/analysis-runs/{analysis_run_id}`` and ``.../estimates``
    (scope ``results:read``). The key gate binds ``analysis_run_id`` to its
    project.

2.63 (2026-11-19): import provenance and idempotent re-import (migration 147).
  - ``import_jobs.payload_sha256``, ``source_manifest`` (JSONB),
    ``idempotency_key`` and ``duplicate_of_job_id`` (``models.ImportJob``),
    built by the shared module ``import_provenance`` (``hash_fileobj``,
    ``build_manifest``, ``idempotency_key``, ``lock_import_key``,
    ``find_completed_import``, ``no_op_result``,
    ``validate_declared_manifest``, ``track_written_tasks``,
    ``record_written_tasks``), and the table ``import_job_tasks``
    (``models.ImportJobTask``) linking each import to the tasks it wrote.
  - ``tasks.import_project`` takes ``reimport``. A job whose key (payload
    hash, target, mode, model map) equals that of a completed import whose
    written tasks all still exist completes as a no-op: nothing written,
    ``duplicate_of_job_id`` set, ``result.no_op`` true and
    ``result.duplicate_of``.
  - The import job requests take ``source_manifest`` (declared, stored under
    ``source_manifest.declared``) and ``reimport``; cloud imports take
    ``reimport``. The job status carries ``payload_sha256``,
    ``source_manifest`` and ``duplicate_of_job_id``.

2.64 (2026-11-19): analysis results page and the /compliance route shells
  (no migration).
  - ``GET /api/analysis-runs/{analysis_run_id}/estimates`` items carry their
    row ``id`` (``serialize_estimate(row, with_id=True)``), the value a
    compliance finding's ``analysis_estimate_id`` cites; the v1 estimates
    keep their schema without it.
  - Pages ``/projects/[id]/analysis`` (the project's runs; editors start a
    run from a spec, ``?from=<runId>`` prefills one) and
    ``/projects/[id]/analysis/[runId]`` (status, forest plot, estimates with
    families and adjusted p-values, provenance, spec, fits, frame download).
  - Reusable components for overlays: ``@/components/analysis/ForestPlot``
    (``ForestPlot`` with ``rows``, ``nullValue``, an optional shaded
    ``band`` and inner intervals), ``ContrastForestPlot``,
    ``EstimatesTable``, ``RunProvenance``; ``@/lib/api/analysis``
    (``analysisAPI`` and the run and estimate types) and
    ``@/lib/analysis/results`` (formatting and grouping helpers).
  - Compliance slots, rendered only while the master flag
    ``extension.compliance`` is on for the viewer
    (``@/components/compliance/ComplianceSlot``: ``useComplianceSlot``,
    ``ComplianceRouteShell``, ``ComplianceInlineSlot``):
    ``ComplianceDashboard`` on ``/compliance`` (no props),
    ``AssessmentDetail`` on ``/compliance/assessments/[assessmentId]``
    (``{ assessmentId }``) and ``AnalysisRunFindings`` on the analysis run
    page (``{ projectId, run, estimates }``). A registered
    ``ComplianceDashboard`` also adds the Compliance entry to the
    navigation.

2.65 (2026-11-19): estimator extensions, slot frames, cross-project frames and
lookup tables of the analysis engine (migration 148; ``ENGINE_VERSION`` 1.1.0,
frame format 2).
  - Estimators ``logit`` (Newton-Raphson; iid, HC1 and cluster sandwich
    variances; fixed effects as dummies with ``informative_only``; contrasts
    of kind ``ame``, the average marginal effect of setting a column to a
    level; ``separation_bound`` withholds p-values, status ``separation``),
    ``mixedlm`` (statsmodels ``MixedLM``, random intercept per ``groups``,
    ``reml``, ``mixedlm_optimizers`` and ``mixedlm_max_se_ratio``; a fit with
    an infinite log-likelihood or a variance on the boundary is refused),
    ``bradley_terry`` (``players``, ``reference``, ``link`` logit or linear;
    parameters ``strength[<level>]``), ``plackett_luce`` (``stages``) and
    ``clogit_rank1`` over ``choice_set`` (default ``generation_id``), and
    ``spearman`` (``x``; parameter ``(rho)``). Estimator-only conventions in
    ``analysis.spec.ESTIMATOR_CONVENTIONS``; estimand keys per estimator in
    ``ESTIMATOR_KEYS``. Modules ``analysis.ml`` (``newton``, ``fit_logit``,
    ``fit_plackett_luce``, ``sandwich``) and ``analysis.mixed``.
  - Every estimand takes ``joint_tests`` (by ``contrasts``, ``parameters``
    with ``*`` or weight ``rows``): estimate rows of kind ``wald`` with the
    chi2 statistic, its rank as ``df`` and the p-value
    (``analysis.inference.wald_test``).
  - Frames: base column ``project_id``; ``frame: {"unit": "slot"}`` unpivots
    ``meta.variant.slots`` to one row per generation and slot (column
    ``slot``, the slot factors as columns; ``Observation.slots``,
    ``variant_of_task_meta`` returns ``slots``). Measures: field names with
    ``{idx}`` and ``slot`` (own, other or an index), ``slot_factor`` and
    ``slot_aggregate`` (mean, sum, min, max, sd, count, is_ranking).
  - ``inputs.projects`` stacks further projects with their own designs
    (``analysis.db_source.iter_run_observations``); starting such a run and
    downloading its frame need the ORG_ADMIN or CONTRIBUTOR role on each of
    them and, for a project-restricted access key, the key's access to each
    (403 ``analysis_input_forbidden``). Reading such a run (detail,
    estimates, the v1 reads) needs read access to each input project and
    the stored lookup tables' owners, otherwise 404, and the run lists leave
    it out (``routers.analysis.may_read_run_inputs``, ``hidden_runs_filter``;
    a purged input project no longer counts). The worker fails a run whose
    input project was deleted or purged before its results are stored
    (``analysis.db_source.check_input_projects``). Purging a project removes
    the frames of other projects' runs that read it.
  - Lookups (``lookups`` in the spec: inline ``rows`` or a stored ``table``
    with ``name``, ``version`` and optional ``project_id`` and
    ``content_hash``) join by key columns before the measures
    (``analysis.frame.join_lookups``). Table ``analysis_lookup_tables``
    (``models.AnalysisLookupTable``, immutable versions,
    ``analysis.lookups.validate_table`` and ``lookup_hash``) and
    ``analysis_runs.resolved_inputs`` (further projects, stored tables with
    their hashes); ``analysis.db_source.load_lookup_tables``.
  - Routes ``POST|GET /api/projects/{project_id}/analysis-lookups`` and
    ``GET .../analysis-lookups/{name}/versions/{version}``
    (``routers.analysis``: ``serialize_lookup``, ``check_run_inputs``);
    ``create_run`` takes the request's access-key principal; runs serialize
    ``resolved_inputs`` (also in the v1 run detail). ``library_versions``
    record statsmodels.

2.66 (2026-11-19): codes for variant experiments (migration 149).
  - Coder plugins: an overlay's workers module may export
    ``register_coders(registry)``; the workers call it through
    ``analysis.coders.load_overlay_coders`` (each package as owner) before an
    analysis run or a code validation reads a coder. A coder subclasses
    ``analysis.coders.Coder`` (``name``, ``version``, ``outputs`` typed
    ``number`` | ``text`` | ``bool``, optional ``source_modules``,
    ``code(text, context: CoderContext)``; ``FunctionCoder`` wraps a plain
    function). The registry hashes the name, version, outputs and the
    source of every counted module (``coder_code_hash``); runs and
    validations record the hash and the owner, and a coder of a package
    switched off for the run's context does not run (gated).
  - Text pattern sets (``analysis.text_patterns``: ``validate_pattern_set``,
    ``normalize_pattern_set``, ``pattern_set_hash``, ``compile_pattern_set``,
    ``CompiledPatternSet``, schema ``schemas/text_pattern_set.schema.json``,
    format 1) with task literals ``{{task.<path>}}``; list measures
    (``analysis.list_measures``); code identity and the confirmatory rule
    (``analysis.codes``: ``code_identity``, ``confirmatory_code_measures``,
    ``CodeInputs``); coding samples and agreement (``analysis.coding``:
    ``draw_sample``, ``normalize_validation_code``, ``validation_metrics``).
  - Spec measures ``list``, ``text_pattern``, ``coder``, ``judge_code`` and
    the spec key ``pattern_sets`` (spec format 1 stays; a spec without them
    hashes as before). ``Observation.answer_text``;
    ``iter_observations(..., with_text=)``, ``code_needs``,
    ``load_judge_values``, ``coding_task_sources``,
    ``coding_generation_values`` in ``analysis.db_source``;
    ``build_frame(..., codes=CodeInputs)`` and ``FrameResult.codes``.
    ``ENGINE_VERSION`` stays 1.1.0: no existing number moves.
  - Tables ``coding_projects`` (``models.CodingProject``) and
    ``code_validations`` (``models.CodeValidation``), column
    ``analysis_runs.codes``; coding tasks carry ``tasks.meta.coding``.
    Worker task ``tasks.run_code_validation`` on the ``analysis`` queue
    (``analysis_jobs.coding``). A confirmatory family's code measures need
    a completed validation with the same identity hash, or the run fails.
  - Routes ``POST|GET /api/projects/{project_id}/coding-projects``,
    ``GET /api/projects/{project_id}/coding``,
    ``POST|GET /api/projects/{project_id}/code-validations`` and
    ``GET /api/code-validations/{code_validation_id}`` (``routers.coding``;
    key-gate kind ``code_validation``). ``GET /api/analysis-runs/{id}``
    returns ``codes``.
  - Evaluation metric ``text_pattern`` (``metric_parameters.pattern_set`` and
    ``code``, checked on save). Metric handlers may set
    ``wants_raw_values`` (values as stored, not lower-cased),
    ``uses_task_data`` (``compute(..., task_data=)``) and ``reference_free``
    (cells run once per prediction field, under the field key
    ``<config>|<pred>|``, without a reference value);
    ``SampleEvaluator.evaluate_sample`` takes ``task_data``.

2.67 (2026-11-19): counts and listings reflect analysis runs (no
  migration, additive response fields only).
  - ``ProjectResponse.analysis_count``: completed analysis runs of the
    project, on the detail and, batched in one grouped count, on the list
    (``routers.projects.helpers.count_analysis_runs_by_project`` and
    ``count_analysis_runs_by_project_async``, ``build_select_analysis_counts``).
    A run that reads a further project counts for its own project.
  - ``GET /api/dashboard/stats`` (overview) adds ``generations_count``,
    ``evaluations_count`` and ``analyses_count``; ``projects_with_generations``
    and ``projects_with_evaluations`` stay as aliases with the same values
    (they always carried the counts, not a number of projects).
  - ``GET /api/runs`` takes ``type=analysis`` (``RunSummary`` gains ``name``,
    ``frame_rows``, ``estimates_count``, ``spec_hash``, ``engine_version``).
    Every type filters the accessible projects in the query, so ``total``
    and the pages count exactly the listed runs; analysis runs that read a
    further project the user may not read are left out, as in the
    per-project run list.
  - Report statistics (``report_service.get_report_statistics`` and
    ``get_report_statistics_batch``), the snapshot's ``statistics`` and the
    published list items carry ``analysis_count``.

2.68 (2026-11-19): inter-annotator agreement per control (no migration,
  additive only).
  - ``GET /api/evaluations/projects/{project_id}/annotator-agreement``
    (access-key scope ``annotations:read``): per control of the labeling
    interface, Fleiss' kappa, pairwise Cohen's kappa and percent agreement
    for ``choices`` and ``rating``, Pearson's r and mean absolute deviation
    for ``number``, over tasks with two or more active annotations;
    ``available: false`` without overlap. Computed by
    ``annotator_agreement.project_annotator_agreement`` (shared) with
    ``bg_statistics.compute_agreement``; annotators are labelled by
    ``user_display.masked_name``.
  - The report snapshot gains ``annotator_agreement`` (the same object
    without ``available``, or ``None``), and the Annotation section the
    flag ``show_agreement``.
  - ``report_snapshot.apply_section_visibility`` applies the section flags
    when a report is served: with ``show_agreement`` off, every read path
    serves ``annotator_agreement`` as ``None``; with ``show_participants``
    off, every read path leaves out the agreement pairs and the participant
    lists of the snapshot and the Annotation section, keeping the aggregates
    and ``participant_count``. The stored snapshot is not changed.

2.69 (2026-11-19): the experiment features behind platform feature flags
  (migration 151; docs/features/feature-flags.md).
  - Two platform flags (``feature_flags.registry.VARIANT_EXPERIMENTS`` =
    ``variant_experiments``, ``COMPLIANCE_RECORDS`` = ``compliance_records``),
    owner ``platform``, default ``off``, coupled to no master flag. An
    overlay that uses these features (the compliance overlay) needs them on
    for its users: ``compliance_records`` for ``/api/compliance`` and the
    ``/compliance`` shells (besides ``extension.compliance``),
    ``variant_experiments`` for everything else listed below.
  - Off, the routes of 2.56-2.68 answer 404 ``feature_disabled``
    (``feature_flags.deps.require_variant_experiments`` /
    ``require_compliance_records``; an organization key's organization
    counts on the v1 analysis routes), the analysis and code-validation
    jobs end failed with ``FEATURE_DISABLED_MESSAGE``, and every changed
    behaviour takes its previous branch: no request record (the httpx hook
    is installed on the first capture scope, no longer at import), no
    system key, prompt structures at the default answer format, the
    single-value multi-choice schema and the previous parsing
    (``ResponseParser(..., variant_experiments=)``,
    ``generate_json_schema_from_label_config(..., variant_experiments=)``),
    runs per task at most 25 (``generation_fidelity.max_runs_per_task``),
    ``text_pattern`` neither offered nor run
    (``metric_filters.FLAGGED_METRICS``, ``without_flagged_metrics``),
    ``<Repeater>`` an unsupported field type, no import provenance, the
    previous generation export and nested import, no analysis counts, no
    annotator agreement in new snapshots and none served while the flag is
    off for everybody (``report_snapshot.without_experiment_parts``).
  - Catalog entries can belong to a flag: ``default_config.feature_flag``
    (the model) and ``default_config.reasoning_config.feature_flag`` (its
    reasoning knob); ``catalog_flags`` (``model_offered``,
    ``served_default_config``, ``reasoning_config_for``) applies them and
    ``provider_capabilities.model_reasoning_config`` returns no knob while
    its flag is off.
  - ``feature_flags.scope`` (``flag_scope``, ``scoped_flag``,
    ``scoped_answer``, ``flag_on_for_anybody``) carries a job's answer into
    shared code; ``feature_flags.worker.flag_enabled_or_default``;
    ``service.is_enabled_for_caller(_sync)``, ``on_for_anybody``,
    ``is_on_for_anybody(_sync)``; ``extension_activation.flag_snapshot``;
    ``require_feature_flag(name, key_organization=False)``.
  - The reserved task key of variant assignments is ``meta.benger_variant``
    (``variant_designs.META_KEY``; the CSV column ``meta.benger_variant``);
    ``meta.variant`` is plain data again. Migration 142 no longer rewrites
    stored rows; migration 151 moves the assignments of a database that ran
    its first version and returns ``meta.variant_legacy`` to
    ``meta.variant``. Design files, imports and specs name the new key.
"""

import os

CORE_API_VERSION = "2.69"


def extended_required() -> bool:
    """True when this deployment must run the extended edition.

    Set BENGER_REQUIRE_EXTENDED=true (Helm: {api,workers}.extraEnv, see
    benger-extended/infra/helm/values-extended.yaml) to make a failed
    extended import or a handshake mismatch crash the process at startup
    instead of silently degrading to the community edition. Unset (the
    default) preserves graceful degradation for community installs and
    local development.
    """
    return os.getenv("BENGER_REQUIRE_EXTENDED", "").strip().lower() in ("1", "true", "yes")

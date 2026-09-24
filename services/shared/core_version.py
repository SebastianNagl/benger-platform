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
"""

import os

CORE_API_VERSION = "2.24"


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

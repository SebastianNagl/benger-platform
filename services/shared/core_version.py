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
- 2.20: LMS connections run by org admins (first cut, refined as the
  release lands).
  Schema: migration 105 (``tool_host`` on registrations and invites;
  ``lti_user_links.research_consent_at`` / ``link_method`` / ``unlinked_at``;
  ``lti_resource_links.ai_lineitem_*``; ``lti_grade_syncs.kind`` /
  ``last_synced_source`` / ``last_checked_at`` with ``uq_lti_grade_sync`` on
  (resource_link_id, user_id, kind); the new ``lti_resource_link_users``
  and ``lti_admin_events`` tables) and migration 106
  (``task_evaluations.updated_at``, ``users.anonymized_at``,
  ``ix_users_email_lower``, the ``lti_claim`` email state of provisioned
  accounts, ``project_organizations.attached_via``); the activation and
  password-reset confirm paths verify an unproven routable address
  (``account_activation.verify_email_by_link``). Modules: ``public_hosts``
  (tool host key to base URL), ``user_display`` (real name or pseudonym label),
  ``auth_module.org_scope`` (``OrgAdminScope``, ``require_scope_admin`` and
  its sync twin). API hooks the extended ``get_hooks()`` registers:
  ``dispatch_lti_grade_sync``, ``privacy_protected_member_ids``,
  ``project_real_name_viewer``, ``lti_anonymization_policy``,
  ``lti_protected_org_ids``. Billing contract: the grading dispatch policy
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
  ``GET /tool-hosts``, ``DELETE /registrations/{id}`` (``accounts=keep``),
  ``PATCH .../deployments/{pk}``, ``GET .../resource-links``,
  ``GET|DELETE .../user-links``, ``GET .../events``, grade transfers with
  context and a retry that dispatches through ``dispatch_lti_grade_sync``.
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
"""

import os

CORE_API_VERSION = "2.20"


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

# API key resolution — who pays for an LLM dispatch

Every lane that spends LLM tokens (generation runs, evaluation runs, extension
dispatches) resolves its API key through one rule, implemented twice for the
two runtimes and kept in lockstep:

- API: `services/api/services/org_api_key_service.py` → `resolve_api_key`
- Workers: `services/shared/shared_org_api_key_service.py` → `resolve_api_key`

## The rule

```
resolve_api_key(db, user_id, org_id, provider):
  org_id is None                          -> the user's personal key
  org.settings.require_private_keys      -> the user's personal key
    (unset defaults to True)
  otherwise ("org-pays" mode)            -> the ORG key, for active members
                                            and superadmins only; anyone else
                                            falls back to their personal key
```

There is no platform/env key fallback: when the resolved key is missing, the
dispatch fails loudly rather than silently billing the deployment.

The membership gate (2026-08-31) mirrors the BYOM credential path's
`_user_is_active_org_member` check: an org that pays, pays for its members —
an unvalidated header or a historical fallback naming the org is not enough.
`get_available_providers_for_context` applies the same gate so the UI never
advertises a provider the resolution would refuse.

## Dispatch-time org attribution

Which org id reaches `resolve_api_key` is decided by
`services/shared/org_resolution.py` — the single source of truth since
2026-08-31 (three drifting copies previously existed):

- `resolve_dispatch_org_for_project(db, user, project)` (+ async twin working
  from a project id): the user's first ACTIVE membership among the project's
  orgs; a superadmin without a membership falls back to the project's first
  org (admin backfills keep working); everyone else resolves to `None` →
  personal key.
- `validate_org_context_header(db, user, org_id)` (+ async twin): a
  client-supplied `X-Organization-Context` value is honored only for an
  active member or a superadmin — the middleware passes the header through
  unvalidated, so this is the trust boundary.

Callers: batch evaluation dispatch (`routers/evaluations/helpers.py`),
immediate-evaluation dispatch (`shared/immediate_eval_dispatch.resolve_org`),
generation start (`routers/generation_task_list.py` — header first, then the
project's sole linked org, both validated), and extension routers.

## Lane notes

- **Generation runs** freeze `organization_id` and `created_by` on the
  `ResponseGeneration` row at creation; retries and resumes reuse the stored
  values (provenance stays stable — a later org re-link does not change who
  pays, a later `require_private_keys` flip does).
- **Batch evaluation** runs every configured judge, including duplicated
  judge metrics, on the resolved key. Extensions may install a dispatch
  policy hook for the immediate (single-sample) lane via
  `_get_grading_dispatch_policy_fn`; the batch lane deliberately has no hook.
- **BYOM / custom models** resolve differently
  (`shared/ai_services/user_aware_ai_service.get_ai_service_for_model_row`):
  the invoking user's per-model credential always wins; an org-shared
  credential is a fallback only in org-pays mode with an active membership
  and a live model share.

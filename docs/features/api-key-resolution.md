# API key resolution: who pays for an LLM dispatch

Every lane that spends LLM tokens (generation runs, evaluation runs, extension
dispatches) resolves its API key through one rule, implemented twice for the
two runtimes and kept in lockstep:

- API: `services/api/services/org_api_key_service.py` → `resolve_api_key`
- Workers: `services/shared/shared_org_api_key_service.py` → `resolve_api_key`

## The rule

```
resolve_api_key(db, user_id, org_id, provider, project_id=None,
                org_billing_authorized=False):
  org_id is None                          -> the user's personal key
  org.settings.require_private_keys      -> the user's personal key
    (unset defaults to True)
  otherwise ("org-pays" mode)            -> the ORG key, for active members
                                            and superadmins only; anyone else
                                            falls back to their personal key
                                            unless org_billing_authorized
```

There is no platform/env key fallback: when the resolved key is missing, the
dispatch fails loudly rather than silently billing the deployment.

`org_billing_authorized` is a policy-asserted flag. Only code that derived it
from the database in the same process sets it (an extension's dispatch
policy), never an HTTP request or a task payload. It lifts the membership gate
and nothing else: an org that requires private keys is never charged.

## Group scope (org → group → user layer, 2026-08-31)

Org keys live per `(organization_id, provider, group_id)`. A `group_id` of NULL
is the org-wide pool, a set `group_id` is that organization group's own key.
`project_id` selects WHICH row the org-pays arm spends: when the project's
attachment to the org (`project_organizations.group_id`) is group-scoped,
the group's key is tried first, falling back to the org-wide row. The key
follows the PROJECT's attachment, never the dispatching user's groups. An
org admin grading a chair's exam spends the chair's key. Two invariants:

- Every read/write against `organization_api_keys` carries an explicit
  group-scope predicate (`services/api/services/org_api_key_service.py`
  documents this on the model too). A bare `(org, provider)` filter would
  silently mix org-wide and group rows once both exist.
- Callers that omit `project_id` resolve the org-wide row only, so worker
  dispatch leaves all thread the project id
  (`services/workers/tests/test_group_key_threading.py` pins each site).
  For an org whose keys are ALL group-scoped, an unthreaded site means
  "no key configured" and a loud failure. Known exception: the synthetic
  builder generates before its project exists and therefore always
  resolves the org-wide row.

`get_available_providers_for_context` reports the union of the org-wide
pool and the caller's own groups' keys so a group-only-keyed org does not
show zero providers to its members.

The membership gate (2026-08-31) mirrors the BYOM credential path's
`_user_is_active_org_member` check: an org that pays, pays for its members.
An unvalidated header or a historical fallback naming the org is not enough.
`get_available_providers_for_context` applies the same gate so the UI never
advertises a provider the resolution would refuse.

## Dispatch-time org attribution

Which org id reaches `resolve_api_key` is decided by
`services/shared/org_resolution.py`, the single source of truth since
2026-08-31 (three drifting copies previously existed):

- `resolve_dispatch_org_for_project(db, user, project)` (+ async twin working
  from a project id): the user's first ACTIVE membership among the project's
  orgs; a superadmin without a membership falls back to the project's first
  org (admin backfills keep working); everyone else resolves to `None` →
  personal key.
- `validate_org_context_header(db, user, org_id)` (+ async twin): a
  client-supplied `X-Organization-Context` value is honored only for an
  active member or a superadmin. The middleware passes the header through
  unvalidated, so this is the trust boundary.

Callers: batch evaluation dispatch (`routers/evaluations/helpers.py`),
immediate-evaluation dispatch (`shared/immediate_eval_dispatch.resolve_org`),
generation start (`routers/generation_task_list.py`: header first, then the
project's sole linked org, both validated), and extension routers.

## Lane notes

- **Generation runs** freeze `organization_id` and `created_by` on the
  `ResponseGeneration` row at creation; retries and resumes reuse the stored
  values (provenance stays stable: a later org re-link does not change who
  pays, a later `require_private_keys` flip does).
- **Immediate evaluation** (single-sample lane) asks the optional extension
  hook `_get_grading_dispatch_policy_fn` for the organization, the configs and
  the `org_billing_authorized` flag. Since core 2.20 the result may carry a
  fourth element, a billing block (`{reason, ...}`). A blocked grading runs no
  judge. The run is marked failed with the reason
  (`billing_blocked:<reason>`, the block under `eval_metadata.billing_block`),
  and `shared/immediate_eval_dispatch` keeps one blocked run per annotation.
  Its `ensure_immediate_evaluation` (used by the submit hook, the endpoint,
  the timer auto-submit and the hourly `sweep_missing_immediate_evals`)
  consults the optional worker hook
  `benger_extended.workers.get_grading_block_fn` before dispatching, so a
  blocked annotation is dispatched again only once the block is gone.
- **Batch evaluation** runs every configured judge, including duplicated
  judge metrics, on the resolved key. Since core 2.20 the optional worker hook
  `benger_extended.workers.get_batch_evaluation_policy_fn` may name another
  organization for a batch run, refuse it, or authorize the starter to spend
  that organization's keys. A refused run fails before any judge runs
  (`billing_blocked:<reason>`). Every evaluation cell asks the hook again for
  the authorization instead of reading it from the task payload.
- **Exams linked to an LMS** (the LTI integration, commercial edition) follow
  one rule: every AI grading of such an exam is billed to the organization of
  the LMS connection. That covers the connection's LMS users, the
  organization's staff and batch runs. The key follows the exam's
  attachment, so a group connection spends its group's key before the
  organization's. When that organization does not provide keys or has no key
  for the judge's provider, the policy returns a block (`org_not_paying`,
  `org_key_missing`, `connection_removed`, or `billing_check_failed` when the
  check itself failed) and the grading does not run. It is
  never rerouted to another organization, a personal key or a deployment key.
  Teacher AI helpers on a linked exam use the same rule. Users who reach a
  linked exam without the LMS (share links, catalog) keep the rules above.
  See [LMS integration](../lms-integration.md#85-where-the-data-lives-and-who-pays).
- **BYOM / custom models** resolve differently
  (`shared/ai_services/user_aware_ai_service.get_ai_service_for_model_row`):
  the invoking user's per-model credential always wins; an org-shared
  credential is a fallback only in org-pays mode with an active membership
  and a live model share.

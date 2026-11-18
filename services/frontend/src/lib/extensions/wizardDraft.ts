/**
 * Wizard draft mode (CORE 2.55): the extension points that switch the project
 * creation wizard to a draft project and let an overlay act on it.
 *
 * Without a registered policy (the community edition) or when no policy
 * applies, the wizard works as before: everything is collected locally and
 * the project is created on "Create". When a policy applies as the user
 * leaves the first step, the wizard creates a draft project right away
 * (private, without organization rows, hidden from every list; see
 * `routers/projects/wizard_drafts.py`), saves its state there, syncs the
 * tasks into it when the data step is left, writes the configuration before
 * the rubric step, and finishes it on "Create" through the finish route,
 * which applies the visibility as the last write.
 *
 * Hook contract (all hooks are awaited in registration order; a hook that
 * throws only shows a toast, the wizard goes on, except for the guard
 * `beforeLeaveStep` below):
 *
 * - The policy itself, `registerWizardDraftPolicy({ applies(wizardData),
 *   describeDiscard?({ projectId }), beforeLeaveStep?(ctx) })`: `applies`
 *   is asked when the user leaves step 1 (draft mode only while it applies or a draft is open);
 *   `describeDiscard` returns extra lines shown in the confirmation before
 *   a draft is discarded (from the wizard footer or the unfinished-drafts
 *   list), e.g. how many generated or checked grading sheets will be lost;
 *   a failing `describeDiscard` is ignored.
 * - The awaited guard `beforeLeaveStep?({ projectId, fromStepId, toStepId,
 *   skippedStepIds, wizardData, confirm })` of a policy that applies to the
 *   current state, the only member that can hold the wizard: asked in draft
 *   mode on every forward move (Next, and a step-dot jump forward, which
 *   passes the steps in `skippedStepIds` without opening them), after the
 *   draft exists and before the move's syncs and save, and on "Create"
 *   (`toStepId` null) before the final syncs. Resolving false keeps the
 *   user on the current step; a guard that throws shows its message and
 *   also keeps the user there. `confirm` opens the wizard's own
 *   confirmation dialog and resolves whether the user confirmed. Backward
 *   moves are never guarded, and nothing is asked outside draft mode.
 *   Example: ask before the user leaves (or skips) the rubric step or
 *   creates the project while tasks have no checked sheet.
 * - `created` `{ projectId, wizardData }`: once, right after the draft was
 *   created (not on resume). Example: switch on the check requirement of
 *   grading sheets before the first import.
 * - `tasksSynced` `{ projectId, wizardData, tasks }`: after every task sync
 *   that ran (leaving the data step, and before the finish). `tasks` lists
 *   the draft's tasks in row order with `status` `kept` (same content),
 *   `updated` (content replaced in place, its sheets were archived) or
 *   `created` (imported now). Example: create the structured-entry sheet of
 *   a new task as a candidate.
 * - `configSynced` `{ projectId, wizardData }`: after the wizard wrote title,
 *   label config and (when they changed) the evaluation configs into the
 *   draft, and before it reads the evaluation configs back. Runs every time
 *   the user moves to the rubric step, and once more on "Create", after the
 *   final task sync and before the settings PATCH, the post-create hooks and
 *   the finish route, so it also runs when the rubric step was never
 *   visited. Example: apply the judge the check requirement needs.
 *
 * The rubric step slot (`ProjectWizardRubricStep`) receives
 * `draftProjectId` in draft mode; post-create hooks receive `draft: true`.
 * Only registrations of active owners count (see ./active.ts).
 */

import { isOwnerActive } from './active'
import { currentOwnerLabel } from './owner'

/** A request for the wizard's confirmation dialog. */
export interface WizardConfirmRequest {
  title: string
  message: string
  confirmText: string
  variant?: 'warning' | 'danger'
}

export interface WizardLeaveStepContext {
  projectId: string
  fromStepId: string
  /** The step the user moves to; null on "Create". */
  toStepId: string | null
  /** Steps between the two that a step-dot jump passes without opening. */
  skippedStepIds: string[]
  wizardData: Record<string, any>
  /** The wizard's confirmation dialog; resolves whether the user confirmed. */
  confirm: (request: WizardConfirmRequest) => Promise<boolean>
}

export interface WizardDraftPolicy {
  /** Draft mode for this wizard state (asked when leaving the first step). */
  applies: (wizardData: Record<string, any>) => boolean
  /**
   * Extra lines for the confirmation before a draft is discarded, e.g. the
   * grading sheets that were already checked in it.
   */
  describeDiscard?: (ctx: { projectId: string }) => Promise<string[]> | string[]
  /**
   * Asked before a forward move and before "Create" in draft mode; false
   * keeps the user on the current step.
   */
  beforeLeaveStep?: (ctx: WizardLeaveStepContext) => Promise<boolean>
}

export type WizardDraftTaskStatus = 'kept' | 'updated' | 'created'

export interface WizardDraftSyncedTask {
  id: string
  /** Position of the wizard row the task holds (0-based). */
  rowIndex: number
  status: WizardDraftTaskStatus
}

export interface WizardDraftHookContexts {
  created: { projectId: string; wizardData: Record<string, any> }
  tasksSynced: {
    projectId: string
    wizardData: Record<string, any>
    tasks: WizardDraftSyncedTask[]
  }
  configSynced: { projectId: string; wizardData: Record<string, any> }
}

export type WizardDraftHookName = keyof WizardDraftHookContexts

export type WizardDraftHook<K extends WizardDraftHookName> = (
  ctx: WizardDraftHookContexts[K],
) => Promise<void> | void

const policies: { owner: string; policy: WizardDraftPolicy }[] = []
const hooks: {
  owner: string
  name: WizardDraftHookName
  fn: WizardDraftHook<any>
}[] = []

export function registerWizardDraftPolicy(policy: WizardDraftPolicy) {
  if (policies.some((p) => p.policy === policy)) return
  policies.push({ owner: currentOwnerLabel(), policy })
}

/** The policies of active owners, in registration order. */
export function getWizardDraftPolicies(): WizardDraftPolicy[] {
  return policies.filter((p) => isOwnerActive(p.owner)).map((p) => p.policy)
}

/** Whether the wizard should run on a draft for `wizardData`. */
export function wizardDraftApplies(wizardData: Record<string, any>): boolean {
  return getApplyingWizardDraftPolicies(wizardData).length > 0
}

/** The policies of active owners that apply to `wizardData`. */
export function getApplyingWizardDraftPolicies(
  wizardData: Record<string, any>,
): WizardDraftPolicy[] {
  return getWizardDraftPolicies().filter((p) => {
    try {
      return p.applies(wizardData)
    } catch {
      return false
    }
  })
}

export function registerWizardDraftHook<K extends WizardDraftHookName>(
  name: K,
  fn: WizardDraftHook<K>,
) {
  if (hooks.some((h) => h.name === name && h.fn === fn)) return
  hooks.push({ owner: currentOwnerLabel(), name, fn })
}

export function getWizardDraftHooks<K extends WizardDraftHookName>(
  name: K,
): WizardDraftHook<K>[] {
  return hooks
    .filter((h) => h.name === name && isOwnerActive(h.owner))
    .map((h) => h.fn as WizardDraftHook<K>)
}

/** Test helper. */
export function _resetWizardDraftRegistry() {
  policies.length = 0
  hooks.length = 0
}

/**
 * Wizard-finish contributor registry — the public extension point for
 * extended packages to inject extra fields into the project-update payload
 * built at the end of the project creation wizard.
 *
 * Each contributor receives the wizard's accumulated state and returns a
 * partial payload to merge. Contributors run in registration order; later
 * contributors can override earlier ones via Object.assign semantics. Only
 * contributors of active owners run (see ./active.ts).
 */

import type { EvaluationConfig } from '@/lib/api/evaluation-types'
import { isOwnerActive } from './active'
import { currentOwnerLabel } from './owner'

export interface WizardFinishContext {
  evaluationConfigs: EvaluationConfig[]
  features: { annotation: boolean; generation: boolean; evaluation: boolean }
}

export type WizardFinishContributor = (
  ctx: WizardFinishContext,
) => Record<string, unknown>

const contributors: { owner: string; fn: WizardFinishContributor }[] = []

export function registerWizardFinishContributor(fn: WizardFinishContributor) {
  if (contributors.some((c) => c.fn === fn)) return
  contributors.push({ owner: currentOwnerLabel(), fn })
}

export function getWizardFinishContributors(): WizardFinishContributor[] {
  return contributors.filter((c) => isOwnerActive(c.owner)).map((c) => c.fn)
}

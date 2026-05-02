/**
 * Wizard-finish contributor registry — the public extension point for
 * extended packages to inject extra fields into the project-update payload
 * built at the end of the project creation wizard.
 *
 * Each contributor receives the wizard's accumulated state and returns a
 * partial payload to merge. Contributors run in registration order; later
 * contributors can override earlier ones via Object.assign semantics.
 */

import type { EvaluationConfig } from '@/lib/api/evaluation-types'

export interface WizardFinishContext {
  evaluationConfigs: EvaluationConfig[]
  features: { annotation: boolean; generation: boolean; evaluation: boolean }
}

export type WizardFinishContributor = (
  ctx: WizardFinishContext,
) => Record<string, unknown>

const contributors: WizardFinishContributor[] = []

export function registerWizardFinishContributor(fn: WizardFinishContributor) {
  if (contributors.includes(fn)) return
  contributors.push(fn)
}

export function getWizardFinishContributors(): WizardFinishContributor[] {
  return [...contributors]
}

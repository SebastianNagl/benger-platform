/**
 * Wizard template registry — the public extension point for adding labeling
 * templates (Klausurlösung, etc.) from `benger-extended` without hardcoding
 * proprietary XML in the public wizard.
 *
 * Stores i18n keys, not resolved strings: extended packages register at module
 * load (outside any React/i18n context), so the wizard resolves `nameKey` /
 * `descriptionKey` through `t()` at composition time.
 */

import type { LabelingTemplate } from '@/components/projects/wizard/types'

export interface RegisteredWizardTemplate
  extends Omit<LabelingTemplate, 'name' | 'description'> {
  nameKey: string
  descriptionKey: string
}

const registry: RegisteredWizardTemplate[] = []

export function registerWizardTemplate(template: RegisteredWizardTemplate) {
  if (registry.some((r) => r.id === template.id)) return
  registry.push(template)
}

export function getRegisteredWizardTemplates(): RegisteredWizardTemplate[] {
  return [...registry]
}

/**
 * Post-create hooks — run by the project wizard after the project exists and
 * its data import has been dispatched, right before the redirect. Extended
 * options that need the project id (e.g. kicking off rubric generation for
 * every imported task) register one; the wizard awaits them in order. A
 * hook that throws only surfaces a toast: the project is already created.
 */
export type WizardPostCreateHook = (ctx: {
  projectId: string
  wizardData: Record<string, any>
}) => Promise<void> | void

const postCreateHooks: WizardPostCreateHook[] = []

export function registerWizardPostCreateHook(hook: WizardPostCreateHook) {
  if (!postCreateHooks.includes(hook)) postCreateHooks.push(hook)
}

export function getWizardPostCreateHooks(): WizardPostCreateHook[] {
  return [...postCreateHooks]
}

/** Test helper. */
export function _resetWizardPostCreateHooks() {
  postCreateHooks.length = 0
}

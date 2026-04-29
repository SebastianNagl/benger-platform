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

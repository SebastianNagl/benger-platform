/**
 * Wizard template registry — the public extension point for adding labeling
 * templates (Klausurlösung, etc.) from `benger-extended` without hardcoding
 * proprietary XML in the public wizard.
 *
 * Stores i18n keys, not resolved strings: extended packages register at module
 * load (outside any React/i18n context), so the wizard resolves `nameKey` /
 * `descriptionKey` through `t()` at composition time.
 *
 * Every registration remembers its owner; the getters only return entries
 * of active owners (see ./active.ts), so an overlay switched off at runtime
 * drops out of the wizard.
 */

import type { LabelingTemplate } from '@/components/projects/wizard/types'
import { isOwnerActive } from './active'
import {
  currentOwnerLabel,
  pushRegistration,
  recordRegistration,
  resolveRegistration,
  type RegistrationOwners,
  type RegistrationStacks,
} from './owner'

export interface RegisteredWizardTemplate extends Omit<
  LabelingTemplate,
  'name' | 'description'
> {
  nameKey: string
  descriptionKey: string
  /**
   * Offered only to projects created for these jurisdictions ('DE' | 'FR',
   * see '@/lib/jurisdiction'). Omitted = offered everywhere.
   */
  jurisdictions?: string[]
}

const registry: { owner: string; template: RegisteredWizardTemplate }[] = []

export function registerWizardTemplate(template: RegisteredWizardTemplate) {
  const owner = currentOwnerLabel()
  if (registry.some((r) => r.template.id === template.id && r.owner === owner))
    return
  registry.push({ owner, template })
}

/**
 * Templates of active owners in registration order. When several owners
 * register the same id, the newest active one counts (at the position of the
 * first registration).
 */
export function getRegisteredWizardTemplates(): RegisteredWizardTemplate[] {
  const byId = new Map<string, RegisteredWizardTemplate>()
  for (const { owner, template } of registry) {
    if (isOwnerActive(owner)) byId.set(template.id, template)
  }
  return [...byId.values()]
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

const postCreateHooks: { owner: string; hook: WizardPostCreateHook }[] = []

export function registerWizardPostCreateHook(hook: WizardPostCreateHook) {
  if (postCreateHooks.some((h) => h.hook === hook)) return
  postCreateHooks.push({ owner: currentOwnerLabel(), hook })
}

export function getWizardPostCreateHooks(): WizardPostCreateHook[] {
  return postCreateHooks
    .filter((h) => isOwnerActive(h.owner))
    .map((h) => h.hook)
}

/** Test helper. */
export function _resetWizardPostCreateHooks() {
  postCreateHooks.length = 0
}

/**
 * Kind presets — applied by the wizard when the user picks a project type
 * (Klausur / Kartenstapel). The extended edition registers presets that
 * prefill evaluation configs (tier judge pair), immediate evaluation and
 * exam settings so a wizard-made project works on both the benger and the
 * vertretbar surface without manual setup. The preset receives the wizard
 * state AFTER the template/annotation defaults and returns a partial to
 * merge (nested objects must be returned whole). Each owner keeps one preset
 * per kind; the newest one whose owner is active counts, and a different
 * owner registering a kind logs a warning (see ./owner.ts).
 */
export type WizardKindPreset = (
  data: Record<string, any>,
) => Record<string, any>

const kindPresets: RegistrationStacks<WizardKindPreset> = new Map()
const kindPresetOwners: RegistrationOwners = new Map()

export function registerWizardKindPreset(
  kind: string,
  preset: WizardKindPreset,
) {
  recordRegistration(kindPresetOwners, 'wizard kind preset', kind)
  pushRegistration(kindPresets, kind, preset)
}

export function getWizardKindPreset(
  kind: string,
): WizardKindPreset | undefined {
  return resolveRegistration(kindPresets, kind, isOwnerActive)
}

/** Test helper. */
export function _resetWizardKindPresets() {
  kindPresets.clear()
  kindPresetOwners.clear()
}

/**
 * Project types — extra options for the wizard's project-type picker next
 * to the three built-in ones (Generisch / Klausur / Kartenstapel, always
 * shown). A registered type is a flavour of a base kind: the project is
 * created with `kind`, the wizard selects `templateId` as the labeling
 * template, applies the base kind's preset and then the type's own
 * `preset` (same contract as a kind preset). `jurisdictions` limits the
 * type to projects created for those jurisdictions, e.g. the French exam
 * types the extended edition registers for 'FR'. A duplicate `id` is
 * ignored, like a duplicate template.
 */
export interface RegisteredWizardProjectType {
  id: string
  kind: 'generic' | 'exam' | 'flashcard_collection'
  icon: string
  nameKey: string
  descriptionKey: string
  templateId?: string
  jurisdictions?: string[]
  preset?: WizardKindPreset
}

const projectTypes: RegisteredWizardProjectType[] = []

export function registerWizardProjectType(type: RegisteredWizardProjectType) {
  if (projectTypes.some((r) => r.id === type.id)) return
  projectTypes.push(type)
}

export function getRegisteredWizardProjectTypes(): RegisteredWizardProjectType[] {
  return [...projectTypes]
}

/** Test helper. */
export function _resetWizardProjectTypes() {
  projectTypes.length = 0
}

/**
 * Extension loader for BenGER extended features.
 *
 * At app startup, if NEXT_PUBLIC_BENGER_EDITION=extended, this module
 * dynamically imports the @benger/extended package and calls registerAll()
 * to register additional components, slots, and metric definitions.
 *
 * If the extended package is not installed or the env var is not set,
 * the platform runs as the community edition with all extension points
 * returning null/empty.
 */

export { registerSlot, getSlot, useSlot, hasSlot } from './slots'
export {
  registerChangelogEntries,
  getChangelogEntries,
  useChangelogEntries,
} from './changelog'
export type { ChangelogEntry, ChangelogAudience } from './changelog'
export {
  registerWizardTemplate,
  getRegisteredWizardTemplates,
  registerWizardPostCreateHook,
  getWizardPostCreateHooks,
  registerWizardKindPreset,
  getWizardKindPreset,
} from './wizardTemplates'
export type { RegisteredWizardTemplate, WizardPostCreateHook, WizardKindPreset } from './wizardTemplates'

let extendedLoaded = false

export async function loadExtended(): Promise<boolean> {
  if (process.env.NEXT_PUBLIC_BENGER_EDITION !== 'extended') return false
  try {
    const extended = await import('@benger/extended')
    extended.registerAll()
    extendedLoaded = true
    return true
  } catch {
    // Extended package not available -- community edition
    return false
  }
}

export function isExtendedLoaded(): boolean {
  return extendedLoaded
}

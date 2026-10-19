/**
 * Extension loader for the BenGER overlays.
 *
 * At app startup (providers.tsx) `loadExtensions()` imports every enabled
 * overlay in the order given by NEXT_PUBLIC_BENGER_EXTENSIONS (./enabled.ts
 * holds the env rule and the legacy NEXT_PUBLIC_BENGER_EDITION fallback) and
 * calls its `registerAll()`, which fills the slot, metric, wizard and
 * changelog registries. Overlays load one after another, each in its own
 * try/catch: a missing or crashing overlay logs a warning and the next one
 * still loads. While an overlay registers, the registration owner is set to
 * its name so the registries can attribute collisions (./owner.ts).
 *
 * The import specifiers are static strings because Turbopack has to resolve
 * them at build time. next.config.js aliases each `@benger/<name>` to the
 * overlay tree when the overlay is enabled and to ./community-stub.ts
 * otherwise, so the community build never fails on a package it does not
 * ship. Every overlay is loaded at most once per page load; a failed load is
 * retried on the next call.
 */

export {
  getChangelogEntries,
  registerChangelogEntries,
  useChangelogEntries,
} from './changelog'
export type { ChangelogAudience, ChangelogEntry } from './changelog'
export {
  enabledExtensions,
  EXTENSION_NAMES,
  isExtensionEnabled,
} from './enabled'
export type { ExtensionName } from './enabled'
export { getRegistrationOwner, setRegistrationOwner } from './owner'
export { getSlot, hasSlot, registerSlot, useSlot } from './slots'
export {
  getRegisteredWizardProjectTypes,
  getRegisteredWizardTemplates,
  getWizardKindPreset,
  getWizardPostCreateHooks,
  registerWizardKindPreset,
  registerWizardPostCreateHook,
  registerWizardProjectType,
  registerWizardTemplate,
} from './wizardTemplates'
export type {
  RegisteredWizardProjectType,
  RegisteredWizardTemplate,
  WizardKindPreset,
  WizardPostCreateHook,
} from './wizardTemplates'
export {
  getWritingPresenceReporter,
  registerWritingPresenceReporter,
} from './writingPresence'
export type { WritingPresenceReporter } from './writingPresence'

import {
  _resetEnabledExtensionsForTests,
  enabledExtensions,
  type ExtensionName,
} from './enabled'
import { setRegistrationOwner } from './owner'

interface Overlay {
  registerAll: () => void
}

/** Static import per overlay: Turbopack resolves the specifier at build time. */
const OVERLAYS: Record<ExtensionName, () => Promise<Overlay>> = {
  extended: () => import('@benger/extended'),
  compliance: () => import('@benger/compliance'),
}

const loaded = new Set<string>()
const inFlight = new Map<string, Promise<boolean>>()

async function loadOne(name: ExtensionName): Promise<boolean> {
  if (loaded.has(name)) return true
  const pending = inFlight.get(name)
  if (pending) return pending
  const attempt = (async () => {
    try {
      const overlay = await OVERLAYS[name]()
      setRegistrationOwner(name)
      try {
        overlay.registerAll()
      } finally {
        setRegistrationOwner(null)
      }
      loaded.add(name)
      return true
    } catch (error) {
      // The overlay is not shipped in this build, or its registerAll() threw.
      console.warn(`[extensions] overlay "${name}" failed to load`, error)
      return false
    } finally {
      inFlight.delete(name)
    }
  })()
  inFlight.set(name, attempt)
  return attempt
}

/**
 * Load every enabled overlay in order. Resolves with the names that are
 * registered afterwards (including ones loaded by an earlier call).
 */
export async function loadExtensions(): Promise<ExtensionName[]> {
  const result: ExtensionName[] = []
  for (const name of enabledExtensions()) {
    if (await loadOne(name)) result.push(name)
  }
  return result
}

/** Whether the named overlay has registered in this page load. */
export function isExtensionLoaded(name: string): boolean {
  return loaded.has(name)
}

/**
 * Legacy entry point from before the overlay list: loads every enabled
 * overlay and reports whether the extended one is registered.
 */
export async function loadExtended(): Promise<boolean> {
  const names = await loadExtensions()
  return names.includes('extended')
}

export function isExtendedLoaded(): boolean {
  return isExtensionLoaded('extended')
}

/** Test helper: forget loaded overlays, pending loads and the owner. */
export function _resetExtensionsForTests(): void {
  loaded.clear()
  inFlight.clear()
  setRegistrationOwner(null)
  _resetEnabledExtensionsForTests()
}

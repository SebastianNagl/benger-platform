/**
 * Which extension overlays are ACTIVE for the current viewer.
 *
 * Every overlay the build enables is loaded and registers at startup
 * (./index.ts), but whether its registrations count is decided at runtime by
 * the platform master flags `extension.<id>` (off / everyone / allowlist).
 * The feature flag store (lib/featureFlags) feeds the `extensions` part of
 * `GET /api/feature-flags/me` into this module; the registries (slots,
 * metrics, metric editors, wizard templates and hooks, wizard finish
 * contributors, writing presence, changelog, how-to) ask `isOwnerActive` when
 * they resolve a registration, so a switched-off overlay falls back to the
 * registration below it, or to none.
 *
 * Registrations made outside an overlay load (owner `platform`) are always
 * active. Never filtered by design: translations, label-config components and
 * metric renderers, so stored data keeps rendering while an overlay is off.
 *
 * Owner names equal the overlay names in ./enabled.ts (`extended`,
 * `compliance`), which are the ids of the master flags (`extension.<id>`).
 */

import { PLATFORM_OWNER } from './owner'

let active: ReadonlySet<string> = new Set()
// Sorted copy, replaced only on change: a stable useSyncExternalStore snapshot.
let activeList: readonly string[] = []
const listeners = new Set<() => void>()

function sameSet(a: ReadonlySet<string>, b: ReadonlySet<string>): boolean {
  if (a.size !== b.size) return false
  for (const name of a) if (!b.has(name)) return false
  return true
}

/** Replace the active set; listeners run only when it changed. */
export function setActiveExtensions(names: Iterable<string>): void {
  const next = new Set(names)
  if (sameSet(active, next)) return
  active = next
  activeList = Object.freeze([...next].sort())
  listeners.forEach((listener) => listener())
}

/** The active overlay names, sorted (the same array until the set changes). */
export function getActiveExtensions(): readonly string[] {
  return activeList
}

/** Whether registrations of `owner` count right now (platform: always). */
export function isOwnerActive(owner: string | null | undefined): boolean {
  if (!owner || owner === PLATFORM_OWNER) return true
  return active.has(owner)
}

/** Run `listener` whenever the active set changes; returns the unsubscribe. */
export function subscribeActiveExtensions(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Test helper: nothing active (listeners are kept). */
export function _resetActiveExtensionsForTests(): void {
  active = new Set()
  activeList = []
}

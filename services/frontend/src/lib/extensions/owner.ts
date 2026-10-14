/**
 * Registration owner: which extension overlay is registering right now.
 *
 * The loader (`loadExtensions` in ./index.ts) sets the owner to the overlay's
 * name around its `registerAll()` and clears it afterwards. Keyed registries
 * record the owner per key through `recordRegistration` and warn when a
 * different owner overwrites an earlier registration, so a collision between
 * two overlays (or between an overlay and platform code) shows up in the
 * console instead of silently going last-write-wins. The same owner may
 * re-register a key without a warning: React strict mode runs effects twice
 * and tests call registerAll() repeatedly.
 */

/** Label for registrations made outside any overlay load (platform code, tests). */
export const PLATFORM_OWNER = 'platform'

let currentOwner: string | null = null

export function setRegistrationOwner(name: string | null): void {
  currentOwner = name
}

export function getRegistrationOwner(): string | null {
  return currentOwner
}

/** Per-key owner memory of one registry. */
export type RegistrationOwners = Map<string, string | null>

/**
 * Remember the current owner for `key` in a registry of the given kind and
 * warn when it differs from the owner of the previous registration under the
 * same key. Call right before storing the value; the registry keeps its
 * last-write-wins behaviour either way.
 */
export function recordRegistration(
  owners: RegistrationOwners,
  kind: string,
  key: string,
): void {
  const owner = currentOwner
  if (owners.has(key)) {
    const previous = owners.get(key) ?? null
    if (previous !== owner) {
      console.warn(
        `[extensions] ${kind} "${key}" registered by ${owner ?? PLATFORM_OWNER} replaces ${previous ?? PLATFORM_OWNER}`,
      )
    }
  }
  owners.set(key, owner)
}

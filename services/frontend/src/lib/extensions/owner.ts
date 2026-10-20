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

/** Owner label of a registration made right now (platform when no overlay loads). */
export function currentOwnerLabel(): string {
  return currentOwner ?? PLATFORM_OWNER
}

/** One registration of a key, with the owner that made it. */
export interface OwnedRegistration<T> {
  owner: string
  value: T
}

/**
 * Per-key registration stacks of one registry, oldest first. Every owner
 * keeps at most one entry per key: a repeated registration by the same owner
 * replaces its value in place, a registration by another owner goes on top.
 * Which entry counts is decided at read time (`resolveRegistration`), so an
 * overlay switched off at runtime falls back to the registration below it.
 */
export type RegistrationStacks<T> = Map<string, OwnedRegistration<T>[]>

/** Push `value` for `key` under the current owner (see RegistrationStacks). */
export function pushRegistration<T>(
  stacks: RegistrationStacks<T>,
  key: string,
  value: T,
): void {
  const owner = currentOwnerLabel()
  const stack = stacks.get(key) ?? []
  const own = stack.find((entry) => entry.owner === owner)
  if (own) {
    own.value = value
  } else {
    stack.push({ owner, value })
  }
  stacks.set(key, stack)
}

/**
 * The newest registration of `key` whose owner `isActive` accepts, or
 * undefined. Registries pass `isOwnerActive` from ./active.
 */
export function resolveRegistration<T>(
  stacks: RegistrationStacks<T>,
  key: string,
  isActive: (owner: string) => boolean,
): T | undefined {
  const stack = stacks.get(key)
  if (!stack) return undefined
  for (let i = stack.length - 1; i >= 0; i--) {
    if (isActive(stack[i].owner)) return stack[i].value
  }
  return undefined
}

/**
 * Feature flags: `useFeatureFlag(name)` and the active extension packages.
 *
 * One module-level store per page, read through `useSyncExternalStore`, so no
 * provider is needed. The store holds the answer of
 * `GET /api/feature-flags/me` (`{flags: {name: bool}, extensions: {id: bool}}`)
 * for the current viewer, signed in or anonymous, and refetches it
 *
 *  - when the signed-in user changes (`useAuth().user?.id`, once auth has
 *    settled; FeatureFlagsSync in the app providers keeps it in step),
 *  - when the window regains focus (at most every FOCUS_REFETCH_MS),
 *  - when `refreshFeatureFlags()` is called (the admin console does after
 *    every write),
 *  - when the API answers 404 `feature_disabled` (./disabled.ts).
 *
 * A flag reads `false` while loading, after an error and for names the server
 * does not know. That way a gated feature never flashes up and then
 * disappears; the server enforces the same rule.
 *
 * `extensions` says which overlay packages (master flags `extension.<id>`)
 * are active for the viewer; it feeds lib/extensions/active.ts, which the
 * registries consult. While the answer is loading the last known set of the
 * same viewer (localStorage) stands in; without one nothing is active.
 */

import { useEffect, useSyncExternalStore } from 'react'

import { useAuth } from '@/contexts/AuthContext'
import apiClient from '@/lib/api'
import {
  getActiveExtensions,
  isOwnerActive,
  setActiveExtensions,
  subscribeActiveExtensions,
} from '@/lib/extensions/active'

import { setFeatureDisabledHandler } from './disabled'

/**
 * Any registered flag. The names belong to their owners (platform, extended,
 * compliance), which this module cannot enumerate; `string & {}` keeps
 * literal suggestions possible while accepting every name. The server
 * answers false for a name it does not know.
 */
export type FeatureFlagName = string & {}

export const FEATURE_FLAGS_ME_PATH = '/feature-flags/me'

/** Minimum gap between two focus-triggered refetches. */
export const FOCUS_REFETCH_MS = 30_000

/** localStorage key of the last known active extensions per viewer. */
export const ACTIVE_EXTENSIONS_STORAGE_KEY = 'benger.activeExtensions'

/** Viewers remembered in localStorage (the most recent ones). */
const MAX_REMEMBERED_VIEWERS = 10

/** Subject of an anonymous viewer (user ids are UUIDs, never this). */
const ANONYMOUS = 'anonymous'

type Status = 'idle' | 'loading' | 'ready' | 'error'

interface FlagState {
  /** User id, ANONYMOUS, or null before auth has settled. */
  subject: string | null
  flags: Record<string, boolean> | null
  status: Status
  /** Whether a last known extension set of this subject stood in. */
  seeded: boolean
}

const INITIAL: FlagState = {
  subject: null,
  flags: null,
  status: 'idle',
  seeded: false,
}

let state: FlagState = INITIAL
let generation = 0
let lastFetchAt = 0
let inFlight: Promise<void> | null = null
const listeners = new Set<() => void>()

// --- last known active extensions (localStorage, every access guarded) ---

interface StoredActive {
  last: string | null
  bySubject: Record<string, string[]>
}

function readStored(): StoredActive {
  const empty: StoredActive = { last: null, bySubject: {} }
  try {
    if (typeof window === 'undefined') return empty
    const raw = window.localStorage.getItem(ACTIVE_EXTENSIONS_STORAGE_KEY)
    if (!raw) return empty
    const parsed = JSON.parse(raw) as Partial<StoredActive> | null
    if (!parsed || typeof parsed !== 'object') return empty
    const bySubject: Record<string, string[]> = {}
    if (parsed.bySubject && typeof parsed.bySubject === 'object') {
      for (const [subject, names] of Object.entries(parsed.bySubject)) {
        if (Array.isArray(names)) {
          bySubject[subject] = names.filter(
            (n): n is string => typeof n === 'string',
          )
        }
      }
    }
    return {
      last: typeof parsed.last === 'string' ? parsed.last : null,
      bySubject,
    }
  } catch {
    return empty
  }
}

function writeStored(subject: string, names: readonly string[]): void {
  try {
    if (typeof window === 'undefined') return
    const stored = readStored()
    const bySubject: Record<string, string[]> = {}
    // Re-insert this subject last so the oldest viewers drop out first.
    const others = Object.entries(stored.bySubject).filter(
      ([s]) => s !== subject,
    )
    for (const [s, list] of others.slice(-(MAX_REMEMBERED_VIEWERS - 1))) {
      bySubject[s] = list
    }
    bySubject[subject] = [...names]
    window.localStorage.setItem(
      ACTIVE_EXTENSIONS_STORAGE_KEY,
      JSON.stringify({ last: subject, bySubject }),
    )
  } catch {
    // Storage blocked or full: the next page load just starts without a seed.
  }
}

/** The last known set of `subject`, or null when none is stored. */
function storedFor(subject: string): string[] | null {
  return readStored().bySubject[subject] ?? null
}

// --- store ---

function setState(next: FlagState) {
  state = next
  listeners.forEach((listener) => listener())
}

function onFocus() {
  if (!state.subject) return
  if (Date.now() - lastFetchAt < FOCUS_REFETCH_MS) return
  void refreshFeatureFlags()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  if (listeners.size === 1 && typeof window !== 'undefined') {
    window.addEventListener('focus', onFocus)
  }
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0 && typeof window !== 'undefined') {
      window.removeEventListener('focus', onFocus)
    }
  }
}

function getSnapshot() {
  return state
}

function toBoolMap(value: unknown): Record<string, boolean> {
  const out: Record<string, boolean> = {}
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [name, on] of Object.entries(value)) out[name] = on === true
  }
  return out
}

/** Fetch the current viewer's flags again (no-op before auth has settled). */
export async function refreshFeatureFlags(): Promise<void> {
  const subject = state.subject
  if (!subject) return
  const mine = ++generation
  lastFetchAt = Date.now()
  if (state.flags === null && state.status !== 'loading') {
    setState({ ...state, status: 'loading' })
  }
  const run = (async () => {
    try {
      ;(
        apiClient as { invalidateCache?: (pattern: string) => void }
      ).invalidateCache?.(FEATURE_FLAGS_ME_PATH)
      const answer = (await apiClient.get(FEATURE_FLAGS_ME_PATH)) as {
        flags?: unknown
        extensions?: unknown
      } | null
      if (mine !== generation) return
      const flags = toBoolMap(answer?.flags)
      const extensions = toBoolMap(answer?.extensions)
      const active = Object.keys(extensions).filter((id) => extensions[id])
      setActiveExtensions(active)
      writeStored(subject, getActiveExtensions())
      setState({ subject, flags, status: 'ready', seeded: state.seeded })
    } catch {
      if (mine !== generation) return
      // Fail closed for flags; the active extensions keep their last value.
      setState({ subject, flags: null, status: 'error', seeded: state.seeded })
    }
  })()
  inFlight = run
  try {
    await run
  } finally {
    if (inFlight === run) inFlight = null
  }
}

/**
 * Point the store at a viewer and load their flags: a user id, or null for
 * an anonymous viewer. Call only once auth has settled (FeatureFlagsSync).
 */
export function setFeatureFlagUser(userId: string | null): void {
  const subject = userId ?? ANONYMOUS
  if (subject === state.subject) return
  generation++
  const seed = storedFor(subject)
  setActiveExtensions(seed ?? [])
  setState({ subject, flags: null, status: 'loading', seeded: seed !== null })
  void refreshFeatureFlags()
}

// A `feature_disabled` 404 means the flags changed: refetch, unless a fetch
// is already on its way.
setFeatureDisabledHandler(() => {
  if (!inFlight) void refreshFeatureFlags()
})

// Before auth settles, the last viewer of this browser is the best guess.
;(() => {
  const stored = readStored()
  if (stored.last && stored.bySubject[stored.last]) {
    setActiveExtensions(stored.bySubject[stored.last])
  }
})()

/**
 * The current value outside React (event handlers, wizard hooks). Reads the
 * store as the mounted components loaded it; false until it has loaded.
 */
export function getFeatureFlag(name: FeatureFlagName): boolean {
  return state.flags?.[name] === true
}

/**
 * Keep the store pointed at the signed-in user (anonymous when nobody is
 * signed in), once auth has settled. Mounted once by the app providers;
 * the flag hooks call it too, which is idempotent.
 */
export function useFeatureFlagsSync(): void {
  const { user, isLoading } = useAuth()
  const userId = user?.id != null ? String(user.id) : null
  useEffect(() => {
    if (isLoading) return
    setFeatureFlagUser(userId)
  }, [userId, isLoading])
}

/** Renders nothing; keeps the flag store in step with the auth state. */
export function FeatureFlagsSync(): null {
  useFeatureFlagsSync()
  return null
}

export type FeatureFlagStatus = 'loading' | 'on' | 'off'

/**
 * Three-way answer for pages that act on "off" (redirect, not-available
 * notice) and must not do so before the answer is in. `loading` while auth
 * has not settled or the request runs; an error reads `off`.
 */
export function useFeatureFlagStatus(name: FeatureFlagName): FeatureFlagStatus {
  const { user, isLoading } = useAuth()
  const subject = user?.id != null ? String(user.id) : ANONYMOUS
  useFeatureFlagsSync()
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, () => INITIAL)
  if (isLoading || snapshot.subject !== subject) return 'loading'
  if (snapshot.status === 'loading' || snapshot.status === 'idle') {
    return 'loading'
  }
  return snapshot.flags?.[name] === true ? 'on' : 'off'
}

/** Whether `name` is on for the current viewer (false while loading). */
export function useFeatureFlag(name: FeatureFlagName): boolean {
  return useFeatureFlagStatus(name) === 'on'
}

const serverActive = (): readonly string[] => []

/** The extension packages active for the current viewer, sorted. */
export function useActiveExtensions(): readonly string[] {
  return useSyncExternalStore(
    subscribeActiveExtensions,
    getActiveExtensions,
    serverActive,
  )
}

/** Whether the extension package `id` is active for the current viewer. */
export function useExtensionActive(id: string): boolean {
  return useSyncExternalStore(
    subscribeActiveExtensions,
    () => isOwnerActive(id),
    () => false,
  )
}

/** Outside React: whether the extension package `id` is active right now. */
export function isExtensionActive(id: string): boolean {
  return isOwnerActive(id)
}

/**
 * Whether the active extensions can be trusted for the current viewer: the
 * server answered (or failed), or a last known set of this viewer stood in.
 * Shells that would otherwise flash the wrong layout wait for it.
 */
export function useActiveExtensionsReady(): boolean {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, () => INITIAL)
  if (!snapshot.subject) return false
  return (
    snapshot.seeded ||
    snapshot.status === 'ready' ||
    snapshot.status === 'error'
  )
}

/** Test helper: forget everything (listeners keep their own lifecycle). */
export function resetFeatureFlagsForTests(): void {
  generation++
  lastFetchAt = 0
  inFlight = null
  state = INITIAL
  setActiveExtensions([])
}

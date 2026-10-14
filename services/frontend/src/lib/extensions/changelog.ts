/**
 * Changelog entry registry for BenGER extended features.
 *
 * The /changelog page renders the platform's own entries plus whatever
 * the extended package registers here during initialization. Entries are
 * kept in per-source buckets so a repeated registerAll() (tests call it
 * directly) replaces a source's entries instead of duplicating them.
 */

import { useEffect, useState } from 'react'

export type ChangelogAudience = 'benger' | 'vertretbar' | 'both'

export interface ChangelogEntry {
  /**
   * Stable id, `<date>-<short-kebab-slug>`, unique across platform and
   * extensions. The bullet text lives in the locale catalogs at
   * `changelogEntries.<id>` (src/locales/<locale>/changelog.json, or the
   * extension's own changelog.json).
   */
  id: string
  /** ISO date the change shipped, 'YYYY-MM-DD'. */
  date: string
  audience: ChangelogAudience
  /**
   * Feature the entry announces. While it is off for the current user the
   * entry is hidden on /changelog. `publicApi` = access keys and /api/v1
   * (feature flag `public_api`).
   */
  requires?: 'publicApi'
}

/** The entries the current user may see, given what is switched on. */
export function filterAvailableChangelogEntries(
  entries: ChangelogEntry[],
  availability: { publicApi: boolean },
): ChangelogEntry[] {
  return entries.filter(
    (e) => e.requires !== 'publicApi' || availability.publicApi,
  )
}

const buckets: Record<string, ChangelogEntry[]> = {}
const listeners: Set<() => void> = new Set()

function notifyListeners() {
  listeners.forEach((fn) => fn())
}

/**
 * Register changelog entries under a named source.
 * Re-registering the same source replaces its entries (idempotent).
 * Notifies all useChangelogEntries() hooks to re-render.
 */
export function registerChangelogEntries(
  source: string,
  entries: ChangelogEntry[],
) {
  buckets[source] = entries
  notifyListeners()
}

/**
 * All registered entries, flattened across sources. Unsorted --
 * the changelog page owns ordering and grouping.
 */
export function getChangelogEntries(): ChangelogEntry[] {
  return Object.values(buckets).flat()
}

/**
 * React hook returning all registered entries.
 * Re-renders when entries are registered (handles async loadExtended).
 */
export function useChangelogEntries(): ChangelogEntry[] {
  const [, setTick] = useState(0)

  useEffect(() => {
    const listener = () => setTick((t) => t + 1)
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }, [])

  return getChangelogEntries()
}

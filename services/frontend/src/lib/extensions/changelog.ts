/**
 * Changelog entry registry for BenGER extended features.
 *
 * The /changelog page renders the platform's own entries plus whatever
 * the extended package registers here during initialization. Entries are
 * kept in per-source buckets so a repeated registerAll() (tests call it
 * directly; loadExtended has no re-entry guard) replaces a source's
 * entries instead of duplicating them.
 */

import { useEffect, useState } from 'react'

export type ChangelogAudience = 'benger' | 'vertretbar' | 'both'

export interface ChangelogEntry {
  /** ISO date the change shipped, 'YYYY-MM-DD'. */
  date: string
  audience: ChangelogAudience
  /** Bilingual copy, kept inline rather than in the locale JSONs. */
  text: { de: string; en: string }
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
    return () => { listeners.delete(listener) }
  }, [])

  return getChangelogEntries()
}

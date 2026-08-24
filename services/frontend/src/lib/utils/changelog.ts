import type {
  ChangelogAudience,
  ChangelogEntry,
} from '@/lib/extensions/changelog'

export interface ChangelogDateGroup {
  date: string
  entries: ChangelogEntry[]
}

/**
 * Keep entries matching the current brand ('both' always shows), grouped by
 * date, newest date first. Within a date, input order is preserved
 * (platform entries first, then extended).
 */
export function filterAndGroup(
  entries: ChangelogEntry[],
  brand: ChangelogAudience,
): ChangelogDateGroup[] {
  const groups = new Map<string, ChangelogEntry[]>()
  for (const entry of entries) {
    if (entry.audience !== 'both' && entry.audience !== brand) continue
    const group = groups.get(entry.date)
    if (group) {
      group.push(entry)
    } else {
      groups.set(entry.date, [entry])
    }
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0))
    .map(([date, dateEntries]) => ({ date, entries: dateEntries }))
}

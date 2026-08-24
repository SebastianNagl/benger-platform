import type { ChangelogEntry } from '@/lib/extensions/changelog'

/**
 * Platform changelog entries, newest first. One short user-facing bullet
 * per meaningful change; both languages. Extended-edition entries live in
 * the extended package and are merged in via registerChangelogEntries().
 */
export const PLATFORM_CHANGELOG: ChangelogEntry[] = [
  {
    date: '2026-08-24',
    audience: 'both',
    text: {
      de: 'Neue Changelog-Seite: alle Neuerungen im Überblick, erreichbar über den Footer.',
      en: "New changelog page: an overview of what's new, reachable from the footer.",
    },
  },
]

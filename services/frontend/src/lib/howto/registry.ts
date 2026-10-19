/**
 * How-To guide registry.
 *
 * The /how-to page renders the platform's own guides plus whatever the
 * extended package registers here during initialization (student-surface
 * guides, edition-specific answers). A guide object carries only structure
 * (id, category, link targets); its copy lives in the locale catalogs under
 * `howToGuides.<id>` and the category copy under `howToCategories.<id>`, so
 * every language (de, en, fr) is translated in one place. The extended
 * package ships its guide copy in its own catalog (registerTranslations).
 *
 * The same registry feeds the nav-bar search: every guide is a searchable
 * result that deep-links to its anchor on /how-to.
 */

import { useEffect, useState } from 'react'

import {
  isOwnerActive,
  subscribeActiveExtensions,
} from '@/lib/extensions/active'
import { currentOwnerLabel } from '@/lib/extensions/owner'
import { lookup } from '@/lib/i18n/catalog'
import { LOCALES, toLocale } from '@/lib/i18n/locales'

export type HowToCategoryId =
  | 'start'
  | 'organizations'
  | 'projects'
  | 'data'
  | 'annotation'
  | 'generation'
  | 'evaluation'
  | 'integrations'
  | 'student'
  | 'troubleshooting'

/** Category order = page order. Copy: `howToCategories.<id>.{title,blurb}`. */
export const HOWTO_CATEGORIES: { id: HowToCategoryId }[] = [
  { id: 'start' },
  { id: 'organizations' },
  { id: 'projects' },
  { id: 'data' },
  { id: 'annotation' },
  { id: 'generation' },
  { id: 'evaluation' },
  { id: 'integrations' },
  { id: 'student' },
  { id: 'troubleshooting' },
]

export type HowToCategory = (typeof HOWTO_CATEGORIES)[number]

/**
 * A guide's structure. Its copy lives in the catalog at `howToGuides.<id>`:
 * `title` (question-style, what users search for), `summary` (the short
 * answer), `steps[]`, `tips[]` ("good to know"), `pitfalls[]`, `keywords[]`
 * (extra search terms) and `links[]` (labels of `links`, same order).
 * Inline `code`, **bold** and [label](/path) in the copy are rendered.
 */
export interface HowToGuide {
  /** Stable anchor id, kebab-case; deep link is /how-to#<id>. */
  id: string
  category: HowToCategoryId
  /** Related pages / guides (guide anchors as /how-to#id); labels in the catalog. */
  links?: string[]
  /** Language-neutral search terms (e.g. error codes), matched in every locale. */
  searchTerms?: string[]
  /**
   * Feature the guide is about. While it is off for the current user the
   * guide is hidden on /how-to and in the nav search.
   * `publicApi` = access keys and /api/v1 (feature flag `public_api`).
   */
  requires?: 'publicApi'
}

/** What is switched on for the current user, for guides with `requires`. */
export interface HowToAvailability {
  publicApi: boolean
}

/** The guides the current user may see, given what is switched on. */
export function filterAvailableGuides(
  guides: HowToGuide[],
  availability: HowToAvailability,
): HowToGuide[] {
  return guides.filter(
    (g) => g.requires !== 'publicApi' || availability.publicApi,
  )
}

/** A guide's copy in one locale (missing lists come back empty). */
export interface HowToGuideText {
  title: string
  summary: string
  steps: string[]
  tips: string[]
  pitfalls: string[]
  keywords: string[]
  /** Link label + target pairs, in the order of `guide.links`. */
  links: { label: string; href: string }[]
}

function text(locale: string, key: string): string {
  const value = lookup(toLocale(locale), key)
  return typeof value === 'string' ? value : key
}

function list(locale: string, key: string): string[] {
  const value = lookup(toLocale(locale), key)
  return Array.isArray(value) ? value.map(String) : []
}

/** Title and blurb of a category in one locale. */
export function categoryText(
  id: HowToCategoryId,
  locale: string,
): { title: string; blurb: string } {
  return {
    title: text(locale, `howToCategories.${id}.title`),
    blurb: text(locale, `howToCategories.${id}.blurb`),
  }
}

/** All copy of a guide in one locale, from the catalog. */
export function guideText(guide: HowToGuide, locale: string): HowToGuideText {
  const base = `howToGuides.${guide.id}`
  const labels = list(locale, `${base}.links`)
  return {
    title: text(locale, `${base}.title`),
    summary: text(locale, `${base}.summary`),
    steps: list(locale, `${base}.steps`),
    tips: list(locale, `${base}.tips`),
    pitfalls: list(locale, `${base}.pitfalls`),
    keywords: list(locale, `${base}.keywords`),
    links: (guide.links ?? []).map((href, i) => ({
      label: labels[i] ?? href,
      href,
    })),
  }
}

const buckets: Record<string, { owner: string; guides: HowToGuide[] }> = {}
const listeners: Set<() => void> = new Set()

function notifyListeners() {
  listeners.forEach((fn) => fn())
}

/**
 * Register guides under a named source. Re-registering the same source
 * replaces its guides (idempotent), so tests and a repeated loadExtended()
 * never duplicate entries. The source remembers the registering owner; its
 * guides are listed only while that owner is active
 * (lib/extensions/active.ts).
 */
export function registerHowToGuides(source: string, guides: HowToGuide[]) {
  buckets[source] = { owner: currentOwnerLabel(), guides }
  notifyListeners()
}

/**
 * The guides of active owners in category order, sources in registration
 * order.
 */
export function getHowToGuides(): HowToGuide[] {
  const order = new Map(HOWTO_CATEGORIES.map((c, i) => [c.id, i]))
  return Object.values(buckets)
    .filter((bucket) => isOwnerActive(bucket.owner))
    .flatMap((bucket) => bucket.guides)
    .sort(
      (a, b) => (order.get(a.category) ?? 99) - (order.get(b.category) ?? 99),
    )
}

/**
 * React hook: the guides of active owners, re-rendering when a source
 * registers later or the active overlays change.
 */
export function useHowToGuides(): HowToGuide[] {
  const [, setTick] = useState(0)
  useEffect(() => {
    const listener = () => setTick((t) => t + 1)
    listeners.add(listener)
    const unsubscribeActive = subscribeActiveExtensions(listener)
    return () => {
      listeners.delete(listener)
      unsubscribeActive()
    }
  }, [])
  return getHowToGuides()
}

/** Plain text of guide copy: drops `code`, **bold**, *italic* markers and link targets. */
export function stripInlineMarkup(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*\s][^*]*)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
}

/** Lower-cased, diacritics-folded text for matching (ä→a, ß→ss). */
export function normalizeForSearch(text: string): string {
  return text
    .toLowerCase()
    .replace(/ß/g, 'ss')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
}

/**
 * Every word of a guide in one locale, used by the page filter and the nav
 * search. Keywords of all locales count too: users mix languages.
 */
export function guideSearchText(guide: HowToGuide, locale: string): string {
  const copy = guideText(guide, locale)
  const keywords = new Set<string>(copy.keywords)
  for (const other of LOCALES) {
    for (const k of list(other, `howToGuides.${guide.id}.keywords`)) {
      keywords.add(k)
    }
  }
  const parts = [
    copy.title,
    copy.summary,
    ...copy.steps,
    ...copy.tips,
    ...copy.pitfalls,
    ...keywords,
    ...(guide.searchTerms ?? []),
  ]
  return normalizeForSearch(stripInlineMarkup(parts.join(' ')))
}

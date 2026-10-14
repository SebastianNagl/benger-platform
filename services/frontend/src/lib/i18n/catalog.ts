/**
 * The translation catalog: one message tree per locale.
 *
 * Every user-visible string lives in a locale JSON, never inline in a
 * component. The platform tree is built from src/locales/<locale>/*.json;
 * an extension package (benger-extended, benger-compliance) adds its own
 * trees through registerTranslations() during initialization, so its copy
 * stays in its own repo. Lookups fall back from the active locale to English
 * and then German, so a key that one language is missing degrades to a
 * readable string instead of the raw key (the catalog parity tests keep that
 * from happening in practice).
 */

import { LOCALES, type Locale } from './locales'

// require() rather than import: typed JSON imports of the ~600 KB catalogs
// make tsc infer (and re-check) enormous literal types for no benefit.
/* eslint-disable @typescript-eslint/no-require-imports */
const platformSources: Record<Locale, Messages[]> = {
  de: [
    require('@/locales/de/common.json'),
    require('@/locales/de/howto.json'),
    require('@/locales/de/changelog.json'),
  ],
  en: [
    require('@/locales/en/common.json'),
    require('@/locales/en/howto.json'),
    require('@/locales/en/changelog.json'),
  ],
  fr: [
    require('@/locales/fr/common.json'),
    require('@/locales/fr/howto.json'),
    require('@/locales/fr/changelog.json'),
  ],
}
/* eslint-enable @typescript-eslint/no-require-imports */

export type Messages = { [key: string]: unknown }

export type TranslationVars = Record<string, unknown>

/** Per-locale message trees an extension contributes. */
export type TranslationBundle = Record<Locale, Messages>

function isPlainObject(value: unknown): value is Messages {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Deep merge `source` into `target` in place; source leaves win. */
function mergeInto(target: Messages, source: Messages): Messages {
  for (const [key, value] of Object.entries(source)) {
    const existing = target[key]
    if (isPlainObject(existing) && isPlainObject(value)) {
      mergeInto(existing, value)
    } else {
      target[key] = isPlainObject(value) ? mergeInto({}, value) : value
    }
  }
  return target
}

function build(...parts: Messages[]): Messages {
  return parts.reduce<Messages>((acc, part) => mergeInto(acc, part), {})
}

const platform = Object.fromEntries(
  LOCALES.map((locale) => [locale, build(...platformSources[locale])]),
) as Record<Locale, Messages>

const extensions = new Map<string, TranslationBundle>()
let catalogs: Record<Locale, Messages> = rebuild()
let version = 0
const listeners = new Set<() => void>()

function rebuild(): Record<Locale, Messages> {
  const next = {} as Record<Locale, Messages>
  for (const locale of LOCALES) {
    next[locale] = build(
      platform[locale],
      ...[...extensions.values()].map((bundle) => bundle[locale] ?? {}),
    )
  }
  return next
}

/**
 * Add an extension's message trees under a named source. Re-registering a
 * source replaces its trees (idempotent), and subscribed providers re-render
 * so copy registered after the first paint shows up immediately.
 */
export function registerTranslations(
  source: string,
  bundle: TranslationBundle,
) {
  extensions.set(source, bundle)
  catalogs = rebuild()
  version += 1
  listeners.forEach((fn) => fn())
}

export function subscribeTranslations(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Bumps on every registration; lets React consumers memoize on it. */
export function getTranslationsVersion(): number {
  return version
}

/** The merged message tree of a locale (platform + extensions). */
export function getMessages(locale: Locale): Messages {
  return catalogs[locale]
}

function resolve(tree: Messages, key: string): unknown {
  let value: unknown = tree
  for (const part of key.split('.')) {
    if (!isPlainObject(value)) return undefined
    value = value[part]
  }
  return value
}

const FALLBACK_CHAIN: Record<Locale, Locale[]> = {
  de: ['de', 'en'],
  en: ['en', 'de'],
  fr: ['fr', 'en', 'de'],
}

/**
 * The raw catalog value (string, list or number) for a key, walking the
 * fallback chain. Branch nodes don't count as a value.
 */
export function lookup(locale: Locale, key: string): unknown {
  for (const candidate of FALLBACK_CHAIN[locale]) {
    const value = resolve(catalogs[candidate], key)
    if (value !== undefined && !isPlainObject(value)) return value
  }
  return undefined
}

/** Whether the key has a leaf in the given locale itself (no fallback). */
export function hasTranslation(locale: Locale, key: string): boolean {
  const value = resolve(catalogs[locale], key)
  return value !== undefined && !isPlainObject(value)
}

export function interpolate(text: string, vars?: TranslationVars): string {
  if (!vars) return text
  return text.replace(/\{(\w+)\}/g, (match, name: string) =>
    vars[name] !== undefined ? String(vars[name]) : match,
  )
}

/**
 * Translate a key. Strings get their {placeholders} filled; lists come back
 * as-is (some keys are intentionally arrays). A key no locale carries
 * returns the key itself, which the catalog tests flag.
 */
export function translateKey(
  locale: Locale,
  key: string,
  vars?: TranslationVars,
): any {
  // Defensive: a non-string key (bad call site) comes back unchanged.
  if (typeof key !== 'string') return key
  const value = lookup(locale, key)
  if (value === undefined) return key
  if (typeof value === 'string') return interpolate(value, vars)
  return value
}

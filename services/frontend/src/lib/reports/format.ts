/**
 * Formatting helpers for the report viewer (pure, locale-aware).
 *
 * Numbers are formatted with `toLocaleString(locale)` so German readers get
 * "84,7 %" and English readers "84.7 %". The scale families mirror
 * `ReportMetricScale` / `MetricDisplayScale`.
 */
import type { ReportMethod, ReportMetricScale } from '@/types/report'

/** Minimal shape of a metric registry entry the viewer cares about. */
export interface MetricRegistryEntry {
  display_name?: string
  display_scale?: ReportMetricScale
}

export type MetricRegistry = Record<string, MetricRegistryEntry>

const LOCALE_TAGS: Record<string, string> = { de: 'de-DE', en: 'en-US' }

/** Map the app locale ('de' | 'en') to a BCP-47 tag for Intl APIs. */
export function localeTag(locale: string): string {
  return LOCALE_TAGS[locale] ?? locale
}

export function formatNumber(
  value: number,
  locale: string,
  maximumFractionDigits = 1,
  minimumFractionDigits = 0,
): string {
  return value.toLocaleString(localeTag(locale), {
    minimumFractionDigits,
    maximumFractionDigits,
  })
}

/** Integer counts ("3.626" in German). */
export function formatCount(value: number, locale: string): string {
  return formatNumber(value, locale, 0)
}

/**
 * Format a metric aggregate per scale family:
 * - '0-1'   → "84,7 %"
 * - '0-100' → "84,7 / 100"
 * - '0-18'  → "13,9 NP"
 * - 'raw'   → two decimals
 */
export function formatMetricValue(
  value: number | null | undefined,
  scale: ReportMetricScale | undefined,
  locale: string,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'
  switch (scale) {
    case '0-1':
      return `${formatNumber(value * 100, locale, 1)} %`
    case '0-100':
      return `${formatNumber(value, locale, 1)} / 100`
    case '0-18':
      return `${formatNumber(value, locale, 1)} NP`
    default:
      return formatNumber(value, locale, 2, 2)
  }
}

/** Grade points with the full denominator: "13,9 / 18 NP". */
export function formatGradePoints(
  value: number | null | undefined,
  locale: string,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'
  return `${formatNumber(value, locale, 1)} / 18 NP`
}

/** A 0..1 rate as a whole percentage: 0.93 → "93 %". */
export function formatRate(
  rate: number | null | undefined,
  locale: string,
): string {
  if (rate === null || rate === undefined || Number.isNaN(rate)) return '–'
  return `${formatNumber(rate * 100, locale, 0)} %`
}

/** "llm_judge_falloesung_grade_points" → "Llm Judge Falloesung Grade Points". */
export function humanizeMetricId(id: string): string {
  return id
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/**
 * Display name for a metric id: registry display_name first (extended may
 * register nicer names), then the snapshot method name, then a humanized id.
 */
export function metricLabel(
  id: string,
  methods: ReportMethod[] | undefined,
  registry?: MetricRegistry,
): string {
  const fromRegistry = registry?.[id]?.display_name
  if (fromRegistry) return fromRegistry
  const fromSnapshot = methods?.find((m) => m.id === id)?.name
  if (fromSnapshot) return fromSnapshot
  return humanizeMetricId(id)
}

/** Scale for a metric id: snapshot method first, then registry, then 'raw'. */
export function metricScale(
  id: string,
  methods: ReportMethod[] | undefined,
  registry?: MetricRegistry,
): ReportMetricScale {
  const fromSnapshot = methods?.find((m) => m.id === id)?.scale
  if (fromSnapshot) return fromSnapshot
  return registry?.[id]?.display_scale ?? 'raw'
}

/** Human-readable scale description (German, matches the viewer's language). */
export function scaleLabel(scale: ReportMetricScale | undefined): string {
  switch (scale) {
    case '0-1':
      return '0–1 (Anteil)'
    case '0-100':
      return '0–100 Punkte'
    case '0-18':
      return '0–18 Notenpunkte'
    default:
      return 'Rohwert'
  }
}

/** Upper bound of a scale for axis domains; null for open-ended raw values. */
export function scaleMax(scale: ReportMetricScale | undefined): number | null {
  switch (scale) {
    case '0-1':
      return 1
    case '0-100':
      return 100
    case '0-18':
      return 18
    default:
      return null
  }
}

/** Short tick formatter for chart axes (no unit suffix noise). */
export function formatAxisValue(
  value: number,
  scale: ReportMetricScale | undefined,
  locale: string,
): string {
  if (scale === '0-1') return `${formatNumber(value * 100, locale, 0)} %`
  return formatNumber(value, locale, scale === 'raw' ? 2 : 0)
}

/** Date-only formatting ("2. September 2026"); returns '' for invalid input. */
export function formatDate(iso: string | null | undefined, locale: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(localeTag(locale), {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

/** Date + time for the snapshot line ("2. Sept. 2026, 14:00"). */
export function formatDateTime(
  iso: string | null | undefined,
  locale: string,
): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString(localeTag(locale), {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

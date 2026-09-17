/**
 * Display helpers for the evaluation run page (`/evaluations/[id]`) and its
 * per-sample table.
 *
 * The worker stores what it needs to stay unambiguous: metric keys composed
 * as `config|pred_field|ref_field|metric`, sample field keys as
 * `config|pred_field|ref_field`, companion keys such as `raw_score` or
 * `<metric>_passed`, reason codes and English diagnostics. None of that is
 * meant for a reader. These helpers turn it into labels in the reader's
 * language and keep the parsing in one tested place.
 */

import {
  getFieldLabel,
  getMetricDefinitions,
  metricDisplayName,
  type AvailableMetric,
} from '@/lib/api/evaluation-types'
import { humanizeMetricId } from '@/lib/reports/format'

type Translate = (
  key: string,
  varsOrFallback?: Record<string, unknown> | string,
) => string

/** An evaluation config as far as labels are concerned. */
export interface RunConfigLabel {
  id?: string
  display_name?: string | null
  metric?: string
}

/** Bare metric name of an aggregated metrics key (`config|pred|ref|metric`,
 * the legacy `:`-delimited form, or a plain name). */
export function bareMetricName(key: string): string {
  if (key.includes('|')) return key.split('|').pop() || key
  if (key.includes(':')) return key.split(':').slice(3).join(':') || key
  return key
}

/** Config id of an aggregated metrics key, or null for a plain name. */
export function metricKeyConfigId(key: string): string | null {
  if (key.includes('|')) return key.split('|')[0] || null
  if (key.includes(':') && key.split(':').length >= 4) {
    return key.split(':')[0] || null
  }
  return null
}

/**
 * Companion values a metric writes next to its score: the raw score, the
 * pass flag, detail blobs and raw outputs. They are bookkeeping, not results.
 * `<metric>_grade_points` is a result (Notenpunkte) and stays visible under
 * its registered label.
 */
export function isSidecarMetricKey(key: string): boolean {
  const bare = bareMetricName(key)
  return (
    bare === 'raw_score' ||
    bare.endsWith('_passed') ||
    bare.endsWith('_details') ||
    bare.endsWith('_raw')
  )
}

/** Display name of a metric: the registry's name (translated when the metric
 * carries a key and a translator is given), else the humanized id. */
export function metricDisplayLabel(
  key: string,
  registry: Record<string, AvailableMetric> = getMetricDefinitions(),
  t?: Translate,
): string {
  const bare = bareMetricName(key)
  const def = registry[bare]
  if (!def?.display_name) return humanizeMetricId(bare)
  return t ? metricDisplayName(def, t) : def.display_name
}

/** Format an aggregated or per-sample number according to the metric scale. */
export function formatMetricNumber(
  key: string,
  value: number,
  registry: Record<string, AvailableMetric> = getMetricDefinitions(),
): string {
  const scale = registry[bareMetricName(key)]?.display_scale
  if (scale === '0-18') return value.toFixed(1)
  return value.toFixed(3)
}

/** The three parts of a sample's field key. A plain field name has no config
 * and no reference. */
export function parseSampleFieldKey(fieldName: string): {
  configId: string | null
  predictionField: string
  referenceField: string | null
} {
  const parts = fieldName.split('|')
  if (parts.length >= 3) {
    return {
      configId: parts[0] || null,
      predictionField: parts[1],
      referenceField: parts.slice(2).join('|'),
    }
  }
  return { configId: null, predictionField: fieldName, referenceField: null }
}

function xmlAttribute(attrs: string, name: string): string | null {
  const match = new RegExp(`\\b${name}\\s*=\\s*"([^"]*)"`).exec(attrs)
  return match ? match[1] : null
}

/** The `<Header value>` directly preceding the element named `field` in a
 * label config, or null when the field has no header of its own. */
export function headerForField(
  labelConfig: string | null | undefined,
  field: string,
): string | null {
  if (!labelConfig || !field) return null
  const tag = /<\s*([A-Za-z][\w-]*)\b([^>]*)>/g
  let lastHeader: string | null = null
  for (let m = tag.exec(labelConfig); m; m = tag.exec(labelConfig)) {
    const [, type, attrs] = m
    if (type.toLowerCase() === 'header') {
      lastHeader = xmlAttribute(attrs, 'value')
      continue
    }
    const name = xmlAttribute(attrs, 'name')
    if (name === null) continue
    if (name === field) return lastHeader?.trim() || null
    lastHeader = null
  }
  return null
}

/** Readable name of a prediction or reference field selector: the special
 * selectors' translated names, else the header the project's label config
 * gives the field, else the field name without its role prefix. */
export function fieldSelectorLabel(
  field: string,
  t: Translate,
  labelConfig?: string | null,
): string {
  const special = getFieldLabel(field, (key) => t(key))
  if (special !== field) return special
  const bare = field.replace(/^(human:|model:|task\.)/, '')
  return headerForField(labelConfig, bare) ?? bare
}

/** Display name of a config: its own name, else its metric's name. */
export function configDisplayLabel(
  configId: string | null,
  configs: ReadonlyArray<RunConfigLabel>,
  fallbackMetric?: string,
  t?: Translate,
): string | null {
  const config = configId ? configs.find((c) => c.id === configId) : undefined
  if (config?.display_name) return config.display_name
  const metric = config?.metric || fallbackMetric
  return metric ? metricDisplayLabel(metric, undefined, t) : null
}

/**
 * Mean of a bare metric over one config's field pairs in `results_by_config`
 * (`{config: {pred_vs_ref: {metric: value}}}`), or null when the config has
 * no numeric value for it.
 */
export function configMetricMean(
  resultsByConfig:
    Record<string, Record<string, Record<string, unknown>>> | null | undefined,
  configId: string,
  metric: string,
): number | null {
  const pairs = resultsByConfig?.[configId]
  if (!pairs || !metric) return null
  const values = Object.values(pairs)
    .map((scores) => scores?.[metric])
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  if (values.length === 0) return null
  return values.reduce((sum, v) => sum + v, 0) / values.length
}

const RUN_STATUSES = new Set([
  'completed',
  'failed',
  'running',
  'pending',
  'queued',
  'cancelled',
  'paused',
])

/** Localized label of a run status; an unknown status shows as stored. */
export function runStatusLabel(status: string, t: Translate): string {
  if (!RUN_STATUSES.has(status)) return status
  return t(`evaluations.detail.statusLabels.${status}`)
}

/** One config's record in `eval_metadata.match_by_config`. */
export interface ConfigMatchRecord {
  metric: string
  display_name?: string | null
  human_fields?: string[]
  llm_fields?: string[]
  reason: string | null
  /** Subjects on the run's tasks, written with every unmatched config. */
  subject_counts?: { generations?: number; annotations?: number } | null
}

const REASON_KEYS: Record<string, string> = {
  no_generations: 'noGenerations',
  generation_filters_excluded_all: 'generationFiltersExcludedAll',
  no_annotations: 'noAnnotations',
  all_annotations_cancelled: 'allAnnotationsCancelled',
  annotator_filter_excluded_all: 'annotatorFilterExcludedAll',
  no_prediction_fields: 'noPredictionFields',
  classifier_unavailable: 'classifierUnavailable',
  other: 'other',
}

/**
 * Why a config matched nothing, phrased in the reader's language. The two
 * side-mismatch reasons name what the other side holds when the worker
 * recorded subject counts. Returns null for a code this page does not know,
 * so the caller can fall back to the worker's own message.
 */
export function describeConfigMatchReason(
  record: ConfigMatchRecord,
  t: Translate,
): string | null {
  const reason = record.reason
  if (!reason || !(reason in REASON_KEYS)) return null
  const base = `evaluations.detail.matchReasons.${REASON_KEYS[reason]}`
  const generations = record.subject_counts?.generations
  const annotations = record.subject_counts?.annotations
  const haveCounts =
    typeof generations === 'number' && typeof annotations === 'number'

  if (reason === 'no_generations' && haveCounts) {
    return annotations > 0
      ? t(`${base}WithAnswers`, { count: annotations })
      : t(`${base}Nothing`)
  }
  if (reason === 'no_annotations' && haveCounts) {
    return generations > 0
      ? t(`${base}WithGenerations`, { count: generations })
      : t(`${base}Nothing`)
  }
  return t(base)
}

/** Prefix the worker writes when the billing policy refused a run. */
const BILLING_BLOCKED_PREFIX = 'billing_blocked:'

const BILLING_BLOCK_KEYS: Record<string, string> = {
  org_not_paying: 'orgNotPaying',
  org_key_missing: 'orgKeyMissing',
  connection_removed: 'connectionRemoved',
  billing_check_failed: 'checkFailed',
}

/**
 * The reader's sentence for a run the billing policy refused
 * (`billing_blocked:<reason>`, e.g. an exam linked to a learning platform
 * whose organization provides no API key), else null.
 */
export function describeBillingBlock(
  errorMessage: string | null | undefined,
  t: Translate,
): string | null {
  if (!errorMessage?.startsWith(BILLING_BLOCKED_PREFIX)) return null
  const reason = errorMessage.slice(BILLING_BLOCKED_PREFIX.length).trim()
  const key = Object.prototype.hasOwnProperty.call(BILLING_BLOCK_KEYS, reason)
    ? BILLING_BLOCK_KEYS[reason]
    : 'other'
  return t(`evaluations.detail.billingBlocked.${key}`)
}

/** Reasons that mean nothing was left to do, not that the run failed. */
export const BENIGN_MATCH_REASONS = new Set([
  'all_cells_already_evaluated',
  'manual_metric',
])

// Word bookmark anchors that .docx conversion leaves in stored text.
const EMPTY_ANCHOR = /<a\s+id="[^"]*"\s*>\s*<\/a>/g
// Markdown escapes the .docx conversion writes before punctuation
// (`A\. Zulässigkeit`, `Polizei\- und`).
const MARKDOWN_ESCAPE = /\\([\\`*_{}[\]()#+\-.!|<>~])/g
// Bold markers (`__Lösungshinweise__`, `**fett**`), also when a converted
// span is empty or crosses a line break. Single `_` and `*` stay.
const MARKDOWN_STRONG = /\*\*|__/g

function plainText(value: string): string {
  return value
    .replace(EMPTY_ANCHOR, '')
    .replace(MARKDOWN_STRONG, '')
    .replace(MARKDOWN_ESCAPE, '$1')
}

/**
 * A stored reference or prediction as text a reader can follow. Strings are
 * shown as plain text (without Word bookmark anchors, bold markers and the
 * Markdown escapes of converted .docx files), a single-string wrapper such as
 * `{text: "..."}` is unwrapped, anything structured is pretty-printed JSON.
 * `isStructured` tells the caller which of the two.
 */
export function readableSampleValue(value: unknown): {
  text: string
  isStructured: boolean
} {
  if (value === null || value === undefined) {
    return { text: '', isStructured: false }
  }
  if (typeof value === 'string') {
    return { text: plainText(value), isStructured: false }
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return { text: String(value), isStructured: false }
  }
  if (typeof value === 'object' && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 1 && typeof entries[0][1] === 'string') {
      return readableSampleValue(entries[0][1])
    }
  }
  return { text: JSON.stringify(value, null, 2), isStructured: true }
}

import type { EvaluationConfig } from '@/lib/api/evaluation-types'

/**
 * Bring the evaluation card's buffer up to date with the server after
 * another writer changed the stored configs (e.g. a section that saves
 * grading policy keys into `metric_parameters` on its own).
 *
 * The card auto-saves its whole `evaluation_configs` list and the server
 * replaces that list, so a buffer that missed the other write would put the
 * old values back on the next card save. This is a three-way merge:
 *
 * - `baseline`: the list as the card last read or saved it,
 * - `local`: the card's buffer (baseline plus any unsaved user edits),
 * - `fresh`: the list the server holds now.
 *
 * Without unsaved edits the result is `fresh`. With edits, whatever the user
 * changed wins and everything else comes from the server: per config (matched
 * by id), each top-level field the user changed keeps the local value, and
 * `metric_parameters` merges key by key the same way. Configs the user added
 * stay, configs the user removed stay removed, configs only the server has
 * (added elsewhere since the baseline) are appended.
 */
export function refreshEvaluationConfigs(
  baseline: EvaluationConfig[],
  local: EvaluationConfig[],
  fresh: EvaluationConfig[],
): EvaluationConfig[] {
  if (sameValue(local, baseline)) return fresh

  const baselineById = new Map(baseline.map((c) => [c.id, c]))
  const freshById = new Map(fresh.map((c) => [c.id, c]))
  const localIds = new Set(local.map((c) => c.id))

  const merged: EvaluationConfig[] = []
  for (const config of local) {
    const base = baselineById.get(config.id)
    const server = freshById.get(config.id)
    if (!base) {
      // Added by the user and not saved yet.
      merged.push(config)
    } else if (!server) {
      // Deleted on the server meanwhile: keep it only if the user edited it.
      if (!sameValue(config, base)) merged.push(config)
    } else {
      merged.push(mergeConfig(base, config, server))
    }
  }
  for (const server of fresh) {
    if (!localIds.has(server.id) && !baselineById.has(server.id)) {
      merged.push(server)
    }
  }
  return merged
}

function mergeConfig(
  base: EvaluationConfig,
  local: EvaluationConfig,
  server: EvaluationConfig,
): EvaluationConfig {
  const result = mergeRecords(
    base as unknown as Record<string, unknown>,
    local as unknown as Record<string, unknown>,
    server as unknown as Record<string, unknown>,
    ['metric_parameters'],
  )
  const params = mergeRecords(
    (base.metric_parameters ?? {}) as Record<string, unknown>,
    (local.metric_parameters ?? {}) as Record<string, unknown>,
    (server.metric_parameters ?? {}) as Record<string, unknown>,
    [],
  )
  if (
    Object.keys(params).length > 0 ||
    local.metric_parameters !== undefined ||
    server.metric_parameters !== undefined
  ) {
    result.metric_parameters = params
  }
  return result as unknown as EvaluationConfig
}

/** Key-wise three-way merge: a key the user changed keeps its local value. */
function mergeRecords(
  base: Record<string, unknown>,
  local: Record<string, unknown>,
  server: Record<string, unknown>,
  skip: string[],
): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  const keys = new Set([
    ...Object.keys(base),
    ...Object.keys(local),
    ...Object.keys(server),
  ])
  for (const key of keys) {
    if (skip.includes(key)) continue
    const edited = !sameValue(local[key], base[key])
    const value = edited ? local[key] : server[key]
    if (value !== undefined) result[key] = value
  }
  return result
}

function sameValue(a: unknown, b: unknown): boolean {
  return JSON.stringify(canonical(a)) === JSON.stringify(canonical(b))
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical)
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const key of Object.keys(value).sort()) {
      const v = (value as Record<string, unknown>)[key]
      if (v !== undefined) out[key] = canonical(v)
    }
    return out
  }
  return value
}

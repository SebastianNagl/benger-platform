/**
 * Labels of the analysis views: system keys, scope levels and chart labels.
 * Plain text helpers with no formatting of numbers (see ./results).
 */

/** A system key `model@profilehash` split for display. */
export function systemParts(key: string | null | undefined): {
  model: string
  profile: string | null
} {
  if (!key) return { model: '', profile: null }
  const at = key.lastIndexOf('@')
  if (at <= 0) return { model: key, profile: null }
  return { model: key.slice(0, at), profile: key.slice(at + 1) }
}

/**
 * Chart labels of system keys: the model alone where no other key shares
 * it, else the model with `@` and the first 6 characters of the profile.
 */
export function systemLabels(
  keys: readonly (string | null | undefined)[],
): Map<string, string> {
  const parts = [...new Set(keys.map((k) => k ?? ''))].map((key) => ({
    key,
    ...systemParts(key),
  }))
  return new Map(
    parts.map(({ key, model, profile }) => [
      key,
      profile && parts.filter((p) => p.model === model).length > 1
        ? `${model}@${profile.slice(0, 6)}`
        : model || key,
    ]),
  )
}

/**
 * A label cut to `max` characters in the middle of its part before the last
 * `@`, so an `@profile` suffix always stays whole.
 */
export function shortenLabel(label: string, max: number): string {
  if (label.length <= max) return label
  const at = label.lastIndexOf('@')
  const suffix = at > 0 ? label.slice(at) : ''
  const head = at > 0 ? label.slice(0, at) : label
  const room = Math.max(2, max - suffix.length - 1)
  const front = Math.ceil(room / 2)
  return `${head.slice(0, front)}…${head.slice(head.length - (room - front))}${suffix}`
}

/** The text of a factor level or scope value (numbers as the engine names them). */
export function levelText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

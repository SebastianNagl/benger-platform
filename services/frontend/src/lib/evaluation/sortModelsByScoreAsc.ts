/**
 * Pure ordering helper for the model-comparison bar chart (Issue C).
 *
 * The chart's bar / X-axis order is simply the order of the `models` array it
 * receives. The backend returns models DESCENDING by score; this helper
 * re-orders them ASCENDING (lowest first) so bars read left-to-right from
 * worst to best.
 *
 * The average score used for ordering is the mean of the given `metricNames`
 * for each model. A metric that is missing (or whose value can't be resolved)
 * counts as 0, so models with no score cluster at the bottom.
 *
 * The function is pure: it returns a new array and never mutates its input,
 * and the sort is stable (models with equal scores keep their original order).
 */

interface MetricValueLike {
  value: number
}

type MetricEntry = number | MetricValueLike | null | undefined

interface ModelWithMetrics {
  metrics?: Record<string, MetricEntry>
}

/** Resolve a metric entry to a plain number, treating anything unusable as 0. */
function resolveMetricValue(entry: MetricEntry): number {
  if (typeof entry === 'number') {
    return Number.isFinite(entry) ? entry : 0
  }
  if (entry && typeof entry === 'object' && typeof entry.value === 'number') {
    return Number.isFinite(entry.value) ? entry.value : 0
  }
  return 0
}

/** Mean of the given metric names for a single model (missing → 0). */
export function averageMetricScore<T extends ModelWithMetrics>(
  model: T,
  metricNames: string[]
): number {
  if (!metricNames || metricNames.length === 0) return 0
  const metrics = model.metrics ?? {}
  let sum = 0
  for (const name of metricNames) {
    sum += resolveMetricValue(metrics[name])
  }
  return sum / metricNames.length
}

/**
 * Return a NEW array of `models` sorted ascending by their average score
 * across `metricNames`. Stable; does not mutate the input.
 */
export function sortModelsByScoreAsc<T extends ModelWithMetrics>(
  models: readonly T[],
  metricNames: string[]
): T[] {
  return models
    .map((model, index) => ({
      model,
      index,
      score: averageMetricScore(model, metricNames),
    }))
    .sort((a, b) => a.score - b.score || a.index - b.index)
    .map((entry) => entry.model)
}

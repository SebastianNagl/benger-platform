import {
  averageMetricScore,
  sortModelsByScoreAsc,
} from '../sortModelsByScoreAsc'

const ids = (models: { model_id: string }[]) => models.map((m) => m.model_id)

describe('averageMetricScore', () => {
  it('averages across the given metric names', () => {
    const model = { model_id: 'a', metrics: { acc: 0.8, f1: 0.4 } }
    expect(averageMetricScore(model, ['acc', 'f1'])).toBeCloseTo(0.6)
  })

  it('treats a missing metric as 0', () => {
    const model = { model_id: 'a', metrics: { acc: 0.8 } }
    // (0.8 + 0) / 2
    expect(averageMetricScore(model, ['acc', 'f1'])).toBeCloseTo(0.4)
  })

  it('unwraps MetricValue objects via .value', () => {
    const model = { model_id: 'a', metrics: { acc: { value: 0.9 } } }
    expect(averageMetricScore(model, ['acc'])).toBeCloseTo(0.9)
  })

  it('returns 0 when metricNames is empty', () => {
    const model = { model_id: 'a', metrics: { acc: 0.9 } }
    expect(averageMetricScore(model, [])).toBe(0)
  })

  it('returns 0 when the model has no metrics object', () => {
    const model = { model_id: 'a' }
    expect(averageMetricScore(model, ['acc'])).toBe(0)
  })
})

describe('sortModelsByScoreAsc', () => {
  it('orders models ascending by single-metric score (lowest first)', () => {
    const models = [
      { model_id: 'mid', metrics: { acc: 0.5 } },
      { model_id: 'high', metrics: { acc: 0.9 } },
      { model_id: 'low', metrics: { acc: 0.1 } },
    ]
    expect(ids(sortModelsByScoreAsc(models, ['acc']))).toEqual([
      'low',
      'mid',
      'high',
    ])
  })

  it('orders by the AVERAGE across multiple metrics', () => {
    const models = [
      // avg 0.7
      { model_id: 'balanced', metrics: { acc: 0.7, f1: 0.7 } },
      // avg 0.5
      { model_id: 'lopsided', metrics: { acc: 0.9, f1: 0.1 } },
    ]
    expect(ids(sortModelsByScoreAsc(models, ['acc', 'f1']))).toEqual([
      'lopsided',
      'balanced',
    ])
  })

  it('sorts models with a missing metric (score 0) to the bottom', () => {
    const models = [
      { model_id: 'scored', metrics: { acc: 0.3 } },
      { model_id: 'unscored', metrics: {} },
    ]
    expect(ids(sortModelsByScoreAsc(models, ['acc']))).toEqual([
      'unscored',
      'scored',
    ])
  })

  it('is stable for ties (preserves input order)', () => {
    const models = [
      { model_id: 'first', metrics: { acc: 0.5 } },
      { model_id: 'second', metrics: { acc: 0.5 } },
      { model_id: 'third', metrics: { acc: 0.5 } },
    ]
    expect(ids(sortModelsByScoreAsc(models, ['acc']))).toEqual([
      'first',
      'second',
      'third',
    ])
  })

  it('does not mutate the input array', () => {
    const models = [
      { model_id: 'b', metrics: { acc: 0.9 } },
      { model_id: 'a', metrics: { acc: 0.1 } },
    ]
    const snapshot = ids(models)
    sortModelsByScoreAsc(models, ['acc'])
    expect(ids(models)).toEqual(snapshot)
  })

  it('returns an empty array for empty input', () => {
    expect(sortModelsByScoreAsc([], ['acc'])).toEqual([])
  })
})

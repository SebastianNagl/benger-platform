import { REPORT_SNAPSHOT_FIXTURE as FIX } from '../fixture'
import {
  binLabel,
  configsForMetric,
  distributionFor,
  isHiddenMetricKey,
  otherMetricColumns,
  rankSeries,
  selectPrimary,
  selectVisibleConfigs,
  toPercentSeries,
  topSubjectDistributions,
} from '../select'

describe('select helpers', () => {
  it('flags hidden companion keys', () => {
    expect(isHiddenMetricKey('llm_judge_falloesung_raw')).toBe(true)
    expect(isHiddenMetricKey('llm_judge_falloesung_passed')).toBe(true)
    expect(isHiddenMetricKey('llm_judge_falloesung_details')).toBe(true)
    expect(isHiddenMetricKey('llm_judge_falloesung')).toBe(false)
    expect(isHiddenMetricKey('llm_judge_falloesung_grade_points')).toBe(false)
  })

  describe('selectVisibleConfigs', () => {
    it('returns all configs without a filter', () => {
      expect(selectVisibleConfigs(FIX, undefined)).toHaveLength(4)
      expect(selectVisibleConfigs(FIX, { visible_configs: [] })).toHaveLength(4)
    })

    it('filters by visible_configs in snapshot order', () => {
      const out = selectVisibleConfigs(FIX, { visible_configs: ['cfg-bleu', 'cfg-judge-mini'] })
      expect(out.map((c) => c.id)).toEqual(['cfg-judge-mini', 'cfg-bleu'])
    })
  })

  describe('selectPrimary', () => {
    it('uses the snapshot defaults', () => {
      expect(selectPrimary(FIX, undefined)).toEqual({
        metric: 'llm_judge_falloesung',
        configId: 'cfg-judge-sonnet',
        gradeMetric: 'llm_judge_falloesung_grade_points',
      })
    })

    it('honours editor overrides', () => {
      expect(selectPrimary(FIX, { primary_config_id: 'cfg-judge-mini' }).configId).toBe('cfg-judge-mini')
      const bleu = selectPrimary(FIX, { primary_metric: 'bleu' })
      expect(bleu).toEqual({ metric: 'bleu', configId: 'cfg-bleu', gradeMetric: null })
    })

    it('falls back to the first visible config for the metric when the preferred one is hidden', () => {
      const sel = selectPrimary(FIX, { visible_configs: ['cfg-judge-mini', 'cfg-bleu'] })
      expect(sel.configId).toBe('cfg-judge-mini')
    })

    it('ignores a primary_config_id that scores a different metric', () => {
      expect(selectPrimary(FIX, { primary_config_id: 'cfg-bleu' }).configId).toBe('cfg-judge-sonnet')
    })

    it('returns nulls when no metric can be resolved', () => {
      expect(selectPrimary({ ...FIX, primary_metric: null }, undefined)).toEqual({
        metric: null,
        configId: null,
        gradeMetric: null,
      })
      expect(selectPrimary(FIX, { visible_configs: ['cfg-bleu'] }).configId).toBeNull()
    })
  })

  it('lists selector options for the primary metric', () => {
    expect(configsForMetric(FIX.configs, 'llm_judge_falloesung').map((c) => c.id)).toEqual([
      'cfg-judge-sonnet',
      'cfg-judge-mini',
    ])
    expect(configsForMetric(FIX.configs, null)).toEqual([])
  })

  describe('rankSeries', () => {
    it('ranks models DESC by mean with ranks from the sort', () => {
      const rows = rankSeries(FIX.series, 'cfg-judge-sonnet', 'llm_judge_falloesung', 'model')
      expect(rows.map((r) => [r.rank, r.subject.label])).toEqual([
        [1, 'GPT-5.4'],
        [2, 'Claude Opus 4.7'],
        [3, 'DeepSeek V4 Flash'],
        [4, 'Llama 4 Maverick'],
      ])
      expect(rows[0].primary.mean).toBe(84.7)
    })

    it('does not rank by array order', () => {
      const reversed = [...FIX.series].reverse()
      const rows = rankSeries(reversed, 'cfg-judge-sonnet', 'llm_judge_falloesung', 'model')
      expect(rows[0].subject.label).toBe('GPT-5.4')
      expect(rows[3].subject.label).toBe('Llama 4 Maverick')
    })

    it('breaks ties by n, then label', () => {
      const series = [
        { subject: { id: 'b', kind: 'model' as const, label: 'B' }, config_id: 'c', metrics: { m: { mean: 1, n: 5 } } },
        { subject: { id: 'a', kind: 'model' as const, label: 'A' }, config_id: 'c', metrics: { m: { mean: 1, n: 5 } } },
        { subject: { id: 'z', kind: 'model' as const, label: 'Z' }, config_id: 'c', metrics: { m: { mean: 1, n: 9 } } },
      ]
      expect(rankSeries(series, 'c', 'm', 'model').map((r) => r.subject.id)).toEqual(['z', 'a', 'b'])
    })

    it('separates humans, excludes hidden subjects and rows without the metric', () => {
      const humans = rankSeries(FIX.series, 'cfg-judge-sonnet', 'llm_judge_falloesung', 'human')
      expect(humans.map((r) => r.subject.label)).toEqual(['KindAlly', 'BraveOtter'])

      const hidden = rankSeries(FIX.series, 'cfg-judge-sonnet', 'llm_judge_falloesung', 'model', ['gpt-5.4'])
      expect(hidden.map((r) => r.subject.label)).toEqual(['Claude Opus 4.7', 'DeepSeek V4 Flash', 'Llama 4 Maverick'])
      expect(hidden[0].rank).toBe(1)

      expect(rankSeries(FIX.series, 'cfg-judge-sonnet', 'bleu', 'model')).toEqual([])
      expect(rankSeries(FIX.series, null, 'bleu', 'model')).toEqual([])
      expect(rankSeries(FIX.series, 'cfg-bleu', null, 'model')).toEqual([])
    })

    it('switches rows with the config', () => {
      const mini = rankSeries(FIX.series, 'cfg-judge-mini', 'llm_judge_falloesung', 'model')
      expect(mini).toHaveLength(1)
      expect(mini[0].primary.mean).toBe(79.1)
    })
  })

  describe('otherMetricColumns', () => {
    const rows = rankSeries(FIX.series, 'cfg-judge-sonnet', 'llm_judge_falloesung', 'model')

    it('drops primary, grade and hidden companions', () => {
      expect(otherMetricColumns(rows, 'llm_judge_falloesung', 'llm_judge_falloesung_grade_points')).toEqual([])
      expect(otherMetricColumns(rows, 'llm_judge_falloesung', null)).toEqual(['llm_judge_falloesung_grade_points'])
    })

    it('respects visible_metrics', () => {
      const extra = [{ metrics: { a: { mean: 1, n: 1 }, b: { mean: 2, n: 1 }, b_raw: { mean: 2, n: 1 } } }]
      expect(otherMetricColumns(extra, 'a', null)).toEqual(['b'])
      expect(otherMetricColumns(extra, 'a', null, ['a'])).toEqual([])
      expect(otherMetricColumns(extra, 'a', null, ['b'])).toEqual(['b'])
      expect(otherMetricColumns(extra, 'a', null, [])).toEqual(['b'])
    })
  })

  describe('distributions', () => {
    it('finds the distribution for a config/metric pair', () => {
      const d = distributionFor(FIX, 'cfg-judge-sonnet', 'llm_judge_falloesung_grade_points')
      expect(d?.scale).toBe('0-18')
      expect(distributionFor(FIX, 'cfg-judge-mini', 'llm_judge_falloesung_grade_points')).toBeNull()
      expect(distributionFor(FIX, null, 'x')).toBeNull()
      expect(distributionFor(FIX, 'cfg-judge-sonnet', null)).toBeNull()
    })

    it('normalizes each kind to its own total', () => {
      const d = distributionFor(FIX, 'cfg-judge-sonnet', 'llm_judge_falloesung_grade_points')!
      const series = toPercentSeries(d)
      expect(series).toHaveLength(19)
      expect(series[13]).toEqual({ bin: 13, label: '13', model: 12, human: 3, modelPct: 20, humanPct: 4.8 })
      const modelSum = series.reduce((a, b) => a + b.modelPct, 0)
      const humanSum = series.reduce((a, b) => a + b.humanPct, 0)
      expect(Math.round(modelSum)).toBe(100)
      expect(Math.round(humanSum)).toBe(100)
    })

    it('yields zero shares for an empty kind', () => {
      const d = { ...FIX.distributions[0], by_kind: { model: FIX.distributions[0].by_kind.model, human: [] } }
      const series = toPercentSeries(d)
      expect(series.every((s) => s.human === 0 && s.humanPct === 0)).toBe(true)
    })

    it('labels bins per scale', () => {
      expect(binLabel([0, 1, 2], 1, '0-18')).toBe('1')
      expect(binLabel([0, 10, 20], 1, '0-100')).toBe('10–20')
      expect(binLabel([0, 10, 90], 2, '0-100')).toBe('90–100')
      expect(binLabel([0, 0.5], 1, '0-1')).toBe('50–100 %')
      expect(binLabel([0, 0.5], 0, '0-1')).toBe('0–50 %')
      expect(binLabel([0, 0.25, 0.5], 2, 'raw')).toBe('0.50–0.75')
      expect(binLabel([3], 0, 'raw')).toBe('3–4')
      expect(binLabel([0, 1], 1, '0-18')).toBe('1')
    })

    it('builds per-subject histograms for top ranked rows with data', () => {
      const rows = rankSeries(FIX.series, 'cfg-judge-sonnet', 'llm_judge_falloesung', 'model')
      const d = distributionFor(FIX, 'cfg-judge-sonnet', 'llm_judge_falloesung_grade_points')
      const subjects = topSubjectDistributions(rows, d)
      expect(subjects).toHaveLength(1)
      expect(subjects[0]).toMatchObject({ id: 'gpt-5.4', label: 'GPT-5.4', total: 15 })
      expect(subjects[0].bins[13]).toEqual({ bin: 13, label: '13', count: 5, pct: 33.3 })
      expect(topSubjectDistributions(rows, null)).toEqual([])
      expect(topSubjectDistributions(rows, d, 0)).toEqual([])
    })

    it('skips subjects whose histogram is empty', () => {
      const rows = rankSeries(FIX.series, 'cfg-judge-sonnet', 'llm_judge_falloesung', 'model')
      const d = { ...FIX.distributions[0], by_subject: { 'gpt-5.4': [0, 0, 0] } }
      expect(topSubjectDistributions(rows, d)).toEqual([])
    })
  })
})

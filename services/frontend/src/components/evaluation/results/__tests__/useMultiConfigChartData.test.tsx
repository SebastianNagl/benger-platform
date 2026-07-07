import { renderHook, waitFor } from '@testing-library/react'

import { apiClient } from '@/lib/api/client'

import {
  mergeConfigChartData,
  useMultiConfigChartData,
  type ChartConfigInput,
  type PerConfigSummary,
} from '../useMultiConfigChartData'

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjectResultsByTaskModel: jest.fn(),
  },
}))

const getByTaskModel = apiClient.getProjectResultsByTaskModel as jest.Mock

const summary = (
  entries: Record<string, { avg: number; count?: number; name?: string }>
): PerConfigSummary => ({
  models: Object.keys(entries),
  summary: Object.fromEntries(
    Object.entries(entries).map(([id, v]) => [
      id,
      { avg: v.avg, count: v.count ?? 1, model_name: v.name ?? id },
    ])
  ),
})

describe('mergeConfigChartData', () => {
  it('two configs of the SAME metric produce two series keyed by display_name', () => {
    const configs: ChartConfigInput[] = [
      { id: 'cfg-a', displayName: 'Judge GPT', metric: 'llm_judge_falloesung' },
      { id: 'cfg-b', displayName: 'Judge Claude', metric: 'llm_judge_falloesung' },
    ]
    const perConfig = [
      summary({ 'model-1': { avg: 0.8 }, 'model-2': { avg: 0.6 } }),
      summary({ 'model-1': { avg: 0.5 }, 'model-2': { avg: 0.9 } }),
    ]

    const { models, seriesNames } = mergeConfigChartData(perConfig, configs)

    expect(seriesNames).toEqual(['Judge GPT', 'Judge Claude'])
    const m1 = models.find((m) => m.model_id === 'model-1')!
    const m2 = models.find((m) => m.model_id === 'model-2')!
    expect(m1.metrics).toEqual({ 'Judge GPT': 0.8, 'Judge Claude': 0.5 })
    expect(m2.metrics).toEqual({ 'Judge GPT': 0.6, 'Judge Claude': 0.9 })
  })

  it('a model present in only one config omits the other series key', () => {
    const configs: ChartConfigInput[] = [
      { id: 'cfg-a', displayName: 'A', metric: 'm' },
      { id: 'cfg-b', displayName: 'B', metric: 'm' },
    ]
    const perConfig = [
      summary({ 'model-1': { avg: 0.4 } }),
      summary({ 'model-2': { avg: 0.7 } }),
    ]

    const { models } = mergeConfigChartData(perConfig, configs)

    const m1 = models.find((m) => m.model_id === 'model-1')!
    const m2 = models.find((m) => m.model_id === 'model-2')!
    expect(m1.metrics).toEqual({ A: 0.4 })
    expect(m1.metrics.B).toBeUndefined()
    expect(m2.metrics).toEqual({ B: 0.7 })
    expect(m2.metrics.A).toBeUndefined()
  })

  it('unions models across configs in first-seen order', () => {
    const configs: ChartConfigInput[] = [
      { id: 'cfg-a', displayName: 'A', metric: 'm' },
      { id: 'cfg-b', displayName: 'B', metric: 'm' },
    ]
    const perConfig = [
      summary({ 'model-1': { avg: 0.1 } }),
      summary({ 'model-2': { avg: 0.2 }, 'model-1': { avg: 0.3 } }),
    ]

    const { models } = mergeConfigChartData(perConfig, configs)
    expect(models.map((m) => m.model_id)).toEqual(['model-1', 'model-2'])
  })

  it('disambiguates duplicate display_names by appending the config id', () => {
    const configs: ChartConfigInput[] = [
      { id: 'aaaaaaaa-1111', displayName: 'Same', metric: 'm' },
      { id: 'bbbbbbbb-2222', displayName: 'Same', metric: 'm' },
    ]
    const perConfig = [
      summary({ 'model-1': { avg: 0.8 } }),
      summary({ 'model-1': { avg: 0.4 } }),
    ]

    const { models, seriesNames } = mergeConfigChartData(perConfig, configs)

    expect(seriesNames[0]).toBe('Same')
    expect(seriesNames[1]).toBe('Same (bbbbbbbb)')
    expect(seriesNames[0]).not.toBe(seriesNames[1])
    const m1 = models.find((m) => m.model_id === 'model-1')!
    expect(m1.metrics['Same']).toBe(0.8)
    expect(m1.metrics['Same (bbbbbbbb)']).toBe(0.4)
  })

  it('falls back to metric then id when display_name is blank', () => {
    const configs: ChartConfigInput[] = [
      { id: 'cfg-a', displayName: '   ', metric: 'accuracy' },
      { id: 'cfg-b', displayName: '', metric: '' },
    ]
    const perConfig = [summary({ x: { avg: 1 } }), summary({ x: { avg: 2 } })]

    const { seriesNames } = mergeConfigChartData(perConfig, configs)
    expect(seriesNames).toEqual(['accuracy', 'cfg-b'])
  })

  it('a failed config (null result) still lists its series but contributes no values', () => {
    const configs: ChartConfigInput[] = [
      { id: 'cfg-a', displayName: 'Good', metric: 'm' },
      { id: 'cfg-b', displayName: 'Broken', metric: 'm' },
    ]
    const perConfig = [summary({ 'model-1': { avg: 0.9 } }), null]

    const { models, seriesNames } = mergeConfigChartData(perConfig, configs)

    expect(seriesNames).toEqual(['Good', 'Broken'])
    const m1 = models.find((m) => m.model_id === 'model-1')!
    expect(m1.metrics).toEqual({ Good: 0.9 })
  })

  it('empty inputs produce empty output', () => {
    expect(mergeConfigChartData([], [])).toEqual({
      models: [],
      seriesNames: [],
    })
  })

  it('single config yields exactly one series labeled by its display_name', () => {
    const configs: ChartConfigInput[] = [
      { id: 'cfg-a', displayName: 'Only Judge', metric: 'm' },
    ]
    const perConfig = [summary({ 'model-1': { avg: 0.55, name: 'GPT-5' } })]

    const { models, seriesNames } = mergeConfigChartData(perConfig, configs)
    expect(seriesNames).toEqual(['Only Judge'])
    expect(models).toHaveLength(1)
    expect(models[0].model_name).toBe('GPT-5')
    expect(models[0].metrics).toEqual({ 'Only Judge': 0.55 })
  })
})

describe('useMultiConfigChartData', () => {
  beforeEach(() => {
    getByTaskModel.mockReset()
  })

  it('does not fetch when disabled', async () => {
    const { result } = renderHook(() =>
      useMultiConfigChartData({
        projectId: 'p1',
        configs: [{ id: 'cfg-a', displayName: 'A', metric: 'm' }],
        enabled: false,
      })
    )
    expect(getByTaskModel).not.toHaveBeenCalled()
    expect(result.current.models).toEqual([])
    expect(result.current.seriesNames).toEqual([])
  })

  it('fetches one request per config and merges into two series', async () => {
    getByTaskModel
      .mockResolvedValueOnce(
        summary({ 'model-1': { avg: 0.8 }, 'model-2': { avg: 0.6 } })
      )
      .mockResolvedValueOnce(
        summary({ 'model-1': { avg: 0.5 }, 'model-2': { avg: 0.9 } })
      )

    const configs: ChartConfigInput[] = [
      { id: 'cfg-a', displayName: 'Judge A', metric: 'llm_judge_falloesung' },
      { id: 'cfg-b', displayName: 'Judge B', metric: 'llm_judge_falloesung' },
    ]

    const { result } = renderHook(() =>
      useMultiConfigChartData({ projectId: 'p1', configs, enabled: true })
    )

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(getByTaskModel).toHaveBeenCalledTimes(2)
    // Scoped by evaluation_config_id (5th arg) + metric (4th arg).
    expect(getByTaskModel).toHaveBeenCalledWith(
      'p1',
      undefined,
      false,
      'llm_judge_falloesung',
      'cfg-a'
    )
    expect(result.current.seriesNames).toEqual(['Judge A', 'Judge B'])
    const m1 = result.current.models.find((m) => m.model_id === 'model-1')!
    expect(m1.metrics).toEqual({ 'Judge A': 0.8, 'Judge B': 0.5 })
  })

  it('renders remaining series when one config request fails', async () => {
    getByTaskModel
      .mockResolvedValueOnce(summary({ 'model-1': { avg: 0.7 } }))
      .mockRejectedValueOnce(new Error('boom'))

    const configs: ChartConfigInput[] = [
      { id: 'cfg-a', displayName: 'Good', metric: 'm' },
      { id: 'cfg-b', displayName: 'Broken', metric: 'm' },
    ]

    const { result } = renderHook(() =>
      useMultiConfigChartData({ projectId: 'p1', configs, enabled: true })
    )

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.seriesNames).toEqual(['Good', 'Broken'])
    const m1 = result.current.models.find((m) => m.model_id === 'model-1')!
    expect(m1.metrics).toEqual({ Good: 0.7 })
  })
})

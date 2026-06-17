/**
 * @jest-environment jsdom
 *
 * Covers the eval-with-configs ("subject_count > 0") branch of CostEstimatePanel
 * that the base suite never reaches:
 *   - the "Berechnet um …" staleness hint (valid + unparseable estimated_at)
 *   - the per-cell breakdown line ("{cells} Zellen über {models} Judge-Modell(e)")
 *   - the API-error `response.data.detail` precedence path
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import { CostEstimatePanel } from '../CostEstimatePanel'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (_key: string, fallback?: any) =>
      typeof fallback === 'string' ? fallback : _key,
  }),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

const mockPost = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { post: (...args: any[]) => mockPost(...args) },
}))

const evalEstimate = (overrides: Record<string, any> = {}) => ({
  mode: 'evaluation' as const,
  runs_per_call: 2,
  sample_size: 8,
  tasks_total: 50,
  subject_count: 42,
  estimated_at: '2026-06-14T10:30:00Z',
  per_model: [
    {
      model_id: 'judge-a',
      per_call_usd: 0.002,
      per_run_usd: 0.2,
      total_usd: 1.5,
      pricing_known: true,
    },
    {
      model_id: 'judge-b',
      per_call_usd: 0.003,
      per_run_usd: 0.3,
      total_usd: 2.5,
      pricing_known: true,
    },
  ],
  total_usd: 4.0,
  token_estimate: {
    input_mean: 500,
    input_p95: 900,
    output_estimate: 300,
    encoding: 'o200k_base',
  },
  note: 'Estimate accuracy ± ~20%.',
  ...overrides,
})

beforeEach(() => {
  mockPost.mockReset()
  mockAddToast.mockReset()
})

describe('CostEstimatePanel — subject_count (eval-with-configs) path', () => {
  it('renders the cells breakdown and the staleness hint with a parsed time', async () => {
    mockPost.mockResolvedValueOnce(evalEstimate())
    render(
      <CostEstimatePanel
        projectId="p1"
        mode="evaluation"
        judgeModels={['judge-a', 'judge-b']}
        runsPerCall={2}
        evaluationConfigs={[
          { metric: 'llm_judge', prediction_fields: ['answer'] },
        ]}
        enabled
      />,
    )

    await waitFor(() =>
      expect(screen.getByText('$4.00')).toBeInTheDocument(),
    )

    // Per-cell breakdown line (subject_count > 0 branch) instead of the
    // tasks×runs×models legacy line.
    expect(
      screen.getByText('42 Zellen über 2 Judge-Modell(e)'),
    ).toBeInTheDocument()

    // Staleness hint info glyph is shown when subject_count and estimated_at
    // are both set, with a "Berechnet um {time}" title.
    const hint = screen.getByText('ⓘ')
    expect(hint).toBeInTheDocument()
    expect(hint.getAttribute('title')).toMatch(/^Berechnet um /)
    // The title must not still contain the raw {time} placeholder.
    expect(hint.getAttribute('title')).not.toContain('{time}')
  })

  it('falls back to the raw timestamp when estimated_at cannot be parsed', async () => {
    mockPost.mockResolvedValueOnce(
      evalEstimate({ estimated_at: 'not-a-real-date' }),
    )
    render(
      <CostEstimatePanel
        projectId="p1"
        mode="evaluation"
        judgeModels={['judge-a', 'judge-b']}
        runsPerCall={2}
        evaluationConfigs={[{ prediction_fields: ['answer'] }]}
        enabled
      />,
    )

    await waitFor(() =>
      expect(screen.getByText('$4.00')).toBeInTheDocument(),
    )
    const hint = screen.getByText('ⓘ')
    // new Date('not-a-real-date').toLocaleTimeString() === 'Invalid Date',
    // so the catch re-uses the raw string. Either way the title is present;
    // assert it reflects the unparseable input rather than a real clock time.
    const title = hint.getAttribute('title') || ''
    expect(
      title.includes('not-a-real-date') || title.includes('Invalid Date'),
    ).toBe(true)
  })

  it('surfaces response.data.detail over the generic message on error', async () => {
    mockPost.mockRejectedValueOnce({
      response: { data: { detail: 'project not found' } },
      message: 'Request failed with status 404',
    })
    render(
      <CostEstimatePanel
        projectId="p1"
        mode="evaluation"
        judgeModels={['judge-a']}
        runsPerCall={1}
        enabled
      />,
    )

    await waitFor(() =>
      expect(screen.getByText('project not found')).toBeInTheDocument(),
    )
    // The detail (not the axios message) is the toast payload too.
    expect(mockAddToast).toHaveBeenCalledWith('project not found', 'error')
  })

  it('re-fires the estimate when evaluationConfigs change (hashConfigs dep)', async () => {
    mockPost.mockResolvedValue(evalEstimate())
    const { rerender } = render(
      <CostEstimatePanel
        projectId="p1"
        mode="evaluation"
        judgeModels={['judge-a']}
        runsPerCall={1}
        evaluationConfigs={[{ metric: 'm1', prediction_fields: ['a'] }]}
        enabled
      />,
    )
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1))

    rerender(
      <CostEstimatePanel
        projectId="p1"
        mode="evaluation"
        judgeModels={['judge-a']}
        runsPerCall={1}
        evaluationConfigs={[{ metric: 'm2', prediction_fields: ['a', 'b'] }]}
        enabled
      />,
    )
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(2))
    // Confirm evaluation_configs were forwarded in the request body.
    const lastBody = mockPost.mock.calls[mockPost.mock.calls.length - 1][1]
    expect(lastBody.evaluation_configs).toEqual([
      { metric: 'm2', prediction_fields: ['a', 'b'] },
    ])
  })
})

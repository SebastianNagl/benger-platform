/**
 * @jest-environment jsdom
 *
 * Tests for CostEstimatePanel — the inline cost-preview embedded in
 * Start Generation / Start Evaluation modals (multi-run feature).
 *
 * Verifies the panel:
 *   - skips fetching when disabled or when the relevant model list is empty
 *   - renders per-model rows + total + token-estimate + ±20% caveat
 *   - shows "Keine Preisdaten" when a row's pricing is unknown
 *   - surfaces errors from the API
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import { CostEstimatePanel } from '../CostEstimateModal'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (_key: string, fallback?: any) =>
      typeof fallback === 'string' ? fallback : _key,
  }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

const mockPost = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { post: (...args: any[]) => mockPost(...args) },
}))

const sampleEstimate = {
  mode: 'generation' as const,
  runs_per_call: 3,
  sample_size: 10,
  tasks_total: 100,
  per_model: [
    { model_id: 'gpt-4o', per_call_usd: 0.012, per_run_usd: 1.2, total_usd: 3.6, pricing_known: true },
    { model_id: 'mystery-model', per_call_usd: 0, per_run_usd: 0, total_usd: 0, pricing_known: false },
  ],
  total_usd: 3.6,
  token_estimate: { input_mean: 800, input_p95: 1200, output_estimate: 600, encoding: 'o200k_base' },
  note: 'Estimate accuracy ± ~20%.',
}

beforeEach(() => {
  mockPost.mockReset()
})

describe('CostEstimatePanel', () => {
  it('renders nothing when disabled', () => {
    const { container } = render(
      <CostEstimatePanel
        projectId="p1"
        mode="generation"
        modelIds={['gpt-4o']}
        runsPerCall={1}
        enabled={false}
      />,
    )
    expect(container.firstChild).toBeNull()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('skips fetch and renders nothing when generation mode has no models', () => {
    const { container } = render(
      <CostEstimatePanel
        projectId="p1"
        mode="generation"
        modelIds={[]}
        runsPerCall={1}
        enabled={true}
      />,
    )
    expect(container.firstChild).toBeNull()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('skips fetch and renders nothing when evaluation mode has no judges', () => {
    const { container } = render(
      <CostEstimatePanel
        projectId="p1"
        mode="evaluation"
        judgeModels={[]}
        runsPerCall={1}
        enabled={true}
      />,
    )
    expect(container.firstChild).toBeNull()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('renders the headline total + per-model breakdown after fetch', async () => {
    mockPost.mockResolvedValueOnce(sampleEstimate)
    render(
      <CostEstimatePanel
        projectId="p1"
        mode="generation"
        modelIds={['gpt-4o', 'mystery-model']}
        runsPerCall={3}
        enabled={true}
      />,
    )
    await waitFor(() => expect(screen.getAllByText('$3.60').length).toBeGreaterThan(0))
    expect(screen.getByText('gpt-4o')).toBeInTheDocument()
    expect(screen.getByText('mystery-model')).toBeInTheDocument()
    // Per-call cell on the priced row.
    expect(screen.getByText('$0.0120')).toBeInTheDocument()
    // Unknown pricing surfaces a label rather than a $0 figure.
    expect(screen.getAllByText('Keine Preisdaten').length).toBeGreaterThan(0)
  })

  it('renders the token-estimate block + ±20% caveat', async () => {
    mockPost.mockResolvedValueOnce(sampleEstimate)
    render(
      <CostEstimatePanel
        projectId="p1"
        mode="generation"
        modelIds={['gpt-4o']}
        runsPerCall={3}
        enabled={true}
      />,
    )
    await waitFor(() => expect(screen.getAllByText('$3.60').length).toBeGreaterThan(0))
    // Token-estimate breakdown line is rendered once the estimate arrives.
    expect(screen.getByText(/Input: 800 \(mean\) \/ 1200 \(p95\)/)).toBeInTheDocument()
    expect(screen.getByText(/Estimate accuracy ± ~20%/)).toBeInTheDocument()
  })

  it('renders an error banner when the API fails', async () => {
    mockPost.mockRejectedValueOnce({ message: 'boom' })
    render(
      <CostEstimatePanel
        projectId="p1"
        mode="generation"
        modelIds={['gpt-4o']}
        runsPerCall={1}
        enabled={true}
      />,
    )
    await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument())
  })

  it('refires the estimate when runsPerCall changes', async () => {
    mockPost.mockResolvedValue(sampleEstimate)
    const { rerender } = render(
      <CostEstimatePanel
        projectId="p1"
        mode="generation"
        modelIds={['gpt-4o']}
        runsPerCall={1}
        enabled={true}
      />,
    )
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1))
    rerender(
      <CostEstimatePanel
        projectId="p1"
        mode="generation"
        modelIds={['gpt-4o']}
        runsPerCall={5}
        enabled={true}
      />,
    )
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(2))
    // Confirm runs_per_call was forwarded to the body.
    const lastCall = mockPost.mock.calls[mockPost.mock.calls.length - 1]
    expect(lastCall[0]).toBe('/llm-models/cost-estimate')
    expect(lastCall[1].runs_per_call).toBe(5)
  })
})

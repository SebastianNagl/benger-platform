/**
 * @jest-environment jsdom
 *
 * The scope picker while the API is down (e.g. during a restart): the failed
 * scope load is logged once, the picker shows an error with a Retry button,
 * and nothing is requested again until the user retries - no matter how often
 * the parent re-renders or the user toggles the selection. The cost estimate
 * (real CostEstimatePanel here) waits for a successful scope load instead of
 * adding its own failing requests and error toasts.
 */
import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { EvaluationControlModal } from '../EvaluationControlModal'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

const mockGetEvaluatedModels = jest.fn()
const mockGet = jest.fn()
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: (...args: any[]) => mockGet(...args),
    evaluations: {
      runEvaluation: jest.fn(),
      getEvaluatedModels: (...args: any[]) => mockGetEvaluatedModels(...args),
    },
  },
}))

const mockPost = jest.fn()
const mockGetBillingOptions = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { post: (...args: any[]) => mockPost(...args) },
  api: {
    getBillingOptions: (...args: any[]) => mockGetBillingOptions(...args),
  },
}))

jest.mock('@headlessui/react', () => {
  const Dialog: any = ({ children }: any) => <div>{children}</div>
  // eslint-disable-next-line react/display-name
  Dialog.Title = ({ children, as }: any) => {
    const Tag = as || 'h3'
    return <Tag>{children}</Tag>
  }
  // eslint-disable-next-line react/display-name
  Dialog.Panel = ({ children }: any) => <div>{children}</div>
  const Transition: any = ({ children, show }: any) =>
    show !== false ? <>{children}</> : null
  Transition.Root = Transition
  // eslint-disable-next-line react/display-name
  Transition.Child = ({ children }: any) => <>{children}</>
  return { Dialog, Transition }
})

// The parents build this list inline, so every parent render passes a new
// array; the modal must not treat that as a reason to refetch.
const configs = () => [
  {
    id: 'cfg-judge',
    metric: 'llm_judge_falloesung',
    prediction_fields: ['loesung'],
    reference_fields: [],
    metric_parameters: { judge_model: 'gpt-5.4-mini' },
  },
]

function renderModal() {
  const props = { isOpen: true, projectId: 'p1', onClose: jest.fn() }
  const utils = render(
    <EvaluationControlModal {...props} evaluationConfigs={configs()} />,
  )
  const rerender = () =>
    utils.rerender(
      <EvaluationControlModal {...props} evaluationConfigs={configs()} />,
    )
  return { ...utils, rerender }
}

const scopeErrorText =
  'Could not load the models and annotators. The server may be restarting.'

let consoleError: jest.SpyInstance

beforeEach(() => {
  jest.useFakeTimers()
  consoleError = jest.spyOn(console, 'error').mockImplementation(() => {})
  const down = () => Promise.reject(new Error('502 Bad Gateway'))
  mockGetEvaluatedModels.mockReset().mockImplementation(down)
  mockGet.mockReset().mockImplementation(down)
  mockPost.mockReset().mockImplementation(down)
  mockGetBillingOptions.mockReset().mockImplementation(down)
  mockAddToast.mockReset()
})

afterEach(() => {
  consoleError.mockRestore()
  jest.useRealTimers()
})

async function settle(ms = 30_000) {
  for (let elapsed = 0; elapsed < ms; elapsed += 500) {
    await act(async () => {
      jest.advanceTimersByTime(500)
    })
  }
}

function scopeErrorLogs() {
  return consoleError.mock.calls.filter((c) =>
    String(c[0]).includes('scope picker'),
  ).length
}

describe('EvaluationControlModal scope picker while the API is down', () => {
  it('logs once, shows a retry state and stops requesting', async () => {
    const { rerender } = renderModal()
    await settle()

    expect(await screen.findByText(scopeErrorText)).toBeInTheDocument()
    expect(screen.getByTestId('scope-retry')).toBeInTheDocument()
    // The empty states would claim the project has no models at all.
    expect(
      screen.queryByText('No evaluated models on this project yet'),
    ).not.toBeInTheDocument()

    // Parent re-renders and selection changes while the API stays down.
    for (let i = 0; i < 20; i++) rerender()
    fireEvent.click(screen.getByRole('checkbox', { name: /falloesung/i }))
    fireEvent.click(screen.getByRole('checkbox', { name: /falloesung/i }))
    fireEvent.click(document.getElementById('mode-all') as HTMLElement)
    await settle()

    expect(mockGetEvaluatedModels).toHaveBeenCalledTimes(1)
    // The structures and the cost estimate come from the same API: neither
    // is requested while the scope load failed.
    expect(mockGet).not.toHaveBeenCalled()
    expect(mockPost).not.toHaveBeenCalled()
    expect(mockAddToast).not.toHaveBeenCalled()
    expect(scopeErrorLogs()).toBe(1)
    expect(consoleError).toHaveBeenCalledTimes(1)
  })

  it('retries only on click and logs the failure only once per opening', async () => {
    renderModal()
    await settle()
    expect(mockGetEvaluatedModels).toHaveBeenCalledTimes(1)

    for (let i = 0; i < 3; i++) {
      fireEvent.click(screen.getByTestId('scope-retry'))
      await settle(5_000)
    }
    expect(mockGetEvaluatedModels).toHaveBeenCalledTimes(4)
    expect(scopeErrorLogs()).toBe(1)
    expect(mockPost).not.toHaveBeenCalled()

    // The API is back: the retry loads the scope, the structures and one
    // cost estimate.
    mockGetEvaluatedModels.mockResolvedValue([
      {
        model_id: 'gpt-5.4',
        model_name: 'gpt-5.4',
        provider: 'openai',
        evaluation_count: 1,
        total_samples: 0,
        last_evaluated: null,
        average_score: null,
        ci_lower: null,
        ci_upper: null,
      },
    ])
    mockGet.mockResolvedValue({})
    mockPost.mockResolvedValue({
      mode: 'evaluation',
      runs_per_call: 1,
      sample_size: 1,
      tasks_total: 1,
      subject_count: 0,
      estimated_at: '2026-10-20T10:00:00Z',
      per_model: [],
      total_usd: 0.12,
      token_estimate: {
        input_mean: 1,
        input_p95: 1,
        output_estimate: 1,
        encoding: 'o200k_base',
      },
      note: 'n',
    })
    fireEvent.click(screen.getByTestId('scope-retry'))
    await settle(5_000)

    expect(await screen.findByLabelText('gpt-5.4')).toBeInTheDocument()
    expect(screen.queryByText(scopeErrorText)).not.toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1))
    expect(mockPost.mock.calls[0][1]).toMatchObject({
      model_ids: ['gpt-5.4'],
    })
    expect(scopeErrorLogs()).toBe(1)
  })
})

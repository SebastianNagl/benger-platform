/**
 * @jest-environment jsdom
 *
 * Behavior tests for the in-flight runs banner: render gating, per-run
 * cancel, bulk cancel, confirm dialog flow, failure-reason aggregation,
 * and the +N overflow cap.
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InflightRunsBanner } from '../InflightRunsBanner'

// Stable mocks for the I18nContext — the banner uses `t(key, default)`
// and `t(key, { defaultValue, count })`; preserve both shapes.
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (_key: string, fallback: any) => {
      if (typeof fallback === 'string') return fallback
      if (fallback && typeof fallback === 'object' && 'defaultValue' in fallback) {
        return fallback.defaultValue
      }
      return _key
    },
  }),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

const mockCancelEvaluationRun = jest.fn()
const mockCancelAll = jest.fn()
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    evaluations: {
      cancelEvaluationRun: (...args: any[]) => mockCancelEvaluationRun(...args),
      cancelAllProjectEvaluations: (...args: any[]) => mockCancelAll(...args),
    },
  },
}))

// `useConfirm` returns an async function that resolves to a boolean.
// Default to "user clicked confirm" so we exercise the cancel path.
const mockConfirm = jest.fn().mockResolvedValue(true)
jest.mock('@/hooks/useDialogs', () => ({
  useConfirm: () => mockConfirm,
}))

const baseRun = (id: string, overrides: any = {}) => ({
  evaluation_id: id,
  status: 'running',
  samples_evaluated: 0,
  eval_metadata: { cells_dispatched: 100, failures_by_reason: {} },
  ...overrides,
})

const PROJECT_ID = 'proj-xyz'

describe('InflightRunsBanner', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockConfirm.mockResolvedValue(true)
  })

  test('renders nothing when no in-flight runs', () => {
    const { container } = render(
      <InflightRunsBanner
        projectId={PROJECT_ID}
        evaluations={[
          { evaluation_id: 'r1', status: 'completed' },
          { evaluation_id: 'r2', status: 'failed' },
          { evaluation_id: 'r3', status: 'cancelled' },
        ]}
        onChanged={jest.fn()}
      />
    )
    expect(container.firstChild).toBeNull()
  })

  test('renders per-run row with progress and a Cancel button', () => {
    render(
      <InflightRunsBanner
        projectId={PROJECT_ID}
        evaluations={[
          baseRun('aabbccddee112233', {
            samples_evaluated: 42,
            eval_metadata: { cells_dispatched: 100 },
          }),
        ]}
        onChanged={jest.fn()}
      />
    )
    // Shows the truncated id + progress.
    expect(screen.getByText(/aabbccdd/)).toBeInTheDocument()
    expect(screen.getByText(/42\/100/)).toBeInTheDocument()
    // The role="status" + aria-live announce live changes for SRs.
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite')
  })

  test('bulk-cancel button hidden when only one in-flight, shown when >=2', () => {
    const { rerender } = render(
      <InflightRunsBanner
        projectId={PROJECT_ID}
        evaluations={[baseRun('r1')]}
        onChanged={jest.fn()}
      />
    )
    expect(screen.queryByText('Alle abbrechen')).not.toBeInTheDocument()

    rerender(
      <InflightRunsBanner
        projectId={PROJECT_ID}
        evaluations={[baseRun('r1'), baseRun('r2')]}
        onChanged={jest.fn()}
      />
    )
    expect(screen.getByText('Alle abbrechen')).toBeInTheDocument()
  })

  test('per-run cancel: confirm → API → toast → onChanged', async () => {
    mockCancelEvaluationRun.mockResolvedValue({
      cancelled_run_ids: ['r1'],
      failed_child_judge_run_count: 0,
      preserved_task_evaluation_count: 5,
      message: 'ok',
    })
    const onChanged = jest.fn()
    render(
      <InflightRunsBanner
        projectId={PROJECT_ID}
        evaluations={[baseRun('r1aaaaaa')]}
        onChanged={onChanged}
      />
    )
    await userEvent.click(screen.getByLabelText('Diesen Lauf abbrechen'))
    await waitFor(() => expect(mockConfirm).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(mockCancelEvaluationRun).toHaveBeenCalledWith('r1aaaaaa'))
    await waitFor(() => expect(mockAddToast).toHaveBeenCalledTimes(1))
    expect(mockAddToast.mock.calls[0][1]).toBe('success')
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  test('per-run cancel: user clicks "keep running" in dialog → no API call', async () => {
    mockConfirm.mockResolvedValueOnce(false)
    render(
      <InflightRunsBanner
        projectId={PROJECT_ID}
        evaluations={[baseRun('r1')]}
        onChanged={jest.fn()}
      />
    )
    await userEvent.click(screen.getByLabelText('Diesen Lauf abbrechen'))
    await waitFor(() => expect(mockConfirm).toHaveBeenCalled())
    expect(mockCancelEvaluationRun).not.toHaveBeenCalled()
    expect(mockAddToast).not.toHaveBeenCalled()
  })

  test('per-run cancel: API failure shows error toast and re-enables button', async () => {
    mockCancelEvaluationRun.mockRejectedValue(new Error('boom'))
    render(
      <InflightRunsBanner
        projectId={PROJECT_ID}
        evaluations={[baseRun('r1')]}
        onChanged={jest.fn()}
      />
    )
    const btn = screen.getByLabelText('Diesen Lauf abbrechen')
    await userEvent.click(btn)
    await waitFor(() => expect(mockAddToast).toHaveBeenCalledTimes(1))
    expect(mockAddToast.mock.calls[0][1]).toBe('error')
    // Button is not stuck in disabled state after error.
    expect(btn).not.toBeDisabled()
  })

  test('cancel-all: API → toast', async () => {
    mockCancelAll.mockResolvedValue({
      cancelled_run_ids: ['r1', 'r2'],
      failed_child_judge_run_count: 2,
      preserved_task_evaluation_count: 99,
      message: 'ok',
    })
    const onChanged = jest.fn()
    render(
      <InflightRunsBanner
        projectId={PROJECT_ID}
        evaluations={[baseRun('r1'), baseRun('r2')]}
        onChanged={onChanged}
      />
    )
    await userEvent.click(screen.getByText('Alle abbrechen'))
    await waitFor(() => expect(mockCancelAll).toHaveBeenCalledWith(PROJECT_ID))
    await waitFor(() => expect(mockAddToast).toHaveBeenCalledTimes(1))
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  test('failure-reason breakdown aggregates across runs', () => {
    render(
      <InflightRunsBanner
        projectId={PROJECT_ID}
        evaluations={[
          baseRun('r1', {
            eval_metadata: {
              cells_dispatched: 100,
              failures_by_reason: { rate_limit: 5, timeout: 1 },
            },
          }),
          baseRun('r2', {
            eval_metadata: {
              cells_dispatched: 100,
              failures_by_reason: { rate_limit: 3, content_policy: 2 },
            },
          }),
        ]}
        onChanged={jest.fn()}
      />
    )
    // rate_limit sums across both runs (5 + 3 = 8).
    expect(screen.getByText('rate_limit: 8')).toBeInTheDocument()
    expect(screen.getByText('timeout: 1')).toBeInTheDocument()
    expect(screen.getByText('content_policy: 2')).toBeInTheDocument()
  })

  test('failure-reason badges cap at 8 with overflow chip', () => {
    const reasons: Record<string, number> = {}
    for (let i = 0; i < 12; i++) reasons[`reason_${i}`] = 12 - i
    render(
      <InflightRunsBanner
        projectId={PROJECT_ID}
        evaluations={[
          baseRun('r1', {
            eval_metadata: {
              cells_dispatched: 100,
              failures_by_reason: reasons,
            },
          }),
        ]}
        onChanged={jest.fn()}
      />
    )
    // Top 8 by count are shown; the rest collapse into "+4 weitere".
    // (Order is desc by count: reason_0=12, ..., reason_7=5 visible;
    // reason_8=4, ..., reason_11=1 hidden.)
    expect(screen.getByText('reason_0: 12')).toBeInTheDocument()
    expect(screen.getByText('reason_7: 5')).toBeInTheDocument()
    expect(screen.queryByText('reason_8: 4')).not.toBeInTheDocument()
    expect(screen.getByText('+4 weitere')).toBeInTheDocument()
  })
})

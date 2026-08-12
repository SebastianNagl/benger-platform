/**
 * @jest-environment jsdom
 *
 * Prompt-structure scope section (LEXam reproduction follow-up to issue #69):
 *   - Modal fetches `/projects/{id}/generation-config/structures` on open and
 *     renders a structure picker ONLY when the project defines >1 structure
 *     (with a single structure the filter is a no-op)
 *   - Defaults to all-selected; dispatch omits `structure_keys` unless the
 *     user actually narrowed the set (no-op-preservation, same contract as
 *     model_ids / annotator_user_ids)
 *   - Narrowing sends exactly the selected keys
 *   - Zero selected structures blocks Run with a role=alert reason
 *   - A failing structures fetch degrades to "no section" without breaking
 *     the model/annotator pickers or the dispatch
 *
 * Sibling `EvaluationControlModal.scope.test.tsx` covers the model/annotator
 * sections; this file targets the structure additions exclusively.
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { EvaluationControlModal } from '../EvaluationControlModal'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, paramOrFallback?: any) => {
      if (typeof paramOrFallback === 'string') return paramOrFallback
      if (paramOrFallback && typeof paramOrFallback === 'object' && 'count' in paramOrFallback) {
        return `${paramOrFallback.count}`
      }
      const translations: Record<string, string> = {
        'evaluation.controlModal.title': 'Run Evaluation',
        'evaluation.controlModal.startEvaluation': 'Start Evaluation',
        'evaluation.controlModal.starting': 'Starting...',
        'evaluation.controlModal.cancel': 'Cancel',
        'shared.alertDialog.close': 'Close',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

jest.mock('@/components/shared/CostEstimatePanel', () => ({
  CostEstimatePanel: () => <div data-testid="cost-panel" />,
}))

const mockRunEvaluation = jest.fn()
const mockGetEvaluatedModels = jest.fn()
const mockGet = jest.fn()
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: (...args: any[]) => mockGet(...args),
    evaluations: {
      runEvaluation: (...args: any[]) => mockRunEvaluation(...args),
      getEvaluatedModels: (...args: any[]) => mockGetEvaluatedModels(...args),
    },
  },
}))

jest.mock('@headlessui/react', () => {
  const Dialog = ({ children }: any) => <div data-testid="dialog">{children}</div>
  // eslint-disable-next-line react/display-name
  Dialog.Title = ({ children, as }: any) => {
    const Tag = as || 'h3'
    return <Tag>{children}</Tag>
  }
  // eslint-disable-next-line react/display-name
  Dialog.Panel = ({ children }: any) => <div data-testid="dialog-panel">{children}</div>
  const Transition: any = ({ children, show }: any) => (show !== false ? <>{children}</> : null)
  // eslint-disable-next-line react/display-name
  Transition.Root = ({ children, show }: any) => (show !== false ? <>{children}</> : null)
  // eslint-disable-next-line react/display-name
  Transition.Child = ({ children }: any) => <>{children}</>
  return { Dialog, Transition, Fragment: ({ children }: any) => <>{children}</> }
})

const defaultProps = {
  isOpen: true,
  projectId: 'project-1',
  evaluationConfigs: [
    {
      id: 'cfg-1',
      metric: 'llm_judge_lexam',
      prediction_fields: ['__all_model__'],
      reference_fields: ['musterloesung'],
    },
  ],
  onClose: jest.fn(),
  onSuccess: jest.fn(),
}

const evaluatedModelsRows = [
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
]

const twoStructures = {
  fallloesung: { name: 'Falllösung', system_prompt: 'x' },
  'lexam-open': { name: 'LEXam Open', system_prompt: { template: '' } },
}

beforeEach(() => {
  mockRunEvaluation.mockReset().mockResolvedValue({})
  mockGetEvaluatedModels.mockReset().mockResolvedValue(evaluatedModelsRows)
  mockGet.mockReset().mockResolvedValue(twoStructures)
})

describe('EvaluationControlModal structure scope', () => {
  it('fetches structures on open and renders the picker for >1 structure', async () => {
    render(<EvaluationControlModal {...defaultProps} />)
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(
        '/projects/project-1/generation-config/structures',
      ),
    )
    expect(await screen.findByLabelText(/Falllösung/)).toBeInTheDocument()
    expect(await screen.findByLabelText(/LEXam Open/)).toBeInTheDocument()
  })

  it('hides the picker when the project has a single structure', async () => {
    mockGet.mockResolvedValue({ fallloesung: { name: 'Falllösung' } })
    render(<EvaluationControlModal {...defaultProps} />)
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(screen.queryByText('Prompt-Strukturen')).not.toBeInTheDocument()
  })

  it('omits structure_keys when nothing is narrowed (all selected)', async () => {
    render(<EvaluationControlModal {...defaultProps} />)
    const box = await screen.findByLabelText(/LEXam Open/)
    expect(box).toBeChecked()
    const startButton = screen.getByText('Start Evaluation')
    await waitFor(() => expect(startButton).not.toBeDisabled())
    fireEvent.click(startButton)
    await waitFor(() => expect(mockRunEvaluation).toHaveBeenCalled())
    expect(mockRunEvaluation.mock.calls[0][0].structure_keys).toBeUndefined()
  })

  it('passes exactly the selected keys when narrowed to a subset', async () => {
    render(<EvaluationControlModal {...defaultProps} />)
    const falloesungBox = await screen.findByLabelText(/Falllösung/)
    fireEvent.click(falloesungBox) // deselect, leaving only lexam-open
    const startButton = screen.getByText('Start Evaluation')
    await waitFor(() => expect(startButton).not.toBeDisabled())
    fireEvent.click(startButton)
    await waitFor(() => expect(mockRunEvaluation).toHaveBeenCalled())
    expect(mockRunEvaluation.mock.calls[0][0].structure_keys).toEqual([
      'lexam-open',
    ])
  })

  it('blocks Run with a role=alert reason when all structures are deselected', async () => {
    render(<EvaluationControlModal {...defaultProps} />)
    fireEvent.click(await screen.findByLabelText(/Falllösung/))
    fireEvent.click(await screen.findByLabelText(/LEXam Open/))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/prompt-struktur/i)
    expect(screen.getByText('Start Evaluation')).toHaveAttribute(
      'aria-disabled',
      'true',
    )
  })

  it('degrades to no structure section when the structures fetch fails', async () => {
    mockGet.mockRejectedValue(new Error('no generation config'))
    render(<EvaluationControlModal {...defaultProps} />)
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(screen.queryByText('Prompt-Strukturen')).not.toBeInTheDocument()
    // Dispatch still works, unscoped.
    const startButton = screen.getByText('Start Evaluation')
    await waitFor(() => expect(startButton).not.toBeDisabled())
    fireEvent.click(startButton)
    await waitFor(() => expect(mockRunEvaluation).toHaveBeenCalled())
    expect(mockRunEvaluation.mock.calls[0][0].structure_keys).toBeUndefined()
  })
})

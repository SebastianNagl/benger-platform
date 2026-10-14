/**
 * @jest-environment jsdom
 *
 * Scope-section behavior locked here (issue #69 follow-up E1):
 *   - Modal fetches `/evaluated-models` on open and partitions models vs annotators
 *   - Run is disabled when any rendered scope section has zero selections
 *   - Disabled-Run reason is rendered as `role=alert` (screen-reader visible)
 *   - Dispatch only includes `model_ids` / `annotator_user_ids` when the user
 *     actually narrowed the set (sending an explicit "all" filter would defeat
 *     the no-op-preservation property)
 *
 * Sibling test `EvaluationControlModal.test.tsx` covers the original mode-only
 * surface; this file targets the scope-picker additions exclusively.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { EvaluationControlModal } from '../EvaluationControlModal'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('de'),
)

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

jest.mock('@/components/shared/CostEstimatePanel', () => ({
  CostEstimatePanel: () => <div data-testid="cost-panel" />,
}))

const mockRunEvaluation = jest.fn()
const mockGetEvaluatedModels = jest.fn()
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    evaluations: {
      runEvaluation: (...args: any[]) => mockRunEvaluation(...args),
      getEvaluatedModels: (...args: any[]) => mockGetEvaluatedModels(...args),
    },
  },
}))

// Stub HeadlessUI portal components so the dialog children render in-place.
jest.mock('@headlessui/react', () => {
  const Dialog = ({ children }: any) => (
    <div data-testid="dialog">{children}</div>
  )
  // eslint-disable-next-line react/display-name
  Dialog.Title = ({ children, as }: any) => {
    const Tag = as || 'h3'
    return <Tag>{children}</Tag>
  }
  // eslint-disable-next-line react/display-name
  Dialog.Panel = ({ children }: any) => (
    <div data-testid="dialog-panel">{children}</div>
  )
  const Transition: any = ({ children, show }: any) =>
    show !== false ? <>{children}</> : null
  // eslint-disable-next-line react/display-name
  Transition.Root = ({ children, show }: any) =>
    show !== false ? <>{children}</> : null
  // eslint-disable-next-line react/display-name
  Transition.Child = ({ children }: any) => <>{children}</>
  return {
    Dialog,
    Transition,
    Fragment: ({ children }: any) => <>{children}</>,
  }
})

const defaultProps = {
  isOpen: true,
  projectId: 'project-1',
  evaluationConfigs: [
    {
      id: 'cfg-1',
      metric: 'llm_judge_falloesung',
      prediction_fields: ['loesung'],
      reference_fields: ['gold'],
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
  {
    model_id: 'annotator:Alice',
    model_name: 'Annotator: Alice',
    provider: 'Annotator',
    user_id: 'user-alice',
    evaluation_count: 1,
    total_samples: 0,
    last_evaluated: null,
    average_score: null,
    ci_lower: null,
    ci_upper: null,
  },
]

beforeEach(() => {
  mockRunEvaluation.mockReset().mockResolvedValue({})
  mockGetEvaluatedModels.mockReset().mockResolvedValue(evaluatedModelsRows)
})

describe('EvaluationControlModal scope picker', () => {
  it('renders all three sections after fetch resolves', async () => {
    render(<EvaluationControlModal {...defaultProps} />)
    await waitFor(() => expect(mockGetEvaluatedModels).toHaveBeenCalled())
    // Metrics section: derived from the prop, not the fetch.
    expect(screen.getByLabelText('Llm Judge Falloesung')).toBeInTheDocument()
    // Models + annotators section: from the fetch.
    expect(await screen.findByLabelText('gpt-5.4')).toBeInTheDocument()
    expect(await screen.findByLabelText('Annotator: Alice')).toBeInTheDocument()
  })

  it('defaults to all options selected (preserves today behavior)', async () => {
    render(<EvaluationControlModal {...defaultProps} />)
    const metricBox = await screen.findByLabelText('Llm Judge Falloesung')
    const modelBox = await screen.findByLabelText('gpt-5.4')
    const annotatorBox = await screen.findByLabelText('Annotator: Alice')
    expect(metricBox).toBeChecked()
    expect(modelBox).toBeChecked()
    expect(annotatorBox).toBeChecked()
  })

  it('does NOT pass model_ids or annotator_user_ids when nothing is narrowed', async () => {
    render(<EvaluationControlModal {...defaultProps} />)
    const startButton = await screen.findByText('Evaluation starten')
    await waitFor(() => expect(mockGetEvaluatedModels).toHaveBeenCalled())
    await waitFor(() => expect(startButton).not.toBeDisabled())
    fireEvent.click(startButton)
    await waitFor(() => expect(mockRunEvaluation).toHaveBeenCalled())
    const payload = mockRunEvaluation.mock.calls[0][0]
    // No filter sent → backend full-sweep path. Sending [] would mean "filter
    // to nothing" and would silently zero the run — test pins the contract.
    expect(payload.model_ids).toBeUndefined()
    expect(payload.annotator_user_ids).toBeUndefined()
  })

  it('disables Run with role=alert reason when metrics are deselected', async () => {
    render(<EvaluationControlModal {...defaultProps} />)
    const metricBox = await screen.findByLabelText('Llm Judge Falloesung')
    fireEvent.click(metricBox)
    expect(metricBox).not.toBeChecked()
    const alert = await screen.findByRole('alert')
    // German catalog copy ("Mindestens eine Metrik auswählen"); assert
    // case-insensitively against the German stem.
    expect(alert).toHaveTextContent(/metrik/i)
    const startButton = screen.getByText('Evaluation starten')
    expect(startButton).toHaveAttribute('aria-disabled', 'true')
  })

  it('grades only submitted answers when no model is selected', async () => {
    render(<EvaluationControlModal {...defaultProps} />)
    const modelBox = await screen.findByLabelText('gpt-5.4')
    fireEvent.click(modelBox)
    expect(
      await screen.findByText(/nur eingereichte Antworten/i),
    ).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    const startButton = screen.getByText('Evaluation starten')
    await waitFor(() => expect(startButton).not.toBeDisabled())
    fireEvent.click(startButton)
    await waitFor(() => expect(mockRunEvaluation).toHaveBeenCalled())
    expect(mockRunEvaluation.mock.calls[0][0].model_ids).toEqual([])
  })

  it('grades only model answers when no annotator is selected', async () => {
    render(<EvaluationControlModal {...defaultProps} />)
    const annotatorBox = await screen.findByLabelText('Annotator: Alice')
    fireEvent.click(annotatorBox)
    expect(await screen.findByText(/nur Modellantworten/i)).toBeInTheDocument()
    const startButton = screen.getByText('Evaluation starten')
    await waitFor(() => expect(startButton).not.toBeDisabled())
    fireEvent.click(startButton)
    await waitFor(() => expect(mockRunEvaluation).toHaveBeenCalled())
    const payload = mockRunEvaluation.mock.calls[0][0]
    expect(payload.annotator_user_ids).toEqual([])
    expect(payload.model_ids).toBeUndefined()
  })

  it('disables Run when neither a model nor an annotator is selected', async () => {
    render(<EvaluationControlModal {...defaultProps} />)
    fireEvent.click(await screen.findByLabelText('gpt-5.4'))
    fireEvent.click(await screen.findByLabelText('Annotator: Alice'))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Modell oder eine:n Annotator:in/i)
  })

  it('passes annotator_user_ids when narrowed to a subset', async () => {
    // Two annotators on the project — picking one should narrow.
    mockGetEvaluatedModels.mockResolvedValue([
      ...evaluatedModelsRows,
      {
        model_id: 'annotator:Bob',
        model_name: 'Annotator: Bob',
        provider: 'Annotator',
        user_id: 'user-bob',
        evaluation_count: 1,
        total_samples: 0,
        last_evaluated: null,
        average_score: null,
        ci_lower: null,
        ci_upper: null,
      },
    ])
    render(<EvaluationControlModal {...defaultProps} />)
    const bobBox = await screen.findByLabelText('Annotator: Bob')
    fireEvent.click(bobBox) // deselect Bob, leaving only Alice
    const startButton = screen.getByText('Evaluation starten')
    await waitFor(() => expect(startButton).not.toBeDisabled())
    fireEvent.click(startButton)
    await waitFor(() => expect(mockRunEvaluation).toHaveBeenCalled())
    const payload = mockRunEvaluation.mock.calls[0][0]
    expect(payload.annotator_user_ids).toEqual(['user-alice'])
  })

  it('renders empty-state when the fetch returns no models', async () => {
    mockGetEvaluatedModels.mockResolvedValue([])
    render(<EvaluationControlModal {...defaultProps} />)
    await waitFor(() => expect(mockGetEvaluatedModels).toHaveBeenCalled())
    // German catalog copy ("Keine bewerteten Modelle in diesem Projekt").
    expect(
      await screen.findByText(/keine bewerteten modelle/i),
    ).toBeInTheDocument()
  })
})

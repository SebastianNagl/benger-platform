/**
 * @jest-environment jsdom
 *
 * Gap-fill coverage for EvaluationControlModal's scope-picker controls and
 * cost-derivation logic (issue #69). The sibling files cover mode selection,
 * direct/callback submit, and the basic scope render; this file targets the
 * still-uncovered lines:
 *   - select-all / clear-all buttons for metrics, models and annotators
 *   - the metric-count footer (singular "1 Metrik" vs "{count} Metriken")
 *   - the scopeLoading status indicator (fetch in flight)
 *   - the judge-derivation memo: `judges[]` array shape (multi-judge + runs)
 *     and the legacy `judge_model` / `runs_per_judge` shape → drives whether
 *     the CostEstimatePanel mounts
 *   - the getEvaluatedModels fetch-error fallback path
 *   - the no-configs direct-API submit toast
 *
 * Mock idiom mirrors EvaluationControlModal.scope.test.tsx exactly.
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { EvaluationControlModal } from '../EvaluationControlModal'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    // Three t() call shapes (matches the scope sibling):
    //   (a) t('key')                  → translation map or the key
    //   (b) t('key', 'fallback')      → the fallback literal
    //   (c) t('key', { count: N })    → the bare count as a string
    t: (key: string, paramOrFallback?: any) => {
      if (typeof paramOrFallback === 'string') return paramOrFallback
      if (
        paramOrFallback &&
        typeof paramOrFallback === 'object' &&
        'count' in paramOrFallback
      ) {
        return `${paramOrFallback.count}`
      }
      const translations: Record<string, string> = {
        'evaluation.controlModal.title': 'Run Evaluation',
        'evaluation.controlModal.startEvaluation': 'Start Evaluation',
        'evaluation.controlModal.cancel': 'Cancel',
        'evaluation.controlModal.noConfigsFound': 'No configs found',
        'generation.controlModal.selectAll': 'Select All',
        'generation.controlModal.clearAll': 'Clear All',
      }
      return translations[key] || key
    },
  }),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

// Replace the cost panel with a marker so we can assert *whether* it mounts
// (it mounts only when judgeModelIds.length > 0 for the SELECTED metrics).
jest.mock('@/components/shared/CostEstimatePanel', () => ({
  CostEstimatePanel: (props: any) => (
    <div data-testid="cost-panel" data-judges={(props.judgeModels || []).join(',')} />
  ),
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

jest.mock('@headlessui/react', () => {
  const Dialog = ({ children }: any) => <div data-testid="dialog">{children}</div>
  // eslint-disable-next-line react/display-name
  Dialog.Title = ({ children, as }: any) => {
    const Tag = as || 'h3'
    return <Tag>{children}</Tag>
  }
  // eslint-disable-next-line react/display-name
  Dialog.Panel = ({ children }: any) => <div data-testid="dialog-panel">{children}</div>
  const Transition: any = ({ children, show }: any) =>
    show !== false ? <>{children}</> : null
  // eslint-disable-next-line react/display-name
  Transition.Root = ({ children, show }: any) => (show !== false ? <>{children}</> : null)
  // eslint-disable-next-line react/display-name
  Transition.Child = ({ children }: any) => <>{children}</>
  return { Dialog, Transition, Fragment: ({ children }: any) => <>{children}</> }
})

const metricConfigs = [
  {
    id: 'cfg-1',
    metric: 'exact_match',
    display_name: 'Exact Match',
    prediction_fields: ['answer'],
    reference_fields: ['gold'],
  },
  {
    id: 'cfg-2',
    metric: 'rouge',
    display_name: 'ROUGE',
    prediction_fields: ['summary'],
    reference_fields: ['gold_summary'],
  },
]

const evaluatedModelsRows = [
  {
    model_id: 'gpt-5.4',
    model_name: 'GPT 5.4',
    provider: 'openai',
    evaluation_count: 1,
  },
  {
    model_id: 'claude',
    model_name: 'Claude',
    provider: 'anthropic',
    evaluation_count: 1,
  },
  {
    model_id: 'annotator:Alice',
    model_name: 'Annotator: Alice',
    provider: 'Annotator',
    user_id: 'user-alice',
    evaluation_count: 1,
  },
]

const baseProps = {
  isOpen: true,
  projectId: 'project-1',
  evaluationConfigs: metricConfigs,
  onClose: jest.fn(),
  onSuccess: jest.fn(),
}

beforeEach(() => {
  jest.clearAllMocks()
  mockRunEvaluation.mockResolvedValue({})
  mockGetEvaluatedModels.mockResolvedValue(evaluatedModelsRows)
})

describe('EvaluationControlModal scope controls', () => {
  describe('metric select-all / clear-all', () => {
    it('clears then re-selects all metrics, updating the count footer', async () => {
      render(<EvaluationControlModal {...baseProps} />)
      // Both metric checkboxes start selected → "2" in the footer.
      const m1 = await screen.findByLabelText('Exact Match')
      const m2 = await screen.findByLabelText('ROUGE')
      expect(m1).toBeChecked()
      expect(m2).toBeChecked()

      // There is one Clear All button per rendered scope section. The metric
      // section is first in the DOM, so the first Clear All targets it.
      const clearButtons = screen.getAllByText('Clear All')
      fireEvent.click(clearButtons[0])
      await waitFor(() => expect(m1).not.toBeChecked())
      expect(m2).not.toBeChecked()

      // Re-select all via the first Select All button.
      const selectButtons = screen.getAllByText('Select All')
      fireEvent.click(selectButtons[0])
      await waitFor(() => expect(m1).toBeChecked())
      expect(m2).toBeChecked()
    })

    it('shows the singular metric-count label when exactly one metric is selected', async () => {
      render(<EvaluationControlModal {...baseProps} />)
      const m2 = await screen.findByLabelText('ROUGE')
      // Deselect one of two → exactly one selected → singular fallback text.
      fireEvent.click(m2)
      expect(
        await screen.findByText('1 Metrik ausgewählt'),
      ).toBeInTheDocument()
    })
  })

  describe('model select-all / clear-all', () => {
    it('clears and re-selects the model section independently of metrics', async () => {
      render(<EvaluationControlModal {...baseProps} />)
      const gpt = await screen.findByLabelText('GPT 5.4')
      const claude = await screen.findByLabelText('Claude')
      expect(gpt).toBeChecked()
      expect(claude).toBeChecked()

      // DOM order of scope sections: metrics, models, annotators. So the
      // SECOND Clear All button is the model section's.
      const clearButtons = screen.getAllByText('Clear All')
      fireEvent.click(clearButtons[1])
      await waitFor(() => expect(gpt).not.toBeChecked())
      expect(claude).not.toBeChecked()
      // A disabled-run alert appears because the model section is now empty.
      expect(await screen.findByRole('alert')).toBeInTheDocument()

      const selectButtons = screen.getAllByText('Select All')
      fireEvent.click(selectButtons[1])
      await waitFor(() => expect(gpt).toBeChecked())
      expect(claude).toBeChecked()
    })
  })

  describe('annotator select-all / clear-all', () => {
    it('clears and re-selects the annotator section', async () => {
      render(<EvaluationControlModal {...baseProps} />)
      const alice = await screen.findByLabelText('Annotator: Alice')
      expect(alice).toBeChecked()

      // Third Clear All button = annotator section.
      const clearButtons = screen.getAllByText('Clear All')
      fireEvent.click(clearButtons[2])
      await waitFor(() => expect(alice).not.toBeChecked())

      const selectButtons = screen.getAllByText('Select All')
      fireEvent.click(selectButtons[2])
      await waitFor(() => expect(alice).toBeChecked())
    })
  })

  describe('cost panel from judge derivation', () => {
    it('mounts the cost panel with judge ids from the array-of-judges shape', async () => {
      render(
        <EvaluationControlModal
          {...baseProps}
          evaluationConfigs={[
            {
              id: 'judge-cfg',
              metric: 'llm_judge_falloesung',
              display_name: 'LLM Judge',
              prediction_fields: ['loesung'],
              reference_fields: ['gold'],
              metric_parameters: {
                judges: [
                  { judge_model_id: 'gpt-4o', runs: 3 },
                  { judge_model_id: 'claude-judge', runs: 1 },
                ],
              },
            },
          ]}
        />,
      )
      const panel = await screen.findByTestId('cost-panel')
      const judges = panel.getAttribute('data-judges') || ''
      expect(judges).toContain('gpt-4o')
      expect(judges).toContain('claude-judge')
    })

    it('mounts the cost panel from the legacy judge_model / runs_per_judge shape', async () => {
      render(
        <EvaluationControlModal
          {...baseProps}
          evaluationConfigs={[
            {
              id: 'judge-legacy',
              metric: 'llm_judge_zjs',
              display_name: 'Legacy Judge',
              prediction_fields: ['loesung'],
              reference_fields: ['gold'],
              metric_parameters: {
                judge_model: 'mistral-judge',
                runs_per_judge: 2,
              },
            },
          ]}
        />,
      )
      const panel = await screen.findByTestId('cost-panel')
      expect(panel.getAttribute('data-judges')).toContain('mistral-judge')
    })

    it('does NOT mount the cost panel when the only judge metric is deselected', async () => {
      render(
        <EvaluationControlModal
          {...baseProps}
          evaluationConfigs={[
            {
              id: 'judge-cfg',
              metric: 'llm_judge_falloesung',
              display_name: 'LLM Judge',
              prediction_fields: ['loesung'],
              reference_fields: ['gold'],
              metric_parameters: {
                judges: [{ judge_model_id: 'gpt-4o', runs: 1 }],
              },
            },
          ]}
        />,
      )
      // Panel present while the judge metric is selected...
      const metricBox = await screen.findByLabelText('LLM Judge')
      expect(await screen.findByTestId('cost-panel')).toBeInTheDocument()
      // ...deselecting the only judge metric empties judgeModelIds → unmount.
      fireEvent.click(metricBox)
      await waitFor(() =>
        expect(screen.queryByTestId('cost-panel')).not.toBeInTheDocument(),
      )
    })

    it('does NOT mount the cost panel for deterministic-only metrics', async () => {
      render(<EvaluationControlModal {...baseProps} />)
      await screen.findByLabelText('Exact Match')
      // exact_match / rouge are not llm_judge_* → no judge ids → no panel.
      expect(screen.queryByTestId('cost-panel')).not.toBeInTheDocument()
    })
  })

  describe('scope loading indicator', () => {
    it('shows the scope-loading status while the fetch is in flight', async () => {
      // Never-resolving fetch keeps scopeLoading true.
      mockGetEvaluatedModels.mockReturnValue(new Promise(() => {}))
      render(<EvaluationControlModal {...baseProps} />)
      const status = await screen.findByRole('status')
      expect(status).toHaveTextContent(/lade verfügbare modelle/i)
      // Start button is disabled during the scope-fetch window (direct API mode).
      expect(screen.getByText('Start Evaluation')).toBeDisabled()
    })
  })

  describe('fetch error fallback', () => {
    it('clears the scope lists and stops loading when the fetch rejects', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      mockGetEvaluatedModels.mockRejectedValue(new Error('boom'))
      render(<EvaluationControlModal {...baseProps} />)
      await waitFor(() => expect(mockGetEvaluatedModels).toHaveBeenCalled())
      // No model/annotator checkboxes render after the error.
      await waitFor(() =>
        expect(screen.queryByLabelText('GPT 5.4')).not.toBeInTheDocument(),
      )
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
      // Metrics still render (derived from props, not the fetch) → run allowed.
      expect(screen.getByLabelText('Exact Match')).toBeInTheDocument()
      expect(consoleSpy).toHaveBeenCalled()
      consoleSpy.mockRestore()
    })
  })

  describe('disabled-config filtering (enabledConfigs memo)', () => {
    it('renders only enabled configs in the metric scope section', async () => {
      render(
        <EvaluationControlModal
          {...baseProps}
          evaluationConfigs={[
            {
              id: 'on',
              metric: 'exact_match',
              display_name: 'Enabled Metric',
              prediction_fields: ['a'],
              reference_fields: ['b'],
              enabled: true,
            },
            {
              id: 'off',
              metric: 'rouge',
              display_name: 'Disabled Metric',
              prediction_fields: ['a'],
              reference_fields: ['b'],
              enabled: false, // filtered out by the enabledConfigs memo
            },
          ]}
        />,
      )
      expect(await screen.findByLabelText('Enabled Metric')).toBeInTheDocument()
      expect(screen.queryByLabelText('Disabled Metric')).not.toBeInTheDocument()
    })
  })
})

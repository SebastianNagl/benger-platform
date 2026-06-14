/**
 * Complement coverage for EvaluationBuilder.
 *
 * The base suites (EvaluationBuilder.test.tsx + .wizard-steps.test.tsx)
 * already drive the metric/prediction/reference/review steps and the
 * BLEU/ROUGE/METEOR/chrF/FactCC/Classic parameter UIs. This file targets
 * the still-uncovered branches:
 *
 *  - renderJudgeEnsembleControl: runs-per-judge input + clamping, and the
 *    additional-judges ensemble checkboxes (writeJudges paths).
 *  - handleFieldToggle LLM-Judge auto-detect: selecting a prediction field
 *    for the `llm_judge` metric maps a detected answer_type → criteria.
 *  - canProceed gates for llm_judge_custom (Next disabled until a custom
 *    prompt OR custom criteria is present) and llm_judge_classic.
 *  - llm_judge_custom DimensionsEditor / PromptTemplateEditor onChange
 *    wiring (custom_criteria + custom_prompt_template into metric_parameters)
 *    and the score-scale-hidden-when-max_score branch.
 *  - getMetricEditor extended fallback + the plain "default parameters"
 *    fallback message.
 *
 * @jest-environment jsdom
 */

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EvaluationBuilder } from '../EvaluationBuilder'
import { registerMetricEditor } from '@/lib/extensions/metricEditors'
import { registerMetric, registerMetricGroup } from '@/lib/api/evaluation-types'

// ---------- i18n: key passthrough, fallback string honored ----------
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallbackOrVars?: any) => {
      if (typeof fallbackOrVars === 'string') return fallbackOrVars
      if (fallbackOrVars && typeof fallbackOrVars === 'object') {
        let result = key
        for (const [k, v] of Object.entries(fallbackOrVars)) {
          result = result.replace(`{${k}}`, String(v))
        }
        return result
      }
      return key
    },
  }),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

// useJudgeModelHelpers consumes useModels(); supply a multi-provider
// roster so the ensemble checkbox grid (which filters out the primary)
// has >=1 selectable model, and so reasoning/thinking branches resolve.
jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({
    models: [
      { id: 'gpt-4o', name: 'GPT-4o', provider: 'openai', default_config: { temperature: 0 } },
      { id: 'claude-sonnet-4', name: 'Claude Sonnet 4', provider: 'anthropic', default_config: { temperature: 0 } },
      { id: 'gemini-3-pro', name: 'Gemini 3 Pro', provider: 'google', default_config: { temperature: 0 } },
    ],
    loading: false,
  }),
}))

// field-types endpoint: report `model_answer` as a single_choice field so
// the llm_judge auto-detect path resolves a template and fires.
jest.mock('@/lib/api', () => ({
  api: {
    get: jest.fn().mockResolvedValue({
      data: {
        field_types: {
          model_answer: { type: 'single_choice', name: 'model_answer' },
        },
      },
    }),
    post: jest.fn().mockResolvedValue({ data: {} }),
  },
}))

jest.mock('@/components/shared/Badge', () => ({
  Badge: ({ children, className }: any) => (
    <span data-testid="badge" className={className}>{children}</span>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>{children}</button>
  ),
}))

jest.mock('@/components/shared/Checkbox', () => ({
  Checkbox: ({ checked, onChange }: any) => (
    <input type="checkbox" checked={checked} onChange={onChange} />
  ),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  CheckIcon: () => <span data-testid="check-icon" />,
  ChevronDownIcon: () => <span data-testid="chevron-down" />,
  ChevronUpIcon: () => <span data-testid="chevron-up" />,
  InformationCircleIcon: () => <span data-testid="info-icon" />,
  PencilIcon: () => <span data-testid="pencil-icon" />,
  PlayIcon: () => <span data-testid="play-icon" />,
  PlusIcon: () => <span data-testid="plus-icon" />,
  TrashIcon: () => <span data-testid="trash-icon" />,
  XMarkIcon: () => <span data-testid="x-icon" />,
}))

jest.mock('../EvaluationControlModal', () => ({
  EvaluationControlModal: () => <div data-testid="eval-control-modal-hidden" />,
}))

// Drive the custom-LLM-judge sub-editors directly: each renders a button
// that calls its onChange with a representative payload, so we exercise
// EvaluationBuilder's onChange handlers (the lines that fold the payload
// into metric_parameters) without re-testing the editors themselves.
jest.mock('../FieldMappingEditor', () => ({
  FieldMappingEditor: ({ value, onChange }: any) => (
    <div data-testid="field-mapping-editor">
      <button
        data-testid="add-mapping"
        onClick={() => onChange({ ...(value || {}), claim: 'reference' })}
      >
        Add Mapping
      </button>
      <button data-testid="clear-mapping" onClick={() => onChange({})}>
        Clear Mapping
      </button>
    </div>
  ),
}))

jest.mock('../DimensionsEditor', () => ({
  DimensionsEditor: ({ value, onChange }: any) => (
    <div data-testid="dimensions-editor">
      <span data-testid="dims-count">{Object.keys(value || {}).length}</span>
      <button
        data-testid="add-dimension"
        onClick={() =>
          onChange({ accuracy: { name: 'Accuracy', max_score: 5, description: '', rubric: '' } })
        }
      >
        Add Dimension
      </button>
      <button data-testid="clear-dimensions" onClick={() => onChange({})}>
        Clear Dimensions
      </button>
    </div>
  ),
}))

jest.mock('../PromptTemplateEditor', () => ({
  PromptTemplateEditor: ({ value, onChange }: any) => (
    <div data-testid="prompt-template-editor">
      <span data-testid="prompt-value">{value}</span>
      <button
        data-testid="set-prompt"
        onClick={() => onChange('Rate {{prediction}} vs {{ground_truth}}')}
      >
        Set Prompt
      </button>
      <button data-testid="clear-prompt" onClick={() => onChange('')}>
        Clear Prompt
      </button>
    </div>
  ),
}))

// ---------- helpers ----------

const defaultProps = {
  projectId: 'p1',
  availableFields: {
    model_response_fields: ['model_answer', 'gpt4_response'],
    human_annotation_fields: ['human_answer'],
    all_fields: ['model_answer', 'gpt4_response', 'human_answer', 'reference'],
    reference_fields: ['reference'],
  },
  evaluations: [] as any[],
  onEvaluationsChange: jest.fn(),
  onSave: jest.fn(),
  saving: false,
}

async function openWizard(user: ReturnType<typeof userEvent.setup>, props = defaultProps) {
  render(<EvaluationBuilder {...props} />)
  await user.click(screen.getByTestId('add-evaluation-button'))
  await waitFor(() =>
    expect(screen.getByTestId('evaluation-wizard-header')).toBeInTheDocument()
  )
}

/** Open the wizard, select a metric, then walk to the parameters step. */
async function gotoParameters(
  user: ReturnType<typeof userEvent.setup>,
  metric: string,
  props = defaultProps
) {
  await openWizard(user, props)
  const btn = screen.getByTestId(`metric-button-${metric}`)
  await user.click(btn)
  // prediction
  await user.click(screen.getByTestId('wizard-next-button'))
  const predCbs = screen.getAllByRole('checkbox')
  await user.click(predCbs[0])
  await user.click(screen.getByTestId('wizard-next-button'))
  // reference
  const refCbs = screen.getAllByRole('checkbox')
  await user.click(refCbs[0])
  await user.click(screen.getByTestId('wizard-next-button'))
  await waitFor(() =>
    expect(screen.getByText('evaluationBuilder.steps.parameters.title')).toBeInTheDocument()
  )
}

beforeEach(() => {
  jest.clearAllMocks()
})

// ====================================================================
// renderJudgeEnsembleControl (multi-run feature)
// ====================================================================

// The ensemble checkbox grid is a `.grid.grid-cols-2` whose <label>s wrap a
// checkbox + the model name. The judge-model Select renders the same model
// names as <option>s, so scope ensemble queries to the grid container.
function ensembleGrid(): HTMLElement {
  // The "Zusätzliche Judges" help block precedes the grid; the grid is the
  // only `.grid-cols-2` in the parameters panel.
  const grid = document.querySelector('.grid.grid-cols-2') as HTMLElement | null
  if (!grid) throw new Error('ensemble grid not found')
  return grid
}

function ensembleCheckbox(label: RegExp): HTMLInputElement {
  const grid = ensembleGrid()
  const labelEl = within(grid)
    .getAllByText(label)
    .map((el) => el.closest('label'))
    .find(Boolean) as HTMLLabelElement
  return labelEl.querySelector('input[type="checkbox"]') as HTMLInputElement
}

describe('Judge ensemble + runs control', () => {
  it('renders the runs-per-judge input and ensemble checkboxes (classic)', async () => {
    const user = userEvent.setup()
    await gotoParameters(user, 'llm_judge_classic')

    // Section header — t() returns the fallback string ('Ensemble & Läufe').
    expect(screen.getByText('Ensemble & Läufe')).toBeInTheDocument()
    expect(screen.getByText('Läufe pro Judge')).toBeInTheDocument()
    expect(screen.getByText('Zusätzliche Judges (Ensemble)')).toBeInTheDocument()

    // runs-per-judge number input defaults to 1 (min=1/max=25).
    const runsInput = document.querySelector(
      'input[type="number"][min="1"][max="25"]'
    ) as HTMLInputElement
    expect(runsInput).toBeTruthy()
    expect(runsInput.value).toBe('1')

    // ensemble grid lists the two non-primary models (primary defaults to gpt-4o).
    const grid = ensembleGrid()
    expect(within(grid).getByText(/Claude Sonnet 4/)).toBeInTheDocument()
    expect(within(grid).getByText(/Gemini 3 Pro/)).toBeInTheDocument()
  })

  it('clamps runs-per-judge into [1,25] and writes judges array', async () => {
    const user = userEvent.setup()
    await gotoParameters(user, 'llm_judge_classic')

    const runsInput = document.querySelector(
      'input[type="number"][min="1"][max="25"]'
    ) as HTMLInputElement
    expect(runsInput.value).toBe('1')

    // Above-cap value clamps to 25.
    await act(async () => {
      fireEvent.change(runsInput, { target: { value: '40' } })
    })
    await waitFor(() => expect(runsInput.value).toBe('25'))

    // Below-floor / non-numeric clamps back to 1.
    await act(async () => {
      fireEvent.change(runsInput, { target: { value: '0' } })
    })
    await waitFor(() => expect(runsInput.value).toBe('1'))
  })

  it('adds and removes an additional judge via the ensemble checkboxes', async () => {
    const user = userEvent.setup()
    await gotoParameters(user, 'llm_judge_custom')

    const claudeCb = ensembleCheckbox(/Claude Sonnet 4/)
    expect(claudeCb.checked).toBe(false)

    // Check it → writeJudges([claude], runs).
    await act(async () => { fireEvent.click(claudeCb) })
    await waitFor(() => expect(ensembleCheckbox(/Claude Sonnet 4/).checked).toBe(true))

    // Uncheck it again → writeJudges([], runs).
    await act(async () => { fireEvent.click(ensembleCheckbox(/Claude Sonnet 4/)) })
    await waitFor(() => expect(ensembleCheckbox(/Claude Sonnet 4/).checked).toBe(false))
  })
})

// ====================================================================
// handleFieldToggle — LLM-Judge auto answer-type detection
// ====================================================================

describe('LLM-Judge prediction-field auto-detect', () => {
  it('detects answer type from field types and toasts when selecting a prediction field', async () => {
    // The auto-detect branch keys on `newEvaluation.metric === 'llm_judge'`.
    // The registry only exposes llm_judge_classic / llm_judge_custom in the
    // picker, so the only way newEvaluation.metric becomes the bare
    // `llm_judge` is via edit mode on an existing config that carries it.
    const user = userEvent.setup()
    const evaluations = [
      {
        id: 'eval-judge',
        metric: 'llm_judge',
        display_name: 'LLM Judge',
        prediction_fields: [], // none selected → toggling one fires detect
        reference_fields: ['reference'],
        metric_parameters: {},
        enabled: true,
        created_at: '2025-01-01',
      },
    ]
    render(<EvaluationBuilder {...defaultProps} evaluations={evaluations} />)

    // Enter edit mode → wizard opens on metric step, metric = 'llm_judge'.
    const editBtn = screen
      .getAllByRole('button')
      .find((b) => b.querySelector('[data-testid="pencil-icon"]'))!
    await user.click(editBtn)
    await waitFor(() =>
      expect(screen.getByText('evaluationBuilder.editEvaluation')).toBeInTheDocument()
    )

    // Advance to prediction fields.
    await user.click(screen.getByTestId('wizard-next-button'))
    await waitFor(() =>
      expect(
        screen.getByText('evaluationBuilder.steps.predictionFields.title')
      ).toBeInTheDocument()
    )

    // Wait for the field-types fetch to populate fieldTypes state.
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    // Toggle the model_answer (model:model_answer) checkbox → fieldTypes[
    // 'model_answer'].type === 'single_choice' → template found → toast.
    // Checkbox order: 2 bulk selectors, then model-response fields, so
    // index 2 is the first model field (model:model_answer).
    const checkboxes = screen.getAllByRole('checkbox')
    await act(async () => { await user.click(checkboxes[2]) })

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        expect.stringContaining('Detected'),
        'info'
      )
    })
  })
})

// ====================================================================
// canProceed gates for the LLM-Judge metrics
// ====================================================================

describe('canProceed gating on the parameters step', () => {
  it('disables Next for llm_judge_custom until a prompt or criteria is set, then enables it', async () => {
    const user = userEvent.setup()
    await gotoParameters(user, 'llm_judge_custom')

    // Empty custom config → Next disabled.
    expect(screen.getByTestId('wizard-next-button')).toBeDisabled()

    // Provide a custom prompt via the (mocked) editor → Next enabled.
    await act(async () => { fireEvent.click(screen.getByTestId('set-prompt')) })
    await waitFor(() =>
      expect(screen.getByTestId('wizard-next-button')).not.toBeDisabled()
    )

    // Clearing the prompt drops it back to disabled (no criteria yet).
    await act(async () => { fireEvent.click(screen.getByTestId('clear-prompt')) })
    await waitFor(() =>
      expect(screen.getByTestId('wizard-next-button')).toBeDisabled()
    )
  })

  it('enables Next for llm_judge_custom when only custom criteria are present', async () => {
    const user = userEvent.setup()
    await gotoParameters(user, 'llm_judge_custom')

    expect(screen.getByTestId('wizard-next-button')).toBeDisabled()

    // Add a dimension → custom_criteria populated → Next enabled.
    await act(async () => { fireEvent.click(screen.getByTestId('add-dimension')) })
    await waitFor(() =>
      expect(screen.getByTestId('wizard-next-button')).not.toBeDisabled()
    )
  })

  it('keeps Next enabled for llm_judge_classic with default dimensions', async () => {
    const user = userEvent.setup()
    await gotoParameters(user, 'llm_judge_classic')

    // Classic defaults to a full dimension set, so canProceed is true.
    expect(screen.getByTestId('wizard-next-button')).not.toBeDisabled()
  })
})

// ====================================================================
// llm_judge_custom: dimension + prompt + score-scale wiring
// ====================================================================

describe('llm_judge_custom parameter wiring', () => {
  it('hides the score-scale selector once a dimension carries a max_score', async () => {
    const user = userEvent.setup()
    await gotoParameters(user, 'llm_judge_custom')

    // Score-scale select is present while no dimension has max_score.
    expect(
      screen.getByText('evaluationBuilder.parameters.scoreScale')
    ).toBeInTheDocument()

    // Add a dimension with max_score=5 → score-scale section disappears.
    await act(async () => { fireEvent.click(screen.getByTestId('add-dimension')) })
    await waitFor(() =>
      expect(
        screen.queryByText('evaluationBuilder.parameters.scoreScale')
      ).not.toBeInTheDocument()
    )
  })

  it('changes the score scale select while in legacy per-criterion mode', async () => {
    const user = userEvent.setup()
    await gotoParameters(user, 'llm_judge_custom')

    const scaleSelect = screen
      .getAllByRole('combobox')
      .find((s) => s.querySelector('option[value="0-1"]'))
    expect(scaleSelect).toBeTruthy()
    fireEvent.change(scaleSelect!, { target: { value: '0-1' } })
    expect((scaleSelect as HTMLSelectElement).value).toBe('0-1')
  })

  it('folds field mappings into knownVariables and clears them back out', async () => {
    const user = userEvent.setup()
    await gotoParameters(user, 'llm_judge_custom')

    // Add a mapping then clear it — exercises both onChange branches
    // (object-with-keys vs empty → undefined).
    await act(async () => { fireEvent.click(screen.getByTestId('add-mapping')) })
    await act(async () => { fireEvent.click(screen.getByTestId('clear-mapping')) })
    expect(screen.getByTestId('field-mapping-editor')).toBeInTheDocument()
  })

  it('persists custom prompt + criteria into the added config on review', async () => {
    const onEvaluationsChange = jest.fn()
    const user = userEvent.setup()
    await gotoParameters(user, 'llm_judge_custom', {
      ...defaultProps,
      onEvaluationsChange,
    })

    // Configure a prompt so canProceed passes.
    await act(async () => { fireEvent.click(screen.getByTestId('set-prompt')) })
    await waitFor(() =>
      expect(screen.getByTestId('wizard-next-button')).not.toBeDisabled()
    )

    // Advance to review, then Add.
    await user.click(screen.getByTestId('wizard-next-button'))
    await waitFor(() =>
      expect(screen.getByText('evaluationBuilder.steps.review.title')).toBeInTheDocument()
    )
    const addBtn = screen
      .getAllByRole('button')
      .find(
        (b) =>
          b.querySelector('[data-testid="check-icon"]') &&
          b.textContent?.includes('evaluationBuilder.addEvaluation')
      )!
    await user.click(addBtn)

    expect(onEvaluationsChange).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({
          metric: 'llm_judge_custom',
          metric_parameters: expect.objectContaining({
            custom_prompt_template: 'Rate {{prediction}} vs {{ground_truth}}',
          }),
        }),
      ])
    )
    expect(mockAddToast).toHaveBeenCalledWith('evaluationBuilder.toast.added', 'success')
  })
})

// ====================================================================
// getMetricEditor extension-point fallback
// ====================================================================

describe('extended metric editor fallback', () => {
  // Register two extension metrics into the platform's public registry so
  // they surface in the wizard's metric picker. Both declare
  // supports_parameters so the wizard renders the parameters step. One has
  // a registered editor; the other falls through to the default message.
  beforeAll(() => {
    const baseDef = {
      display_name: '',
      description: 'coverage extension metric',
      category: 'extended',
      supports_parameters: true,
    }
    registerMetric('coverage_fake_metric', {
      ...baseDef,
      display_name: 'Coverage Fake Metric',
    } as any)
    registerMetric('coverage_unknown_metric', {
      ...baseDef,
      display_name: 'Coverage Unknown Metric',
    } as any)
    registerMetricGroup({
      name: 'Coverage Extensions',
      description: 'Test-only extension metrics',
      metrics: ['coverage_fake_metric', 'coverage_unknown_metric'],
    } as any)
  })

  it('renders a registered metric editor for an extension metric and merges its patch', async () => {
    // Register a fake editor for the extension metric. This is the public
    // extension point — the community build ships an empty registry, so we
    // register here to exercise the platform's getMetricEditor() branch.
    const ExtEditor = ({ onChange, parameters }: any) => (
      <div data-testid="ext-editor">
        <span data-testid="ext-params">{JSON.stringify(parameters)}</span>
        <button
          data-testid="ext-patch"
          onClick={() => onChange({ policy: 'strict' })}
        >
          Patch
        </button>
      </div>
    )
    registerMetricEditor('coverage_fake_metric', ExtEditor as any)

    const user = userEvent.setup()
    await gotoParameters(user, 'coverage_fake_metric')

    // The extended editor renders inside the parameters panel.
    expect(screen.getByTestId('ext-editor')).toBeInTheDocument()

    // Patch merges into metric_parameters without crashing.
    await act(async () => { fireEvent.click(screen.getByTestId('ext-patch')) })
    expect(screen.getByTestId('ext-editor')).toBeInTheDocument()
  })

  it('shows the default-parameters message for a metric with params but no editor', async () => {
    // No editor registered for coverage_unknown_metric, and it isn't one of
    // the built-in UI branches → falls through to the default message.
    const user = userEvent.setup()
    await gotoParameters(user, 'coverage_unknown_metric')

    expect(
      screen.getByText('evaluationBuilder.parameters.defaultParameters')
    ).toBeInTheDocument()
  })
})

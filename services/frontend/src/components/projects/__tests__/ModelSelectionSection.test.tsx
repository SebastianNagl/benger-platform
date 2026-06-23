/**
 * Tests for ModelSelectionSection — the collapsible "Model Selection" block on
 * the project detail page.
 *
 * The component is purely presentational: every piece of state and every
 * handler is prop-drilled in, so the tests drive it directly through props and
 * assert on rendered DOM + handler callbacks. Covered:
 *   - the outer canEditProject() gate (read-only message vs editable shell)
 *   - the collapsed summary badge (loading / error / count / no-models)
 *   - expand/collapse toggle
 *   - loading state
 *   - error states: NO_API_KEYS (with "configure" button), generic with a
 *     message, generic falling back to the default copy
 *   - the model checklist: selection highlight, toggle handler, description,
 *     thinking badge, provider colour (known + fallback)
 *   - per-model config for selected models: temperature (free + fixed/disabled),
 *     max-tokens, and both reasoning-config shapes ('select' and 'budget',
 *     including the budget "custom" input branch)
 *   - the empty-catalog ("no models for your profile") branch
 *   - the inner read-only branch (canEditProject flips false mid-expand)
 *
 * @jest-environment jsdom
 */

import type { Model, ModelError } from '@/hooks/useModels'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import {
  ModelSelectionSection,
  providerColors,
  type ReasoningConfig,
} from '@/components/projects/ModelSelectionSection'

// --- Lightweight shared-component mocks -----------------------------------
// Button: plain <button>.
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, ...props }: any) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}))

// Tooltip: render the title attribute (string content) + children, mirroring
// the real implementation closely enough to assert tooltip copy.
jest.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({ children, content }: any) => (
    <div title={typeof content === 'string' ? content : undefined}>
      {children}
    </div>
  ),
}))

// Select: a richer mock than the page tests use. It exposes a button per
// SelectItem that calls the parent onValueChange — this lets us exercise the
// reasoning-config 'select' and 'budget' onValueChange branches deterministically.
jest.mock('@/components/shared/Select', () => {
  const React = require('react')
  const Ctx = React.createContext<any>(null)
  return {
    Select: ({ children, onValueChange, displayValue, value }: any) => (
      <Ctx.Provider value={{ onValueChange }}>
        <div data-testid="select" data-value={value}>
          <span data-testid="select-display">{displayValue}</span>
          {children}
        </div>
      </Ctx.Provider>
    ),
    SelectTrigger: ({ children }: any) => <div>{children}</div>,
    SelectValue: () => null,
    SelectContent: ({ children }: any) => <div>{children}</div>,
    SelectItem: ({ children, value }: any) => {
      const ctx = React.useContext(Ctx)
      return (
        <button
          type="button"
          data-testid={`select-item-${value}`}
          onClick={() => ctx?.onValueChange(value)}
        >
          {children}
        </button>
      )
    },
  }
})

// modelConstraints is real — exercise it with crafted parameter_constraints.

// --- Fixtures --------------------------------------------------------------

const makeModel = (overrides: Partial<Model> = {}): Model =>
  ({
    id: 'gpt-x',
    name: 'GPT-X',
    provider: 'OpenAI',
    description: 'A fine model',
    ...overrides,
  }) as Model

// A trivial translator: returns the fallback when supplied, else the key.
const t = (key: string, params?: any): string => {
  if (typeof params === 'string') return params // fallback-as-2nd-arg form
  if (params && typeof params === 'object') {
    if (key === 'project.modelSelection.selectedCount') {
      return `${params.selected} / ${params.total} selected`
    }
  }
  return key
}

type Props = React.ComponentProps<typeof ModelSelectionSection>

const baseProps = (overrides: Partial<Props> = {}): Props => ({
  t,
  canEditProject: () => true,
  getReadOnlyMessage: (title: string) => `read-only: ${title}`,
  expandedModels: true,
  setExpandedModels: jest.fn(),
  modelsLoading: false,
  modelsError: null,
  sortedModels: [makeModel()],
  availableModels: [makeModel()],
  selectedModelIds: [],
  modelConfigs: {},
  handleModelToggle: jest.fn(),
  updateModelConfig: jest.fn(),
  getReasoningConfig: () => undefined,
  onNavigateToProfile: jest.fn(),
  ...overrides,
})

const renderSection = (overrides: Partial<Props> = {}) =>
  render(<ModelSelectionSection {...baseProps(overrides)} />)

// --- Tests -----------------------------------------------------------------

describe('ModelSelectionSection', () => {
  describe('outer canEditProject gate', () => {
    it('renders only the read-only message when the user cannot edit', () => {
      renderSection({ canEditProject: () => false })
      expect(
        screen.getByText('read-only: project.modelSelection.title')
      ).toBeInTheDocument()
      // The editable header button is absent.
      expect(
        screen.queryByText('project.modelSelection.title')
      ).not.toBeInTheDocument()
    })

    it('renders the editable header when the user can edit', () => {
      renderSection()
      expect(
        screen.getByText('project.modelSelection.title')
      ).toBeInTheDocument()
    })
  })

  describe('collapsed summary badge', () => {
    it('shows the loading label when collapsed + loading', () => {
      renderSection({ expandedModels: false, modelsLoading: true })
      expect(
        screen.getByText('project.modelSelection.loading')
      ).toBeInTheDocument()
    })

    it('shows the error label when collapsed + error', () => {
      renderSection({
        expandedModels: false,
        modelsError: { type: 'OTHER', message: 'boom' } as ModelError,
      })
      expect(
        screen.getByText('project.modelSelection.errorLoading')
      ).toBeInTheDocument()
    })

    it('shows the selected/total count when collapsed + models present', () => {
      renderSection({
        expandedModels: false,
        selectedModelIds: ['gpt-x'],
        sortedModels: [makeModel(), makeModel({ id: 'b', name: 'B' })],
      })
      expect(screen.getByText('1 / 2 selected')).toBeInTheDocument()
    })

    it('shows the no-models label when collapsed + sortedModels is null', () => {
      renderSection({ expandedModels: false, sortedModels: null })
      expect(
        screen.getByText('project.modelSelection.noModelsAvailable')
      ).toBeInTheDocument()
    })

    it('hides the badge entirely when expanded', () => {
      renderSection({ expandedModels: true, sortedModels: null })
      expect(
        screen.queryByText('project.modelSelection.noModelsAvailable')
      ).not.toBeInTheDocument()
    })
  })

  describe('expand / collapse toggle', () => {
    it('flips setExpandedModels when the header button is clicked', async () => {
      const user = userEvent.setup()
      const setExpandedModels = jest.fn()
      renderSection({ expandedModels: false, setExpandedModels })
      await user.click(
        screen.getByRole('button', {
          name: /project\.modelSelection\.title/i,
        })
      )
      expect(setExpandedModels).toHaveBeenCalledWith(true)
    })

    it('passes the negation of the current expanded state', async () => {
      const user = userEvent.setup()
      const setExpandedModels = jest.fn()
      renderSection({ expandedModels: true, setExpandedModels })
      await user.click(
        screen.getByRole('button', {
          name: /project\.modelSelection\.title/i,
        })
      )
      expect(setExpandedModels).toHaveBeenCalledWith(false)
    })
  })

  describe('loading state (expanded)', () => {
    it('shows the loadingModels copy', () => {
      renderSection({ modelsLoading: true })
      expect(
        screen.getByText('project.modelSelection.loadingModels')
      ).toBeInTheDocument()
    })
  })

  describe('error states (expanded)', () => {
    it('NO_API_KEYS shows the no-keys message + configure button that navigates', async () => {
      const user = userEvent.setup()
      const onNavigateToProfile = jest.fn()
      renderSection({
        modelsError: { type: 'NO_API_KEYS' } as ModelError,
        onNavigateToProfile,
      })
      expect(
        screen.getByText('project.modelSelection.noApiKeys')
      ).toBeInTheDocument()
      await user.click(
        screen.getByRole('button', {
          name: 'project.modelSelection.configureApiKeys',
        })
      )
      expect(onNavigateToProfile).toHaveBeenCalledTimes(1)
    })

    it('generic error shows the error message and no configure button', () => {
      renderSection({
        modelsError: { type: 'OTHER', message: 'Network down' } as ModelError,
      })
      expect(screen.getByText('Network down')).toBeInTheDocument()
      expect(
        screen.queryByRole('button', {
          name: 'project.modelSelection.configureApiKeys',
        })
      ).not.toBeInTheDocument()
    })

    it('generic error with no message falls back to failedToLoad copy', () => {
      renderSection({
        modelsError: { type: 'OTHER' } as ModelError,
      })
      expect(
        screen.getByText('project.modelSelection.failedToLoad')
      ).toBeInTheDocument()
    })
  })

  describe('inner read-only branch', () => {
    it('shows the read-only message when canEditProject flips false at the inner gate', () => {
      // canEditProject true at the outer gate, false at the inner one — drive
      // it via a counter so the second call (inner branch) returns false.
      let calls = 0
      const canEditProject = () => {
        calls += 1
        // first call (outer) true, all later calls false
        return calls === 1
      }
      renderSection({ canEditProject })
      expect(
        screen.getByText('read-only: project.modelSelection.title')
      ).toBeInTheDocument()
    })
  })

  describe('empty catalog branch', () => {
    it('shows the no-models-for-profile copy + configure button', async () => {
      const user = userEvent.setup()
      const onNavigateToProfile = jest.fn()
      renderSection({ sortedModels: [], onNavigateToProfile })
      expect(
        screen.getByText('project.modelSelection.noModelsForProfile')
      ).toBeInTheDocument()
      await user.click(
        screen.getByRole('button', {
          name: 'project.modelSelection.configureApiKeys',
        })
      )
      expect(onNavigateToProfile).toHaveBeenCalledTimes(1)
    })

    it('also shows the empty branch when sortedModels is null', () => {
      renderSection({ sortedModels: null })
      expect(
        screen.getByText('project.modelSelection.noModelsForProfile')
      ).toBeInTheDocument()
    })
  })

  describe('model checklist', () => {
    it('renders model name + description', () => {
      renderSection({
        sortedModels: [makeModel({ name: 'Claude', description: 'desc here' })],
      })
      expect(screen.getByText('Claude')).toBeInTheDocument()
      expect(screen.getByText('desc here')).toBeInTheDocument()
    })

    it('omits the description paragraph when absent', () => {
      renderSection({
        sortedModels: [makeModel({ description: undefined })],
      })
      // name still there
      expect(screen.getByText('GPT-X')).toBeInTheDocument()
    })

    it('checkbox reflects selection and calls handleModelToggle on click', async () => {
      const user = userEvent.setup()
      const handleModelToggle = jest.fn()
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        selectedModelIds: [],
        handleModelToggle,
      })
      const checkbox = screen.getByRole('checkbox') as HTMLInputElement
      expect(checkbox.checked).toBe(false)
      await user.click(checkbox)
      expect(handleModelToggle).toHaveBeenCalledWith('m1')
    })

    it('shows a checked box for a selected model', () => {
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
      })
      expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(
        true
      )
    })

    it('renders a known provider badge with the provider name', () => {
      renderSection({
        sortedModels: [makeModel({ provider: 'Anthropic' })],
      })
      // provider label is rendered as text
      expect(screen.getByText('Anthropic')).toBeInTheDocument()
      // sanity: the colour map carries Anthropic
      expect(providerColors.Anthropic).toMatch(/orange/)
    })

    it('falls back gracefully for an unknown provider', () => {
      renderSection({
        sortedModels: [makeModel({ provider: 'MysteryCorp' as any })],
      })
      expect(screen.getByText('MysteryCorp')).toBeInTheDocument()
    })

    it('shows the Thinking badge when the model has a reasoning config', () => {
      const reasoning: ReasoningConfig = {
        parameter: 'reasoning_effort',
        type: 'select',
        values: ['low', 'high'],
        default: 'low',
        label: 'Effort',
      }
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        getReasoningConfig: () => reasoning,
      })
      expect(screen.getByText('Thinking')).toBeInTheDocument()
    })
  })

  describe('per-model config (selected)', () => {
    it('renders temperature + max-tokens inputs for a selected model', () => {
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: { temperature: 0.5, max_tokens: 2000 } },
      })
      const temp = screen.getByDisplayValue('0.5') as HTMLInputElement
      expect(temp).toHaveAttribute('type', 'number')
      expect(screen.getByDisplayValue('2000')).toBeInTheDocument()
    })

    it('does not render config inputs for an unselected model', () => {
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        selectedModelIds: [],
      })
      expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
    })

    it('calls updateModelConfig with a parsed float when temperature changes', async () => {
      const user = userEvent.setup()
      const updateModelConfig = jest.fn()
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: {} },
        updateModelConfig,
      })
      // first spinbutton is temperature
      const [tempInput] = screen.getAllByRole('spinbutton')
      await user.type(tempInput, '1')
      expect(updateModelConfig).toHaveBeenLastCalledWith('m1', 'temperature', 1)
    })

    it('clearing temperature sends undefined', async () => {
      const user = userEvent.setup()
      const updateModelConfig = jest.fn()
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: { temperature: 0.5 } },
        updateModelConfig,
      })
      const temp = screen.getByDisplayValue('0.5') as HTMLInputElement
      await user.clear(temp)
      expect(updateModelConfig).toHaveBeenLastCalledWith(
        'm1',
        'temperature',
        undefined
      )
    })

    it('calls updateModelConfig with a parsed int when max-tokens changes', async () => {
      const user = userEvent.setup()
      const updateModelConfig = jest.fn()
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: {} },
        updateModelConfig,
      })
      const spinbuttons = screen.getAllByRole('spinbutton')
      const maxTokens = spinbuttons[1] // second spinbutton is max_tokens
      await user.type(maxTokens, '5')
      expect(updateModelConfig).toHaveBeenLastCalledWith('m1', 'max_tokens', 5)
    })

    it('clearing max-tokens sends undefined', async () => {
      const user = userEvent.setup()
      const updateModelConfig = jest.fn()
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: { max_tokens: 2000 } },
        updateModelConfig,
      })
      const maxTokens = screen.getByDisplayValue('2000') as HTMLInputElement
      await user.clear(maxTokens)
      expect(updateModelConfig).toHaveBeenLastCalledWith(
        'm1',
        'max_tokens',
        undefined
      )
    })

    it('uses the model default-max-tokens as the placeholder when configured', () => {
      const model = makeModel({
        id: 'm1',
        parameter_constraints: { max_tokens: { default: 9001 } } as any,
      })
      renderSection({
        sortedModels: [model],
        availableModels: [model],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: {} },
      })
      const maxTokens = screen.getAllByRole('spinbutton')[1]
      expect(maxTokens).toHaveAttribute('placeholder', '9001')
    })

    it('falls back to the 4000 placeholder when the model has no default-max-tokens', () => {
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: {} },
      })
      const maxTokens = screen.getAllByRole('spinbutton')[1]
      expect(maxTokens).toHaveAttribute('placeholder', '4000')
    })

    it('disables the temperature input for a fixed-temperature model and shows the fixed tooltip', () => {
      const fixedModel = makeModel({
        id: 'm1',
        // parameter_constraints with temperature unsupported → fixed
        parameter_constraints: {
          temperature: { supported: false, required_value: 1 },
        } as any,
      })
      renderSection({
        sortedModels: [fixedModel],
        availableModels: [fixedModel],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: {} },
      })
      const [tempInput] = screen.getAllByRole('spinbutton')
      expect(tempInput).toBeDisabled()
      // The fixed tooltip copy is supplied via fallback string
      expect(
        screen.getByTitle(/This model requires temperature=1/)
      ).toBeInTheDocument()
    })

    it('shows the reason-based tooltip when constraints carry a reason', () => {
      const model = makeModel({
        id: 'm1',
        parameter_constraints: {
          temperature: { supported: true, min: 0, max: 1, reason: 'capped' },
        } as any,
      })
      renderSection({
        sortedModels: [model],
        availableModels: [model],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: {} },
      })
      expect(screen.getByTitle('capped (0-1)')).toBeInTheDocument()
    })
  })

  describe("reasoning config — 'select' type", () => {
    const selectReasoning: ReasoningConfig = {
      parameter: 'reasoning_effort',
      type: 'select',
      values: ['low', 'medium', 'high'],
      default: 'medium',
      label: 'Reasoning Effort',
    }

    const renderWithSelectReasoning = (configOverride: any = {}) =>
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: configOverride },
        getReasoningConfig: () => selectReasoning,
        ...{},
      })

    it('renders the label, the default tag, and capitalised options', () => {
      renderWithSelectReasoning()
      expect(screen.getByText('Reasoning Effort:')).toBeInTheDocument()
      // default tag: t(...,'Default') resolves to the fallback 'Default', and
      // the raw default value ('medium') is rendered alongside it inside one
      // <span> whose combined text reads "(Default: medium)".
      expect(
        screen.getByText(
          (_content, el) =>
            el?.tagName === 'SPAN' &&
            el.textContent === '(Default: medium)'
        )
      ).toBeInTheDocument()
      // options rendered capitalised by the SelectItem children
      expect(screen.getByTestId('select-item-low')).toHaveTextContent('Low')
      expect(screen.getByTestId('select-item-high')).toHaveTextContent('High')
    })

    it('capitalises the display value from the config value', () => {
      renderWithSelectReasoning({ reasoning_effort: 'high' })
      expect(screen.getByTestId('select-display')).toHaveTextContent('High')
    })

    it('falls back to the default for the display value when unset', () => {
      renderWithSelectReasoning({})
      expect(screen.getByTestId('select-display')).toHaveTextContent('Medium')
    })

    it('calls updateModelConfig with the chosen value on selection', async () => {
      const user = userEvent.setup()
      const updateModelConfig = jest.fn()
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: {} },
        getReasoningConfig: () => selectReasoning,
        updateModelConfig,
      })
      await user.click(screen.getByTestId('select-item-low'))
      expect(updateModelConfig).toHaveBeenCalledWith(
        'm1',
        'reasoning_effort',
        'low'
      )
    })
  })

  describe("reasoning config — 'budget' type", () => {
    const budgetReasoning: ReasoningConfig = {
      parameter: 'thinking_budget',
      type: 'budget',
      presets: [
        { label: 'Low', value: 1024 },
        { label: 'High', value: 8192 },
      ],
      min: 512,
      max: 16000,
      default: 1024,
      label: 'Thinking Budget',
    }

    const renderBudget = (configOverride: any = {}) =>
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: configOverride },
        getReasoningConfig: () => budgetReasoning,
      })

    it('renders the min-max range and the preset options + Custom', () => {
      renderBudget()
      // range span (numbers locale-formatted)
      expect(screen.getByText(/512.*16,000|512.*16.000/)).toBeInTheDocument()
      expect(screen.getByTestId('select-item-1024')).toHaveTextContent(
        /Low \(1,024 tokens\)|Low \(1.024 tokens\)/
      )
      expect(screen.getByTestId('select-item-custom')).toBeInTheDocument()
    })

    it('shows the matching preset label as the display value', () => {
      renderBudget({ thinking_budget: 8192 })
      expect(screen.getByTestId('select-display')).toHaveTextContent(
        /High \(8,192 tokens\)|High \(8.192 tokens\)/
      )
    })

    it('selecting a preset writes the int value + disables custom', async () => {
      const user = userEvent.setup()
      const updateModelConfig = jest.fn()
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: {} },
        getReasoningConfig: () => budgetReasoning,
        updateModelConfig,
      })
      await user.click(screen.getByTestId('select-item-8192'))
      expect(updateModelConfig).toHaveBeenCalledWith(
        'm1',
        'thinking_budget',
        8192
      )
      expect(updateModelConfig).toHaveBeenCalledWith(
        'm1',
        'thinking_budget_custom',
        false
      )
    })

    it('selecting Custom enables custom mode and surfaces the custom number input', async () => {
      const user = userEvent.setup()
      const updateModelConfig = jest.fn()
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: {} },
        getReasoningConfig: () => budgetReasoning,
        updateModelConfig,
      })
      await user.click(screen.getByTestId('select-item-custom'))
      // value falls back to default, custom flag set
      expect(updateModelConfig).toHaveBeenCalledWith(
        'm1',
        'thinking_budget',
        1024
      )
      expect(updateModelConfig).toHaveBeenCalledWith(
        'm1',
        'thinking_budget_custom',
        true
      )
    })

    it('renders the custom input + "Custom" display when already in custom mode', () => {
      renderBudget({ thinking_budget: 3000, thinking_budget_custom: true })
      expect(screen.getByTestId('select-display')).toHaveTextContent('Custom')
      // a number input bound to the current custom value exists
      expect(screen.getByDisplayValue('3000')).toBeInTheDocument()
    })

    it('renders an empty custom input when custom mode is on but no value is set', () => {
      renderBudget({ thinking_budget_custom: true })
      // showCustomInput is true via the explicit flag; currentValue is
      // undefined → the input falls back to '' (value={currentValue ?? ''}).
      expect(screen.getByTestId('select-display')).toHaveTextContent('Custom')
      const inputs = screen.getAllByRole('spinbutton')
      // temp, max_tokens, then the custom budget input — the last one is empty
      const customInput = inputs[inputs.length - 1] as HTMLInputElement
      expect(customInput.value).toBe('')
    })

    it('renders the custom input when the value matches no preset (implicit custom)', () => {
      renderBudget({ thinking_budget: 4321 })
      // not a preset → custom input shows even without the explicit flag
      expect(screen.getByDisplayValue('4321')).toBeInTheDocument()
      expect(screen.getByTestId('select-display')).toHaveTextContent('Custom')
    })

    it('editing the custom input writes a parsed int', async () => {
      const user = userEvent.setup()
      const updateModelConfig = jest.fn()
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: { thinking_budget: 3000, thinking_budget_custom: true } },
        getReasoningConfig: () => budgetReasoning,
        updateModelConfig,
      })
      const custom = screen.getByDisplayValue('3000') as HTMLInputElement
      await user.type(custom, '1')
      // typing appends → '30001'
      expect(updateModelConfig).toHaveBeenLastCalledWith(
        'm1',
        'thinking_budget',
        30001
      )
    })

    it('clearing the custom input writes undefined', async () => {
      const user = userEvent.setup()
      const updateModelConfig = jest.fn()
      renderSection({
        sortedModels: [makeModel({ id: 'm1' })],
        availableModels: [makeModel({ id: 'm1' })],
        selectedModelIds: ['m1'],
        modelConfigs: { m1: { thinking_budget: 3000, thinking_budget_custom: true } },
        getReasoningConfig: () => budgetReasoning,
        updateModelConfig,
      })
      const custom = screen.getByDisplayValue('3000') as HTMLInputElement
      await user.clear(custom)
      expect(updateModelConfig).toHaveBeenLastCalledWith(
        'm1',
        'thinking_budget',
        undefined
      )
    })

    it('does NOT render the select-only default tag for the budget type', () => {
      renderBudget()
      // The 'select'-type branch renders a "Default: <x>" tag; the budget
      // branch renders the min-max range instead.
      expect(screen.queryByText('Default')).not.toBeInTheDocument()
    })
  })

  describe('multiple models', () => {
    it('renders each model and only configs the selected ones', () => {
      renderSection({
        sortedModels: [
          makeModel({ id: 'a', name: 'Alpha' }),
          makeModel({ id: 'b', name: 'Beta' }),
        ],
        availableModels: [
          makeModel({ id: 'a', name: 'Alpha' }),
          makeModel({ id: 'b', name: 'Beta' }),
        ],
        selectedModelIds: ['a'],
        modelConfigs: { a: {} },
      })
      expect(screen.getByText('Alpha')).toBeInTheDocument()
      expect(screen.getByText('Beta')).toBeInTheDocument()
      // exactly two spinbuttons (temp + max_tokens) — only Alpha is selected
      expect(screen.getAllByRole('spinbutton')).toHaveLength(2)
      // checkboxes: 2 total, 1 checked
      const checkboxes = screen.getAllByRole('checkbox') as HTMLInputElement[]
      expect(checkboxes).toHaveLength(2)
      expect(checkboxes.filter((c) => c.checked)).toHaveLength(1)
    })
  })
})

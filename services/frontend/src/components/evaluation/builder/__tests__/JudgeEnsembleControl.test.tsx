/**
 * JudgeEnsembleControl — unit tests.
 *
 * Focus: the BYOM credential gating inside the additional-judges ensemble
 * grid. A custom judge (`is_official === false`) that requires an API key
 * the user has not stored (`has_credential === false`) renders its checkbox
 * disabled with a muted label and an amber configure-key hint linking to
 * /models; official judges and credentialed customs stay
 * selectable and write metric_parameters.judges via setNewEvaluation.
 *
 * judgeModels is a plain prop (no useModels mock needed). next/link is the
 * real component — it renders a plain <a href> under jsdom.
 *
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { JudgeEnsembleControl } from '../JudgeEnsembleControl'

// i18n: key passthrough, fallback string honored (same pattern as the
// EvaluationBuilder suites).
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

// The primary judge (metric_parameters.judge_model) is filtered OUT of the
// grid, so include a second official to prove officials render enabled.
const judgeModels = [
  { id: 'gpt-4o', name: 'GPT-4o', provider: 'openai' },
  { id: 'claude-sonnet-4', name: 'Claude Sonnet 4', provider: 'anthropic' },
  {
    id: 'custom-haskey',
    name: 'Keyed Llama',
    provider: 'custom',
    is_official: false,
    requires_api_key: true,
    has_credential: true,
  },
  {
    id: 'custom-nokey',
    name: 'Locked Llama',
    provider: 'custom',
    is_official: false,
    requires_api_key: true,
    has_credential: false,
  },
] as any[]

interface TestBuilderState {
  metric: string
  metric_parameters: Record<string, any>
}

const defaultProps = {
  metricParameters: { judge_model: 'gpt-4o' } as Record<string, any>,
  judgeModels,
  setNewEvaluation: jest.fn() as jest.Mock,
}

function renderControl(overrides: Partial<typeof defaultProps> = {}) {
  const props = { ...defaultProps, ...overrides }
  render(<JudgeEnsembleControl<TestBuilderState> {...props} />)
  return props
}

/** Checkbox of the grid entry whose label text matches `name`. */
function entryCheckbox(name: RegExp): HTMLInputElement {
  const labelEl = screen.getByText(name).closest('label')
  if (!labelEl) throw new Error(`no <label> found for ${name}`)
  return labelEl.querySelector('input[type="checkbox"]') as HTMLInputElement
}

beforeEach(() => {
  jest.clearAllMocks()
})

describe('JudgeEnsembleControl — BYOM credential gating', () => {
  it('disables the credential-less custom judge and shows the amber hint with a /models link', () => {
    renderControl()

    // Locked custom: checkbox disabled, label muted, Custom badge shown.
    const lockedCb = entryCheckbox(/Locked Llama/)
    expect(lockedCb).toBeDisabled()
    expect(lockedCb).not.toBeChecked()
    expect(screen.getByText(/Locked Llama/)).toHaveClass('text-gray-400')

    // Amber hint below the locked entry, linking to the key settings page.
    expect(
      screen.getByText('customModels.picker.missingKey')
    ).toBeInTheDocument()
    const link = screen
      .getByText('customModels.picker.configureKey')
      .closest('a')
    expect(link).toHaveAttribute('href', '/models')

    // Official (non-primary) and credentialed custom stay enabled…
    expect(entryCheckbox(/Claude Sonnet 4/)).not.toBeDisabled()
    expect(entryCheckbox(/Keyed Llama/)).not.toBeDisabled()
    expect(screen.getByText(/Keyed Llama/)).not.toHaveClass('text-gray-400')

    // …and the primary judge is not offered as an additional judge.
    expect(screen.queryByText(/GPT-4o/)).not.toBeInTheDocument()

    // Both customs carry the Custom badge under the custom section header.
    expect(screen.getAllByTestId('custom-badge')).toHaveLength(2)
    expect(
      screen.getByText('customModels.picker.customSection')
    ).toBeInTheDocument()
  })

  it('clicking the locked checkbox does not call setNewEvaluation', async () => {
    const user = userEvent.setup()
    const { setNewEvaluation } = renderControl()

    await user.click(entryCheckbox(/Locked Llama/))

    expect(setNewEvaluation).not.toHaveBeenCalled()
  })

  it('clicking the credentialed custom writes it into metric_parameters.judges', async () => {
    const user = userEvent.setup()
    const { setNewEvaluation } = renderControl()

    await user.click(entryCheckbox(/Keyed Llama/))

    expect(setNewEvaluation).toHaveBeenCalledTimes(1)

    // setNewEvaluation receives an updater fn — apply it to a prev state to
    // assert the written shape (primary judge first, then the addition).
    const updater = setNewEvaluation.mock.calls[0][0]
    const prev: TestBuilderState = {
      metric: 'llm_judge_classic',
      metric_parameters: { judge_model: 'gpt-4o', temperature: 0.1 },
    }
    const next = updater(prev)

    expect(next.metric_parameters.judges).toEqual([
      { judge_model_id: 'gpt-4o', runs: 1 },
      { judge_model_id: 'custom-haskey', runs: 1 },
    ])
    expect(next.metric_parameters.runs_per_judge).toBe(1)
    // Unrelated state slices are preserved.
    expect(next.metric).toBe('llm_judge_classic')
    expect(next.metric_parameters.temperature).toBe(0.1)
  })

  it('clicking an enabled official judge also goes through setNewEvaluation', async () => {
    const user = userEvent.setup()
    const { setNewEvaluation } = renderControl()

    await user.click(entryCheckbox(/Claude Sonnet 4/))

    const updater = setNewEvaluation.mock.calls[0][0]
    const next = updater({
      metric: 'llm_judge_classic',
      metric_parameters: { judge_model: 'gpt-4o' },
    })
    expect(next.metric_parameters.judges).toEqual([
      { judge_model_id: 'gpt-4o', runs: 1 },
      { judge_model_id: 'claude-sonnet-4', runs: 1 },
    ])
  })
})

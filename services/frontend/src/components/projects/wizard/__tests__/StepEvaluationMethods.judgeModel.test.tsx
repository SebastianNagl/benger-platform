/**
 * @jest-environment jsdom
 *
 * StepEvaluationMethods - the judge model a toggled LLM judge starts with.
 *
 * The judge picker displays the shared default model for a config that names
 * none, while the worker runs a config without a judge model on its own
 * fallback. Toggling a judge therefore stored no model, and grading used a
 * different judge than the one on screen. The toggle now stores the model the
 * picker shows.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen, within } from '@testing-library/react'

import {
  type EvaluationConfig,
  registerMetric,
} from '@/lib/api/evaluation-types'
import { DEFAULT_MODEL_ID } from '@/lib/modelDefaults'
import { StepEvaluationMethods } from '../StepEvaluationMethods'

let mockModels: { id: string; name: string }[] = []

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, def?: any) => (typeof def === 'string' ? def : key),
  }),
}))

jest.mock('@/lib/extensions/slots', () => ({
  useSlot: () => null,
  getSlot: () => null,
  hasSlot: () => false,
  registerSlot: jest.fn(),
}))

jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({ models: mockModels }),
}))

function toggleAndCapture(metricKey: string): EvaluationConfig {
  const onEvaluationConfigsChange = jest.fn()
  render(
    <StepEvaluationMethods
      evaluationConfigs={[]}
      onEvaluationConfigsChange={onEvaluationConfigsChange}
      immediateEvaluationEnabled={false}
      onImmediateEvaluationChange={jest.fn()}
      annotationFields={[{ name: 'loesung', type: 'TextArea' } as any]}
      dataColumns={['musterloesung']}
      selectedModelIds={[]}
    />,
  )
  const row = screen.getByTestId(`wizard-metric-${metricKey}`)
  fireEvent.click(within(row).getByRole('checkbox'))
  const configs: EvaluationConfig[] =
    onEvaluationConfigsChange.mock.calls.at(-1)![0]
  return configs.find((c) => c.metric === metricKey)!
}

describe('StepEvaluationMethods: judge model of a toggled judge', () => {
  afterEach(() => {
    mockModels = []
  })

  it('stores the default model the judge picker shows', () => {
    mockModels = [
      { id: 'gpt-4o', name: 'GPT-4o' },
      { id: DEFAULT_MODEL_ID, name: 'Default model' },
    ]
    const cfg = toggleAndCapture('llm_judge_classic')
    expect((cfg.metric_parameters as any)?.judge_model).toBe(DEFAULT_MODEL_ID)
  })

  it('stores no model when the catalog does not offer the default', () => {
    // The picker then shows its placeholder, and the choice is the user's.
    mockModels = [{ id: 'gpt-4o', name: 'GPT-4o' }]
    const cfg = toggleAndCapture('llm_judge_classic')
    expect((cfg.metric_parameters as any)?.judge_model).toBeUndefined()
  })

  it('keeps a judge model the metric declares itself', () => {
    mockModels = [{ id: DEFAULT_MODEL_ID, name: 'Default model' }]
    registerMetric('llm_judge_custom', {
      name: 'llm_judge_custom',
      display_name: 'Custom LLM Judge',
      description: 'test metric',
      category: 'LLM-as-Judge',
      status: 'stable',
      supports_parameters: true,
      default_parameters: { judge_model: 'claude-sonnet-4-5' },
    } as any)
    const cfg = toggleAndCapture('llm_judge_custom')
    expect((cfg.metric_parameters as any)?.judge_model).toBe(
      'claude-sonnet-4-5',
    )
  })

  it('gives a metric that is not a judge no judge model', () => {
    mockModels = [{ id: DEFAULT_MODEL_ID, name: 'Default model' }]
    const cfg = toggleAndCapture('rouge')
    expect((cfg.metric_parameters as any)?.judge_model).toBeUndefined()
  })
})

/**
 * @jest-environment jsdom
 *
 * StepEvaluationMethods - which evaluation FIELDS the step offers, and what a
 * freshly-toggled metric starts with.
 *
 * The regression these pin: this step used to build its own prediction list
 * from `__all_model__` plus `model:<field>` only. It offered no human field at
 * all, so a judge that grades a submitted answer could not be configured here.
 * Toggling one produced a config aimed at model generations that an exam
 * project never has, the batch evaluation dispatched zero cells, and the run
 * reported success having graded nothing.
 *
 * Kept separate from StepEvaluationMethods.test.tsx so that file stays about
 * config pairing.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen, within } from '@testing-library/react'

import type { ComponentProps } from 'react'

import {
  type AvailableMetric,
  type EvaluationConfig,
  registerMetric,
} from '@/lib/api/evaluation-types'
import { StepEvaluationMethods } from '../StepEvaluationMethods'

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
  useModels: () => ({ models: [{ id: 'gpt-5-mini', name: 'GPT-5 Mini' }] }),
}))

function setup(
  extra: Partial<ComponentProps<typeof StepEvaluationMethods>> = {},
) {
  const onEvaluationConfigsChange = jest.fn()
  const utils = render(
    <StepEvaluationMethods
      evaluationConfigs={[]}
      onEvaluationConfigsChange={onEvaluationConfigsChange}
      immediateEvaluationEnabled={false}
      onImmediateEvaluationChange={jest.fn()}
      annotationFields={[{ name: 'loesung', type: 'TextArea' } as any]}
      dataColumns={['musterloesung']}
      selectedModelIds={[]}
      {...extra}
    />,
  )
  return { onEvaluationConfigsChange, ...utils }
}

function toggle(metricKey: string) {
  const row = screen.getByTestId(`wizard-metric-${metricKey}`)
  fireEvent.click(within(row).getByRole('checkbox'))
}

/** The field selects only render for a metric that is already selected AND
 * expanded, so seed a config for it and open the row. */
function setupExpanded(metricKey: string) {
  const cfg: EvaluationConfig = {
    id: `${metricKey}-1`,
    metric: metricKey,
    prediction_fields: ['__all_model__'],
    reference_fields: ['musterloesung'],
    enabled: true,
  }
  const utils = setup({ evaluationConfigs: [cfg] })
  const row = screen.getByTestId(`wizard-metric-${metricKey}`)
  fireEvent.click(within(row).getByRole('button'))
  return utils
}

function lastConfigs(mock: jest.Mock): EvaluationConfig[] {
  return mock.mock.calls.at(-1)![0]
}

/** Re-register an EXISTING core metric with declared fields. `registerMetric`
 * overrides by key, and only metrics that belong to a rendered group show a
 * row, so overriding a real one is how a test metric becomes reachable. A
 * different metric per test keeps them independent. */
function registerTestMetric(key: string, extra: Partial<AvailableMetric> = {}) {
  registerMetric(key, {
    name: key,
    display_name: key,
    description: 'test metric',
    category: 'Lexical Metrics',
    status: 'stable',
    supports_parameters: false,
    ...extra,
  } as AvailableMetric)
}

describe('offered prediction fields', () => {
  it('offers the human side, which it previously did not', () => {
    setupExpanded('rouge')
    const values = screen
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value)
    expect(values).toContain('human:loesung')
    expect(values).toContain('__all_human__')
  })

  it('still offers the model side and the all-model selector', () => {
    setupExpanded('rouge')
    const values = screen
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value)
    expect(values).toContain('__all_model__')
    expect(values).toContain('model:loesung')
  })
})

describe('what a freshly toggled metric starts with', () => {
  it('leaves a benchmark metric on the model side', () => {
    // ROUGE compares model outputs. Declaring nothing must keep the historical
    // positional default, or every benchmark project silently changes meaning.
    const { onEvaluationConfigsChange } = setup()
    toggle('rouge')
    expect(lastConfigs(onEvaluationConfigsChange)[0].prediction_fields).toEqual(
      ['__all_model__'],
    )
  })

  it('honours a metric that declares human fields', () => {
    registerTestMetric('bleu', {
      default_prediction_fields: ['human:loesung', '__all_human__'],
      default_reference_fields: ['musterloesung'],
    })
    const { onEvaluationConfigsChange } = setup()
    toggle('bleu')
    const cfg = lastConfigs(onEvaluationConfigsChange)[0]
    expect(cfg.prediction_fields).toEqual(['human:loesung', '__all_human__'])
    expect(cfg.reference_fields).toEqual(['musterloesung'])
  })

  it('ignores a declared field the project does not have', () => {
    registerTestMetric('meteor', {
      default_prediction_fields: ['human:nonexistent'],
    })
    const { onEvaluationConfigsChange } = setup()
    toggle('meteor')
    expect(lastConfigs(onEvaluationConfigsChange)[0].prediction_fields).toEqual(
      ['__all_model__'],
    )
  })

  it('keeps the offered subset instead of falling back', () => {
    registerTestMetric('chrf', {
      default_prediction_fields: ['human:nonexistent', 'human:loesung'],
    })
    const { onEvaluationConfigsChange } = setup()
    toggle('chrf')
    expect(lastConfigs(onEvaluationConfigsChange)[0].prediction_fields).toEqual(
      ['human:loesung'],
    )
  })
})

describe('a project with no fields yet', () => {
  it('still reports that it has no fields to map', () => {
    // The two bulk selectors are unconditional, so the option list is never
    // empty. Deriving "has fields" from its length would hide this notice and
    // offer a field mapping with nothing to map.
    setup({ annotationFields: [], dataColumns: [] })
    expect(
      screen.getByText('projects.creation.wizard.step7.noFieldsNote'),
    ).toBeInTheDocument()
  })
})

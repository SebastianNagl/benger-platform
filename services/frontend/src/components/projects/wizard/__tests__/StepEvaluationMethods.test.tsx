/**
 * @jest-environment jsdom
 *
 * StepEvaluationMethods — the wizard's evaluation step. Focus: configs are
 * keyed by ID, not metric, so a metric carrying SEVERAL configs at once
 * (e.g. the synthetic prefill's free/paid Falllösung judge pair) renders one
 * editor per config and edits each independently; unchecking the metric
 * removes the whole group. Uses the real metric registry (core metrics) and
 * the shared native-select mock from jest.config moduleNameMapper.
 *
 * Also pins the step's one extension point: the exam-level Notenschlüssel
 * section (`ProjectWizardEvaluationGradeScale`) renders LAST and receives the
 * raw wizard state + updater; a community build registers nothing and the
 * step is unchanged.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen, within } from '@testing-library/react'

import type { ComponentProps } from 'react'

import type { EvaluationConfig } from '@/lib/api/evaluation-types'
import { StepEvaluationMethods } from '../StepEvaluationMethods'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, def?: any) => (typeof def === 'string' ? def : key),
  }),
}))

// `mock` prefix = hoist-safe; flipped per test to simulate the community
// (nothing registered) and the extended build.
let mockGradeScaleSlotRegistered = false
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => {
    if (name !== 'ProjectWizardEvaluationGradeScale') return null
    if (!mockGradeScaleSlotRegistered) return null
    const GradeScaleStub = ({ data, onChange }: any) => (
      <div
        data-testid="grade-scale-section"
        data-slice={JSON.stringify(data?.gradeScale ?? null)}
      >
        <button
          data-testid="grade-scale-write"
          onClick={() => onChange({ gradeScale: { unit: 'percent' } })}
        />
      </div>
    )
    GradeScaleStub.displayName = 'GradeScaleStub'
    return GradeScaleStub
  },
  getSlot: () => null,
  hasSlot: () => false,
  registerSlot: jest.fn(),
}))

jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({
    models: [
      { id: 'gpt-5-mini', name: 'GPT-5 Mini' },
      { id: 'gpt-5.4-mini', name: 'GPT-5.4 Mini' },
    ],
  }),
}))

const JUDGE_PAIR: EvaluationConfig[] = [
  {
    id: 'pair-free',
    metric: 'llm_judge_classic',
    display_name: 'Notenpunkte (Gratis-Modell)',
    prediction_fields: ['loesung'],
    reference_fields: ['task.musterloesung'],
    enabled: true,
    variant: 'free',
    metric_parameters: { judge_model: 'gpt-5-mini' },
  },
  {
    id: 'pair-paid',
    metric: 'llm_judge_classic',
    display_name: 'Notenpunkte (Abo-Modell)',
    prediction_fields: ['loesung'],
    reference_fields: ['task.musterloesung'],
    enabled: true,
    variant: 'paid',
    metric_parameters: { judge_model: 'gpt-5.4-mini' },
  },
]

function setup(
  configs: EvaluationConfig[] = [],
  extra: Partial<ComponentProps<typeof StepEvaluationMethods>> = {},
) {
  const onEvaluationConfigsChange = jest.fn()
  const onImmediateEvaluationChange = jest.fn()
  const utils = render(
    <StepEvaluationMethods
      evaluationConfigs={configs}
      onEvaluationConfigsChange={onEvaluationConfigsChange}
      immediateEvaluationEnabled={false}
      onImmediateEvaluationChange={onImmediateEvaluationChange}
      annotationFields={[{ name: 'loesung', type: 'TextArea' } as any]}
      dataColumns={['musterloesung']}
      selectedModelIds={[]}
      {...extra}
    />,
  )
  return { onEvaluationConfigsChange, onImmediateEvaluationChange, ...utils }
}

afterEach(() => {
  mockGradeScaleSlotRegistered = false
})

function expandMetric(metricKey: string) {
  const row = screen.getByTestId(`wizard-metric-${metricKey}`)
  // The chevron is the only button in the row (checkbox is an input).
  fireEvent.click(within(row).getByRole('button'))
}

describe('StepEvaluationMethods — same-metric config pairs', () => {
  it('shows both configs as badges and the metric row as checked', () => {
    setup(JUDGE_PAIR)
    expect(screen.getByText('Notenpunkte (Gratis-Modell)')).toBeInTheDocument()
    expect(screen.getByText('Notenpunkte (Abo-Modell)')).toBeInTheDocument()
    const row = screen.getByTestId('wizard-metric-llm_judge_classic')
    expect(within(row).getByRole('checkbox')).toBeChecked()
  })

  it('renders one editor per config with its own judge model and variant tag', () => {
    setup(JUDGE_PAIR)
    expandMetric('llm_judge_classic')
    const first = screen.getByTestId('wizard-metric-config-llm_judge_classic-0')
    const second = screen.getByTestId(
      'wizard-metric-config-llm_judge_classic-1',
    )
    expect(first).toHaveTextContent('free')
    expect(second).toHaveTextContent('paid')
    // Each panel's judge-model select carries that config's own model.
    expect(
      (within(first).getAllByRole('combobox').at(-1) as HTMLSelectElement)
        .value,
    ).toBe('gpt-5-mini')
    expect(
      (within(second).getAllByRole('combobox').at(-1) as HTMLSelectElement)
        .value,
    ).toBe('gpt-5.4-mini')
  })

  it('edits only the targeted config (judge model + name), never its sibling', () => {
    const { onEvaluationConfigsChange } = setup(JUDGE_PAIR)
    expandMetric('llm_judge_classic')
    const second = screen.getByTestId(
      'wizard-metric-config-llm_judge_classic-1',
    )

    const judgeSelect = within(second).getAllByRole('combobox').at(-1)!
    fireEvent.change(judgeSelect, { target: { value: 'gpt-5-mini' } })
    let updated = onEvaluationConfigsChange.mock.calls.at(-1)![0]
    expect(
      updated.find((c: any) => c.id === 'pair-paid').metric_parameters
        .judge_model,
    ).toBe('gpt-5-mini')
    expect(
      updated.find((c: any) => c.id === 'pair-free').metric_parameters
        .judge_model,
    ).toBe('gpt-5-mini')
    // ...the free config is UNCHANGED (it already was gpt-5-mini) — assert by
    // reference inequality on the paid one only:
    expect(updated.find((c: any) => c.id === 'pair-paid')).not.toBe(
      JUDGE_PAIR[1],
    )
    expect(updated.find((c: any) => c.id === 'pair-free')).toBe(JUDGE_PAIR[0])

    fireEvent.change(
      screen.getByTestId('wizard-metric-name-llm_judge_classic-1'),
      { target: { value: 'Abo-Korrektur' } },
    )
    updated = onEvaluationConfigsChange.mock.calls.at(-1)![0]
    expect(updated.find((c: any) => c.id === 'pair-paid').display_name).toBe(
      'Abo-Korrektur',
    )
    expect(updated.find((c: any) => c.id === 'pair-free').display_name).toBe(
      'Notenpunkte (Gratis-Modell)',
    )
  })

  it('unchecking the metric removes the whole pair', () => {
    const { onEvaluationConfigsChange } = setup(JUDGE_PAIR)
    const row = screen.getByTestId('wizard-metric-llm_judge_classic')
    fireEvent.click(within(row).getByRole('checkbox'))
    expect(onEvaluationConfigsChange).toHaveBeenCalledWith([])
  })
})

describe('StepEvaluationMethods — single-config behavior unchanged', () => {
  it('checking a metric adds exactly one config with defaults', () => {
    const { onEvaluationConfigsChange } = setup([])
    const row = screen.getByTestId('wizard-metric-rouge')
    fireEvent.click(within(row).getByRole('checkbox'))
    const configs = onEvaluationConfigsChange.mock.calls.at(-1)![0]
    expect(configs).toHaveLength(1)
    expect(configs[0].metric).toBe('rouge')
    expect(configs[0].prediction_fields).toEqual(['__all_model__'])
  })

  it('keeps the unsuffixed name testid and no sub-header for a lone config', () => {
    setup([
      {
        id: 'solo',
        metric: 'rouge',
        prediction_fields: ['__all_model__'],
        reference_fields: ['human:loesung'],
        enabled: true,
      },
    ])
    expandMetric('rouge')
    expect(screen.getByTestId('wizard-metric-name-rouge')).toBeInTheDocument()
    const panel = screen.getByTestId('wizard-metric-config-rouge-0')
    // No variant/sub-header line for single configs.
    expect(within(panel).queryByText('free')).not.toBeInTheDocument()
  })
})

describe('StepEvaluationMethods — Notenschlüssel slot', () => {
  const onWizardChange = jest.fn()
  const wizardData = { gradeScale: null, title: 'Klausur' }

  beforeEach(() => onWizardChange.mockClear())

  it('renders nothing extra in a community build (slot unregistered)', () => {
    setup([], { wizardData, onWizardChange })
    expect(screen.queryByTestId('grade-scale-section')).not.toBeInTheDocument()
  })

  it('mounts the section last, with the wizard state and updater', () => {
    mockGradeScaleSlotRegistered = true
    const { container } = setup([], { wizardData, onWizardChange })
    const section = screen.getByTestId('grade-scale-section')
    expect(section).toHaveAttribute('data-slice', 'null')
    // Last child of the step body — below the advanced-note alert.
    expect(container.firstChild!.lastChild).toBe(section)

    fireEvent.click(screen.getByTestId('grade-scale-write'))
    expect(onWizardChange).toHaveBeenCalledWith({
      gradeScale: { unit: 'percent' },
    })
  })

  it('hands the slot the current slice so both editors agree', () => {
    mockGradeScaleSlotRegistered = true
    const scale = { unit: 'percent', preset: 'uebungsklausur' }
    setup([], { wizardData: { gradeScale: scale }, onWizardChange })
    expect(screen.getByTestId('grade-scale-section')).toHaveAttribute(
      'data-slice',
      JSON.stringify(scale),
    )
  })

  it('stays unmounted when the host does not pass the wizard state', () => {
    mockGradeScaleSlotRegistered = true
    setup([])
    expect(screen.queryByTestId('grade-scale-section')).not.toBeInTheDocument()
  })
})

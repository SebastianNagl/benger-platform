/**
 * @jest-environment jsdom
 *
 * StepEvaluationMethods renders the metric catalogue in the UI language:
 * group names, group descriptions, metric names and metric descriptions come
 * from locale keys, and an overlay group or metric without a resolvable key
 * keeps its English literal.
 */
import '@testing-library/jest-dom'
import { render, screen, within } from '@testing-library/react'
import * as fs from 'fs'
import * as path from 'path'

import { registerMetric, registerMetricGroup } from '@/lib/api/evaluation-types'
import { StepEvaluationMethods } from '../StepEvaluationMethods'

const mockDe = JSON.parse(
  fs.readFileSync(
    path.resolve(__dirname, '../../../../locales/de/common.json'),
    'utf8',
  ),
)

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    // Real German lookup with the inline fallback, like the provider.
    t: (key: string, def?: any) => {
      const value = key
        .split('.')
        .reduce((node: any, part) => (node == null ? node : node[part]), mockDe)
      if (typeof value === 'string') return value
      return typeof def === 'string' ? def : key
    },
    locale: 'de',
  }),
}))

jest.mock('@/lib/extensions/slots', () => ({
  useSlot: () => null,
  getSlot: () => null,
  hasSlot: () => false,
  registerSlot: jest.fn(),
}))

jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({ models: [] }),
}))

// An overlay group without keys and a metric whose name key resolves but
// whose description key does not.
registerMetricGroup({
  name: 'Overlay Judges',
  description: 'Registered by an overlay',
  metrics: ['overlay_judge'],
})
registerMetric('overlay_judge', {
  name: 'overlay_judge',
  display_name: 'Overlay Judge',
  description: 'Overlay literal description',
  displayNameKey: 'evaluation.methodSelector.metricName.llmJudgeCustom',
  descriptionKey: 'evaluation.methodSelector.metricDesc.noSuchMetric',
  category: 'Overlay Judges',
  status: 'stable',
  supports_parameters: false,
})

function renderStep() {
  render(
    <StepEvaluationMethods
      evaluationConfigs={[]}
      onEvaluationConfigsChange={jest.fn()}
      immediateEvaluationEnabled={false}
      onImmediateEvaluationChange={jest.fn()}
      annotationFields={[{ name: 'loesung', type: 'TextArea' } as any]}
      dataColumns={['musterloesung']}
      selectedModelIds={[]}
    />,
  )
}

describe('StepEvaluationMethods: translated metric catalogue', () => {
  it('renders group names and descriptions in German', () => {
    renderStep()
    expect(screen.getByText('Lexikalische Metriken')).toBeInTheDocument()
    expect(
      screen.getByText('Zeichenketten- und Oberflächenabgleich'),
    ).toBeInTheDocument()
    expect(screen.getByText('LLM-als-Richter')).toBeInTheDocument()
    expect(screen.queryByText('Lexical Metrics')).not.toBeInTheDocument()
    expect(
      screen.queryByText('String and surface-level matching'),
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/judge_config/)).not.toBeInTheDocument()
  })

  it('renders metric names and descriptions in German', () => {
    renderStep()
    const row = screen.getByTestId('wizard-metric-exact_match')
    expect(within(row).getByText('Exakte Übereinstimmung')).toBeInTheDocument()
    expect(
      within(row).getByText('Exakter Zeichenkettenabgleich'),
    ).toBeInTheDocument()
    expect(within(row).queryByText('Exact Match')).not.toBeInTheDocument()
    expect(
      within(row).queryByText('Exact string matching'),
    ).not.toBeInTheDocument()
  })

  it('keeps the literal of an overlay entry without a resolvable key', () => {
    renderStep()
    expect(screen.getByText('Overlay Judges')).toBeInTheDocument()
    expect(screen.getByText('Registered by an overlay')).toBeInTheDocument()
    const row = screen.getByTestId('wizard-metric-overlay_judge')
    expect(
      within(row).getByText('Benutzerdefinierter LLM-Richter'),
    ).toBeInTheDocument()
    expect(
      within(row).getByText('Overlay literal description'),
    ).toBeInTheDocument()
  })
})

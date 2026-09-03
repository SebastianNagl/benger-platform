import React from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { REPORT_SNAPSHOT_FIXTURE as FIX } from '@/lib/reports/fixture'
import type { ReportChartsConfig } from '@/types/report'
import { t } from '../__mocks__/testUtils'
import { EvaluationSection } from '../EvaluationSection'

jest.mock('recharts', () => require('../__mocks__/testUtils').rechartsMock())

const registry = { llm_judge_falloesung: { display_name: 'Falllösung LLM Judge', display_scale: '0-100' as const } }

function renderSection(chartsConfig?: ReportChartsConfig | null, extra: Partial<React.ComponentProps<typeof EvaluationSection>> = {}) {
  return render(
    <EvaluationSection snapshot={FIX} chartsConfig={chartsConfig} registry={registry} locale="de" t={t} {...extra} />,
  )
}

const modelLabels = () =>
  within(screen.getByTestId('ranking-table-models'))
    .getAllByTestId('ranking-row')
    .map((r) => r.getAttribute('data-subject'))

describe('EvaluationSection', () => {
  it('renders methods, both tables, charts, interpretation and conclusions', () => {
    renderSection(undefined, { interpretation: 'Deutung', conclusions: 'Fazit' })
    expect(screen.getByTestId('methods-list')).toBeInTheDocument()
    expect(screen.getAllByTestId('config-chip')).toHaveLength(4)
    expect(screen.getByText('Deutung')).toBeInTheDocument()
    expect(screen.getByText('Fazit')).toBeInTheDocument()
    expect(modelLabels()).toEqual([
      'gpt-5.4',
      'claude-opus-4-7',
      'deepseek-ai/DeepSeek-V4-Flash',
      'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8',
    ])
    expect(screen.getByTestId('ranking-table-humans')).toBeInTheDocument()
    expect(screen.getByTestId('distribution-chart')).toBeInTheDocument()
    expect(screen.getByText('Verteilung der Notenpunkte: Menschen vs. Modelle')).toBeInTheDocument()
    expect(screen.getByTestId('per-subject-distribution')).toBeInTheDocument()
    expect(screen.getByTestId('mean-bar-chart')).toBeInTheDocument()
    // derived companions never become columns
    const headers = within(screen.getByTestId('ranking-table-models')).getAllByRole('columnheader').map((h) => h.textContent)
    expect(headers).not.toContain('Bestanden (Falllösung)')
    expect(headers).toContain('Notenpunkte')
  })

  it('switches configs via the selector', () => {
    renderSection()
    fireEvent.click(screen.getByRole('radio', { name: 'GPT-5 mini' }))
    expect(modelLabels()).toEqual(['gpt-5.4'])
    expect(within(screen.getByTestId('ranking-table-models')).getByTestId('ranking-row')).toHaveTextContent('79,1 / 100')
    // mini config has no distribution → chart disappears, humans table has no rows
    expect(screen.queryByTestId('distribution-chart')).not.toBeInTheDocument()
    expect(screen.queryByTestId('ranking-table-humans')).not.toBeInTheDocument()
  })

  it('applies hidden_subjects, show_humans and show_distribution', () => {
    renderSection({ hidden_subjects: ['gpt-5.4'], show_humans: false, show_distribution: false })
    expect(modelLabels()).not.toContain('gpt-5.4')
    expect(screen.getAllByTestId('rank-badge')[0]).toHaveTextContent('1')
    expect(screen.queryByTestId('ranking-table-humans')).not.toBeInTheDocument()
    expect(screen.queryByTestId('distribution-chart')).not.toBeInTheDocument()
    expect(screen.queryByTestId('per-subject-distribution')).not.toBeInTheDocument()
  })

  it('hides the selector when only one config is visible and respects visible_configs', () => {
    renderSection({ visible_configs: ['cfg-judge-mini'] })
    expect(screen.queryByTestId('config-selector')).not.toBeInTheDocument()
    expect(modelLabels()).toEqual(['gpt-5.4'])
    expect(screen.getAllByTestId('config-chip')).toHaveLength(1)
  })

  it('falls back to the primary metric distribution when there is no grade metric', () => {
    const snapshot = { ...FIX, grade_metric: null }
    render(<EvaluationSection snapshot={snapshot} registry={registry} locale="de" t={t} />)
    expect(screen.getByText('Verteilung (Falllösung LLM Judge): Menschen vs. Modelle')).toBeInTheDocument()
    expect(screen.getAllByTestId('bar-chart').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByTestId('distribution-chart')).toBeInTheDocument()
    const headers = within(screen.getByTestId('ranking-table-models')).getAllByRole('columnheader').map((h) => h.textContent)
    expect(headers).toContain('Notenpunkte (Falllösung)')
  })

  it('renders the empty state without a snapshot', () => {
    render(<EvaluationSection snapshot={null} registry={{}} locale="de" t={t} interpretation="Text" />)
    expect(screen.getByText('Für diesen Bericht liegt noch keine Auswertung vor.')).toBeInTheDocument()
    expect(screen.getByText('Text')).toBeInTheDocument()
    expect(screen.queryByTestId('ranking-table-models')).not.toBeInTheDocument()
  })

  it('renders a quiet note when no primary metric resolves', () => {
    render(<EvaluationSection snapshot={{ ...FIX, primary_metric: null }} registry={{}} locale="de" t={t} />)
    expect(screen.getByText('Für diese Metrik liegen keine Werte vor.')).toBeInTheDocument()
    expect(screen.queryByTestId('rank-badge')).not.toBeInTheDocument()
  })
})

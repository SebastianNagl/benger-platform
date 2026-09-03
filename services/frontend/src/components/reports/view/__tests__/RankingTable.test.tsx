import React from 'react'
import { render, screen, within } from '@testing-library/react'
import { REPORT_SNAPSHOT_FIXTURE as FIX } from '@/lib/reports/fixture'
import { rankSeries } from '@/lib/reports/select'
import { t } from '../__mocks__/testUtils'
import { RankingTable } from '../RankingTable'

const primary = { id: 'llm_judge_falloesung', label: 'Falllösung LLM Judge', scale: '0-100' as const }

describe('RankingTable', () => {
  it('renders ranked model rows with formatted columns', () => {
    const rows = rankSeries(FIX.series, 'cfg-judge-sonnet', 'llm_judge_falloesung', 'model')
    render(
      <RankingTable
        title="Leistung nach Modell"
        rows={rows}
        primary={primary}
        gradeMetric="llm_judge_falloesung_grade_points"
        subjectHeader="Modell"
        locale="de"
        t={t}
      />,
    )
    const trs = screen.getAllByTestId('ranking-row')
    expect(trs).toHaveLength(4)
    expect(within(trs[0]).getByTestId('rank-badge')).toHaveTextContent('1')
    expect(trs[0]).toHaveTextContent('GPT-5.4')
    expect(trs[0]).toHaveTextContent('openai')
    expect(trs[0]).toHaveTextContent('84,7 / 100')
    expect(trs[0]).toHaveTextContent('13,9 / 18 NP')
    expect(trs[0]).toHaveTextContent('100 %')
    expect(trs[3]).toHaveTextContent('Llama 4 Maverick')
    expect(within(trs[3]).getByTestId('rank-badge')).toHaveTextContent('4')
    expect(trs[3]).toHaveTextContent('58 %')

    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent)
    expect(headers).toEqual(['Rang', 'Modell', 'Falllösung LLM Judge', 'Notenpunkte', 'Bestanden', 'n'])
  })

  it('adds other metric columns and omits grade/pass columns when absent', () => {
    const rows = rankSeries(FIX.series, 'cfg-bleu', 'bleu', 'model')
    render(
      <RankingTable
        title="BLEU"
        rows={rows}
        primary={{ id: 'bleu', label: 'BLEU', scale: '0-1' }}
        otherColumns={[{ id: 'missing', label: 'Missing', scale: 'raw' }]}
        subjectHeader="Modell"
        locale="de"
        t={t}
        testId="bleu-table"
      />,
    )
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent)
    expect(headers).toEqual(['Rang', 'Modell', 'BLEU', 'n', 'Missing'])
    const row = screen.getByTestId('ranking-row')
    expect(row).toHaveTextContent('21 %')
    expect(row).toHaveTextContent('–')
    expect(screen.getByTestId('bleu-table')).toBeInTheDocument()
  })

  it('shows a quiet note instead of an empty table', () => {
    render(<RankingTable title="Leer" rows={[]} primary={primary} subjectHeader="Modell" locale="de" t={t} />)
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByText('Für diese Metrik liegen keine Werte vor.')).toBeInTheDocument()
  })

  it('styles podium ranks and skips the grade column when no row carries it', () => {
    const rows = rankSeries(FIX.series, 'cfg-judge-sonnet', 'llm_judge_falloesung', 'human')
    render(
      <RankingTable
        title="Menschen"
        rows={rows}
        primary={primary}
        gradeMetric="does_not_exist"
        subjectHeader="Teilnehmende"
        locale="en"
        t={t}
      />,
    )
    const badges = screen.getAllByTestId('rank-badge')
    expect(badges[0].className).toContain('bg-emerald-600')
    expect(badges[1].className).toContain('bg-emerald-100')
    expect(screen.queryByText('Notenpunkte')).not.toBeInTheDocument()
    expect(screen.getAllByTestId('ranking-row')[0]).toHaveTextContent('72.3 / 100')
  })
})

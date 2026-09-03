import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { REPORT_SNAPSHOT_FIXTURE as FIX } from '@/lib/reports/fixture'
import { distributionFor, rankSeries, topSubjectDistributions } from '@/lib/reports/select'
import { t } from '../__mocks__/testUtils'
import { DistributionChart, DistributionTooltip } from '../DistributionChart'
import { MeanBarChart, MeanBarTooltip, makeTickFormatter, toMeanBarData } from '../MeanBarChart'
import { PerSubjectDistribution, SubjectBinTooltip } from '../PerSubjectDistribution'

jest.mock('recharts', () => require('../__mocks__/testUtils').rechartsMock())

const gradeDist = distributionFor(FIX, 'cfg-judge-sonnet', 'llm_judge_falloesung_grade_points')!
const modelRows = rankSeries(FIX.series, 'cfg-judge-sonnet', 'llm_judge_falloesung', 'model')

describe('DistributionChart', () => {
  it('renders two series and toggles between share and count', () => {
    render(<DistributionChart distribution={gradeDist} valueLabel="Notenpunkte" title="Verteilung" locale="de" t={t} />)
    const chart = screen.getByTestId('distribution-chart')
    expect(chart).toHaveAttribute('data-mode', 'share')
    let bars = screen.getAllByTestId('bar')
    expect(bars.map((b) => b.getAttribute('data-key'))).toEqual(['modelPct', 'humanPct'])
    expect(bars[0]).toHaveAttribute('data-fill', 'var(--rv-model)')
    expect(bars[1]).toHaveAttribute('data-fill', 'var(--rv-human)')
    expect(screen.getByTestId('bar-chart')).toHaveAttribute('data-rows', '19')
    expect(screen.getByTestId('chart-legend')).toHaveTextContent('Modelle')
    expect(screen.getByTestId('chart-legend')).toHaveTextContent('Menschen')

    fireEvent.click(screen.getByRole('radio', { name: 'Anzahl' }))
    expect(chart).toHaveAttribute('data-mode', 'count')
    bars = screen.getAllByTestId('bar')
    expect(bars.map((b) => b.getAttribute('data-key'))).toEqual(['model', 'human'])
    expect(screen.queryByText(/Keine menschlichen Abgaben/)).not.toBeInTheDocument()
  })

  it('notes a missing human series and honours defaultMode', () => {
    const noHumans = { ...gradeDist, by_kind: { model: gradeDist.by_kind.model, human: gradeDist.by_kind.human.map(() => 0) } }
    render(<DistributionChart distribution={noHumans} valueLabel="NP" title="V" locale="de" t={t} defaultMode="count" />)
    expect(screen.getByTestId('distribution-chart')).toHaveAttribute('data-mode', 'count')
    expect(screen.getByText(/Keine menschlichen Abgaben/)).toBeInTheDocument()
  })

  it('tooltip shows bin label with counts or shares', () => {
    const bin = { bin: 13, label: '13', model: 12, human: 3, modelPct: 20, humanPct: 4.8 }
    const { rerender } = render(
      <DistributionTooltip active payload={[{ payload: bin }]} mode="share" locale="de" t={t} valueLabel="Notenpunkte" />,
    )
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('Notenpunkte 13')
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('20 % (12)')
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('4,8 % (3)')
    rerender(<DistributionTooltip active payload={[{ payload: bin }]} mode="count" locale="de" t={t} valueLabel="NP" />)
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('Modelle12')
    rerender(<DistributionTooltip active={false} payload={[{ payload: bin }]} mode="count" locale="de" t={t} valueLabel="NP" />)
    expect(screen.queryByTestId('chart-tooltip')).not.toBeInTheDocument()
    rerender(<DistributionTooltip active payload={[]} mode="count" locale="de" t={t} valueLabel="NP" />)
    expect(screen.queryByTestId('chart-tooltip')).not.toBeInTheDocument()
  })
})

describe('PerSubjectDistribution', () => {
  it('renders one mini histogram per subject', () => {
    const subjects = topSubjectDistributions(modelRows, gradeDist)
    render(<PerSubjectDistribution subjects={subjects} valueLabel="Notenpunkte" locale="de" t={t} />)
    expect(screen.getByTestId('per-subject-distribution')).toBeInTheDocument()
    expect(screen.getAllByTestId('subject-histogram')).toHaveLength(1)
    expect(screen.getByText('GPT-5.4')).toBeInTheDocument()
    expect(screen.getByText('n = 15')).toBeInTheDocument()
    expect(screen.getByTestId('bar')).toHaveAttribute('data-key', 'pct')
    expect(screen.getByText(/gleiche Achse/)).toBeInTheDocument()
  })

  it('renders nothing without subjects', () => {
    const { container } = render(<PerSubjectDistribution subjects={[]} valueLabel="NP" locale="de" t={t} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('tooltip shows share and count', () => {
    const bin = { bin: 13, label: '13', count: 5, pct: 33.3 }
    const { rerender } = render(<SubjectBinTooltip active payload={[{ payload: bin }]} locale="de" t={t} valueLabel="NP" />)
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('NP 13')
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('33,3 %')
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('Anzahl5')
    rerender(<SubjectBinTooltip active={false} locale="de" t={t} valueLabel="NP" />)
    expect(screen.queryByTestId('chart-tooltip')).not.toBeInTheDocument()
  })
})

describe('MeanBarChart', () => {
  it('renders a horizontal bar chart in ranking order with error bars', () => {
    render(<MeanBarChart rows={modelRows} scale="0-100" metricLabel="Falllösung LLM Judge" locale="de" t={t} />)
    expect(screen.getByTestId('mean-bar-chart')).toBeInTheDocument()
    expect(screen.getByText(/Falllösung LLM Judge je Modell/)).toBeInTheDocument()
    expect(screen.getByTestId('bar-chart')).toHaveAttribute('data-layout', 'vertical')
    expect(screen.getByTestId('bar-chart')).toHaveAttribute('data-rows', '4')
    expect(screen.getByTestId('error-bar')).toHaveAttribute('data-datakey', 'std')
    expect(screen.getByTestId('error-bar')).toHaveAttribute('data-direction', 'x')
  })

  it('formats axis ticks per scale', () => {
    expect(makeTickFormatter('0-1', 'de')(0.5)).toBe('50 %')
    expect(makeTickFormatter('0-100', 'de')(50)).toBe('50')
    expect(makeTickFormatter('raw', 'en')(0.256)).toBe('0.26')
  })

  it('maps rows to chart data and renders nothing when empty', () => {
    const data = toMeanBarData(modelRows)
    expect(data[0]).toMatchObject({ id: 'gpt-5.4', rank: 1, mean: 84.7, std: 6.1, n: 15, kind: 'model' })
    const humanRows = rankSeries(FIX.series, 'cfg-korrektur', 'korrektur_falloesung', 'human')
    expect(toMeanBarData(humanRows)[0].std).toBe(0)
    const { container } = render(<MeanBarChart rows={[]} scale="raw" metricLabel="x" locale="de" t={t} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('tooltip shows rank, mean, std and n', () => {
    const d = toMeanBarData(modelRows)[0]
    const { rerender } = render(
      <MeanBarTooltip active payload={[{ payload: d }]} scale="0-100" locale="de" t={t} metricLabel="Score" />,
    )
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('1. GPT-5.4')
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('Score84,7 / 100')
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('Standardabweichung6,1 / 100')
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('n15')
    rerender(<MeanBarTooltip active={false} scale="0-100" locale="de" t={t} metricLabel="Score" />)
    expect(screen.queryByTestId('chart-tooltip')).not.toBeInTheDocument()
  })
})

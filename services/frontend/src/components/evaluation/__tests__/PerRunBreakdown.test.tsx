/**
 * @jest-environment jsdom
 *
 * Tests for PerRunBreakdown — the per-judge_run table on the eval detail
 * page (multi-run feature, migration 042).
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { PerRunBreakdown, type PerRunRow } from '../PerRunBreakdown'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (_key: string, fallback?: any) =>
      typeof fallback === 'string' ? fallback : _key,
  }),
}))

const sampleRows: PerRunRow[] = [
  {
    target_model_id: 'gpt-5.4',
    judge_model_id: 'gpt-4o',
    run_index: 0,
    judge_run_id: 'jr-1',
    status: 'completed',
    samples_evaluated: 13,
    mean_score: null,
  },
  {
    target_model_id: 'gpt-5.4',
    judge_model_id: 'gpt-4o-mini',
    run_index: 0,
    judge_run_id: 'jr-2',
    status: 'completed',
    samples_evaluated: 13,
    mean_score: null,
  },
  {
    target_model_id: 'gpt-5.4',
    judge_model_id: 'gpt-4o-mini',
    run_index: 1,
    judge_run_id: 'jr-3',
    status: 'failed',
    samples_evaluated: 0,
    mean_score: null,
  },
]

describe('PerRunBreakdown', () => {
  it('renders one row per (judge_model, run_index)', () => {
    render(
      <PerRunBreakdown rows={sampleRows} metric="llm_judge_falloesung" showTargetModel={false} />,
    )
    // Three judge_run rows
    const dataRows = document.querySelectorAll('tbody tr')
    expect(dataRows.length).toBe(3)
  })

  it('shows judge model id and run_index in correct columns', () => {
    render(
      <PerRunBreakdown rows={sampleRows} metric="llm_judge_falloesung" showTargetModel={false} />,
    )
    expect(screen.getAllByText(/gpt-4o-mini/).length).toBe(2)
    expect(screen.getByText('gpt-4o')).toBeInTheDocument()
  })

  it('renders status badges with correct text', () => {
    render(
      <PerRunBreakdown rows={sampleRows} metric="llm_judge_falloesung" showTargetModel={false} />,
    )
    const completed = screen.getAllByText('completed')
    expect(completed.length).toBe(2)
    expect(screen.getByText('failed')).toBeInTheDocument()
  })

  it('shows sample counts when available', () => {
    render(
      <PerRunBreakdown rows={sampleRows} metric="llm_judge_falloesung" showTargetModel={false} />,
    )
    expect(screen.getAllByText('13').length).toBeGreaterThanOrEqual(2)
  })

  it('shows em-dash placeholder when mean_score is null', () => {
    render(
      <PerRunBreakdown rows={sampleRows} metric="llm_judge_falloesung" showTargetModel={false} />,
    )
    // mean_score is null on every row → 3 em-dashes for that column
    const cells = document.querySelectorAll('td')
    const dashCount = Array.from(cells).filter((c) => c.textContent?.trim() === '—').length
    expect(dashCount).toBeGreaterThanOrEqual(3)
  })

  it('shows empty-state hint when rows is empty', () => {
    render(
      <PerRunBreakdown rows={[]} metric="llm_judge_falloesung" showTargetModel={false} />,
    )
    expect(
      screen.getByText(/Keine Lauf-Daten/i),
    ).toBeInTheDocument()
  })

  it('renders deterministic ordering by judge_model then run_index', () => {
    const shuffled = [...sampleRows].reverse()
    render(
      <PerRunBreakdown rows={shuffled} metric="llm_judge_falloesung" showTargetModel={false} />,
    )
    const rows = document.querySelectorAll('tbody tr')
    // First row should be gpt-4o (alphabetically before gpt-4o-mini)
    expect(rows[0].textContent).toContain('gpt-4o')
    expect(rows[0].textContent).not.toContain('gpt-4o-mini')
  })

  it('shows target_model column when showTargetModel=true', () => {
    render(
      <PerRunBreakdown rows={sampleRows} metric="llm_judge_falloesung" showTargetModel={true} />,
    )
    const headers = Array.from(document.querySelectorAll('thead th')).map((th) =>
      th.textContent?.trim(),
    )
    // 6 columns: target, judge, run#, samples, mean, status
    expect(headers.length).toBe(6)
  })
})

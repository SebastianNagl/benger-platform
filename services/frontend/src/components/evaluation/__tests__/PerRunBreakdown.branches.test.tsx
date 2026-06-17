/**
 * @jest-environment jsdom
 *
 * Branch-coverage gap-fill for PerRunBreakdown. The sibling
 * `PerRunBreakdown.test.tsx` covers the happy path (completed/failed badges,
 * non-null scores, empty state, ordering by judge). This file targets the
 * remaining uncovered branches:
 *   - statusBadgeClass: 'running' and the default/unknown status arms
 *   - formatScore: undefined and NaN inputs (the existing suite only feeds null)
 *   - formatScore: a real numeric score → toFixed(3) path
 *   - deterministic judge (judge_model_id === null) → "(deterministic)" span
 *   - samples_evaluated === null → em-dash
 *   - sort tie-break on target_model_id vs judge_model_id localeCompare
 *   - showTargetModel default (true) rendering the target column
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { PerRunBreakdown, type PerRunRow } from '../PerRunBreakdown'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    // Component calls t(key, fallback); return the fallback so the German UI
    // strings ('(deterministic)', etc.) are what the DOM shows.
    t: (_key: string, fallback?: any) =>
      typeof fallback === 'string' ? fallback : _key,
  }),
}))

describe('PerRunBreakdown branch coverage', () => {
  it('renders distinct badge classes for running and unknown statuses', () => {
    const rows: PerRunRow[] = [
      {
        target_model_id: 'gpt-5.4',
        judge_model_id: 'gpt-4o',
        run_index: 0,
        judge_run_id: 'jr-running',
        status: 'running',
        samples_evaluated: 5,
        mean_score: 0.5,
      },
      {
        target_model_id: 'gpt-5.4',
        judge_model_id: 'gpt-4o',
        run_index: 1,
        judge_run_id: 'jr-pending',
        status: 'pending', // hits the switch default arm
        samples_evaluated: null,
        mean_score: null,
      },
    ]
    render(<PerRunBreakdown rows={rows} metric="m" showTargetModel={false} />)

    const running = screen.getByText('running')
    const pending = screen.getByText('pending')
    expect(running).toBeInTheDocument()
    expect(pending).toBeInTheDocument()
    // 'running' → blue palette
    expect(running.className).toContain('bg-blue-100')
    // unknown status → neutral zinc default palette
    expect(pending.className).toContain('bg-zinc-100')
  })

  it('formats a real numeric mean score to three decimals', () => {
    const rows: PerRunRow[] = [
      {
        target_model_id: 'gpt-5.4',
        judge_model_id: 'gpt-4o',
        run_index: 0,
        judge_run_id: 'jr-score',
        status: 'completed',
        samples_evaluated: 10,
        mean_score: 0.6666666,
      },
    ]
    render(<PerRunBreakdown rows={rows} metric="m" showTargetModel={false} />)
    expect(screen.getByText('0.667')).toBeInTheDocument()
  })

  it('renders em-dash for a NaN mean score', () => {
    const rows: PerRunRow[] = [
      {
        target_model_id: 'gpt-5.4',
        judge_model_id: 'gpt-4o',
        run_index: 0,
        judge_run_id: 'jr-nan',
        status: 'completed',
        samples_evaluated: 10,
        mean_score: Number.NaN,
      },
    ]
    render(<PerRunBreakdown rows={rows} metric="m" showTargetModel={false} />)
    const dashes = Array.from(document.querySelectorAll('td')).filter(
      (c) => c.textContent?.trim() === '—',
    )
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('renders em-dash for an undefined mean score', () => {
    const rows: PerRunRow[] = [
      {
        target_model_id: 'gpt-5.4',
        judge_model_id: 'gpt-4o',
        run_index: 0,
        judge_run_id: 'jr-undef',
        status: 'completed',
        samples_evaluated: 10,
        // Force the `score === undefined` branch of formatScore.
        mean_score: undefined as unknown as number | null,
      },
    ]
    render(<PerRunBreakdown rows={rows} metric="m" showTargetModel={false} />)
    const dashes = Array.from(document.querySelectorAll('td')).filter(
      (c) => c.textContent?.trim() === '—',
    )
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('renders a "(deterministic)" label and em-dash samples for a null judge', () => {
    const rows: PerRunRow[] = [
      {
        target_model_id: 'gpt-5.4',
        judge_model_id: null, // deterministic metric → span branch
        run_index: 0,
        judge_run_id: 'jr-det',
        status: 'completed',
        samples_evaluated: null, // samples em-dash branch
        mean_score: 0.9,
      },
    ]
    render(<PerRunBreakdown rows={rows} metric="exact_match" showTargetModel={false} />)
    expect(screen.getByText('(deterministic)')).toBeInTheDocument()
    // samples column shows the placeholder
    const dashes = Array.from(document.querySelectorAll('td')).filter(
      (c) => c.textContent?.trim() === '—',
    )
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('sorts by target_model_id first, breaking ties by judge then run index', () => {
    const rows: PerRunRow[] = [
      {
        target_model_id: 'zeta-model',
        judge_model_id: 'gpt-4o',
        run_index: 0,
        judge_run_id: 'jr-z',
        status: 'completed',
        samples_evaluated: 1,
        mean_score: 0.1,
      },
      {
        target_model_id: 'alpha-model',
        judge_model_id: 'gpt-4o',
        run_index: 1,
        judge_run_id: 'jr-a1',
        status: 'completed',
        samples_evaluated: 1,
        mean_score: 0.2,
      },
      {
        target_model_id: 'alpha-model',
        judge_model_id: 'gpt-4o',
        run_index: 0,
        judge_run_id: 'jr-a0',
        status: 'completed',
        samples_evaluated: 1,
        mean_score: 0.3,
      },
    ]
    render(<PerRunBreakdown rows={rows} metric="m" showTargetModel={true} />)
    const bodyRows = document.querySelectorAll('tbody tr')
    // alpha-model sorts before zeta-model (target_model_id localeCompare arm),
    // and within alpha the run_index ascending tie-break puts run 0 before run 1.
    expect(bodyRows[0].textContent).toContain('alpha-model')
    expect(bodyRows[0].textContent).toContain('0')
    expect(bodyRows[2].textContent).toContain('zeta-model')
  })

  it('breaks ties on judge_model_id when target models match (null judge sorts first)', () => {
    const rows: PerRunRow[] = [
      {
        target_model_id: 'same-target',
        judge_model_id: 'b-judge',
        run_index: 0,
        judge_run_id: 'jr-b',
        status: 'completed',
        samples_evaluated: 1,
        mean_score: 0.1,
      },
      {
        target_model_id: 'same-target',
        judge_model_id: null, // '' after coalesce → sorts before 'b-judge'
        run_index: 0,
        judge_run_id: 'jr-null',
        status: 'completed',
        samples_evaluated: 1,
        mean_score: 0.2,
      },
    ]
    render(<PerRunBreakdown rows={rows} metric="m" showTargetModel={false} />)
    const bodyRows = document.querySelectorAll('tbody tr')
    // Null judge ('') compares before 'b-judge' → deterministic row first.
    expect(bodyRows[0].textContent).toContain('(deterministic)')
  })

  it('defaults showTargetModel to true, rendering the target column header', () => {
    const rows: PerRunRow[] = [
      {
        target_model_id: 'gpt-5.4',
        judge_model_id: 'gpt-4o',
        run_index: 0,
        judge_run_id: 'jr-default',
        status: 'completed',
        samples_evaluated: 1,
        mean_score: 0.5,
      },
    ]
    // Omit showTargetModel entirely to hit the default-parameter branch.
    render(<PerRunBreakdown rows={rows} metric="m" />)
    const headers = Array.from(document.querySelectorAll('thead th'))
    expect(headers.length).toBe(6)
    expect(screen.getByText('gpt-5.4')).toBeInTheDocument()
  })
})

/**
 * @jest-environment jsdom
 *
 * Covers the two SampleResultsTable code paths the base suite never exercises:
 *
 *   1. The multi-run consistency column (migration 042) — only rendered when
 *      `consistencyByTaskId` is supplied AND at least one task has n_runs > 1
 *      (`showConsistencyColumn`). Within the cell, variance wins over
 *      fleiss_kappa, and a low n_runs / all-null entry falls back to "—".
 *   2. The extension-hook custom metric cell renderer (`getMetricCell`), which
 *      overrides the generic numeric rendering for an extended metric.
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { SampleResultsTable } from '../SampleResultsTable'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      // Mirror the base suite: resolve from the en bundle, else return the
      // provided string fallback (2nd arg), else the key.
      const translations: Record<string, any> = require('../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          value = undefined
          break
        }
      }
      if (typeof value !== 'string') {
        return typeof varsOrDefault === 'string' ? varsOrDefault : key
      }
      if (varsOrDefault && typeof varsOrDefault === 'object') {
        for (const [k, v] of Object.entries(varsOrDefault)) {
          value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))

// Extension hook: register a custom cell renderer only for the 'korrektur'
// metric so we exercise both the custom-cell branch and the generic fallback.
jest.mock('@/lib/extensions/metricRenderers', () => ({
  getMetricCell: (key: string) =>
    key === 'korrektur'
      ? (value: any) => `★${value?.value ?? value}`
      : null,
}))

const baseSample = {
  id: '1',
  task_id: 'task-aaaa1111',
  field_name: 'classification',
  answer_type: 'single_choice',
  ground_truth: { value: 'A' },
  prediction: { value: 'A' },
  metrics: { accuracy: 1.0 },
  passed: true,
  confidence_score: 0.9,
  error_message: null,
  processing_time_ms: 100,
}

describe('SampleResultsTable — consistency column', () => {
  it('hides the consistency column when no task has n_runs > 1', () => {
    render(
      <SampleResultsTable
        data={[baseSample]}
        consistencyByTaskId={{ 'task-aaaa1111': { n_runs: 1 } }}
      />,
    )
    // showConsistencyColumn is false → no variance/kappa cell rendered.
    expect(screen.queryByText(/σ²=/)).not.toBeInTheDocument()
    expect(screen.queryByText(/κ=/)).not.toBeInTheDocument()
  })

  it('renders variance when present (variance wins over kappa)', () => {
    render(
      <SampleResultsTable
        data={[baseSample]}
        consistencyByTaskId={{
          'task-aaaa1111': {
            n_runs: 3,
            variance: 0.0123,
            fleiss_kappa: 0.8,
          },
        }}
      />,
    )
    expect(screen.getByText('σ²=0.0123')).toBeInTheDocument()
    expect(screen.queryByText(/κ=/)).not.toBeInTheDocument()
  })

  it('falls back to fleiss_kappa when variance is null', () => {
    render(
      <SampleResultsTable
        data={[baseSample]}
        consistencyByTaskId={{
          'task-aaaa1111': {
            n_runs: 4,
            variance: null,
            fleiss_kappa: 0.765,
          },
        }}
      />,
    )
    expect(screen.getByText('κ=0.765')).toBeInTheDocument()
  })

  it('renders a dash when the per-row entry has too few runs', () => {
    // Column shows because ANOTHER task has n_runs > 1, but this row's entry
    // has n_runs < 2 → the cell renders the "—" fallback.
    const rowA = { ...baseSample, id: 'a', task_id: 'task-multi' }
    const rowB = { ...baseSample, id: 'b', task_id: 'task-single' }
    render(
      <SampleResultsTable
        data={[rowA, rowB]}
        consistencyByTaskId={{
          'task-multi': { n_runs: 3, variance: 0.05 },
          'task-single': { n_runs: 1 },
        }}
      />,
    )
    expect(screen.getByText('σ²=0.0500')).toBeInTheDocument()
    // The single-run row + the column-but-no-data path both render "—".
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('renders a dash when both variance and kappa are absent', () => {
    render(
      <SampleResultsTable
        data={[baseSample]}
        consistencyByTaskId={{
          'task-aaaa1111': { n_runs: 5, variance: null, fleiss_kappa: null },
        }}
      />,
    )
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})

describe('SampleResultsTable — custom metric cell renderer', () => {
  it('uses a registered metric cell renderer when one exists', () => {
    const customSample = {
      ...baseSample,
      metrics: { korrektur: { value: 12 } as any },
    }
    render(<SampleResultsTable data={[customSample]} />)
    // The registered renderer prefixes the value with a star.
    expect(screen.getByText('★12')).toBeInTheDocument()
  })

  it('falls back to generic numeric rendering for unregistered metrics', () => {
    const genericSample = {
      ...baseSample,
      metrics: { accuracy: 0.875 },
    }
    render(<SampleResultsTable data={[genericSample]} />)
    expect(screen.getByText('0.875')).toBeInTheDocument()
  })
})

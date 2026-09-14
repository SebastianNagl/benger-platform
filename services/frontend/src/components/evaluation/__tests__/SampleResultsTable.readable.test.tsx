/**
 * The per-sample table names rows the way a reader thinks about them: by the
 * evaluation config and the answer field, not the worker's composite key.
 * Companion values stay hidden and a stored Musterlösung reads as text.
 */
import { registerMetric } from '@/lib/api/evaluation-types'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SampleResultsTable } from '../SampleResultsTable'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: any) => {
      const tree: any = require('../../../locales/en/common.json')
      let value: any = key
        .split('.')
        .reduce((node: any, part) => (node == null ? node : node[part]), tree)
      if (typeof value !== 'string') return key
      if (vars && typeof vars === 'object') {
        for (const [k, v] of Object.entries(vars)) {
          value = value.split(`{${k}}`).join(String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))

registerMetric('w5_table_rubric', {
  name: 'w5_table_rubric',
  display_name: 'Bewertungsbogen (LLM Judge)',
  description: '',
  category: 'LLM-as-Judge',
  status: 'stable',
  supports_parameters: false,
  display_scale: '0-1',
})
registerMetric('w5_table_rubric_grade_points', {
  name: 'w5_table_rubric_grade_points',
  display_name: 'Notenpunkte (Bewertungsbogen)',
  description: '',
  category: 'LLM-as-Judge',
  status: 'stable',
  supports_parameters: false,
  display_scale: '0-18',
})

const rubricRow = {
  id: 'r1',
  task_id: 'task-rubric-00000001',
  field_name: 'structured-rubric-paid|human:loesung|task.musterloesung',
  answer_type: 'long_text',
  ground_truth:
    '<a id="_Toc1"></a>Musterlösung\n\nA. Zulässigkeit\n    I. Verwaltungsrechtsweg',
  prediction: 'Die Klage ist zulässig.',
  metrics: {
    raw_score: 70,
    w5_table_rubric_passed: true,
    w5_table_rubric_details: { steps: 46 },
    w5_table_rubric_raw: 'raw model output',
    w5_table_rubric: { value: 0.7, details: {}, error: null },
    w5_table_rubric_grade_points: 11,
  },
  passed: true,
  confidence_score: null,
  error_message: null,
  processing_time_ms: null,
}

const configs = [
  {
    id: 'structured-rubric-paid',
    display_name: 'Bewertungsbogen (gpt-5.4-mini)',
    metric: 'w5_table_rubric',
  },
]

describe('SampleResultsTable: readable rows', () => {
  it('names a row by its config and answer field', () => {
    render(<SampleResultsTable data={[rubricRow]} configs={configs} />)
    expect(
      screen.getByText('Bewertungsbogen (gpt-5.4-mini)'),
    ).toBeInTheDocument()
    expect(screen.getByText('loesung')).toBeInTheDocument()
    expect(
      screen.queryByText(/structured-rubric-paid\|/),
    ).not.toBeInTheDocument()
  })

  it('falls back to the metric name when the config is unknown', () => {
    render(<SampleResultsTable data={[rubricRow]} />)
    expect(
      screen.getByText('Bewertungsbogen (LLM Judge)', { selector: 'div' }),
    ).toBeInTheDocument()
  })

  it('filters by the name the reader sees', () => {
    render(<SampleResultsTable data={[rubricRow]} configs={configs} />)
    const input = screen.getByPlaceholderText('Filter by field name...')
    fireEvent.change(input, { target: { value: 'gpt-5.4' } })
    expect(screen.getAllByRole('row')).toHaveLength(2)
    fireEvent.change(input, { target: { value: 'nothing like it' } })
    expect(screen.getAllByRole('row')).toHaveLength(1)
  })

  it('shows result metrics by name and hides companion values', () => {
    render(<SampleResultsTable data={[rubricRow]} configs={configs} />)
    const row = screen.getAllByRole('row')[1]
    expect(
      within(row).getByText('Bewertungsbogen (LLM Judge):'),
    ).toBeInTheDocument()
    expect(
      within(row).getByText('Notenpunkte (Bewertungsbogen):'),
    ).toBeInTheDocument()
    expect(within(row).getByText('11.0')).toBeInTheDocument()
    expect(within(row).queryByText(/Raw Score|raw_score/)).toBeNull()
    expect(within(row).queryByText(/more/)).toBeNull()
  })

  it('hides companion values in the expanded grid too', async () => {
    const user = userEvent.setup()
    render(<SampleResultsTable data={[rubricRow]} configs={configs} />)
    await user.click(screen.getAllByRole('button')[0])
    const heading = await screen.findByText('All Metrics')
    const grid = heading.nextElementSibling as HTMLElement
    expect(
      within(grid).getByText('Notenpunkte (Bewertungsbogen)'),
    ).toBeInTheDocument()
    expect(
      within(grid).getByText('Bewertungsbogen (LLM Judge)'),
    ).toBeInTheDocument()
    // Only the two results: no raw score, pass flag, details or raw output.
    expect(grid.children).toHaveLength(2)
    expect(within(grid).queryByText(/Raw Score|Passed|Details|Raw$/)).toBeNull()
  })

  it('renders the reference and the answer as readable text', async () => {
    const user = userEvent.setup()
    render(<SampleResultsTable data={[rubricRow]} configs={configs} />)
    await user.click(screen.getAllByRole('button')[0])

    const reference = await screen.findByTestId('sample-ground-truth')
    const text = reference.querySelector('.whitespace-pre-wrap')
    expect(text).not.toBeNull()
    // Line breaks and indentation kept, no JSON quotes, no Word anchors.
    expect(text?.textContent).toBe(
      'Musterlösung\n\nA. Zulässigkeit\n    I. Verwaltungsrechtsweg',
    )
    expect(reference.querySelector('pre')).toBeNull()

    const prediction = screen.getByTestId('sample-prediction')
    expect(prediction).toHaveTextContent('Die Klage ist zulässig.')
    expect(prediction.textContent).not.toContain('"')
  })

  it('collapses a long reference and expands it on request', async () => {
    const user = userEvent.setup()
    const long = Array.from({ length: 40 }, (_, i) => `Absatz ${i + 1}`).join(
      '\n',
    )
    render(
      <SampleResultsTable
        data={[{ ...rubricRow, ground_truth: long }]}
        configs={configs}
      />,
    )
    await user.click(screen.getAllByRole('button')[0])

    const reference = await screen.findByTestId('sample-ground-truth')
    const text = reference.querySelector('.whitespace-pre-wrap')
    expect(text).toHaveClass('max-h-60')
    await user.click(within(reference).getByText('Show more'))
    expect(text).not.toHaveClass('max-h-60')
    expect(within(reference).getByText('Show less')).toBeInTheDocument()
  })

  it('says so when a sample has no reference', async () => {
    const user = userEvent.setup()
    render(
      <SampleResultsTable
        data={[{ ...rubricRow, ground_truth: '' }]}
        configs={configs}
      />,
    )
    await user.click(screen.getAllByRole('button')[0])
    const reference = await screen.findByTestId('sample-ground-truth')
    expect(reference).toHaveTextContent('No content')
  })
})

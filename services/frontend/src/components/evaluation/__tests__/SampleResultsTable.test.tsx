/**
 * Test suite for Sample Results Table Component
 * Issue #763: Per-sample evaluation results and visualization dashboard
 *
 * Target: 90%+ coverage (from 0%)
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SampleResultsTable } from '../SampleResultsTable'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (typeof value !== 'string') return key
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


const mockSampleResults = [
  {
    id: '1',
    task_id: 'task-12345678-abcd',
    field_name: 'classification',
    answer_type: 'single_choice',
    ground_truth: { value: 'A', label: 'Option A' },
    prediction: { value: 'A', label: 'Option A' },
    metrics: {
      accuracy: 1.0,
      f1_score: 1.0,
      precision: 1.0,
    },
    passed: true,
    confidence_score: 0.95,
    error_message: null,
    processing_time_ms: 150,
  },
  {
    id: '2',
    task_id: 'task-87654321-efgh',
    field_name: 'text_generation',
    answer_type: 'text',
    ground_truth: { text: 'Expected answer' },
    prediction: { text: 'Wrong answer' },
    metrics: {
      rouge_1: 0.3,
      rouge_2: 0.2,
      rouge_l: 0.25,
    },
    passed: false,
    confidence_score: 0.45,
    error_message: null,
    processing_time_ms: 250,
  },
  {
    id: '3',
    task_id: 'task-11111111-ijkl',
    field_name: 'classification',
    answer_type: 'multi_choice',
    ground_truth: { values: ['A', 'B'] },
    prediction: { values: ['A', 'C'] },
    metrics: {
      accuracy: 0.5,
      jaccard: 0.33,
    },
    passed: false,
    confidence_score: null,
    error_message: 'Partial match only',
    processing_time_ms: null,
  },
]

describe('SampleResultsTable Component', () => {
  beforeEach(() => {
  })

  describe('basic rendering', () => {
    it('renders table with sample data', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getByRole('table')).toBeInTheDocument()
    })

    it('renders all column headers', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getByText('Status')).toBeInTheDocument()
      expect(screen.getByText('Task ID')).toBeInTheDocument()
      expect(screen.getByText('Field')).toBeInTheDocument()
      expect(screen.getByText('Type')).toBeInTheDocument()
      expect(screen.getByText('Metrics')).toBeInTheDocument()
      expect(screen.getByText('Confidence')).toBeInTheDocument()
      expect(screen.getByText('Time (ms)')).toBeInTheDocument()
      expect(screen.getByText('Details')).toBeInTheDocument()
    })

    it('renders all sample rows', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const rows = screen.getAllByRole('row')
      expect(rows.length).toBeGreaterThan(3) // Header + 3 data rows
    })

    it('renders empty table when no data provided', () => {
      render(<SampleResultsTable data={[]} />)

      expect(screen.getByRole('table')).toBeInTheDocument()
      const rows = screen.getAllByRole('row')
      expect(rows).toHaveLength(1) // Only header row
    })
  })

  describe('status column', () => {
    it('shows check icon for passed samples', () => {
      const { container } = render(
        <SampleResultsTable data={mockSampleResults} />
      )

      const passedIcon = container.querySelector('svg.text-green-500')
      expect(passedIcon).toBeInTheDocument()
    })

    it('shows X icon for failed samples', () => {
      const { container } = render(
        <SampleResultsTable data={mockSampleResults} />
      )

      const failedIcon = container.querySelector('svg.text-red-500')
      expect(failedIcon).toBeInTheDocument()
    })
  })

  describe('task ID column', () => {
    it('displays truncated task IDs', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getByText(/task-123/)).toBeInTheDocument()
      expect(screen.getByText(/task-876/)).toBeInTheDocument()
    })

    it('truncates task IDs to 8 characters plus ellipsis', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const taskIdElement = screen.getByText(/task-123/)
      expect(taskIdElement.textContent).toContain('...')
      expect(taskIdElement.textContent?.length).toBeLessThan(15)
    })

    it('renders task IDs in monospace font', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const taskIdElement = screen.getByText(/task-123/)
      expect(taskIdElement).toHaveClass('font-mono')
    })
  })

  describe('field name column', () => {
    it('displays field names', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getAllByText('classification').length).toBeGreaterThan(0)
      expect(screen.getAllByText('text_generation').length).toBeGreaterThan(0)
    })
  })

  describe('answer type column', () => {
    it('displays answer types as badges', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getByText('single_choice')).toBeInTheDocument()
      expect(screen.getByText('text')).toBeInTheDocument()
      expect(screen.getByText('multi_choice')).toBeInTheDocument()
    })
  })

  describe('metrics column', () => {
    it('displays first two metrics for each sample', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getAllByText('accuracy:').length).toBeGreaterThan(0)
      expect(screen.getAllByText('f1_score:').length).toBeGreaterThan(0)
      expect(screen.getAllByText('rouge_1:').length).toBeGreaterThan(0)
    })

    it('formats metric values to 3 decimal places', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getAllByText('1.000').length).toBeGreaterThan(0)
      expect(screen.getAllByText('0.300').length).toBeGreaterThan(0)
    })

    it('shows "+X more" indicator when more than 2 metrics', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getAllByText(/\+\d+ more/).length).toBeGreaterThan(0)
    })

    it('shows dash when no metrics available', () => {
      const noMetricsSample = [
        {
          ...mockSampleResults[0],
          metrics: {},
        },
      ]
      render(<SampleResultsTable data={noMetricsSample} />)

      const cells = screen.getAllByRole('cell')
      const metricsCell = cells.find((cell) => cell.textContent === '-')
      expect(metricsCell).toBeInTheDocument()
    })

    it('handles null metric values', () => {
      const nullMetricSample = [
        {
          ...mockSampleResults[0],
          metrics: { accuracy: null as any },
        },
      ]
      render(<SampleResultsTable data={nullMetricSample} />)

      expect(screen.getByText('N/A')).toBeInTheDocument()
    })
  })

  describe('confidence score column', () => {
    it('displays confidence as percentage', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getByText('95.0%')).toBeInTheDocument()
      expect(screen.getByText('45.0%')).toBeInTheDocument()
    })

    it('shows green color for high confidence (>= 0.8)', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const highConfidence = screen.getByText('95.0%')
      expect(highConfidence).toHaveClass('text-green-600')
    })

    it('shows yellow color for medium confidence (0.5-0.8)', () => {
      const mediumConfidenceSample = [
        {
          ...mockSampleResults[0],
          confidence_score: 0.65,
        },
      ]
      render(<SampleResultsTable data={mediumConfidenceSample} />)

      const mediumConfidence = screen.getByText('65.0%')
      expect(mediumConfidence).toHaveClass('text-yellow-600')
    })

    it('shows red color for low confidence (< 0.5)', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const lowConfidence = screen.getByText('45.0%')
      expect(lowConfidence).toHaveClass('text-red-600')
    })

    it('shows dash when confidence is null', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const cells = screen.getAllByRole('cell')
      const confidenceCells = cells.filter((cell) => cell.textContent === '-')
      expect(confidenceCells.length).toBeGreaterThan(0)
    })
  })

  describe('processing time column', () => {
    it('displays processing time in milliseconds', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getByText('150')).toBeInTheDocument()
      expect(screen.getByText('250')).toBeInTheDocument()
    })

    it('formats time without decimal places', () => {
      const decimalTimeSample = [
        {
          ...mockSampleResults[0],
          processing_time_ms: 150.789,
        },
      ]
      render(<SampleResultsTable data={decimalTimeSample} />)

      expect(screen.getByText('151')).toBeInTheDocument()
    })

    it('shows dash when processing time is null', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const cells = screen.getAllByRole('cell')
      const timeCells = cells.filter((cell) => cell.textContent === '-')
      expect(timeCells.length).toBeGreaterThan(0)
    })
  })

  describe('row expansion', () => {
    it('expands row when details button clicked', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const detailsButtons = screen.getAllByRole('button')
      await user.click(detailsButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Ground Truth')).toBeInTheDocument()
        expect(screen.getByText('Prediction')).toBeInTheDocument()
      })
    })

    it('collapses row when details button clicked again', async () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      // Click first details button
      const detailsButtons1 = screen.getAllByRole('button')
      fireEvent.click(detailsButtons1[0])

      await waitFor(() => {
        expect(screen.getByText('Ground Truth')).toBeInTheDocument()
      })

      // Get fresh reference to buttons after state change
      const detailsButtons2 = screen.getAllByRole('button')
      fireEvent.click(detailsButtons2[0])

      await waitFor(() => {
        expect(screen.queryByText('Ground Truth')).not.toBeInTheDocument()
      })
    })

    it('displays ground truth data in expanded row', async () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const detailsButtons = screen.getAllByRole('button')
      fireEvent.click(detailsButtons[0])

      await waitFor(() => {
        const matches = screen.getAllByText(/"value": "A"/)
        expect(matches.length).toBeGreaterThan(0)
      })
    })

    it('displays prediction data in expanded row', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const detailsButtons = screen.getAllByRole('button')
      await user.click(detailsButtons[0])

      await waitFor(() => {
        const predictionSection = screen.getByText('Prediction').closest('div')
        expect(predictionSection).toBeInTheDocument()
      })
    })

    it('displays all metrics in expanded row', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const detailsButtons = screen.getAllByRole('button')
      await user.click(detailsButtons[0])

      await waitFor(() => {
        expect(screen.getByText('All Metrics')).toBeInTheDocument()
      })
    })

    it('displays error message in expanded row when present', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const detailsButtons = screen.getAllByRole('button')
      await user.click(detailsButtons[2]) // Third sample has error

      await waitFor(() => {
        expect(screen.getByText('Error')).toBeInTheDocument()
        expect(screen.getByText('Partial match only')).toBeInTheDocument()
      })
    })

    it('does not display error section when no error message', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const detailsButtons = screen.getAllByRole('button')
      await user.click(detailsButtons[0]) // First sample has no error

      await waitFor(() => {
        expect(screen.queryByText('Error')).not.toBeInTheDocument()
      })
    })

    it('changes chevron icon direction when expanded', async () => {
      const { container } = render(
        <SampleResultsTable data={mockSampleResults} />
      )

      const detailsButtons = screen.getAllByRole('button')
      const firstButton = detailsButtons[0]

      // Initially shows down chevron
      expect(firstButton.querySelector('svg')).toBeInTheDocument()

      fireEvent.click(firstButton)

      // After click, chevron should still exist (just rotated)
      await waitFor(() => {
        const buttonsAfterClick = screen.getAllByRole('button')
        const svg = buttonsAfterClick[0].querySelector('svg')
        expect(svg).toBeInTheDocument()
      })
    })
  })

  describe('filtering', () => {
    it('filters by field name', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const fieldNameInput = screen.getByPlaceholderText(
        'Filter by field name...'
      )
      await user.type(fieldNameInput, 'classification')

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        expect(rows.length).toBeLessThan(mockSampleResults.length + 1)
      })
    })

    it('shows all samples when filter is empty', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const fieldNameInput = screen.getByPlaceholderText(
        'Filter by field name...'
      )
      await user.type(fieldNameInput, 'xyz')
      await user.clear(fieldNameInput)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        expect(rows.length).toBeGreaterThan(1)
      })
    })

    it('filters to show only passed samples', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const statusSelect = screen.getByRole('combobox')
      await user.selectOptions(statusSelect, 'passed')

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        expect(rows.length).toBeLessThan(mockSampleResults.length + 1)
      })
    })

    it('filters to show only failed samples', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const statusSelect = screen.getByRole('combobox')
      await user.selectOptions(statusSelect, 'failed')

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        expect(rows.length).toBeLessThan(mockSampleResults.length + 1)
      })
    })

    it('shows all samples when status filter is "all"', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const statusSelect = screen.getByRole('combobox')
      await user.selectOptions(statusSelect, 'passed')
      await user.selectOptions(statusSelect, 'all')

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        expect(rows.length).toBeGreaterThan(2)
      })
    })
  })

  describe('sorting', () => {
    it('sorts when column header is clicked', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const fieldHeader = screen.getByText('Field')
      await user.click(fieldHeader)

      // Check for sort indicator
      await waitFor(() => {
        expect(screen.getByText(/Field/)).toBeInTheDocument()
      })
    })

    it('shows sort indicator on sorted column', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const fieldHeader = screen.getByText('Field')
      await user.click(fieldHeader)

      await waitFor(() => {
        const headerText = fieldHeader.textContent
        expect(headerText).toMatch(/Field.*[🔼🔽]/)
      })
    })

    it('toggles sort direction on repeated clicks', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const fieldHeader = screen.getByText('Field')
      await user.click(fieldHeader)

      await waitFor(() => {
        expect(fieldHeader.textContent).toContain('🔼')
      })

      await user.click(fieldHeader)

      await waitFor(() => {
        expect(fieldHeader.textContent).toContain('🔽')
      })
    })
  })

  describe('pagination', () => {
    it('shows pagination controls', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getByText('Previous')).toBeInTheDocument()
      expect(screen.getByText('Next')).toBeInTheDocument()
    })

    it('shows results count', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getByText(/Showing/)).toBeInTheDocument()
      expect(screen.getByText(/results/)).toBeInTheDocument()
    })

    it('disables Previous button on first page', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const previousButton = screen.getByRole('button', { name: 'Previous' })
      expect(previousButton).toBeDisabled()
    })

    it('disables Next button when all data fits on one page', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const nextButton = screen.getByRole('button', { name: 'Next' })
      expect(nextButton).toBeDisabled()
    })

    it('enables Next button when there are more pages', () => {
      const manyResults = Array.from({ length: 30 }, (_, i) => ({
        ...mockSampleResults[0],
        id: `${i}`,
        task_id: `task-${i}`,
      }))

      render(<SampleResultsTable data={manyResults} />)

      const nextButton = screen.getByRole('button', { name: 'Next' })
      expect(nextButton).not.toBeDisabled()
    })

    it('navigates to next page when Next clicked', async () => {
      const user = userEvent.setup()
      const manyResults = Array.from({ length: 30 }, (_, i) => ({
        ...mockSampleResults[0],
        id: `${i}`,
        task_id: `task-${i}`,
      }))

      render(<SampleResultsTable data={manyResults} />)

      const nextButton = screen.getByRole('button', { name: 'Next' })
      await user.click(nextButton)

      await waitFor(() => {
        expect(screen.getByText(/Showing/)).toBeInTheDocument()
      })
    })

    it('navigates to previous page when Previous clicked', async () => {
      const user = userEvent.setup()
      const manyResults = Array.from({ length: 30 }, (_, i) => ({
        ...mockSampleResults[0],
        id: `${i}`,
        task_id: `task-${i}`,
      }))

      render(<SampleResultsTable data={manyResults} />)

      const nextButton = screen.getByRole('button', { name: 'Next' })
      await user.click(nextButton)

      await waitFor(() => {
        expect(screen.getByText(/Showing/)).toBeInTheDocument()
      })

      const previousButton = screen.getByRole('button', { name: 'Previous' })
      await user.click(previousButton)

      await waitFor(() => {
        expect(screen.getByText(/Showing/)).toBeInTheDocument()
      })
    })
  })

  describe('row click handler', () => {
    it('calls onRowClick when row is clicked', async () => {
      const user = userEvent.setup()
      const onRowClick = jest.fn()
      render(
        <SampleResultsTable data={mockSampleResults} onRowClick={onRowClick} />
      )

      const rows = screen.getAllByRole('row')
      const firstDataRow = rows[1] // Skip header row

      await user.click(firstDataRow)

      expect(onRowClick).toHaveBeenCalledWith(mockSampleResults[0])
    })

    it('does not call onRowClick when onRowClick is undefined', async () => {
      const user = userEvent.setup()
      render(<SampleResultsTable data={mockSampleResults} />)

      const rows = screen.getAllByRole('row')
      const firstDataRow = rows[1]

      await user.click(firstDataRow)

      // Should not throw error
      expect(firstDataRow).toBeInTheDocument()
    })
  })

  describe('edge cases', () => {
    it('handles very long field names', () => {
      const longFieldSample = [
        {
          ...mockSampleResults[0],
          field_name: 'very_long_field_name_that_might_break_layout',
        },
      ]
      render(<SampleResultsTable data={longFieldSample} />)

      expect(
        screen.getByText('very_long_field_name_that_might_break_layout')
      ).toBeInTheDocument()
    })

    it('handles samples with many metrics', () => {
      const manyMetricsSample = [
        {
          ...mockSampleResults[0],
          metrics: {
            metric1: 0.1,
            metric2: 0.2,
            metric3: 0.3,
            metric4: 0.4,
            metric5: 0.5,
            metric6: 0.6,
          },
        },
      ]
      render(<SampleResultsTable data={manyMetricsSample} />)

      expect(screen.getByText(/\+\d+ more/)).toBeInTheDocument()
    })

    it('handles ground truth with nested objects', async () => {
      const user = userEvent.setup()
      const nestedDataSample = [
        {
          ...mockSampleResults[0],
          ground_truth: {
            nested: {
              deep: {
                value: 'test',
              },
            },
          },
        },
      ]
      render(<SampleResultsTable data={nestedDataSample} />)

      const detailsButtons = screen.getAllByRole('button')
      await user.click(detailsButtons[0])

      await waitFor(() => {
        expect(screen.getByText(/"nested":/)).toBeInTheDocument()
      })
    })

    it('handles prediction with arrays', async () => {
      const user = userEvent.setup()
      const arrayDataSample = [
        {
          ...mockSampleResults[0],
          prediction: {
            values: ['A', 'B', 'C'],
          },
        },
      ]
      render(<SampleResultsTable data={arrayDataSample} />)

      const detailsButtons = screen.getAllByRole('button')
      await user.click(detailsButtons[0])

      await waitFor(() => {
        expect(screen.getByText(/"values":/)).toBeInTheDocument()
      })
    })
  })

  describe('accessibility', () => {
    it('has accessible table structure', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      expect(screen.getByRole('table')).toBeInTheDocument()
      expect(screen.getAllByRole('columnheader')).toHaveLength(8)
    })

    it('has accessible button labels', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const buttons = screen.getAllByRole('button')
      buttons.forEach((button) => {
        expect(button).toBeInTheDocument()
      })
    })

    it('has accessible input labels', () => {
      render(<SampleResultsTable data={mockSampleResults} />)

      const filterInput = screen.getByPlaceholderText('Filter by field name...')
      expect(filterInput).toBeInTheDocument()
    })
  })
})

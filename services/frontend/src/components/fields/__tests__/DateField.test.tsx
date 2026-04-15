/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DateField } from '../DateField'

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  ExclamationCircleIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="exclamation-icon">
      <path />
    </svg>
  ),
}))

// Mock I18n context
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

describe('DateField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'date_field',
    type: 'date',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Date',
    description: 'Select a date',
    required: false,
  }

  const defaultProps = {
    field: defaultField,
    value: '',
    onChange: mockOnChange,
    context: 'annotation' as DisplayContext,
    readonly: false,
    errors: [],
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders date input with correct type', () => {
      render(<DateField {...defaultProps} />)

      const input = screen.getByDisplayValue('')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('type', 'date')
      expect(input).toHaveAttribute('id', 'date_field')
      expect(input).toHaveAttribute('name', 'date_field')
    })

    it('renders field label', () => {
      render(<DateField {...defaultProps} />)

      expect(screen.getByText('Date (Optional)')).toBeInTheDocument()
    })

    it('renders field description', () => {
      render(<DateField {...defaultProps} />)

      expect(screen.getByText('Select a date')).toBeInTheDocument()
    })
  })

  describe('Value Handling', () => {
    it('formats date value correctly (YYYY-MM-DD)', () => {
      const dateValue = '2025-01-15'
      render(<DateField {...defaultProps} value={dateValue} />)

      const input = screen.getByDisplayValue('2025-01-15')
      expect(input).toBeInTheDocument()
      expect(input).toHaveValue('2025-01-15')
    })

    it('handles ISO datetime string and extracts date', () => {
      const isoDate = '2025-01-15T10:30:00.000Z'
      render(<DateField {...defaultProps} value={isoDate} />)

      const input = screen.getByDisplayValue('2025-01-15')
      expect(input).toHaveValue('2025-01-15')
    })

    it('handles Date object', () => {
      const dateObj = new Date('2025-01-15')
      render(<DateField {...defaultProps} value={dateObj.toISOString()} />)

      const input = screen.getByDisplayValue('2025-01-15')
      expect(input).toHaveValue('2025-01-15')
    })

    it('handles null/undefined values gracefully', () => {
      const { rerender } = render(<DateField {...defaultProps} value={null} />)
      expect(screen.getByDisplayValue('')).toHaveValue('')

      rerender(<DateField {...defaultProps} value={undefined} />)
      expect(screen.getByDisplayValue('')).toHaveValue('')
    })

    it('calls onChange when date is selected', async () => {
      const user = userEvent.setup()
      render(<DateField {...defaultProps} />)

      const input = screen.getByDisplayValue('')
      await user.type(input, '2025-01-15')

      expect(mockOnChange).toHaveBeenCalled()
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<DateField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      render(<DateField {...defaultProps} />)

      expect(screen.getByText('Date (Optional)')).toBeInTheDocument()
    })
  })

  describe('Readonly State', () => {
    it('disables input when readonly is true', () => {
      render(<DateField {...defaultProps} readonly={true} />)

      const input = screen.getByDisplayValue('')
      expect(input).toBeDisabled()
    })

    it('does not call onChange when readonly', async () => {
      const user = userEvent.setup()
      render(<DateField {...defaultProps} readonly={true} />)

      const input = screen.getByDisplayValue('')
      await user.type(input, '2025-01-15')

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('applies readonly styles', () => {
      render(<DateField {...defaultProps} readonly={true} />)

      const input = screen.getByDisplayValue('')
      expect(input).toHaveClass('bg-gray-50', 'dark:bg-gray-800')
    })
  })

  describe('Error Handling', () => {
    it('displays error message', () => {
      const errors = ['Invalid date']
      render(<DateField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Invalid date')).toBeInTheDocument()
    })

    it('applies error styles to input', () => {
      const errors = ['Error']
      render(<DateField {...defaultProps} errors={errors} />)

      const input = screen.getByDisplayValue('')
      expect(input).toHaveClass('border-red-300', 'dark:border-red-600')
    })

    it('displays multiple errors', () => {
      const errors = ['Required field', 'Invalid format']
      render(<DateField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Required field')).toBeInTheDocument()
      expect(screen.getByText('Invalid format')).toBeInTheDocument()
    })
  })

  describe('Date Formatting', () => {
    it('formats past dates correctly', () => {
      render(<DateField {...defaultProps} value="2020-12-25" />)

      const input = screen.getByDisplayValue('2020-12-25')
      expect(input).toHaveValue('2020-12-25')
    })

    it('formats future dates correctly', () => {
      render(<DateField {...defaultProps} value="2030-06-15" />)

      const input = screen.getByDisplayValue('2030-06-15')
      expect(input).toHaveValue('2030-06-15')
    })

    it('handles dates with different month/day formats', () => {
      render(<DateField {...defaultProps} value="2025-03-05" />)

      const input = screen.getByDisplayValue('2025-03-05')
      expect(input).toHaveValue('2025-03-05')
    })
  })

  describe('Styling', () => {
    it('applies default input classes', () => {
      render(<DateField {...defaultProps} />)

      const input = screen.getByDisplayValue('')
      expect(input).toHaveClass('block', 'w-full', 'rounded-md')
    })

    it('applies custom className to wrapper', () => {
      render(<DateField {...defaultProps} className="custom-class" />)

      const wrapper = screen.getByDisplayValue('').closest('.field-wrapper')
      expect(wrapper).toHaveClass('custom-class')
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA attributes', () => {
      render(<DateField {...defaultProps} />)

      const input = screen.getByDisplayValue('')
      expect(input).toHaveAttribute('id', 'date_field')
    })

    it('is keyboard navigable', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <button>Before</button>
          <DateField {...defaultProps} />
          <button>After</button>
        </div>
      )

      const beforeButton = screen.getByRole('button', { name: 'Before' })
      const input = screen.getByDisplayValue('')
      const afterButton = screen.getByRole('button', { name: 'After' })

      beforeButton.focus()
      await user.tab()
      expect(input).toHaveFocus()

      await user.tab()
      expect(afterButton).toHaveFocus()
    })
  })

  describe('Edge Cases', () => {
    it('handles invalid date strings gracefully', () => {
      const { container } = render(
        <DateField {...defaultProps} value="invalid-date" />
      )

      const input = container.querySelector('input[type="date"]')
      expect(input).toBeInTheDocument()
    })

    it('handles empty string value', () => {
      render(<DateField {...defaultProps} value="" />)

      const input = screen.getByDisplayValue('')
      expect(input).toHaveValue('')
    })

    it('handles leap year dates', () => {
      render(<DateField {...defaultProps} value="2024-02-29" />)

      const input = screen.getByDisplayValue('2024-02-29')
      expect(input).toHaveValue('2024-02-29')
    })
  })
})

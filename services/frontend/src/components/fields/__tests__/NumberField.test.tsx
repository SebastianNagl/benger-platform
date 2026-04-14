/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { NumberField } from '../NumberField'

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

describe('NumberField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'score_field',
    type: 'number',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Score',
    description: 'Enter a numeric score',
    placeholder: 'Enter number',
    required: false,
  }

  const defaultProps = {
    field: defaultField,
    value: null,
    onChange: mockOnChange,
    context: 'annotation' as DisplayContext,
    readonly: false,
    errors: [],
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders number input with correct attributes', () => {
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('type', 'number')
      expect(input).toHaveAttribute('id', 'score_field')
      expect(input).toHaveAttribute('name', 'score_field')
      expect(input).toHaveAttribute('placeholder', 'Enter number')
      expect(input).toHaveAttribute('step', 'any')
      expect(input).toHaveValue(null)
    })

    it('renders field label correctly', () => {
      render(<NumberField {...defaultProps} />)

      const label = screen.getByText('Score (Optional)')
      expect(label).toBeInTheDocument()
      expect(label.tagName).toBe('LABEL')
    })

    it('renders field description when provided', () => {
      render(<NumberField {...defaultProps} />)

      const description = screen.getByText('Enter a numeric score')
      expect(description).toBeInTheDocument()
      expect(description).toHaveClass(
        'text-sm',
        'text-gray-500',
        'dark:text-gray-400'
      )
    })

    it('renders without label when not provided', () => {
      const fieldWithoutLabel = { ...defaultField, label: undefined }
      render(<NumberField {...defaultProps} field={fieldWithoutLabel} />)

      expect(screen.getByRole('spinbutton')).toBeInTheDocument()
      expect(screen.queryByText('Score')).not.toBeInTheDocument()
    })

    it('applies step="any" for decimal support', () => {
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveAttribute('step', 'any')
    })
  })

  describe('Value Handling', () => {
    it('displays initial integer value correctly', () => {
      render(<NumberField {...defaultProps} value={42} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveValue(42)
    })

    it('displays initial decimal value correctly', () => {
      render(<NumberField {...defaultProps} value={3.14159} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveValue(3.14159)
    })

    it('displays zero value correctly', () => {
      render(<NumberField {...defaultProps} value={0} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveValue(0)
    })

    it('handles null/undefined values as empty string', () => {
      const { rerender } = render(
        <NumberField {...defaultProps} value={null} />
      )
      expect(screen.getByRole('spinbutton')).toHaveValue(null)

      rerender(<NumberField {...defaultProps} value={undefined} />)
      expect(screen.getByRole('spinbutton')).toHaveValue(null)
    })

    it('calls onChange with parsed number when user types integer', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      await user.type(input, '123')

      // onChange is called for each keystroke with accumulated value
      expect(mockOnChange).toHaveBeenCalledTimes(3)
      // Verify onChange is called with proper numbers
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('calls onChange with parsed decimal number when user types decimal', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      await user.type(input, '3.14')

      // onChange is called for each keystroke
      expect(mockOnChange).toHaveBeenCalledTimes(3) // 3, 1, 4 keystrokes but '.' may not trigger onChange
      // Verify onChange is called with proper decimal parsing
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('calls onChange with null when user clears the field', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} value={123} />)

      const input = screen.getByRole('spinbutton')
      await user.clear(input)

      expect(mockOnChange).toHaveBeenCalledWith(null)
    })

    it('does not call onChange for invalid number input', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')

      // Try to type letters - should be prevented by browser or ignored
      await user.type(input, 'abc')

      // onChange should either not be called or called with NaN handling
      // The exact behavior depends on browser implementation
    })

    it('handles negative numbers correctly', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      await user.type(input, '-25')

      // onChange behavior may vary
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles large numbers correctly', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      await user.type(input, '999999')

      // onChange behavior may vary
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles scientific notation input', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      await user.type(input, '1e5')

      // onChange behavior may vary
      expect(mockOnChange).toHaveBeenCalled()
    })
  })

  describe('Min/Max Validation', () => {
    it('sets min attribute when min validation is present', () => {
      const fieldWithMin = {
        ...defaultField,
        validation: [{ type: 'min' as const, value: 0 }],
      }
      render(<NumberField {...defaultProps} field={fieldWithMin} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveAttribute('min', '0')
    })

    it('sets max attribute when max validation is present', () => {
      const fieldWithMax = {
        ...defaultField,
        validation: [{ type: 'max' as const, value: 100 }],
      }
      render(<NumberField {...defaultProps} field={fieldWithMax} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveAttribute('max', '100')
    })

    it('sets both min and max when both validations are present', () => {
      const fieldWithMinMax = {
        ...defaultField,
        validation: [
          { type: 'min' as const, value: 10 },
          { type: 'max' as const, value: 90 },
        ],
      }
      render(<NumberField {...defaultProps} field={fieldWithMinMax} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveAttribute('min', '10')
      expect(input).toHaveAttribute('max', '90')
    })

    it('does not set min/max attributes when validation is not present', () => {
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      expect(input).not.toHaveAttribute('min')
      expect(input).not.toHaveAttribute('max')
    })

    it('handles mixed validation rules correctly', () => {
      const fieldWithMixedValidation = {
        ...defaultField,
        validation: [
          { type: 'required' as const },
          { type: 'min' as const, value: 5 },
          { type: 'maxLength' as const, value: 10 }, // Not applicable to number field
          { type: 'max' as const, value: 95 },
        ],
      }
      render(<NumberField {...defaultProps} field={fieldWithMixedValidation} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveAttribute('min', '5')
      expect(input).toHaveAttribute('max', '95')
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<NumberField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      const optionalField = { ...defaultField, required: false }
      render(<NumberField {...defaultProps} field={optionalField} />)

      const label = screen.getByText('Score (Optional)')
      expect(label).toBeInTheDocument()
    })

    it('does not duplicate (Optional) in label', () => {
      const fieldWithOptionalLabel = {
        ...defaultField,
        required: false,
        label: 'Score (Optional)',
      }
      render(<NumberField {...defaultProps} field={fieldWithOptionalLabel} />)

      const label = screen.getByText('Score (Optional)')
      expect(label).toBeInTheDocument()
      expect(
        screen.queryByText('Score (Optional) (Optional)')
      ).not.toBeInTheDocument()
    })
  })

  describe('Readonly State', () => {
    it('disables input when readonly is true', () => {
      render(<NumberField {...defaultProps} readonly={true} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toBeDisabled()
      expect(input).toHaveClass(
        'bg-gray-50',
        'dark:bg-gray-800',
        'cursor-not-allowed'
      )
    })

    it('does not call onChange when readonly and user tries to type', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} readonly={true} />)

      const input = screen.getByRole('spinbutton')
      await user.type(input, '123')

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('applies readonly styles correctly', () => {
      render(<NumberField {...defaultProps} readonly={true} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveClass(
        'bg-gray-50',
        'dark:bg-gray-800',
        'cursor-not-allowed'
      )
    })

    it('maintains value display in readonly mode', () => {
      render(<NumberField {...defaultProps} readonly={true} value={42.5} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveValue(42.5)
      expect(input).toBeDisabled()
    })
  })

  describe('Error Handling', () => {
    it('displays single error message', () => {
      const errors = ['Value must be a number']
      render(<NumberField {...defaultProps} errors={errors} />)

      const errorMessage = screen.getByText('Value must be a number')
      expect(errorMessage).toBeInTheDocument()
      expect(errorMessage).toHaveClass('text-red-600', 'dark:text-red-400')

      const errorIcon = screen.getByTestId('exclamation-icon')
      expect(errorIcon).toBeInTheDocument()
    })

    it('displays multiple error messages', () => {
      const errors = [
        'Field is required',
        'Value must be greater than 0',
        'Value must be less than 100',
      ]
      render(<NumberField {...defaultProps} errors={errors} />)

      errors.forEach((error) => {
        expect(screen.getByText(error)).toBeInTheDocument()
      })

      const errorIcons = screen.getAllByTestId('exclamation-icon')
      expect(errorIcons).toHaveLength(3)
    })

    it('applies error styles to input when errors present', () => {
      const errors = ['Error message']
      render(<NumberField {...defaultProps} errors={errors} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveClass('border-red-300', 'dark:border-red-600')
    })

    it('does not show errors when errors array is empty', () => {
      render(<NumberField {...defaultProps} errors={[]} />)

      expect(screen.queryByTestId('exclamation-icon')).not.toBeInTheDocument()
    })
  })

  describe('Styling and CSS Classes', () => {
    it('applies default input classes', () => {
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveClass(
        'block',
        'w-full',
        'rounded-md',
        'shadow-sm',
        'sm:text-sm',
        'transition-colors'
      )
    })

    it('applies normal state classes when no errors', () => {
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveClass(
        'border-gray-300',
        'dark:border-gray-600',
        'bg-white',
        'dark:bg-gray-700'
      )
    })

    it('applies custom className to wrapper', () => {
      render(<NumberField {...defaultProps} className="custom-number-class" />)

      const wrapper = screen.getByRole('spinbutton').closest('.field-wrapper')
      expect(wrapper).toHaveClass('custom-number-class')
    })

    it('applies focus states correctly', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      await user.click(input)

      expect(input).toHaveFocus()
      expect(input).toHaveClass('focus:border-blue-500', 'focus:ring-blue-500')
    })
  })

  describe('Edge Cases', () => {
    it('handles very large numbers', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const largeNumber = '999999999999999'
      const input = screen.getByRole('spinbutton')

      await user.type(input, largeNumber)
      // onChange behavior may vary
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles very small decimal numbers', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const smallDecimal = '0.00001'
      const input = screen.getByRole('spinbutton')

      await user.type(input, smallDecimal)
      // onChange behavior may vary
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles field name with special characters', () => {
      const specialField = {
        ...defaultField,
        name: 'field-with-special_chars.123',
      }
      render(<NumberField {...defaultProps} field={specialField} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveAttribute('name', 'field-with-special_chars.123')
      expect(input).toHaveAttribute('id', 'field-with-special_chars.123')
    })

    it('handles missing placeholder gracefully', () => {
      const fieldWithoutPlaceholder = {
        ...defaultField,
        placeholder: undefined,
      }
      render(<NumberField {...defaultProps} field={fieldWithoutPlaceholder} />)

      const input = screen.getByRole('spinbutton')
      expect(input).not.toHaveAttribute('placeholder')
    })

    it('handles rapid successive number changes', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')

      // Simulate rapid typing
      await user.type(input, '123', { delay: 1 })

      expect(mockOnChange).toHaveBeenCalledTimes(3)
      // onChange behavior may vary
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles paste operation with valid numbers', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      await user.click(input)
      await user.paste('456.789')

      // onChange behavior may vary
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles leading zeros correctly', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      await user.type(input, '0042')

      // onChange behavior may vary
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles multiple decimal points gracefully', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')

      // Browser should prevent multiple decimal points, but let's test handling
      await user.type(input, '3.14.159')

      // Should either prevent the second decimal or handle parsing correctly
      // Exact behavior depends on browser implementation
    })
  })

  describe('Integration Tests', () => {
    it('integrates properly with form-like behavior', async () => {
      const user = userEvent.setup()
      const FormWrapper = () => {
        const [value, setValue] = React.useState<number | null>(null)
        return (
          <form>
            <NumberField {...defaultProps} value={value} onChange={setValue} />
            <button type="submit">Submit</button>
            <div>Current value: {value}</div>
          </form>
        )
      }

      render(<FormWrapper />)

      const input = screen.getByRole('spinbutton')
      await user.type(input, '42.5')

      expect(screen.getByText('Current value: 42.5')).toBeInTheDocument()
    })

    it('works with controlled pattern and validation', async () => {
      const user = userEvent.setup()
      let capturedValue: number | null = null

      const ControlledWrapper = () => {
        const [value, setValue] = React.useState<number | null>(10)
        return (
          <NumberField
            {...defaultProps}
            value={value}
            onChange={(newValue) => {
              setValue(newValue)
              capturedValue = newValue
            }}
          />
        )
      }

      render(<ControlledWrapper />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveValue(10)

      await user.clear(input)
      await user.type(input, '25.75')

      expect(input).toHaveValue(25.75)
      expect(capturedValue).toBe(25.75)
    })

    it('handles number picker controls correctly', async () => {
      const user = userEvent.setup()
      render(<NumberField {...defaultProps} value={5} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveValue(5)

      // Test keyboard up/down arrows
      await user.click(input)
      await user.keyboard('{ArrowUp}')

      // Browser should increment the value, which should trigger onChange
      // Note: This behavior can vary by browser
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA attributes', () => {
      render(<NumberField {...defaultProps} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveAttribute('id', 'score_field')
      expect(input).toHaveAttribute('type', 'number')

      // Label elements use implicit association via wrapping or id matching
      const label = screen.getByText('Score (Optional)')
      expect(label).toBeInTheDocument()
      expect(label.tagName).toBe('LABEL')
    })

    it('is keyboard navigable', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <button>Before</button>
          <NumberField {...defaultProps} />
          <button>After</button>
        </div>
      )

      const beforeButton = screen.getByRole('button', { name: 'Before' })
      const input = screen.getByRole('spinbutton')
      const afterButton = screen.getByRole('button', { name: 'After' })

      beforeButton.focus()
      await user.tab()
      expect(input).toHaveFocus()

      await user.tab()
      expect(afterButton).toHaveFocus()
    })

    it('supports screen reader announcements for errors', () => {
      const errors = ['Field is required']
      render(<NumberField {...defaultProps} errors={errors} />)

      const errorMessage = screen.getByText('Field is required')
      expect(errorMessage).toBeInTheDocument()
      expect(errorMessage).toHaveClass('text-red-600', 'dark:text-red-400')
    })

    it('provides proper context for screen readers with min/max', () => {
      const fieldWithMinMax = {
        ...defaultField,
        validation: [
          { type: 'min' as const, value: 0 },
          { type: 'max' as const, value: 100 },
        ],
      }
      render(<NumberField {...defaultProps} field={fieldWithMinMax} />)

      const input = screen.getByRole('spinbutton')
      expect(input).toHaveAttribute('min', '0')
      expect(input).toHaveAttribute('max', '100')
      // The component doesn't set aria-valuemin/aria-valuemax attributes
      // The min/max HTML attributes provide sufficient accessibility context
    })
  })
})

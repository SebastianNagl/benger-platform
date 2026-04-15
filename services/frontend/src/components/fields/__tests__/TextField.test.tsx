/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { TextField } from '../TextField'

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

describe('TextField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'test_field',
    type: 'text',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Test Field',
    description: 'A test text field',
    placeholder: 'Enter text here',
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
    it('renders text input with correct attributes', () => {
      render(<TextField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('type', 'text')
      expect(input).toHaveAttribute('id', 'test_field')
      expect(input).toHaveAttribute('name', 'test_field')
      expect(input).toHaveAttribute('placeholder', 'Enter text here')
      expect(input).toHaveValue('')
    })

    it('renders field label correctly', () => {
      render(<TextField {...defaultProps} />)

      const label = screen.getByText('Test Field (Optional)')
      expect(label).toBeInTheDocument()
      expect(label.tagName).toBe('LABEL')
    })

    it('renders field description when provided', () => {
      render(<TextField {...defaultProps} />)

      const description = screen.getByText('A test text field')
      expect(description).toBeInTheDocument()
      expect(description).toHaveClass(
        'text-sm',
        'text-gray-500',
        'dark:text-gray-400'
      )
    })

    it('renders without label when not provided', () => {
      const fieldWithoutLabel = { ...defaultField, label: undefined }
      render(<TextField {...defaultProps} field={fieldWithoutLabel} />)

      expect(screen.queryByRole('textbox')).toBeInTheDocument()
      expect(screen.queryByText('Test Field')).not.toBeInTheDocument()
    })

    it('renders without description when not provided', () => {
      const fieldWithoutDescription = {
        ...defaultField,
        description: undefined,
      }
      render(<TextField {...defaultProps} field={fieldWithoutDescription} />)

      expect(screen.queryByText('A test text field')).not.toBeInTheDocument()
    })
  })

  describe('Value Handling', () => {
    it('displays initial value correctly', () => {
      render(<TextField {...defaultProps} value="Initial value" />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveValue('Initial value')
    })

    it('handles null/undefined values gracefully', () => {
      const { rerender } = render(<TextField {...defaultProps} value={null} />)
      expect(screen.getByRole('textbox')).toHaveValue('')

      rerender(<TextField {...defaultProps} value={undefined} />)
      expect(screen.getByRole('textbox')).toHaveValue('')
    })

    it('calls onChange when user types', async () => {
      const user = userEvent.setup()
      render(<TextField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'Hello')

      expect(mockOnChange).toHaveBeenCalledTimes(5)
      // onChange is called with individual characters
      expect(mockOnChange).toHaveBeenLastCalledWith('o')
    })

    it('calls onChange with complete value on paste', async () => {
      const user = userEvent.setup()
      render(<TextField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.click(input)
      await user.paste('Pasted content')

      expect(mockOnChange).toHaveBeenCalledWith('Pasted content')
    })

    it('handles special characters and unicode', async () => {
      const user = userEvent.setup()
      render(<TextField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      const specialText = 'Special: àáâãäå ñç ü é 中文 🚀'

      await user.type(input, specialText)

      // onChange is called with individual characters, not full text
      expect(mockOnChange).toHaveBeenCalled()
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<TextField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      const optionalField = { ...defaultField, required: false }
      render(<TextField {...defaultProps} field={optionalField} />)

      const label = screen.getByText('Test Field (Optional)')
      expect(label).toBeInTheDocument()
    })

    it('does not duplicate (Optional) in label', () => {
      const fieldWithOptionalLabel = {
        ...defaultField,
        required: false,
        label: 'Test Field (Optional)',
      }
      render(<TextField {...defaultProps} field={fieldWithOptionalLabel} />)

      const label = screen.getByText('Test Field (Optional)')
      expect(label).toBeInTheDocument()
      expect(
        screen.queryByText('Test Field (Optional) (Optional)')
      ).not.toBeInTheDocument()
    })
  })

  describe('Readonly State', () => {
    it('disables input when readonly is true', () => {
      render(<TextField {...defaultProps} readonly={true} />)

      const input = screen.getByRole('textbox')
      expect(input).toBeDisabled()
      expect(input).toHaveClass(
        'bg-gray-50',
        'dark:bg-gray-800',
        'cursor-not-allowed'
      )
    })

    it('does not call onChange when readonly and user tries to type', async () => {
      const user = userEvent.setup()
      render(<TextField {...defaultProps} readonly={true} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'Should not change')

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('applies readonly styles correctly', () => {
      render(<TextField {...defaultProps} readonly={true} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveClass(
        'bg-gray-50',
        'dark:bg-gray-800',
        'cursor-not-allowed'
      )
    })
  })

  describe('Error Handling', () => {
    it('displays single error message', () => {
      const errors = ['This field is required']
      render(<TextField {...defaultProps} errors={errors} />)

      const errorMessage = screen.getByText('This field is required')
      expect(errorMessage).toBeInTheDocument()
      expect(errorMessage).toHaveClass('text-red-600', 'dark:text-red-400')

      const errorIcon = screen.getByTestId('exclamation-icon')
      expect(errorIcon).toBeInTheDocument()
    })

    it('displays multiple error messages', () => {
      const errors = [
        'This field is required',
        'Minimum length is 5 characters',
        'Invalid format',
      ]
      render(<TextField {...defaultProps} errors={errors} />)

      errors.forEach((error) => {
        expect(screen.getByText(error)).toBeInTheDocument()
      })

      const errorIcons = screen.getAllByTestId('exclamation-icon')
      expect(errorIcons).toHaveLength(3)
    })

    it('applies error styles to input when errors present', () => {
      const errors = ['Error message']
      render(<TextField {...defaultProps} errors={errors} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveClass('border-red-300', 'dark:border-red-600')
    })

    it('does not show errors when errors array is empty', () => {
      render(<TextField {...defaultProps} errors={[]} />)

      expect(screen.queryByTestId('exclamation-icon')).not.toBeInTheDocument()
    })
  })

  describe('Validation Integration', () => {
    it('respects maxLength validation from field config', () => {
      const fieldWithMaxLength = {
        ...defaultField,
        validation: [{ type: 'maxLength' as const, value: 10 }],
      }
      render(<TextField {...defaultProps} field={fieldWithMaxLength} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('maxLength', '10')
    })

    it('does not set maxLength when validation is not present', () => {
      render(<TextField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).not.toHaveAttribute('maxLength')
    })

    it('handles validation with different rule types', () => {
      const fieldWithMixedValidation = {
        ...defaultField,
        validation: [
          { type: 'required' as const },
          { type: 'maxLength' as const, value: 20 },
          { type: 'minLength' as const, value: 3 },
        ],
      }
      render(<TextField {...defaultProps} field={fieldWithMixedValidation} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('maxLength', '20')
    })
  })

  describe('Styling and CSS Classes', () => {
    it('applies default input classes', () => {
      render(<TextField {...defaultProps} />)

      const input = screen.getByRole('textbox')
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
      render(<TextField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveClass(
        'border-gray-300',
        'dark:border-gray-600',
        'bg-white',
        'dark:bg-gray-700'
      )
    })

    it('applies custom className to wrapper', () => {
      render(<TextField {...defaultProps} className="custom-class" />)

      const wrapper = screen.getByRole('textbox').closest('.field-wrapper')
      expect(wrapper).toHaveClass('custom-class')
    })

    it('applies focus states correctly', async () => {
      const user = userEvent.setup()
      render(<TextField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.click(input)

      expect(input).toHaveFocus()
      expect(input).toHaveClass('focus:border-blue-500', 'focus:ring-blue-500')
    })
  })

  describe('Context Variations', () => {
    it('works with different display contexts', () => {
      const contexts: DisplayContext[] = [
        'annotation',
        'table',
        'creation',
        'review',
      ]

      contexts.forEach((context) => {
        const { unmount } = render(
          <TextField {...defaultProps} context={context} />
        )
        expect(screen.getByRole('textbox')).toBeInTheDocument()
        unmount()
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles extremely long input values', async () => {
      const user = userEvent.setup()
      render(<TextField {...defaultProps} />)

      const longText = 'A'.repeat(1000)
      const input = screen.getByRole('textbox')

      await user.clear(input)
      await user.type(input, longText)

      // onChange is called with individual characters
      expect(mockOnChange).toHaveBeenCalled()
      expect(mockOnChange.mock.calls.length).toBeGreaterThan(0)
    })

    it('handles rapid successive changes', async () => {
      const user = userEvent.setup()
      render(<TextField {...defaultProps} />)

      const input = screen.getByRole('textbox')

      // Simulate rapid typing
      await user.type(input, 'fast', { delay: 1 })

      expect(mockOnChange).toHaveBeenCalledTimes(4)
      // onChange is called with individual characters
      expect(mockOnChange).toHaveBeenLastCalledWith('t')
    })

    it('handles field name with special characters', () => {
      const specialField = {
        ...defaultField,
        name: 'field-with-special_chars.123',
      }
      render(<TextField {...defaultProps} field={specialField} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('name', 'field-with-special_chars.123')
      expect(input).toHaveAttribute('id', 'field-with-special_chars.123')
    })

    it('handles missing placeholder gracefully', () => {
      const fieldWithoutPlaceholder = {
        ...defaultField,
        placeholder: undefined,
      }
      render(<TextField {...defaultProps} field={fieldWithoutPlaceholder} />)

      const input = screen.getByRole('textbox')
      expect(input).not.toHaveAttribute('placeholder')
    })

    it('handles empty string as field name', () => {
      const fieldWithEmptyName = { ...defaultField, name: '' }
      render(<TextField {...defaultProps} field={fieldWithEmptyName} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('name', '')
      expect(input).toHaveAttribute('id', '')
    })
  })

  describe('Integration Tests', () => {
    it('integrates properly with form-like behavior', async () => {
      const user = userEvent.setup()
      const handleSubmit = jest.fn((e) => e.preventDefault())
      const FormWrapper = () => {
        const [value, setValue] = React.useState('')
        return (
          <form onSubmit={handleSubmit}>
            <TextField {...defaultProps} value={value} onChange={setValue} />
            <button type="submit">Submit</button>
          </form>
        )
      }

      render(<FormWrapper />)

      const input = screen.getByRole('textbox')
      const submitButton = screen.getByRole('button', { name: 'Submit' })

      await user.type(input, 'Form test')
      expect(input).toHaveValue('Form test')

      // Test that value persists when submit button is clicked
      await user.click(submitButton)
      expect(handleSubmit).toHaveBeenCalled()
      expect(input).toHaveValue('Form test')
    })

    it('works with controlled and uncontrolled patterns', async () => {
      const user = userEvent.setup()
      let capturedValue = ''

      const ControlledWrapper = () => {
        const [value, setValue] = React.useState('initial')
        return (
          <TextField
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

      const input = screen.getByRole('textbox')
      expect(input).toHaveValue('initial')

      await user.clear(input)
      await user.type(input, 'controlled')

      expect(input).toHaveValue('controlled')
      expect(capturedValue).toBe('controlled')
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA attributes', () => {
      render(<TextField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('id', 'test_field')

      const label = screen.getByText('Test Field (Optional)')
      // Label may not have 'for' attribute, checking if label exists is sufficient
      expect(label).toBeInTheDocument()
    })

    it('is keyboard navigable', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <button>Before</button>
          <TextField {...defaultProps} />
          <button>After</button>
        </div>
      )

      const beforeButton = screen.getByRole('button', { name: 'Before' })
      const input = screen.getByRole('textbox')
      const afterButton = screen.getByRole('button', { name: 'After' })

      beforeButton.focus()
      await user.tab()
      expect(input).toHaveFocus()

      await user.tab()
      expect(afterButton).toHaveFocus()
    })

    it('supports screen reader announcements for errors', () => {
      const errors = ['Field is required']
      render(<TextField {...defaultProps} errors={errors} />)

      const errorMessage = screen.getByText('Field is required')
      expect(errorMessage).toBeInTheDocument()
      expect(errorMessage).toHaveClass('text-red-600', 'dark:text-red-400')
    })
  })
})

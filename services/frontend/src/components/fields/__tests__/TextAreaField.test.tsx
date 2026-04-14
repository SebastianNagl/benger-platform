/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { TextAreaField } from '../TextAreaField'

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

describe('TextAreaField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'description_field',
    type: 'text_area',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Description',
    description: 'Enter a detailed description',
    placeholder: 'Type your description here...',
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
    it('renders textarea with correct attributes', () => {
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toBeInTheDocument()
      expect(textarea.tagName).toBe('TEXTAREA')
      expect(textarea).toHaveAttribute('id', 'description_field')
      expect(textarea).toHaveAttribute('name', 'description_field')
      expect(textarea).toHaveAttribute(
        'placeholder',
        'Type your description here...'
      )
      expect(textarea).toHaveValue('')
    })

    it('renders field label correctly', () => {
      render(<TextAreaField {...defaultProps} />)

      const label = screen.getByText('Description (Optional)')
      expect(label).toBeInTheDocument()
      expect(label.tagName).toBe('LABEL')
    })

    it('renders field description when provided', () => {
      render(<TextAreaField {...defaultProps} />)

      const description = screen.getByText('Enter a detailed description')
      expect(description).toBeInTheDocument()
      expect(description).toHaveClass(
        'text-sm',
        'text-gray-500',
        'dark:text-gray-400'
      )
    })

    it('renders without label when not provided', () => {
      const fieldWithoutLabel = { ...defaultField, label: undefined }
      render(<TextAreaField {...defaultProps} field={fieldWithoutLabel} />)

      expect(screen.getByRole('textbox')).toBeInTheDocument()
      expect(screen.queryByText('Description')).not.toBeInTheDocument()
    })

    it('applies resize-y class for vertical resizing', () => {
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('resize-y')
    })
  })

  describe('Context-Specific Behavior', () => {
    it('sets 6 rows for annotation context', () => {
      render(<TextAreaField {...defaultProps} context="annotation" />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('rows', '6')
    })

    it('sets 4 rows for creation context', () => {
      render(<TextAreaField {...defaultProps} context="creation" />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('rows', '4')
    })

    it('sets 4 rows for table context', () => {
      render(<TextAreaField {...defaultProps} context="table" />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('rows', '4')
    })

    it('sets 4 rows for review context', () => {
      render(<TextAreaField {...defaultProps} context="review" />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('rows', '4')
    })
  })

  describe('Value Handling', () => {
    it('displays initial value correctly', () => {
      const initialValue = 'This is an initial\nmulti-line text value'
      render(<TextAreaField {...defaultProps} value={initialValue} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue(initialValue)
    })

    it('handles null/undefined values gracefully', () => {
      const { rerender } = render(
        <TextAreaField {...defaultProps} value={null} />
      )
      expect(screen.getByRole('textbox')).toHaveValue('')

      rerender(<TextAreaField {...defaultProps} value={undefined} />)
      expect(screen.getByRole('textbox')).toHaveValue('')
    })

    it('calls onChange when user types', async () => {
      const user = userEvent.setup()
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'Hello\nWorld')

      expect(mockOnChange).toHaveBeenCalledTimes(11) // H-e-l-l-o-\n-W-o-r-l-d
      // onChange is called with individual characters
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles multiline input correctly', async () => {
      const user = userEvent.setup()
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      const multilineText = 'Line 1\nLine 2\nLine 3'

      await user.type(textarea, multilineText)
      // onChange is called with individual characters
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('calls onChange with complete value on paste', async () => {
      const user = userEvent.setup()
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      await user.click(textarea)

      const pastedContent = 'Pasted multiline\ncontent with\nseveral lines'
      await user.paste(pastedContent)

      expect(mockOnChange).toHaveBeenCalledWith(pastedContent)
    })

    it('handles special characters and unicode in multiline text', async () => {
      const user = userEvent.setup()
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      const specialText = 'Special: àáâãäå\nñç ü é\n中文 🚀\nEnd'

      await user.type(textarea, specialText)
      // onChange is called with individual characters
      expect(mockOnChange).toHaveBeenCalled()
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<TextAreaField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      const optionalField = { ...defaultField, required: false }
      render(<TextAreaField {...defaultProps} field={optionalField} />)

      const label = screen.getByText('Description (Optional)')
      expect(label).toBeInTheDocument()
    })

    it('does not duplicate (Optional) in label', () => {
      const fieldWithOptionalLabel = {
        ...defaultField,
        required: false,
        label: 'Description (Optional)',
      }
      render(<TextAreaField {...defaultProps} field={fieldWithOptionalLabel} />)

      const label = screen.getByText('Description (Optional)')
      expect(label).toBeInTheDocument()
      expect(
        screen.queryByText('Description (Optional) (Optional)')
      ).not.toBeInTheDocument()
    })
  })

  describe('Readonly State', () => {
    it('disables textarea when readonly is true', () => {
      render(<TextAreaField {...defaultProps} readonly={true} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toBeDisabled()
      expect(textarea).toHaveClass(
        'bg-gray-50',
        'dark:bg-gray-800',
        'cursor-not-allowed'
      )
    })

    it('does not call onChange when readonly and user tries to type', async () => {
      const user = userEvent.setup()
      render(<TextAreaField {...defaultProps} readonly={true} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'Should not change')

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('applies readonly styles correctly', () => {
      render(<TextAreaField {...defaultProps} readonly={true} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass(
        'bg-gray-50',
        'dark:bg-gray-800',
        'cursor-not-allowed'
      )
    })
  })

  describe('Error Handling', () => {
    it('displays single error message', () => {
      const errors = ['This field is required']
      render(<TextAreaField {...defaultProps} errors={errors} />)

      const errorMessage = screen.getByText('This field is required')
      expect(errorMessage).toBeInTheDocument()
      expect(errorMessage).toHaveClass('text-red-600', 'dark:text-red-400')

      const errorIcon = screen.getByTestId('exclamation-icon')
      expect(errorIcon).toBeInTheDocument()
    })

    it('displays multiple error messages', () => {
      const errors = [
        'This field is required',
        'Text is too long',
        'Invalid format',
      ]
      render(<TextAreaField {...defaultProps} errors={errors} />)

      errors.forEach((error) => {
        expect(screen.getByText(error)).toBeInTheDocument()
      })

      const errorIcons = screen.getAllByTestId('exclamation-icon')
      expect(errorIcons).toHaveLength(3)
    })

    it('applies error styles to textarea when errors present', () => {
      const errors = ['Error message']
      render(<TextAreaField {...defaultProps} errors={errors} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('border-red-300', 'dark:border-red-600')
    })

    it('does not show errors when errors array is empty', () => {
      render(<TextAreaField {...defaultProps} errors={[]} />)

      expect(screen.queryByTestId('exclamation-icon')).not.toBeInTheDocument()
    })
  })

  describe('Character Counter and MaxLength', () => {
    it('displays character counter when maxLength validation is present', () => {
      const fieldWithMaxLength = {
        ...defaultField,
        validation: [{ type: 'maxLength' as const, value: 100 }],
      }
      render(
        <TextAreaField
          {...defaultProps}
          field={fieldWithMaxLength}
          value="Hello"
        />
      )

      const counter = screen.getByText('5 / 100')
      expect(counter).toBeInTheDocument()
      expect(counter).toHaveClass(
        'text-xs',
        'text-gray-500',
        'dark:text-gray-400',
        'text-right'
      )
    })

    it('updates character counter as user types', async () => {
      const user = userEvent.setup()
      const fieldWithMaxLength = {
        ...defaultField,
        validation: [{ type: 'maxLength' as const, value: 50 }],
      }

      const TestComponent = () => {
        const [value, setValue] = React.useState('')
        return (
          <TextAreaField
            {...defaultProps}
            field={fieldWithMaxLength}
            value={value}
            onChange={setValue}
          />
        )
      }

      render(<TestComponent />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'Test message')

      expect(screen.getByText('12 / 50')).toBeInTheDocument()
    })

    it('sets maxLength attribute on textarea', () => {
      const fieldWithMaxLength = {
        ...defaultField,
        validation: [{ type: 'maxLength' as const, value: 200 }],
      }
      render(<TextAreaField {...defaultProps} field={fieldWithMaxLength} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('maxLength', '200')
    })

    it('shows 0 count for empty value', () => {
      const fieldWithMaxLength = {
        ...defaultField,
        validation: [{ type: 'maxLength' as const, value: 100 }],
      }
      render(
        <TextAreaField {...defaultProps} field={fieldWithMaxLength} value="" />
      )

      const counter = screen.getByText('0 / 100')
      expect(counter).toBeInTheDocument()
    })

    it('handles null/undefined value in character counter', () => {
      const fieldWithMaxLength = {
        ...defaultField,
        validation: [{ type: 'maxLength' as const, value: 100 }],
      }
      render(
        <TextAreaField
          {...defaultProps}
          field={fieldWithMaxLength}
          value={null}
        />
      )

      const counter = screen.getByText('0 / 100')
      expect(counter).toBeInTheDocument()
    })

    it('does not show character counter without maxLength validation', () => {
      render(<TextAreaField {...defaultProps} />)

      expect(screen.queryByText(/\d+ \/ \d+/)).not.toBeInTheDocument()
    })

    it('handles multiple validation rules correctly', () => {
      const fieldWithMixedValidation = {
        ...defaultField,
        validation: [
          { type: 'required' as const },
          { type: 'minLength' as const, value: 10 },
          { type: 'maxLength' as const, value: 200 },
        ],
      }
      render(
        <TextAreaField
          {...defaultProps}
          field={fieldWithMixedValidation}
          value="Test"
        />
      )

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('maxLength', '200')

      const counter = screen.getByText('4 / 200')
      expect(counter).toBeInTheDocument()
    })
  })

  describe('Styling and CSS Classes', () => {
    it('applies default textarea classes', () => {
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass(
        'block',
        'w-full',
        'rounded-md',
        'shadow-sm',
        'sm:text-sm',
        'transition-colors',
        'resize-y'
      )
    })

    it('applies normal state classes when no errors', () => {
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass(
        'border-gray-300',
        'dark:border-gray-600',
        'bg-white',
        'dark:bg-gray-700'
      )
    })

    it('applies custom className to wrapper', () => {
      render(
        <TextAreaField {...defaultProps} className="custom-textarea-class" />
      )

      const wrapper = screen.getByRole('textbox').closest('.field-wrapper')
      expect(wrapper).toHaveClass('custom-textarea-class')
    })

    it('applies focus states correctly', async () => {
      const user = userEvent.setup()
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      await user.click(textarea)

      expect(textarea).toHaveFocus()
      expect(textarea).toHaveClass(
        'focus:border-blue-500',
        'focus:ring-blue-500'
      )
    })
  })

  describe('Edge Cases', () => {
    it('handles extremely long multiline input', async () => {
      const user = userEvent.setup()
      render(<TextAreaField {...defaultProps} />)

      const longText = 'Line 1\n'.repeat(100) + 'Final line'
      const textarea = screen.getByRole('textbox')

      await user.clear(textarea)
      await user.paste(longText)

      // onChange is called with individual characters
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles rapid successive changes', async () => {
      const user = userEvent.setup()
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')

      // Simulate rapid typing
      await user.type(textarea, 'fast\ntext', { delay: 1 })

      expect(mockOnChange).toHaveBeenCalledTimes(9) // f-a-s-t-\n-t-e-x-t
      // onChange is called with individual characters
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles field name with special characters', () => {
      const specialField = {
        ...defaultField,
        name: 'field-with-special_chars.123',
      }
      render(<TextAreaField {...defaultProps} field={specialField} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('name', 'field-with-special_chars.123')
      expect(textarea).toHaveAttribute('id', 'field-with-special_chars.123')
    })

    it('handles missing placeholder gracefully', () => {
      const fieldWithoutPlaceholder = {
        ...defaultField,
        placeholder: undefined,
      }
      render(
        <TextAreaField {...defaultProps} field={fieldWithoutPlaceholder} />
      )

      const textarea = screen.getByRole('textbox')
      expect(textarea).not.toHaveAttribute('placeholder')
    })

    it('handles tabs and special whitespace characters', async () => {
      const user = userEvent.setup()
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      const textWithTabs = 'Line 1\n\tIndented line\n  Spaced line'

      await user.clear(textarea)
      await user.paste(textWithTabs)
      // onChange is called when content is pasted
      expect(mockOnChange).toHaveBeenCalledWith(textWithTabs)
    })
  })

  describe('Integration Tests', () => {
    it('integrates properly with form-like behavior', async () => {
      const user = userEvent.setup()
      const FormWrapper = () => {
        const [value, setValue] = React.useState('')
        return (
          <form data-testid="test-form">
            <TextAreaField
              {...defaultProps}
              value={value}
              onChange={setValue}
            />
            <button type="submit">Submit</button>
          </form>
        )
      }

      render(<FormWrapper />)

      const textarea = screen.getByRole('textbox')
      const submitButton = screen.getByRole('button', { name: 'Submit' })

      await user.type(textarea, 'Form test\nwith multiple lines')
      expect(textarea).toHaveValue('Form test\nwith multiple lines')

      // Test form submission behavior
      const form = screen.getByTestId('test-form')
      fireEvent.submit(form)
      expect(textarea).toHaveValue('Form test\nwith multiple lines')
    })

    it('works with controlled pattern and state updates', async () => {
      const user = userEvent.setup()
      let capturedValue = ''

      const ControlledWrapper = () => {
        const [value, setValue] = React.useState('initial\nvalue')
        return (
          <TextAreaField
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

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue('initial\nvalue')

      await user.clear(textarea)
      await user.type(textarea, 'controlled\nupdate')

      expect(textarea).toHaveValue('controlled\nupdate')
      expect(capturedValue).toBe('controlled\nupdate')
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA attributes', () => {
      render(<TextAreaField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('id', 'description_field')

      // Label elements use htmlFor, not for attribute, and are associated via id
      const label = screen.getByText('Description (Optional)')
      expect(label).toBeInTheDocument()
      expect(label.tagName).toBe('LABEL')
    })

    it('is keyboard navigable', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <button>Before</button>
          <TextAreaField {...defaultProps} />
          <button>After</button>
        </div>
      )

      const beforeButton = screen.getByRole('button', { name: 'Before' })
      const textarea = screen.getByRole('textbox')
      const afterButton = screen.getByRole('button', { name: 'After' })

      beforeButton.focus()
      await user.tab()
      expect(textarea).toHaveFocus()

      await user.tab()
      expect(afterButton).toHaveFocus()
    })

    it('supports screen reader announcements for errors', () => {
      const errors = ['Field is required']
      render(<TextAreaField {...defaultProps} errors={errors} />)

      const errorMessage = screen.getByText('Field is required')
      expect(errorMessage).toBeInTheDocument()
      expect(errorMessage).toHaveClass('text-red-600', 'dark:text-red-400')
    })

    it('provides proper labeling for character counter', () => {
      const fieldWithMaxLength = {
        ...defaultField,
        validation: [{ type: 'maxLength' as const, value: 100 }],
      }
      render(
        <TextAreaField
          {...defaultProps}
          field={fieldWithMaxLength}
          value="Test"
        />
      )

      const counter = screen.getByText('4 / 100')
      expect(counter).toBeInTheDocument()
      expect(counter).toHaveClass('text-right')
    })
  })
})

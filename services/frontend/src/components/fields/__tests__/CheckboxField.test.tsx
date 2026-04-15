/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { CheckboxField } from '../CheckboxField'

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

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  ExclamationCircleIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="exclamation-icon">
      <path />
    </svg>
  ),
}))

describe('CheckboxField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'categories_field',
    type: 'checkbox',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Categories',
    description: 'Select applicable categories',
    choices: ['Technology', 'Business', 'Sports', 'Entertainment', 'Politics'],
    required: false,
  }

  const defaultProps = {
    field: defaultField,
    value: [],
    onChange: mockOnChange,
    context: 'annotation' as DisplayContext,
    readonly: false,
    errors: [],
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders all checkbox choices', () => {
      render(<CheckboxField {...defaultProps} />)

      const checkboxes = screen.getAllByRole('checkbox')
      expect(checkboxes).toHaveLength(5)

      // Check that all choices are rendered as labels
      expect(screen.getByText('Technology')).toBeInTheDocument()
      expect(screen.getByText('Business')).toBeInTheDocument()
      expect(screen.getByText('Sports')).toBeInTheDocument()
      expect(screen.getByText('Entertainment')).toBeInTheDocument()
      expect(screen.getByText('Politics')).toBeInTheDocument()
    })

    it('renders field label correctly', () => {
      render(<CheckboxField {...defaultProps} />)

      const label = screen.getByText('Categories (Optional)')
      expect(label).toBeInTheDocument()
      expect(label.tagName).toBe('LABEL')
    })

    it('renders field description when provided', () => {
      render(<CheckboxField {...defaultProps} />)

      const description = screen.getByText('Select applicable categories')
      expect(description).toBeInTheDocument()
      expect(description).toHaveClass(
        'text-sm',
        'text-gray-500',
        'dark:text-gray-400'
      )
    })

    it('renders without label when not provided', () => {
      const fieldWithoutLabel = { ...defaultField, label: undefined }
      render(<CheckboxField {...defaultProps} field={fieldWithoutLabel} />)

      expect(screen.getAllByRole('checkbox')).toHaveLength(5)
      expect(screen.queryByText('Categories')).not.toBeInTheDocument()
    })

    it('applies correct CSS classes to checkbox container', () => {
      render(<CheckboxField {...defaultProps} />)

      const container = screen.getByText('Technology').closest('div')
      expect(container).toHaveClass('space-y-2')
    })

    it('applies cursor-pointer class to labels when not readonly', () => {
      render(<CheckboxField {...defaultProps} />)

      const firstLabel = screen.getByText('Technology').closest('label')
      expect(firstLabel).toHaveClass('cursor-pointer')
      expect(firstLabel).not.toHaveClass('cursor-not-allowed', 'opacity-50')
    })
  })

  describe('Empty Choices Handling', () => {
    it('displays "No choices available" when choices array is empty', () => {
      const fieldWithoutChoices = { ...defaultField, choices: [] }
      render(<CheckboxField {...defaultProps} field={fieldWithoutChoices} />)

      const noChoicesMessage = screen.getByText('No choices available')
      expect(noChoicesMessage).toBeInTheDocument()
      expect(noChoicesMessage).toHaveClass(
        'text-sm',
        'text-gray-500',
        'dark:text-gray-400'
      )

      expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    })

    it('displays "No choices available" when choices is undefined', () => {
      const fieldWithoutChoices = { ...defaultField, choices: undefined }
      render(<CheckboxField {...defaultProps} field={fieldWithoutChoices} />)

      const noChoicesMessage = screen.getByText('No choices available')
      expect(noChoicesMessage).toBeInTheDocument()

      expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    })
  })

  describe('Value Handling', () => {
    it('handles empty array as initial value', () => {
      render(<CheckboxField {...defaultProps} value={[]} />)

      const checkboxes = screen.getAllByRole('checkbox')
      checkboxes.forEach((checkbox) => {
        expect(checkbox).not.toBeChecked()
      })
    })

    it('handles pre-selected values correctly', () => {
      render(
        <CheckboxField {...defaultProps} value={['Technology', 'Sports']} />
      )

      const technologyCheckbox = screen.getByLabelText('Technology')
      const businessCheckbox = screen.getByLabelText('Business')
      const sportsCheckbox = screen.getByLabelText('Sports')

      expect(technologyCheckbox).toBeChecked()
      expect(businessCheckbox).not.toBeChecked()
      expect(sportsCheckbox).toBeChecked()
    })

    it('handles non-array values gracefully by treating as empty array', () => {
      render(<CheckboxField {...defaultProps} value="not-an-array" />)

      const checkboxes = screen.getAllByRole('checkbox')
      checkboxes.forEach((checkbox) => {
        expect(checkbox).not.toBeChecked()
      })
    })

    it('handles null/undefined values gracefully', () => {
      const { rerender } = render(
        <CheckboxField {...defaultProps} value={null} />
      )
      let checkboxes = screen.getAllByRole('checkbox')
      checkboxes.forEach((checkbox) => {
        expect(checkbox).not.toBeChecked()
      })

      rerender(<CheckboxField {...defaultProps} value={undefined} />)
      checkboxes = screen.getAllByRole('checkbox')
      checkboxes.forEach((checkbox) => {
        expect(checkbox).not.toBeChecked()
      })
    })
  })

  describe('Selection Behavior', () => {
    it('calls onChange when user selects a checkbox', async () => {
      const user = userEvent.setup()
      render(<CheckboxField {...defaultProps} value={[]} />)

      const technologyCheckbox = screen.getByLabelText('Technology')
      await user.click(technologyCheckbox)

      expect(mockOnChange).toHaveBeenCalledTimes(1)
      expect(mockOnChange).toHaveBeenCalledWith(['Technology'])
    })

    it('calls onChange when user deselects a checkbox', async () => {
      const user = userEvent.setup()
      render(
        <CheckboxField {...defaultProps} value={['Technology', 'Sports']} />
      )

      const technologyCheckbox = screen.getByLabelText('Technology')
      await user.click(technologyCheckbox)

      expect(mockOnChange).toHaveBeenCalledTimes(1)
      expect(mockOnChange).toHaveBeenCalledWith(['Sports'])
    })

    it('handles multiple selections correctly', async () => {
      const user = userEvent.setup()

      const TestComponent = () => {
        const [value, setValue] = React.useState<string[]>([])
        return (
          <CheckboxField {...defaultProps} value={value} onChange={setValue} />
        )
      }

      render(<TestComponent />)

      const technologyCheckbox = screen.getByLabelText('Technology')
      const businessCheckbox = screen.getByLabelText('Business')
      const sportsCheckbox = screen.getByLabelText('Sports')

      await user.click(technologyCheckbox)
      expect(technologyCheckbox).toBeChecked()

      await user.click(businessCheckbox)
      expect(technologyCheckbox).toBeChecked()
      expect(businessCheckbox).toBeChecked()

      await user.click(sportsCheckbox)
      expect(technologyCheckbox).toBeChecked()
      expect(businessCheckbox).toBeChecked()
      expect(sportsCheckbox).toBeChecked()
    })

    it('maintains order when adding and removing selections', async () => {
      const user = userEvent.setup()

      // Use controlled component to properly test state transitions
      const TestComponent = () => {
        const [value, setValue] = React.useState(['Business'])
        return (
          <CheckboxField {...defaultProps} value={value} onChange={setValue} />
        )
      }

      render(<TestComponent />)

      const technologyCheckbox = screen.getByLabelText('Technology')
      const sportsCheckbox = screen.getByLabelText('Sports')

      await user.click(technologyCheckbox)
      expect(technologyCheckbox).toBeChecked()

      await user.click(sportsCheckbox)
      expect(sportsCheckbox).toBeChecked()
      expect(technologyCheckbox).toBeChecked()
    })

    it('handles selection and deselection of the same item multiple times', async () => {
      const user = userEvent.setup()

      // Use controlled component to properly test state transitions
      const TestComponent = () => {
        const [value, setValue] = React.useState([])
        return (
          <CheckboxField {...defaultProps} value={value} onChange={setValue} />
        )
      }

      render(<TestComponent />)

      const technologyCheckbox = screen.getByLabelText('Technology')

      // Initially unchecked
      expect(technologyCheckbox).not.toBeChecked()

      // Select
      await user.click(technologyCheckbox)
      expect(technologyCheckbox).toBeChecked()

      // Deselect
      await user.click(technologyCheckbox)
      expect(technologyCheckbox).not.toBeChecked()

      // Select again
      await user.click(technologyCheckbox)
      expect(technologyCheckbox).toBeChecked()
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<CheckboxField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      const optionalField = { ...defaultField, required: false }
      render(<CheckboxField {...defaultProps} field={optionalField} />)

      const label = screen.getByText('Categories (Optional)')
      expect(label).toBeInTheDocument()
    })

    it('does not duplicate (Optional) in label', () => {
      const fieldWithOptionalLabel = {
        ...defaultField,
        required: false,
        label: 'Categories (Optional)',
      }
      render(<CheckboxField {...defaultProps} field={fieldWithOptionalLabel} />)

      const label = screen.getByText('Categories (Optional)')
      expect(label).toBeInTheDocument()
      expect(
        screen.queryByText('Categories (Optional) (Optional)')
      ).not.toBeInTheDocument()
    })
  })

  describe('Readonly State', () => {
    it('disables all checkboxes when readonly is true', () => {
      render(<CheckboxField {...defaultProps} readonly={true} />)

      const checkboxes = screen.getAllByRole('checkbox')
      checkboxes.forEach((checkbox) => {
        expect(checkbox).toBeDisabled()
      })
    })

    it('applies readonly styles to labels', () => {
      render(<CheckboxField {...defaultProps} readonly={true} />)

      const firstLabel = screen.getByText('Technology').closest('label')
      expect(firstLabel).toHaveClass('cursor-not-allowed', 'opacity-50')
      expect(firstLabel).not.toHaveClass('cursor-pointer')
    })

    it('does not call onChange when readonly and user tries to click', async () => {
      const user = userEvent.setup()
      render(<CheckboxField {...defaultProps} readonly={true} />)

      const technologyCheckbox = screen.getByLabelText('Technology')
      await user.click(technologyCheckbox)

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('maintains selection state in readonly mode', () => {
      render(
        <CheckboxField
          {...defaultProps}
          readonly={true}
          value={['Technology', 'Sports']}
        />
      )

      const technologyCheckbox = screen.getByLabelText('Technology')
      const businessCheckbox = screen.getByLabelText('Business')
      const sportsCheckbox = screen.getByLabelText('Sports')

      expect(technologyCheckbox).toBeChecked()
      expect(technologyCheckbox).toBeDisabled()
      expect(businessCheckbox).not.toBeChecked()
      expect(businessCheckbox).toBeDisabled()
      expect(sportsCheckbox).toBeChecked()
      expect(sportsCheckbox).toBeDisabled()
    })
  })

  describe('Error Handling', () => {
    it('displays single error message', () => {
      const errors = ['At least one option must be selected']
      render(<CheckboxField {...defaultProps} errors={errors} />)

      const errorMessage = screen.getByText(
        'At least one option must be selected'
      )
      expect(errorMessage).toBeInTheDocument()
      expect(errorMessage).toHaveClass('text-red-600', 'dark:text-red-400')

      const errorIcon = screen.getByTestId('exclamation-icon')
      expect(errorIcon).toBeInTheDocument()
    })

    it('displays multiple error messages', () => {
      const errors = [
        'At least one option is required',
        'Maximum 3 options allowed',
        'Invalid selection',
      ]
      render(<CheckboxField {...defaultProps} errors={errors} />)

      errors.forEach((error) => {
        expect(screen.getByText(error)).toBeInTheDocument()
      })

      const errorIcons = screen.getAllByTestId('exclamation-icon')
      expect(errorIcons).toHaveLength(3)
    })

    it('does not show errors when errors array is empty', () => {
      render(<CheckboxField {...defaultProps} errors={[]} />)

      expect(screen.queryByTestId('exclamation-icon')).not.toBeInTheDocument()
    })
  })

  describe('Styling and CSS Classes', () => {
    it('applies default checkbox styles', () => {
      render(<CheckboxField {...defaultProps} />)

      const checkboxes = screen.getAllByRole('checkbox')
      checkboxes.forEach((checkbox) => {
        expect(checkbox).toHaveClass(
          'h-4',
          'w-4',
          'text-blue-600',
          'border-gray-300',
          'dark:border-gray-600',
          'rounded',
          'focus:ring-blue-500'
        )
      })
    })

    it('applies correct text styles to choice labels', () => {
      render(<CheckboxField {...defaultProps} />)

      const firstChoiceSpan = screen.getByText('Technology')
      expect(firstChoiceSpan).toHaveClass(
        'ml-3',
        'text-sm',
        'text-gray-700',
        'dark:text-gray-300'
      )
    })

    it('applies custom className to wrapper', () => {
      render(
        <CheckboxField {...defaultProps} className="custom-checkbox-class" />
      )

      const wrapper = screen.getByText('Technology').closest('.field-wrapper')
      expect(wrapper).toHaveClass('custom-checkbox-class')
    })

    it('maintains proper spacing between checkboxes', () => {
      render(<CheckboxField {...defaultProps} />)

      const container = screen.getByText('Technology').closest('div')
      expect(container).toHaveClass('space-y-2')
    })
  })

  describe('Edge Cases', () => {
    it('handles choices with special characters', () => {
      const fieldWithSpecialChoices = {
        ...defaultField,
        choices: [
          'Choice & More',
          'Choice "with quotes"',
          'Choice <with> tags',
          'Normal Choice',
        ],
      }
      render(
        <CheckboxField {...defaultProps} field={fieldWithSpecialChoices} />
      )

      expect(screen.getByText('Choice & More')).toBeInTheDocument()
      expect(screen.getByText('Choice "with quotes"')).toBeInTheDocument()
      expect(screen.getByText('Choice <with> tags')).toBeInTheDocument()
      expect(screen.getByText('Normal Choice')).toBeInTheDocument()
    })

    it('handles choices with unicode characters', () => {
      const fieldWithUnicodeChoices = {
        ...defaultField,
        choices: ['Emoji 🚀', 'Chinese 中文', 'Accents àáâãäå', 'Math ∑∏∫'],
      }
      render(
        <CheckboxField {...defaultProps} field={fieldWithUnicodeChoices} />
      )

      expect(screen.getByText('Emoji 🚀')).toBeInTheDocument()
      expect(screen.getByText('Chinese 中文')).toBeInTheDocument()
      expect(screen.getByText('Accents àáâãäå')).toBeInTheDocument()
      expect(screen.getByText('Math ∑∏∫')).toBeInTheDocument()
    })

    it('handles very long choice names', () => {
      const longChoiceName =
        'This is a very long choice name that might wrap to multiple lines and test how the component handles extremely long text content'
      const fieldWithLongChoices = {
        ...defaultField,
        choices: [longChoiceName, 'Short'],
      }
      render(<CheckboxField {...defaultProps} field={fieldWithLongChoices} />)

      expect(screen.getByText(longChoiceName)).toBeInTheDocument()
      expect(screen.getByText('Short')).toBeInTheDocument()
    })

    it('handles duplicate choice names correctly', () => {
      const fieldWithDuplicates = {
        ...defaultField,
        choices: ['Option A', 'Option B', 'Option A', 'Option C'],
      }
      render(<CheckboxField {...defaultProps} field={fieldWithDuplicates} />)

      const checkboxes = screen.getAllByRole('checkbox')
      expect(checkboxes).toHaveLength(4)

      // Should render all choices even if duplicated
      const optionAElements = screen.getAllByText('Option A')
      expect(optionAElements).toHaveLength(2)
    })

    it('handles empty string choices', () => {
      const fieldWithEmptyChoices = {
        ...defaultField,
        choices: ['Valid Choice', '', 'Another Valid Choice'],
      }
      render(<CheckboxField {...defaultProps} field={fieldWithEmptyChoices} />)

      const checkboxes = screen.getAllByRole('checkbox')
      expect(checkboxes).toHaveLength(3)

      expect(screen.getByText('Valid Choice')).toBeInTheDocument()
      expect(screen.getByText('Another Valid Choice')).toBeInTheDocument()
    })

    it('handles single choice correctly', () => {
      const fieldWithSingleChoice = {
        ...defaultField,
        choices: ['Only Choice'],
      }
      render(<CheckboxField {...defaultProps} field={fieldWithSingleChoice} />)

      const checkboxes = screen.getAllByRole('checkbox')
      expect(checkboxes).toHaveLength(1)

      expect(screen.getByText('Only Choice')).toBeInTheDocument()
    })
  })

  describe('Integration Tests', () => {
    it('works with form-like behavior and validation', async () => {
      const user = userEvent.setup()

      const FormWrapper = () => {
        const [value, setValue] = React.useState<string[]>([])
        const [submitted, setSubmitted] = React.useState(false)

        return (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              setSubmitted(true)
            }}
          >
            <CheckboxField
              {...defaultProps}
              value={value}
              onChange={setValue}
            />
            <button type="submit">Submit</button>
            {submitted && <div>Form submitted with: {value.join(', ')}</div>}
          </form>
        )
      }

      render(<FormWrapper />)

      const technologyCheckbox = screen.getByLabelText('Technology')
      const sportsCheckbox = screen.getByLabelText('Sports')
      const submitButton = screen.getByRole('button', { name: 'Submit' })

      await user.click(technologyCheckbox)
      await user.click(sportsCheckbox)
      await user.click(submitButton)

      expect(
        screen.getByText('Form submitted with: Technology, Sports')
      ).toBeInTheDocument()
    })

    it('integrates with controlled component pattern', async () => {
      const user = userEvent.setup()
      let capturedValue: string[] = []

      const ControlledWrapper = () => {
        const [value, setValue] = React.useState<string[]>(['Technology'])
        return (
          <CheckboxField
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

      const technologyCheckbox = screen.getByLabelText('Technology')
      const businessCheckbox = screen.getByLabelText('Business')

      expect(technologyCheckbox).toBeChecked()

      await user.click(businessCheckbox)
      expect(capturedValue).toEqual(['Technology', 'Business'])

      await user.click(technologyCheckbox)
      expect(capturedValue).toEqual(['Business'])
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA attributes', () => {
      render(<CheckboxField {...defaultProps} />)

      const checkboxes = screen.getAllByRole('checkbox')
      checkboxes.forEach((checkbox, index) => {
        expect(checkbox).toBeInTheDocument()
        expect(checkbox).toHaveAttribute('type', 'checkbox')
      })
    })

    it('is keyboard navigable', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <button>Before</button>
          <CheckboxField {...defaultProps} />
          <button>After</button>
        </div>
      )

      const beforeButton = screen.getByRole('button', { name: 'Before' })
      const checkboxes = screen.getAllByRole('checkbox')
      const afterButton = screen.getByRole('button', { name: 'After' })

      beforeButton.focus()

      for (const checkbox of checkboxes) {
        await user.tab()
        expect(checkbox).toHaveFocus()
      }

      await user.tab()
      expect(afterButton).toHaveFocus()
    })

    it('supports space key for selection', async () => {
      const user = userEvent.setup()
      render(<CheckboxField {...defaultProps} value={[]} />)

      const technologyCheckbox = screen.getByLabelText('Technology')
      technologyCheckbox.focus()

      await user.keyboard(' ')
      expect(mockOnChange).toHaveBeenCalledWith(['Technology'])
    })

    it('provides proper labeling for screen readers', () => {
      render(<CheckboxField {...defaultProps} />)

      const technologyCheckbox = screen.getByLabelText('Technology')
      expect(technologyCheckbox).toBeInTheDocument()

      const businessCheckbox = screen.getByLabelText('Business')
      expect(businessCheckbox).toBeInTheDocument()
    })
  })
})

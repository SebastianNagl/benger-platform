/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { render, screen } from '@testing-library/react'
import { RadioField } from '../RadioField'

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

// Mock Headless UI RadioGroup
jest.mock('@headlessui/react', () => {
  const MockRadioGroupOption = ({ value, className, children }: any) => {
    const active = false
    const checked = false
    const classNameValue =
      typeof className === 'function'
        ? className({ active, checked })
        : className
    return (
      <div
        className={classNameValue}
        data-value={value}
        data-testid="radio-option"
      >
        {typeof children === 'function' ? children({ checked }) : children}
      </div>
    )
  }

  const MockRadioGroup = Object.assign(
    ({ value, onChange, disabled, children }: any) => (
      <div data-testid="radio-group" data-disabled={disabled}>
        <div onClick={() => !disabled && onChange(value)}>{children}</div>
      </div>
    ),
    { Option: MockRadioGroupOption }
  )

  return {
    RadioGroup: MockRadioGroup,
  }
})

describe('RadioField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'radio_field',
    type: 'radio',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Choose One',
    description: 'Select an option',
    required: false,
    choices: ['Option A', 'Option B', 'Option C'],
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
    it('renders radio group', () => {
      render(<RadioField {...defaultProps} />)

      expect(screen.getByTestId('radio-group')).toBeInTheDocument()
    })

    it('renders field label', () => {
      render(<RadioField {...defaultProps} />)

      expect(screen.getByText('Choose One (Optional)')).toBeInTheDocument()
    })

    it('renders field description', () => {
      render(<RadioField {...defaultProps} />)

      expect(screen.getByText('Select an option')).toBeInTheDocument()
    })

    it('renders all choice options', () => {
      render(<RadioField {...defaultProps} />)

      expect(screen.getByText('Option A')).toBeInTheDocument()
      expect(screen.getByText('Option B')).toBeInTheDocument()
      expect(screen.getByText('Option C')).toBeInTheDocument()
    })

    it('renders correct number of radio options', () => {
      render(<RadioField {...defaultProps} />)

      const options = screen.getAllByTestId('radio-option')
      expect(options).toHaveLength(3)
    })
  })

  describe('Empty Choices Handling', () => {
    it('shows "No choices available" when choices array is empty', () => {
      const fieldWithoutChoices = { ...defaultField, choices: [] }
      render(<RadioField {...defaultProps} field={fieldWithoutChoices} />)

      expect(screen.getByText('No choices available')).toBeInTheDocument()
      expect(screen.queryByTestId('radio-group')).not.toBeInTheDocument()
    })

    it('shows "No choices available" when choices is undefined', () => {
      const fieldWithoutChoices = { ...defaultField, choices: undefined }
      render(<RadioField {...defaultProps} field={fieldWithoutChoices} />)

      expect(screen.getByText('No choices available')).toBeInTheDocument()
    })

    it('applies correct styling to "No choices available"', () => {
      const fieldWithoutChoices = { ...defaultField, choices: [] }
      const { container } = render(
        <RadioField {...defaultProps} field={fieldWithoutChoices} />
      )

      const noChoicesText = screen.getByText('No choices available')
      expect(noChoicesText).toHaveClass(
        'text-sm',
        'text-gray-500',
        'dark:text-gray-400'
      )
    })
  })

  describe('Value Handling', () => {
    it('displays selected value', () => {
      render(<RadioField {...defaultProps} value="Option B" />)

      const radioGroup = screen.getByTestId('radio-group')
      expect(radioGroup).toBeInTheDocument()
    })

    it('handles null/undefined values gracefully', () => {
      const { rerender } = render(<RadioField {...defaultProps} value={null} />)
      expect(screen.getByTestId('radio-group')).toBeInTheDocument()

      rerender(<RadioField {...defaultProps} value={undefined} />)
      expect(screen.getByTestId('radio-group')).toBeInTheDocument()
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<RadioField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      render(<RadioField {...defaultProps} />)

      expect(screen.getByText('Choose One (Optional)')).toBeInTheDocument()
    })
  })

  describe('Readonly State', () => {
    it('disables radio group when readonly is true', () => {
      render(<RadioField {...defaultProps} readonly={true} />)

      const radioGroup = screen.getByTestId('radio-group')
      expect(radioGroup).toHaveAttribute('data-disabled', 'true')
    })

    it('enables radio group when readonly is false', () => {
      render(<RadioField {...defaultProps} readonly={false} />)

      const radioGroup = screen.getByTestId('radio-group')
      expect(radioGroup).toHaveAttribute('data-disabled', 'false')
    })
  })

  describe('Error Handling', () => {
    it('displays error message', () => {
      const errors = ['Selection required']
      render(<RadioField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Selection required')).toBeInTheDocument()
    })

    it('displays multiple errors', () => {
      const errors = ['Required field', 'Invalid selection']
      render(<RadioField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Required field')).toBeInTheDocument()
      expect(screen.getByText('Invalid selection')).toBeInTheDocument()
    })

    it('shows error icon for each error', () => {
      const errors = ['Error 1', 'Error 2']
      render(<RadioField {...defaultProps} errors={errors} />)

      const errorIcons = screen.getAllByTestId('exclamation-icon')
      expect(errorIcons).toHaveLength(2)
    })
  })

  describe('Choice Variations', () => {
    it('handles single choice', () => {
      const singleChoiceField = { ...defaultField, choices: ['Only Option'] }
      render(<RadioField {...defaultProps} field={singleChoiceField} />)

      expect(screen.getByText('Only Option')).toBeInTheDocument()
      const options = screen.getAllByTestId('radio-option')
      expect(options).toHaveLength(1)
    })

    it('handles many choices', () => {
      const manyChoicesField = {
        ...defaultField,
        choices: Array.from({ length: 10 }, (_, i) => `Option ${i + 1}`),
      }
      render(<RadioField {...defaultProps} field={manyChoicesField} />)

      const options = screen.getAllByTestId('radio-option')
      expect(options).toHaveLength(10)
    })

    it('handles choices with special characters', () => {
      const specialChoicesField = {
        ...defaultField,
        choices: ['Option A & B', 'Option <C>', 'Option "D"'],
      }
      render(<RadioField {...defaultProps} field={specialChoicesField} />)

      expect(screen.getByText('Option A & B')).toBeInTheDocument()
      expect(screen.getByText('Option <C>')).toBeInTheDocument()
      expect(screen.getByText('Option "D"')).toBeInTheDocument()
    })

    it('handles choices with unicode characters', () => {
      const unicodeChoicesField = {
        ...defaultField,
        choices: ['Wahl Ä', 'Wahl Ö', 'Wahl Ü', '中文选项', '🚀 Emoji'],
      }
      render(<RadioField {...defaultProps} field={unicodeChoicesField} />)

      expect(screen.getByText('Wahl Ä')).toBeInTheDocument()
      expect(screen.getByText('中文选项')).toBeInTheDocument()
      expect(screen.getByText('🚀 Emoji')).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('applies custom className to wrapper', () => {
      render(<RadioField {...defaultProps} className="custom-class" />)

      const wrapper = screen
        .getByTestId('radio-group')
        .closest('.field-wrapper')
      expect(wrapper).toHaveClass('custom-class')
    })

    it('applies spacing between options', () => {
      const { container } = render(<RadioField {...defaultProps} />)

      const optionsContainer = container.querySelector('.space-y-2')
      expect(optionsContainer).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('renders radio inputs with correct attributes', () => {
      const { container } = render(<RadioField {...defaultProps} />)

      const radioInputs = container.querySelectorAll('input[type="radio"]')
      expect(radioInputs.length).toBeGreaterThan(0)
    })

    it('has labels associated with radio inputs', () => {
      const { container } = render(<RadioField {...defaultProps} />)

      const labels = container.querySelectorAll('label')
      expect(labels.length).toBeGreaterThan(0)
    })
  })

  describe('Edge Cases', () => {
    it('handles empty string in choices', () => {
      const fieldWithEmptyChoice = {
        ...defaultField,
        choices: ['Option A', '', 'Option C'],
      }
      render(<RadioField {...defaultProps} field={fieldWithEmptyChoice} />)

      const options = screen.getAllByTestId('radio-option')
      expect(options).toHaveLength(3)
    })

    it('handles duplicate choices', () => {
      const fieldWithDuplicates = {
        ...defaultField,
        choices: ['Option A', 'Option A', 'Option B'],
      }
      render(<RadioField {...defaultProps} field={fieldWithDuplicates} />)

      const options = screen.getAllByTestId('radio-option')
      expect(options).toHaveLength(3)
    })

    it('handles very long choice text', () => {
      const longChoiceField = {
        ...defaultField,
        choices: ['A'.repeat(100), 'B'.repeat(100), 'C'.repeat(100)],
      }
      render(<RadioField {...defaultProps} field={longChoiceField} />)

      const options = screen.getAllByTestId('radio-option')
      expect(options).toHaveLength(3)
    })
  })
})

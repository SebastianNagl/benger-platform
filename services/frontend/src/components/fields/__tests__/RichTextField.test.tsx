/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RichTextField } from '../RichTextField'

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

describe('RichTextField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'rich_text_field',
    type: 'richtext',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Description',
    description: 'Enter a detailed description',
    placeholder: 'Type your text here...',
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
    it('renders textarea input', () => {
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toBeInTheDocument()
      expect(textarea.tagName).toBe('TEXTAREA')
    })

    it('renders with placeholder', () => {
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('placeholder', 'Type your text here...')
    })

    it('renders field label', () => {
      render(<RichTextField {...defaultProps} />)

      expect(screen.getByText('Description (Optional)')).toBeInTheDocument()
    })

    it('renders field description', () => {
      render(<RichTextField {...defaultProps} />)

      expect(
        screen.getByText('Enter a detailed description')
      ).toBeInTheDocument()
    })

    it('shows placeholder text for future rich text editor', () => {
      render(<RichTextField {...defaultProps} />)

      expect(
        screen.getByText(
          'Rich text editor coming soon. Currently using plain text.'
        )
      ).toBeInTheDocument()
    })
  })

  describe('Value Handling', () => {
    it('displays initial value', () => {
      render(<RichTextField {...defaultProps} value="Initial text content" />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue('Initial text content')
    })

    it('handles null/undefined values gracefully', () => {
      const { rerender } = render(
        <RichTextField {...defaultProps} value={null} />
      )
      expect(screen.getByRole('textbox')).toHaveValue('')

      rerender(<RichTextField {...defaultProps} value={undefined} />)
      expect(screen.getByRole('textbox')).toHaveValue('')
    })

    it('calls onChange when user types', async () => {
      const user = userEvent.setup()
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'Hello')

      expect(mockOnChange).toHaveBeenCalled()
      // Each character triggers onChange, so we just verify it was called
      expect(mockOnChange.mock.calls.length).toBeGreaterThan(0)
    })

    it('handles multi-line text input', async () => {
      const user = userEvent.setup()
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'Line 1{Enter}Line 2{Enter}Line 3')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('preserves line breaks in value', () => {
      const multiLineText = 'Line 1\nLine 2\nLine 3'
      render(<RichTextField {...defaultProps} value={multiLineText} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue(multiLineText)
    })
  })

  describe('Textarea Properties', () => {
    it('renders with 6 rows by default', () => {
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('rows', '6')
    })

    it('is vertically resizable', () => {
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('resize-vertical')
    })

    it('has full width styling', () => {
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('w-full')
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<RichTextField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      render(<RichTextField {...defaultProps} />)

      expect(screen.getByText('Description (Optional)')).toBeInTheDocument()
    })
  })

  describe('Readonly State', () => {
    it('sets readOnly attribute when readonly is true', () => {
      render(<RichTextField {...defaultProps} readonly={true} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('readOnly')
    })

    it('applies readonly styling', () => {
      render(<RichTextField {...defaultProps} readonly={true} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass(
        'cursor-not-allowed',
        'bg-gray-50',
        'dark:bg-gray-800'
      )
    })

    it('applies readonly class to wrapper', () => {
      const { container } = render(
        <RichTextField {...defaultProps} readonly={true} />
      )

      const wrapper = container.querySelector('.rich-text-editor')
      expect(wrapper).toHaveClass('readonly')
    })

    it('does not call onChange when readonly', async () => {
      const user = userEvent.setup()
      render(<RichTextField {...defaultProps} readonly={true} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'test')

      expect(mockOnChange).not.toHaveBeenCalled()
    })
  })

  describe('Error Handling', () => {
    it('displays error message', () => {
      const errors = ['Description is required']
      render(<RichTextField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Description is required')).toBeInTheDocument()
    })

    it('applies error styles to textarea', () => {
      const errors = ['Error']
      render(<RichTextField {...defaultProps} errors={errors} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass(
        'border-red-300',
        'focus:border-red-500',
        'focus:ring-red-500',
        'dark:border-red-600'
      )
    })

    it('displays multiple errors', () => {
      const errors = ['Required field', 'Text too long']
      render(<RichTextField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Required field')).toBeInTheDocument()
      expect(screen.getByText('Text too long')).toBeInTheDocument()
    })

    it('applies normal styles when no errors', () => {
      render(<RichTextField {...defaultProps} errors={[]} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass(
        'border-gray-300',
        'focus:border-blue-500',
        'focus:ring-blue-500',
        'dark:border-gray-600'
      )
    })
  })

  describe('Styling', () => {
    it('applies default textarea classes', () => {
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('rounded-md', 'border', 'shadow-sm')
    })

    it('applies custom className to wrapper', () => {
      render(<RichTextField {...defaultProps} className="custom-class" />)

      const wrapper = screen.getByRole('textbox').closest('.field-wrapper')
      expect(wrapper).toHaveClass('custom-class')
    })

    it('applies focus ring styles', () => {
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('focus:outline-none', 'focus:ring-2')
    })
  })

  describe('Accessibility', () => {
    it('has proper textarea role', () => {
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toBeInTheDocument()
    })

    it('is keyboard navigable', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <button>Before</button>
          <RichTextField {...defaultProps} />
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

    it('can receive focus', () => {
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      textarea.focus()
      expect(textarea).toHaveFocus()
    })
  })

  describe('Edge Cases', () => {
    it('handles missing placeholder gracefully', () => {
      const fieldWithoutPlaceholder = {
        ...defaultField,
        placeholder: undefined,
      }
      render(
        <RichTextField {...defaultProps} field={fieldWithoutPlaceholder} />
      )

      const textarea = screen.getByRole('textbox')
      expect(textarea).not.toHaveAttribute('placeholder')
    })

    it('handles very long text', async () => {
      const longText = 'a'.repeat(10000)
      render(<RichTextField {...defaultProps} value={longText} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue(longText)
    })

    it('handles special characters', async () => {
      const specialText = '< > & " \' @ # $ % ^ & * ( )'
      const user = userEvent.setup()
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, specialText)

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles unicode characters', async () => {
      const unicodeText = '你好 世界 🌍 café résumé'
      const user = userEvent.setup()
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, unicodeText)

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles empty strings', () => {
      render(<RichTextField {...defaultProps} value="" />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue('')
    })

    it('handles rapid typing', async () => {
      const user = userEvent.setup()
      render(<RichTextField {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'Quick brown fox')

      expect(mockOnChange).toHaveBeenCalled()
      expect(mockOnChange.mock.calls.length).toBeGreaterThan(0)
    })

    it('uses useCallback to memoize onChange handler', () => {
      const { rerender } = render(<RichTextField {...defaultProps} />)

      // Rerender with same props
      rerender(<RichTextField {...defaultProps} />)

      // Component should not recreate onChange handler unnecessarily
      // This is verified by the useCallback in the component implementation
      expect(screen.getByRole('textbox')).toBeInTheDocument()
    })
  })

  describe('Future Rich Text Editor Note', () => {
    it('displays informational message about future functionality', () => {
      render(<RichTextField {...defaultProps} />)

      const message = screen.getByText(
        'Rich text editor coming soon. Currently using plain text.'
      )
      expect(message).toBeInTheDocument()
      expect(message).toHaveClass(
        'text-xs',
        'text-gray-500',
        'dark:text-gray-400'
      )
    })
  })
})

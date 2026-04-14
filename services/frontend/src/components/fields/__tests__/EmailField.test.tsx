/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EmailField } from '../EmailField'

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

describe('EmailField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'email_field',
    type: 'email',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Email Address',
    description: 'Enter your email address',
    placeholder: 'email@example.com',
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
    it('renders email input with correct type', () => {
      render(<EmailField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('type', 'email')
      expect(input).toHaveAttribute('id', 'email_field')
      expect(input).toHaveAttribute('name', 'email_field')
    })

    it('renders with placeholder', () => {
      render(<EmailField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('placeholder', 'email@example.com')
    })

    it('renders field label', () => {
      render(<EmailField {...defaultProps} />)

      expect(screen.getByText('Email Address (Optional)')).toBeInTheDocument()
    })

    it('renders field description', () => {
      render(<EmailField {...defaultProps} />)

      expect(screen.getByText('Enter your email address')).toBeInTheDocument()
    })
  })

  describe('Value Handling', () => {
    it('displays initial value', () => {
      render(<EmailField {...defaultProps} value="test@example.com" />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveValue('test@example.com')
    })

    it('handles null/undefined values gracefully', () => {
      const { rerender } = render(<EmailField {...defaultProps} value={null} />)
      expect(screen.getByRole('textbox')).toHaveValue('')

      rerender(<EmailField {...defaultProps} value={undefined} />)
      expect(screen.getByRole('textbox')).toHaveValue('')
    })

    it('calls onChange when user types', async () => {
      const user = userEvent.setup()
      render(<EmailField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'test@')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('allows valid email format', async () => {
      const user = userEvent.setup()
      render(<EmailField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'user@example.com')

      expect(mockOnChange).toHaveBeenCalled()
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<EmailField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      render(<EmailField {...defaultProps} />)

      expect(screen.getByText('Email Address (Optional)')).toBeInTheDocument()
    })
  })

  describe('Readonly State', () => {
    it('disables input when readonly is true', () => {
      render(<EmailField {...defaultProps} readonly={true} />)

      const input = screen.getByRole('textbox')
      expect(input).toBeDisabled()
    })

    it('does not call onChange when readonly', async () => {
      const user = userEvent.setup()
      render(<EmailField {...defaultProps} readonly={true} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'test@example.com')

      expect(mockOnChange).not.toHaveBeenCalled()
    })
  })

  describe('Error Handling', () => {
    it('displays error message', () => {
      const errors = ['Invalid email format']
      render(<EmailField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Invalid email format')).toBeInTheDocument()
    })

    it('applies error styles to input', () => {
      const errors = ['Error']
      render(<EmailField {...defaultProps} errors={errors} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveClass('border-red-300', 'dark:border-red-600')
    })

    it('displays multiple errors', () => {
      const errors = ['Required field', 'Invalid format']
      render(<EmailField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Required field')).toBeInTheDocument()
      expect(screen.getByText('Invalid format')).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('applies default input classes', () => {
      render(<EmailField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveClass('block', 'w-full', 'rounded-md')
    })

    it('applies custom className to wrapper', () => {
      render(<EmailField {...defaultProps} className="custom-class" />)

      const wrapper = screen.getByRole('textbox').closest('.field-wrapper')
      expect(wrapper).toHaveClass('custom-class')
    })
  })

  describe('Email Validation Features', () => {
    it('accepts valid email with subdomain', async () => {
      const user = userEvent.setup()
      render(<EmailField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'user@mail.example.com')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('accepts email with plus sign', async () => {
      const user = userEvent.setup()
      render(<EmailField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'user+tag@example.com')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('accepts email with dots', async () => {
      const user = userEvent.setup()
      render(<EmailField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'first.last@example.com')

      expect(mockOnChange).toHaveBeenCalled()
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA attributes', () => {
      render(<EmailField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('id', 'email_field')
    })

    it('is keyboard navigable', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <button>Before</button>
          <EmailField {...defaultProps} />
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
  })

  describe('Edge Cases', () => {
    it('handles missing placeholder gracefully', () => {
      const fieldWithoutPlaceholder = {
        ...defaultField,
        placeholder: undefined,
      }
      render(<EmailField {...defaultProps} field={fieldWithoutPlaceholder} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('placeholder', 'email@example.com')
    })

    it('handles extremely long email addresses', async () => {
      const user = userEvent.setup()
      render(<EmailField {...defaultProps} />)

      const longEmail = `${'a'.repeat(50)}@${'example.'.repeat(10)}com`
      const input = screen.getByRole('textbox')

      await user.type(input, longEmail)

      expect(mockOnChange).toHaveBeenCalled()
    })
  })
})

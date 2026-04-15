/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { UrlField } from '../UrlField'

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

describe('UrlField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'url_field',
    type: 'url',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Website URL',
    description: 'Enter a valid URL',
    placeholder: 'https://example.com',
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
    it('renders url input with correct type', () => {
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('type', 'url')
      expect(input).toHaveAttribute('id', 'url_field')
      expect(input).toHaveAttribute('name', 'url_field')
    })

    it('renders with placeholder', () => {
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('placeholder', 'https://example.com')
    })

    it('renders field label', () => {
      render(<UrlField {...defaultProps} />)

      expect(screen.getByText('Website URL (Optional)')).toBeInTheDocument()
    })

    it('renders field description', () => {
      render(<UrlField {...defaultProps} />)

      expect(screen.getByText('Enter a valid URL')).toBeInTheDocument()
    })
  })

  describe('Value Handling', () => {
    it('displays initial value', () => {
      render(<UrlField {...defaultProps} value="https://example.com" />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveValue('https://example.com')
    })

    it('handles null/undefined values gracefully', () => {
      const { rerender } = render(<UrlField {...defaultProps} value={null} />)
      expect(screen.getByRole('textbox')).toHaveValue('')

      rerender(<UrlField {...defaultProps} value={undefined} />)
      expect(screen.getByRole('textbox')).toHaveValue('')
    })

    it('calls onChange when user types', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'https://')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('allows valid URL format', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'https://www.example.com')

      expect(mockOnChange).toHaveBeenCalled()
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<UrlField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      render(<UrlField {...defaultProps} />)

      expect(screen.getByText('Website URL (Optional)')).toBeInTheDocument()
    })
  })

  describe('Readonly State', () => {
    it('disables input when readonly is true', () => {
      render(<UrlField {...defaultProps} readonly={true} />)

      const input = screen.getByRole('textbox')
      expect(input).toBeDisabled()
    })

    it('does not call onChange when readonly', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} readonly={true} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'https://example.com')

      expect(mockOnChange).not.toHaveBeenCalled()
    })
  })

  describe('Error Handling', () => {
    it('displays error message', () => {
      const errors = ['Invalid URL format']
      render(<UrlField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Invalid URL format')).toBeInTheDocument()
    })

    it('applies error styles to input', () => {
      const errors = ['Error']
      render(<UrlField {...defaultProps} errors={errors} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveClass('border-red-300', 'dark:border-red-600')
    })

    it('displays multiple errors', () => {
      const errors = ['Required field', 'Invalid format']
      render(<UrlField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Required field')).toBeInTheDocument()
      expect(screen.getByText('Invalid format')).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('applies default input classes', () => {
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveClass('block', 'w-full', 'rounded-md')
    })

    it('applies custom className to wrapper', () => {
      render(<UrlField {...defaultProps} className="custom-class" />)

      const wrapper = screen.getByRole('textbox').closest('.field-wrapper')
      expect(wrapper).toHaveClass('custom-class')
    })
  })

  describe('URL Validation Features', () => {
    it('accepts HTTP URLs', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'http://example.com')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('accepts HTTPS URLs', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'https://example.com')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('accepts URLs with subdomains', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'https://www.subdomain.example.com')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('accepts URLs with paths', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'https://example.com/path/to/page')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('accepts URLs with query parameters', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'https://example.com?param=value&other=123')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('accepts URLs with hash fragments', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'https://example.com/page#section')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('accepts URLs with ports', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'https://example.com:8080')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('accepts localhost URLs', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'http://localhost:3000')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('accepts IP address URLs', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'http://192.168.1.1')

      expect(mockOnChange).toHaveBeenCalled()
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA attributes', () => {
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('id', 'url_field')
    })

    it('is keyboard navigable', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <button>Before</button>
          <UrlField {...defaultProps} />
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
      render(<UrlField {...defaultProps} field={fieldWithoutPlaceholder} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('placeholder', 'https://example.com')
    })

    it('handles extremely long URLs', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const longUrl = `https://example.com/${'path/'.repeat(100)}`
      const input = screen.getByRole('textbox')

      await user.type(input, longUrl)

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles URLs with special characters', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'https://example.com/path?q=test%20value&x=1')

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('handles international domain names', async () => {
      const user = userEvent.setup()
      render(<UrlField {...defaultProps} />)

      const input = screen.getByRole('textbox')
      await user.type(input, 'https://münchen.de')

      expect(mockOnChange).toHaveBeenCalled()
    })
  })
})

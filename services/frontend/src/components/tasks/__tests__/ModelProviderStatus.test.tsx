import { render, screen } from '@testing-library/react'
import { ModelProviderStatus } from '../ModelProviderStatus'

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

// Mock Next.js Link component
jest.mock('next/link', () => {
  return function MockLink({ children, href, className, ...props }: any) {
    return (
      <a href={href} className={className} {...props}>
        {children}
      </a>
    )
  }
})

describe('ModelProviderStatus', () => {
  const defaultProps = {
    provider: 'OpenAI',
    hasApiKey: false,
    modelCount: 5,
  }

  describe('basic rendering', () => {
    it('renders component container', () => {
      const { container } = render(<ModelProviderStatus {...defaultProps} />)

      const statusContainer = container.querySelector('.rounded-md.p-3')
      expect(statusContainer).toBeInTheDocument()
    })

    it('displays provider name in context', () => {
      render(<ModelProviderStatus {...defaultProps} />)

      expect(
        screen.getByText('Configure OpenAI API key to access models')
      ).toBeInTheDocument()
    })

    it('applies custom className when provided', () => {
      const { container } = render(
        <ModelProviderStatus {...defaultProps} className="custom-class" />
      )

      const statusContainer = container.querySelector('.custom-class')
      expect(statusContainer).toBeInTheDocument()
    })

    it('applies empty className by default', () => {
      const { container } = render(<ModelProviderStatus {...defaultProps} />)

      const statusContainer = container.querySelector('.rounded-md.p-3')
      expect(statusContainer).toBeInTheDocument()
    })
  })

  describe('configured state (hasApiKey: true)', () => {
    const configuredProps = {
      ...defaultProps,
      hasApiKey: true,
    }

    it('renders success state styling', () => {
      const { container } = render(<ModelProviderStatus {...configuredProps} />)

      const successContainer = container.querySelector('.bg-emerald-50')
      expect(successContainer).toBeInTheDocument()
      expect(successContainer).toHaveClass(
        'border-emerald-200',
        'dark:bg-emerald-950/50',
        'dark:border-emerald-800'
      )
    })

    it('displays green status indicator', () => {
      const { container } = render(<ModelProviderStatus {...configuredProps} />)

      const statusDot = container.querySelector(
        '.h-2.w-2.bg-emerald-500.rounded-full'
      )
      expect(statusDot).toBeInTheDocument()
    })

    it('shows provider name with success styling', () => {
      render(<ModelProviderStatus {...configuredProps} />)

      const providerName = screen.getByText('OpenAI')
      expect(providerName).toHaveClass(
        'text-emerald-700',
        'dark:text-emerald-400',
        'font-medium'
      )
    })

    it('displays model count with singular form', () => {
      render(<ModelProviderStatus {...configuredProps} modelCount={1} />)

      expect(screen.getByText('1 model available')).toBeInTheDocument()
    })

    it('displays model count with plural form', () => {
      render(<ModelProviderStatus {...configuredProps} modelCount={5} />)

      expect(screen.getByText('5 models available')).toBeInTheDocument()
    })

    it('displays model count with zero models', () => {
      render(<ModelProviderStatus {...configuredProps} modelCount={0} />)

      expect(screen.getByText('0 models available')).toBeInTheDocument()
    })

    it('applies correct layout structure', () => {
      const { container } = render(<ModelProviderStatus {...configuredProps} />)

      const flexContainer = container.querySelector(
        '.flex.items-center.space-x-2'
      )
      expect(flexContainer).toBeInTheDocument()
    })

    it('shows correct text styling for model count', () => {
      render(<ModelProviderStatus {...configuredProps} />)

      const modelCount = screen.getByText('5 models available')
      expect(modelCount).toHaveClass(
        'text-xs',
        'text-emerald-600',
        'dark:text-emerald-500'
      )
    })

    it('does not show configure link when API key is present', () => {
      render(<ModelProviderStatus {...configuredProps} />)

      expect(screen.queryByText('Configure →')).not.toBeInTheDocument()
    })
  })

  describe('unconfigured state (hasApiKey: false)', () => {
    it('renders warning state styling', () => {
      const { container } = render(<ModelProviderStatus {...defaultProps} />)

      const warningContainer = container.querySelector('.bg-amber-50')
      expect(warningContainer).toBeInTheDocument()
      expect(warningContainer).toHaveClass(
        'border-amber-200',
        'dark:bg-amber-950/50',
        'dark:border-amber-800'
      )
    })

    it('displays warning icon', () => {
      const { container } = render(<ModelProviderStatus {...defaultProps} />)

      const warningIcon = container.querySelector('svg.h-4.w-4.text-amber-600')
      expect(warningIcon).toBeInTheDocument()
      expect(warningIcon).toHaveClass('dark:text-amber-500')
    })

    it('renders warning icon with correct path', () => {
      const { container } = render(<ModelProviderStatus {...defaultProps} />)

      const warningPath = container.querySelector('path[d*="M12 9v2m0 4h.01"]')
      expect(warningPath).toBeInTheDocument()
    })

    it('shows configuration message', () => {
      render(<ModelProviderStatus {...defaultProps} />)

      expect(
        screen.getByText('Configure OpenAI API key to access models')
      ).toBeInTheDocument()
    })

    it('displays configuration message with correct styling', () => {
      render(<ModelProviderStatus {...defaultProps} />)

      const message = screen.getByText(
        'Configure OpenAI API key to access models'
      )
      expect(message).toHaveClass(
        'text-sm',
        'text-amber-700',
        'dark:text-amber-400'
      )
    })

    it('renders configure link', () => {
      render(<ModelProviderStatus {...defaultProps} />)

      const configureLink = screen.getByText('Configure →')
      expect(configureLink).toBeInTheDocument()
    })

    it('configure link points to profile page', () => {
      render(<ModelProviderStatus {...defaultProps} />)

      const configureLink = screen.getByText('Configure →')
      expect(configureLink.closest('a')).toHaveAttribute('href', '/profile')
    })

    it('configure link has correct styling', () => {
      render(<ModelProviderStatus {...defaultProps} />)

      const configureLink = screen.getByText('Configure →')
      expect(configureLink).toHaveClass(
        'text-sm',
        'text-amber-600',
        'dark:text-amber-400',
        'hover:text-amber-800',
        'dark:hover:text-amber-300',
        'font-medium',
        'transition-colors'
      )
    })

    it('applies correct layout structure for unconfigured state', () => {
      const { container } = render(<ModelProviderStatus {...defaultProps} />)

      const flexContainer = container.querySelector(
        '.flex.items-center.justify-between'
      )
      expect(flexContainer).toBeInTheDocument()
    })

    it('groups icon and message correctly', () => {
      const { container } = render(<ModelProviderStatus {...defaultProps} />)

      const iconMessageGroup = container.querySelector(
        '.flex.items-center.space-x-2'
      )
      expect(iconMessageGroup).toBeInTheDocument()
    })
  })

  describe('different providers', () => {
    it('handles Anthropic provider', () => {
      render(<ModelProviderStatus {...defaultProps} provider="Anthropic" />)

      expect(
        screen.getByText('Configure Anthropic API key to access models')
      ).toBeInTheDocument()
    })

    it('handles Google provider', () => {
      render(
        <ModelProviderStatus
          {...defaultProps}
          provider="Google"
          hasApiKey={true}
        />
      )

      expect(screen.getByText('Google')).toBeInTheDocument()
    })

    it('handles custom provider names', () => {
      render(
        <ModelProviderStatus {...defaultProps} provider="Custom LLM Service" />
      )

      expect(
        screen.getByText(
          'Configure Custom LLM Service API key to access models'
        )
      ).toBeInTheDocument()
    })

    it('handles empty provider name', () => {
      render(<ModelProviderStatus {...defaultProps} provider="" />)

      expect(
        screen.getByText(/Configure.*API key to access models/)
      ).toBeInTheDocument()
    })
  })

  describe('model count variations', () => {
    it('handles large model counts', () => {
      render(
        <ModelProviderStatus
          {...defaultProps}
          hasApiKey={true}
          modelCount={100}
        />
      )

      expect(screen.getByText('100 models available')).toBeInTheDocument()
    })

    it('handles single model correctly', () => {
      render(
        <ModelProviderStatus
          {...defaultProps}
          hasApiKey={true}
          modelCount={1}
        />
      )

      expect(screen.getByText('1 model available')).toBeInTheDocument()
      expect(screen.queryByText('1 models available')).not.toBeInTheDocument()
    })

    it('handles two models correctly', () => {
      render(
        <ModelProviderStatus
          {...defaultProps}
          hasApiKey={true}
          modelCount={2}
        />
      )

      expect(screen.getByText('2 models available')).toBeInTheDocument()
    })

    it('handles negative model count', () => {
      render(
        <ModelProviderStatus
          {...defaultProps}
          hasApiKey={true}
          modelCount={-1}
        />
      )

      expect(screen.getByText('-1 models available')).toBeInTheDocument()
    })
  })

  describe('dark mode support', () => {
    it('includes dark mode classes for configured state', () => {
      const { container } = render(
        <ModelProviderStatus {...defaultProps} hasApiKey={true} />
      )

      const successContainer = container.querySelector(
        '.dark\\:bg-emerald-950\\/50'
      )
      expect(successContainer).toBeInTheDocument()
      expect(successContainer).toHaveClass('dark:border-emerald-800')
    })

    it('includes dark mode classes for unconfigured state', () => {
      const { container } = render(<ModelProviderStatus {...defaultProps} />)

      const warningContainer = container.querySelector(
        '.dark\\:bg-amber-950\\/50'
      )
      expect(warningContainer).toBeInTheDocument()
      expect(warningContainer).toHaveClass('dark:border-amber-800')
    })

    it('applies dark mode text colors for success state', () => {
      render(<ModelProviderStatus {...defaultProps} hasApiKey={true} />)

      const providerName = screen.getByText('OpenAI')
      expect(providerName).toHaveClass('dark:text-emerald-400')

      const modelCount = screen.getByText('5 models available')
      expect(modelCount).toHaveClass('dark:text-emerald-500')
    })

    it('applies dark mode text colors for warning state', () => {
      render(<ModelProviderStatus {...defaultProps} />)

      const message = screen.getByText(
        'Configure OpenAI API key to access models'
      )
      expect(message).toHaveClass('dark:text-amber-400')

      const link = screen.getByText('Configure →')
      expect(link).toHaveClass(
        'dark:text-amber-400',
        'dark:hover:text-amber-300'
      )
    })

    it('applies dark mode icon colors', () => {
      const { container } = render(<ModelProviderStatus {...defaultProps} />)

      const icon = container.querySelector('svg')
      expect(icon).toHaveClass('dark:text-amber-500')
    })
  })

  describe('accessibility', () => {
    it('provides semantic link structure', () => {
      render(<ModelProviderStatus {...defaultProps} />)

      const link = screen.getByRole('link', { name: 'Configure →' })
      expect(link).toBeInTheDocument()
      expect(link).toHaveAttribute('href', '/profile')
    })

    it('maintains readable text contrast', () => {
      render(<ModelProviderStatus {...defaultProps} />)

      const message = screen.getByText(
        'Configure OpenAI API key to access models'
      )
      expect(message).toBeInTheDocument()
    })

    it('provides clear visual hierarchy in success state', () => {
      render(<ModelProviderStatus {...defaultProps} hasApiKey={true} />)

      const providerName = screen.getByText('OpenAI')
      const modelCount = screen.getByText('5 models available')

      expect(providerName).toHaveClass('font-medium')
      expect(modelCount).toHaveClass('text-xs')
    })

    it('includes proper SVG accessibility attributes', () => {
      const { container } = render(<ModelProviderStatus {...defaultProps} />)

      const svg = container.querySelector('svg')
      expect(svg).toHaveAttribute('fill', 'none')
      expect(svg).toHaveAttribute('stroke', 'currentColor')
      expect(svg).toHaveAttribute('viewBox', '0 0 24 24')
    })
  })

  describe('responsive design', () => {
    it('maintains layout on different screen sizes', () => {
      const { container } = render(<ModelProviderStatus {...defaultProps} />)

      const flexContainer = container.querySelector(
        '.flex.items-center.justify-between'
      )
      expect(flexContainer).toBeInTheDocument()
    })

    it('keeps text readable at different sizes', () => {
      render(<ModelProviderStatus {...defaultProps} />)

      const message = screen.getByText(
        'Configure OpenAI API key to access models'
      )
      expect(message).toHaveClass('text-sm')
    })

    it('maintains consistent spacing', () => {
      const { container } = render(
        <ModelProviderStatus {...defaultProps} hasApiKey={true} />
      )

      const spacedContainer = container.querySelector('.space-x-2')
      expect(spacedContainer).toBeInTheDocument()
    })
  })

  describe('layout integration', () => {
    it('fits well in container layouts', () => {
      const { container } = render(
        <div className="space-y-4">
          <ModelProviderStatus {...defaultProps} />
          <ModelProviderStatus {...defaultProps} hasApiKey={true} />
        </div>
      )

      const statusComponents = container.querySelectorAll('.rounded-md.p-3')
      expect(statusComponents).toHaveLength(2)
    })

    it('handles custom className composition', () => {
      const { container } = render(
        <ModelProviderStatus {...defaultProps} className="mb-4 shadow-sm" />
      )

      const statusContainer = container.querySelector('.mb-4.shadow-sm')
      expect(statusContainer).toBeInTheDocument()
      expect(statusContainer).toHaveClass('rounded-md', 'p-3')
    })
  })

  describe('edge cases', () => {
    it('handles very long provider names', () => {
      const longProvider = 'Very Long Provider Name That Might Wrap'
      render(<ModelProviderStatus {...defaultProps} provider={longProvider} />)

      expect(
        screen.getByText(`Configure ${longProvider} API key to access models`)
      ).toBeInTheDocument()
    })

    it('handles special characters in provider name', () => {
      render(
        <ModelProviderStatus {...defaultProps} provider="Provider-Name_123" />
      )

      expect(
        screen.getByText('Configure Provider-Name_123 API key to access models')
      ).toBeInTheDocument()
    })

    it('maintains consistent styling regardless of content length', () => {
      const { container } = render(
        <ModelProviderStatus {...defaultProps} provider="AI" />
      )

      const statusContainer = container.querySelector('.rounded-md.p-3')
      expect(statusContainer).toBeInTheDocument()
    })

    it('handles state transitions gracefully', () => {
      const { rerender } = render(
        <ModelProviderStatus {...defaultProps} hasApiKey={false} />
      )

      expect(
        screen.getByText('Configure OpenAI API key to access models')
      ).toBeInTheDocument()

      rerender(<ModelProviderStatus {...defaultProps} hasApiKey={true} />)

      expect(screen.getByText('5 models available')).toBeInTheDocument()
      expect(
        screen.queryByText('Configure OpenAI API key to access models')
      ).not.toBeInTheDocument()
    })
  })
})

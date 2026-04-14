/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import { ModelProviderStatus } from '../tasks/ModelProviderStatus'

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../locales/en/common.json')
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
  return function MockLink({ href, children, ...props }: any) {
    return (
      <a href={href} {...props}>
        {children}
      </a>
    )
  }
})

describe('ModelProviderStatus', () => {
  describe('when user has API key', () => {
    it('renders success state with model count', () => {
      render(
        <ModelProviderStatus
          provider="OpenAI"
          hasApiKey={true}
          modelCount={3}
        />
      )

      expect(screen.getByText('OpenAI')).toBeInTheDocument()
      expect(screen.getByText('3 models available')).toBeInTheDocument()
      expect(screen.queryByText('Configure')).not.toBeInTheDocument()
    })

    it('handles singular model count', () => {
      render(
        <ModelProviderStatus
          provider="Anthropic"
          hasApiKey={true}
          modelCount={1}
        />
      )

      expect(screen.getByText('1 model available')).toBeInTheDocument()
    })

    it('renders with green success styling', () => {
      const { container } = render(
        <ModelProviderStatus
          provider="Google"
          hasApiKey={true}
          modelCount={2}
        />
      )

      expect(container.firstChild).toHaveClass('bg-emerald-50')
    })
  })

  describe('when user lacks API key', () => {
    it('renders warning state with configuration link', () => {
      render(
        <ModelProviderStatus
          provider="OpenAI"
          hasApiKey={false}
          modelCount={0}
        />
      )

      expect(
        screen.getByText('Configure OpenAI API key to access models')
      ).toBeInTheDocument()
      expect(
        screen.getByRole('link', { name: 'Configure →' })
      ).toBeInTheDocument()
      expect(screen.getByRole('link')).toHaveAttribute('href', '/profile')
    })

    it('renders with amber warning styling', () => {
      const { container } = render(
        <ModelProviderStatus
          provider="Anthropic"
          hasApiKey={false}
          modelCount={0}
        />
      )

      expect(container.firstChild).toHaveClass('bg-amber-50')
    })

    it('displays warning icon', () => {
      const { container } = render(
        <ModelProviderStatus
          provider="DeepInfra"
          hasApiKey={false}
          modelCount={0}
        />
      )

      const svg = container.querySelector('svg')
      expect(svg).toBeInTheDocument()
      expect(svg).toHaveClass('h-4', 'w-4', 'text-amber-600')
    })
  })

  it('applies custom className', () => {
    const { container } = render(
      <ModelProviderStatus
        provider="Test"
        hasApiKey={true}
        modelCount={1}
        className="custom-class"
      />
    )

    expect(container.firstChild).toHaveClass('custom-class')
  })

  it('renders accessible content', () => {
    render(
      <ModelProviderStatus provider="OpenAI" hasApiKey={false} modelCount={0} />
    )

    // Link should be accessible
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/profile')
    expect(link).toHaveClass('hover:text-amber-800')
  })
})

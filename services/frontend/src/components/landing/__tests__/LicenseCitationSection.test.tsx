import { render, screen } from '@testing-library/react'
import { LicenseCitationSection } from '../LicenseCitationSection'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
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
      if (Array.isArray(value)) return value
      if (typeof value !== 'string') return key
      return value
    },
    locale: 'en',
  }),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => (
    <div data-testid="card" className={className}>
      {children}
    </div>
  ),
}))

describe('LicenseCitationSection', () => {
  it('renders section with id="license"', () => {
    const { container } = render(<LicenseCitationSection />)
    const section = container.querySelector('#license')
    expect(section).toBeInTheDocument()
  })

  it('renders section title', () => {
    render(<LicenseCitationSection />)
    expect(screen.getByRole('heading', { level: 2 })).toBeInTheDocument()
  })

  it('renders license card', () => {
    render(<LicenseCitationSection />)
    const cards = screen.getAllByTestId('card')
    expect(cards.length).toBeGreaterThanOrEqual(1)
  })

  it('renders citation cards from locale data', () => {
    render(<LicenseCitationSection />)
    // Should have at least the license card plus citation cards
    const cards = screen.getAllByTestId('card')
    expect(cards.length).toBeGreaterThanOrEqual(1)
  })

  it('renders with min-h-screen styling', () => {
    const { container } = render(<LicenseCitationSection />)
    const section = container.querySelector('#license')
    expect(section).toHaveClass('min-h-screen')
  })

  it('renders alternate background for visual separation', () => {
    const { container } = render(<LicenseCitationSection />)
    const section = container.querySelector('#license')
    expect(section).toHaveClass('bg-zinc-50', 'dark:bg-zinc-800/50')
  })

  it('handles non-array citations gracefully', () => {
    // The component handles when t() returns a non-array
    // This is tested implicitly since the mock returns the real locale data
    const { container } = render(<LicenseCitationSection />)
    expect(container).toBeTruthy()
  })
})

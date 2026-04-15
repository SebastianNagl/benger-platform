import { render, screen } from '@testing-library/react'
import { NewsSection } from '../NewsSection'

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
      if (Array.isArray(value)) return value
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

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => (
    <div data-testid="card" className={className}>
      {children}
    </div>
  ),
}))

jest.mock('@/components/shared/Badge', () => ({
  Badge: ({ children, variant }: any) => (
    <span data-testid="badge" data-variant={variant}>
      {children}
    </span>
  ),
}))


describe('NewsSection', () => {
  beforeEach(() => {
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  describe('rendering', () => {
    it('renders section with id="news"', () => {
      const { container } = render(<NewsSection />)
      const section = container.querySelector('#news')
      expect(section).toBeInTheDocument()
    })

    it('renders section title and subtitle', () => {
      render(<NewsSection />)
      expect(screen.getByText('Latest News & Publications')).toBeInTheDocument()
      expect(
        screen.getByText(/Stay up to date with our latest research/)
      ).toBeInTheDocument()
    })

    it('renders section with min-h-screen', () => {
      const { container } = render(<NewsSection />)
      const section = container.querySelector('#news')
      expect(section).toHaveClass('min-h-screen')
    })

    it('renders alternate background for visual separation', () => {
      const { container } = render(<NewsSection />)
      const section = container.querySelector('#news')
      expect(section).toHaveClass('bg-zinc-50', 'dark:bg-zinc-800/50')
    })
  })

  describe('cards', () => {
    it('renders correct number of cards', () => {
      render(<NewsSection />)
      const cards = screen.getAllByTestId('card')
      expect(cards).toHaveLength(3)
    })

    it('renders card titles', () => {
      render(<NewsSection />)
      expect(screen.getByText('BenGER Benchathon 2026')).toBeInTheDocument()
      expect(
        screen.getByText('BenGER Platform Update and Roadmap')
      ).toBeInTheDocument()
      expect(
        screen.getByText(/First glimpse into BenGER/)
      ).toBeInTheDocument()
    })

    it('renders dates on cards', () => {
      render(<NewsSection />)
      expect(screen.getByText('2026-02-25')).toBeInTheDocument()
      expect(screen.getByText('2026-01-25')).toBeInTheDocument()
    })

    it('renders read more text on cards', () => {
      render(<NewsSection />)
      // Read more text appears on all cards
      const readMoreTexts = screen.getAllByText(/Read more/)
      expect(readMoreTexts.length).toBeGreaterThan(0)
    })
  })

  describe('badges', () => {
    it('renders badges for each card', () => {
      render(<NewsSection />)
      const badges = screen.getAllByTestId('badge')
      expect(badges).toHaveLength(3)
    })

    it('uses correct variant for news items', () => {
      render(<NewsSection />)
      const badges = screen.getAllByTestId('badge')
      const newsBadges = badges.filter(
        (b) => b.getAttribute('data-variant') === 'secondary'
      )
      expect(newsBadges).toHaveLength(2) // 2 news items
    })

    it('uses correct variant for publication items', () => {
      render(<NewsSection />)
      const badges = screen.getAllByTestId('badge')
      const pubBadges = badges.filter(
        (b) => b.getAttribute('data-variant') === 'default'
      )
      expect(pubBadges).toHaveLength(1) // 1 publication
    })
  })

  describe('accessibility', () => {
    it('uses proper heading hierarchy', () => {
      render(<NewsSection />)
      const heading = screen.getByRole('heading', { level: 2 })
      expect(heading).toHaveTextContent('Latest News & Publications')
    })
  })

  describe('internationalization', () => {
    it('renders translated section text', () => {
      render(<NewsSection />)
      expect(screen.getByText('Latest News & Publications')).toBeInTheDocument()
      expect(screen.getByText(/Stay up to date with our latest research/)).toBeInTheDocument()
    })
  })

  describe('items from locale', () => {
    it('renders all items from the locale file', () => {
      render(<NewsSection />)
      const cards = screen.getAllByTestId('card')
      expect(cards.length).toBeGreaterThan(0)
    })
  })

  describe('link behavior', () => {
    it('wraps items with url in an anchor tag', () => {
      render(<NewsSection />)
      // All items from locale have URLs, so they should be wrapped in <a> tags
      const links = screen.getAllByRole('link')
      expect(links.length).toBeGreaterThan(0)
      links.forEach((link) => {
        expect(link).toHaveAttribute('target', '_blank')
        expect(link).toHaveAttribute('rel', 'noopener noreferrer')
      })
    })

    it('adds hover shadow class to cards with url', () => {
      render(<NewsSection />)
      const cards = screen.getAllByTestId('card')
      // Cards with url get the hover:shadow-lg class
      cards.forEach((card) => {
        expect(card.className).toContain('transition-shadow')
        expect(card.className).toContain('hover:shadow-lg')
      })
    })
  })

  describe('items without url', () => {
    it('renders item without url as plain card (no link wrapper)', () => {
      // Override the useI18n mock for this test only
      const i18nModule = require('@/contexts/I18nContext')
      const originalUseI18n = i18nModule.useI18n
      i18nModule.useI18n = () => ({
        t: (key: string) => {
          if (key === 'landing.news.items') {
            return [
              { title: 'No Link Item', description: 'desc', date: '2026-01-01', type: 'news' },
            ]
          }
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
          return typeof value === 'string' ? value : key
        },
        locale: 'en',
      })

      render(<NewsSection />)
      expect(screen.getByText('No Link Item')).toBeInTheDocument()
      // Should not be wrapped in a link
      expect(screen.queryAllByRole('link')).toHaveLength(0)
      // Card should NOT have hover:shadow-lg since no URL
      const card = screen.getByTestId('card')
      expect(card.className).not.toContain('hover:shadow-lg')

      // Restore
      i18nModule.useI18n = originalUseI18n
    })
  })
})

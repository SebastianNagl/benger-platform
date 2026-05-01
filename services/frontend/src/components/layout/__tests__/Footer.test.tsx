import { render, screen } from '@testing-library/react'
import { Footer } from '../Footer'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = {
        layout: {
          footer: {
            imprint: 'Imprint',
            dataProtection: 'Privacy Policy',
            followNotion: 'Follow us on Notion',
            followGithub: 'Follow us on GitHub',
            allRightsReserved: 'All rights reserved.',
          },
        },
      }
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

// Mock Next.js components
jest.mock('next/link', () => {
  function Link({ href, className, children, tabIndex, ...props }: any) {
    return (
      <a href={href} className={className} tabIndex={tabIndex} {...props}>
        {children}
      </a>
    )
  }
  return Link
})

describe('Footer', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Mock Date.getFullYear to ensure consistent test results
    jest.spyOn(Date.prototype, 'getFullYear').mockReturnValue(2024)
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('basic rendering', () => {
    it('renders footer with correct structure', () => {
      render(<Footer />)

      const footer = screen.getByRole('contentinfo')
      expect(footer).toBeInTheDocument()
      expect(footer).toHaveClass(
        'w-full',
        'px-4',
        'sm:px-6',
        'lg:px-8',
        'pb-16'
      )
    })

    it('renders legal links', () => {
      render(<Footer />)

      expect(screen.getByRole('link', { name: /imprint/i })).toHaveAttribute(
        'href',
        '/about/imprint'
      )
      expect(
        screen.getByRole('link', { name: /privacy policy/i })
      ).toHaveAttribute('href', '/about/data-protection')
    })

    it('renders copyright notice with current year', () => {
      render(<Footer />)

      expect(screen.getByText(/© Copyright/)).toBeInTheDocument()
      expect(screen.getByText(/2024/)).toBeInTheDocument()
      expect(screen.getByText(/All rights reserved/)).toBeInTheDocument()

      const authorLink = screen.getByRole('link', { name: 'pschOrr95' })
      expect(authorLink).toHaveAttribute('href', 'https://legalplusplus.net')
    })

    it('renders social media links', () => {
      render(<Footer />)

      const githubLink = screen.getByRole('link', {
        name: /follow us on github/i,
      })
      expect(githubLink).toHaveAttribute(
        'href',
        'https://github.com/SebastianNagl/benger-platform'
      )
    })
  })

  describe('social media icons', () => {
    it('renders social media icons with correct SVG structure', () => {
      const { container } = render(<Footer />)

      const socialLinks = container.querySelectorAll('a.group')
      expect(socialLinks).toHaveLength(1) // GitHub only

      socialLinks.forEach((link) => {
        const icon = link.querySelector('svg[aria-hidden="true"]')
        expect(icon).not.toBeNull()
        expect(icon).toHaveClass('h-5', 'w-5', 'fill-zinc-700')
        expect(icon).toHaveClass(
          'transition',
          'group-hover:fill-zinc-900',
          'dark:group-hover:fill-zinc-500'
        )
      })
    })

    it('provides screen reader text for social links', () => {
      render(<Footer />)

      const githubSr = screen.getByText('Follow us on GitHub', {
        selector: '.sr-only',
      })
      expect(githubSr).toBeInTheDocument()
    })

    it('applies hover effects to social links', () => {
      const { container } = render(<Footer />)

      const socialLinks = container.querySelectorAll('a.group')
      expect(socialLinks).toHaveLength(1)

      socialLinks.forEach((link) => {
        expect(link).toHaveClass('group')
      })
    })
  })

  describe('responsive design', () => {
    it('applies responsive padding classes', () => {
      render(<Footer />)

      const footer = screen.getByRole('contentinfo')
      expect(footer).toHaveClass('px-4', 'sm:px-6', 'lg:px-8')
    })

    it('applies responsive max-width classes', () => {
      const { container } = render(<Footer />)

      const innerContainer = container.querySelector('.mx-auto')
      expect(innerContainer).toHaveClass(
        'mx-auto',
        'max-w-2xl',
        '3xl:max-w-5xl',
        '4xl:max-w-6xl',
        '5xl:max-w-7xl',
        'lg:max-w-5xl'
      )
    })

    it('applies responsive flex layouts for small print section', () => {
      const { container } = render(<Footer />)

      const smallPrintContainer = container.querySelector(
        '.flex.flex-col.items-center.justify-between'
      )
      expect(smallPrintContainer).toHaveClass('sm:flex-row')

      const linksContainer = container.querySelector(
        '.flex.flex-col.items-center.gap-3'
      )
      expect(linksContainer).toHaveClass(
        'sm:flex-row',
        'sm:items-center',
        'sm:gap-6'
      )
    })

    it('applies responsive gap classes', () => {
      const { container } = render(<Footer />)

      const mainContainer = container.querySelector('.space-y-10')
      expect(mainContainer).toBeInTheDocument()

      const smallPrintContainer = container.querySelector('.gap-5')
      expect(smallPrintContainer).toBeInTheDocument()
    })
  })

  describe('styling and layout', () => {
    it('applies proper border styling to small print section', () => {
      const { container } = render(<Footer />)

      const smallPrintSection = container.querySelector('.border-t')
      expect(smallPrintSection).toHaveClass(
        'border-t',
        'border-zinc-900/5',
        'dark:border-white/5',
        'pt-8'
      )
    })

    it('applies correct text colors and hover states', () => {
      render(<Footer />)

      const legalLinks = [
        screen.getByRole('link', { name: /imprint/i }),
        screen.getByRole('link', { name: /privacy policy/i }),
      ]

      legalLinks.forEach((link) => {
        expect(link).toHaveClass(
          'text-zinc-600',
          'hover:text-zinc-900',
          'dark:text-zinc-400',
          'dark:hover:text-zinc-300'
        )
      })
    })

    it('applies correct typography classes', () => {
      render(<Footer />)

      const copyrightText = screen.getByText(/© Copyright/)
      expect(copyrightText).toHaveClass(
        'text-xs',
        'text-zinc-600',
        'dark:text-zinc-400'
      )

      const authorLink = screen.getByRole('link', { name: 'pschOrr95' })
      expect(authorLink).toHaveClass(
        'font-bold',
        'hover:text-zinc-900',
        'dark:hover:text-zinc-300'
      )
    })
  })

  describe('accessibility', () => {
    it('provides proper footer role', () => {
      render(<Footer />)

      expect(screen.getByRole('contentinfo')).toBeInTheDocument()
    })

    it('provides screen reader only text for social links', () => {
      render(<Footer />)

      const srOnlyTexts = screen.getAllByText(/follow us on/i, {
        selector: '.sr-only',
      })
      expect(srOnlyTexts).toHaveLength(1)
    })

    it('marks decorative icons as aria-hidden', () => {
      const { container } = render(<Footer />)

      const icons = container.querySelectorAll('svg[aria-hidden="true"]')
      expect(icons.length).toBeGreaterThan(0)
    })
  })

  describe('dark mode support', () => {
    it('includes dark mode classes for all styled elements', () => {
      const { container } = render(<Footer />)

      // Check border
      const borderElement = container.querySelector('.dark\\:border-white\\/5')
      expect(borderElement).toBeInTheDocument()

      // Check text colors
      const darkTextElements = container.querySelectorAll(
        '.dark\\:text-zinc-400'
      )
      expect(darkTextElements.length).toBeGreaterThan(0)

      // Check hover states
      const darkHoverElements = container.querySelectorAll(
        '.dark\\:hover\\:text-zinc-300'
      )
      expect(darkHoverElements.length).toBeGreaterThan(0)
    })
  })

})

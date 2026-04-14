/**
 * @jest-environment jsdom
 */
import { render, screen } from '@testing-library/react'
import { MinimalLayout } from '../MinimalLayout'

// Mock dependencies
jest.mock('@/components/layout', () => ({
  ThemeToggle: () => <div data-testid="theme-toggle">Theme Toggle</div>,
}))

jest.mock('@/components/layout/LanguageSwitcher', () => ({
  LanguageSwitcher: () => (
    <div data-testid="language-switcher">Language Switcher</div>
  ),
}))

jest.mock('@/components/layout/SectionProvider', () => ({
  SectionProvider: ({ children, sections }: any) => (
    <div
      data-testid="section-provider"
      data-sections={JSON.stringify(sections)}
    >
      {children}
    </div>
  ),
}))

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode
    href: string
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))
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


describe('MinimalLayout', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders without crashing', () => {
      render(
        <MinimalLayout>
          <div>Test content</div>
        </MinimalLayout>
      )

      expect(screen.getByText('Test content')).toBeInTheDocument()
    })

    it('renders all main structural elements', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Test content</div>
        </MinimalLayout>
      )

      const header = container.querySelector('header')
      const main = container.querySelector('main')
      const footer = container.querySelector('footer')

      expect(header).toBeInTheDocument()
      expect(main).toBeInTheDocument()
      expect(footer).toBeInTheDocument()
    })

    it('wraps content in SectionProvider', () => {
      render(
        <MinimalLayout>
          <div>Test content</div>
        </MinimalLayout>
      )

      expect(screen.getByTestId('section-provider')).toBeInTheDocument()
    })
  })

  describe('Children Rendering', () => {
    it('renders children content correctly', () => {
      render(
        <MinimalLayout>
          <div>Test content</div>
        </MinimalLayout>
      )

      expect(screen.getByText('Test content')).toBeInTheDocument()
    })

    it('renders complex nested children', () => {
      render(
        <MinimalLayout>
          <div>
            <h1>Title</h1>
            <p>Paragraph</p>
            <ul>
              <li>Item 1</li>
              <li>Item 2</li>
            </ul>
          </div>
        </MinimalLayout>
      )

      expect(screen.getByText('Title')).toBeInTheDocument()
      expect(screen.getByText('Paragraph')).toBeInTheDocument()
      expect(screen.getByText('Item 1')).toBeInTheDocument()
      expect(screen.getByText('Item 2')).toBeInTheDocument()
    })

    it('renders multiple child elements', () => {
      render(
        <MinimalLayout>
          <div>First child</div>
          <div>Second child</div>
          <div>Third child</div>
        </MinimalLayout>
      )

      expect(screen.getByText('First child')).toBeInTheDocument()
      expect(screen.getByText('Second child')).toBeInTheDocument()
      expect(screen.getByText('Third child')).toBeInTheDocument()
    })

    it('renders children with React fragments', () => {
      render(
        <MinimalLayout>
          <>
            <div>Fragment child 1</div>
            <div>Fragment child 2</div>
          </>
        </MinimalLayout>
      )

      expect(screen.getByText('Fragment child 1')).toBeInTheDocument()
      expect(screen.getByText('Fragment child 2')).toBeInTheDocument()
    })
  })

  describe('Layout Structure', () => {
    it('renders header with navigation', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const header = container.querySelector('header')
      const nav = header?.querySelector('nav')

      expect(header).toBeInTheDocument()
      expect(nav).toBeInTheDocument()
      expect(nav).toHaveAttribute('aria-label', 'Global')
    })

    it('renders BenGER logo link in header', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const logoLink = screen.getByRole('link', { name: /BenGER/i })
      expect(logoLink).toBeInTheDocument()
      expect(logoLink).toHaveAttribute('href', '/')
    })

    it('renders logo with emoji and text', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      expect(screen.getByText('🤘')).toBeInTheDocument()
      // BenGER appears twice: once as .sr-only and once as visible text
      const bengerTexts = screen.getAllByText('BenGER')
      expect(bengerTexts.length).toBe(2)
    })

    it('renders ThemeToggle component', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
    })

    it('renders LanguageSwitcher component', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
    })

    it('renders main content area with children', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Main content</div>
        </MinimalLayout>
      )

      const main = container.querySelector('main')
      expect(main).toBeInTheDocument()
      expect(main).toHaveTextContent('Main content')
    })

    it('renders footer with links', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const footer = container.querySelector('footer')
      expect(footer).toBeInTheDocument()
    })

    it('renders footer legal links', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const imprintLink = screen.getByRole('link', { name: /Imprint/i })
      const dataProtectionLink = screen.getByRole('link', {
        name: /Data Protection/i,
      })

      expect(imprintLink).toBeInTheDocument()
      expect(imprintLink).toHaveAttribute('href', '/about/imprint')
      expect(dataProtectionLink).toBeInTheDocument()
      expect(dataProtectionLink).toHaveAttribute(
        'href',
        '/about/data-protection'
      )
    })

    it('renders footer social links', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const notionLink = screen.getByRole('link', {
        name: /Follow us on Notion/i,
      })
      const githubLink = screen.getByRole('link', { name: /GitHub/i })

      expect(notionLink).toBeInTheDocument()
      expect(notionLink).toHaveAttribute('href', 'https://legaltechcolab.com/')
      expect(githubLink).toBeInTheDocument()
      expect(githubLink).toHaveAttribute(
        'href',
        'https://github.com/SebastianNagl/BenGER'
      )
    })

    it('renders footer copyright with dynamic year', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const currentYear = new Date().getFullYear()
      expect(
        screen.getByText(new RegExp(`${currentYear}.*All rights reserved`))
      ).toBeInTheDocument()
    })

    it('renders footer copyright link', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const copyrightLink = screen.getByRole('link', { name: /pschOrr95/i })
      expect(copyrightLink).toBeInTheDocument()
      expect(copyrightLink).toHaveAttribute('href', 'https://legalplusplus.net')
    })
  })

  describe('Styling', () => {
    it('applies min-h-screen and background classes to root container', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const rootDiv = container.querySelector('.min-h-screen')
      expect(rootDiv).toBeInTheDocument()
      expect(rootDiv).toHaveClass(
        'min-h-screen',
        'bg-white',
        'dark:bg-zinc-900'
      )
    })

    it('applies correct styling to header', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const header = container.querySelector('header')
      expect(header).toHaveClass('relative', 'z-10')
    })

    it('applies correct styling to navigation', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const nav = container.querySelector('nav')
      expect(nav).toHaveClass(
        'mx-auto',
        'flex',
        'max-w-7xl',
        'items-center',
        'justify-between',
        'p-4',
        'sm:p-6',
        'lg:px-8'
      )
    })

    it('applies correct styling to logo container', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const logoContainer = container.querySelector('.flex.lg\\:flex-1')
      expect(logoContainer).toBeInTheDocument()
    })

    it('applies correct styling to logo link', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const logoLink = container.querySelector('a[href="/"]')
      expect(logoLink).toHaveClass('-m-1.5', 'p-1.5')
    })

    it('applies correct styling to logo text', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const logoText = container.querySelector(
        '.flex.items-center.gap-2.text-lg'
      )
      expect(logoText).toHaveClass(
        'flex',
        'items-center',
        'gap-2',
        'text-lg',
        'font-bold',
        'text-zinc-900',
        'dark:text-white',
        'sm:text-xl'
      )
    })

    it('applies correct styling to emoji in logo', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const emoji = container.querySelector('.text-xl.sm\\:text-2xl')
      expect(emoji).toBeInTheDocument()
      expect(emoji).toHaveTextContent('🤘')
    })

    it('applies correct styling to header controls container', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const controlsContainer = container.querySelector(
        '.flex.items-center.gap-2.sm\\:gap-4'
      )
      expect(controlsContainer).toBeInTheDocument()
    })

    it('applies correct styling to main content area', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const main = container.querySelector('main')
      expect(main).toHaveClass(
        'mx-auto',
        'max-w-4xl',
        'px-4',
        'py-8',
        'sm:px-6',
        'lg:px-8'
      )
    })

    it('applies prose styling to content wrapper', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const proseWrapper = container.querySelector('.prose')
      expect(proseWrapper).toHaveClass(
        'prose',
        'prose-zinc',
        'max-w-none',
        'dark:prose-invert'
      )
    })

    it('applies correct styling to footer', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const footer = container.querySelector('footer')
      expect(footer).toHaveClass(
        'border-t',
        'border-zinc-200',
        'bg-white',
        'dark:border-zinc-800',
        'dark:bg-zinc-900'
      )
    })

    it('applies correct styling to footer inner container', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const footerInner = container.querySelector('footer > div')
      expect(footerInner).toHaveClass(
        'mx-auto',
        'max-w-7xl',
        'px-6',
        'py-12',
        'md:flex',
        'md:items-center',
        'md:justify-between',
        'lg:px-8'
      )
    })

    it('applies correct styling to footer links', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const footerLink = container.querySelector('a[href="/about/imprint"]')
      expect(footerLink).toHaveClass(
        'text-zinc-400',
        'hover:text-zinc-500',
        'dark:hover:text-zinc-300'
      )
    })

    it('applies correct styling to copyright text', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const copyright = container.querySelector(
        '.text-center.text-xs.leading-5'
      )
      expect(copyright).toHaveClass(
        'text-center',
        'text-xs',
        'leading-5',
        'text-zinc-500',
        'dark:text-zinc-400'
      )
    })
  })

  describe('Props/Attributes', () => {
    it('accepts children prop', () => {
      render(
        <MinimalLayout>
          <div>Children content</div>
        </MinimalLayout>
      )

      expect(screen.getByText('Children content')).toBeInTheDocument()
    })

    it('accepts sections prop with empty array by default', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const sectionProvider = screen.getByTestId('section-provider')
      expect(sectionProvider).toHaveAttribute('data-sections', '[]')
    })

    it('accepts sections prop with custom sections', () => {
      const sections = [
        { id: 'section-1', title: 'Section 1' },
        { id: 'section-2', title: 'Section 2' },
      ]

      render(
        <MinimalLayout sections={sections}>
          <div>Content</div>
        </MinimalLayout>
      )

      const sectionProvider = screen.getByTestId('section-provider')
      expect(sectionProvider).toHaveAttribute(
        'data-sections',
        JSON.stringify(sections)
      )
    })

    it('passes sections with all properties', () => {
      const sections = [
        {
          id: 'section-1',
          title: 'Section 1',
          offsetRem: 2,
          tag: 'h2',
        },
      ]

      render(
        <MinimalLayout sections={sections}>
          <div>Content</div>
        </MinimalLayout>
      )

      const sectionProvider = screen.getByTestId('section-provider')
      const dataSections = sectionProvider.getAttribute('data-sections')
      expect(dataSections).toBe(JSON.stringify(sections))
    })
  })

  describe('Responsive Behavior', () => {
    it('applies responsive padding classes to navigation', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const nav = container.querySelector('nav')
      expect(nav).toHaveClass('p-4', 'sm:p-6', 'lg:px-8')
    })

    it('applies responsive text size classes to logo', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const logoText = container.querySelector(
        '.flex.items-center.gap-2.text-lg'
      )
      expect(logoText).toHaveClass('text-lg', 'sm:text-xl')
    })

    it('applies responsive text size classes to emoji', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const emoji = container.querySelector('.text-xl.sm\\:text-2xl')
      expect(emoji).toHaveClass('text-xl', 'sm:text-2xl')
    })

    it('applies responsive gap classes to header controls', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const controls = container.querySelector(
        '.flex.items-center.gap-2.sm\\:gap-4'
      )
      expect(controls).toBeInTheDocument()
      expect(controls).toHaveClass('gap-2', 'sm:gap-4')
    })

    it('applies responsive padding classes to main content', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const main = container.querySelector('main')
      expect(main).toHaveClass('px-4', 'sm:px-6', 'lg:px-8')
    })

    it('applies responsive layout classes to footer', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const footerInner = container.querySelector('footer > div')
      expect(footerInner).toHaveClass(
        'md:flex',
        'md:items-center',
        'md:justify-between'
      )
    })

    it('applies responsive padding classes to footer', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const footerInner = container.querySelector('footer > div')
      expect(footerInner).toHaveClass('px-6', 'lg:px-8')
    })
  })

  describe('Accessibility', () => {
    it('has proper semantic HTML structure', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      expect(container.querySelector('header')).toBeInTheDocument()
      expect(container.querySelector('nav')).toBeInTheDocument()
      expect(container.querySelector('main')).toBeInTheDocument()
      expect(container.querySelector('footer')).toBeInTheDocument()
    })

    it('has aria-label on navigation', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const nav = container.querySelector('nav')
      expect(nav).toHaveAttribute('aria-label', 'Global')
    })

    it('has screen reader text for logo', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const srOnly = screen.getByText('BenGER', { selector: '.sr-only' })
      expect(srOnly).toBeInTheDocument()
    })

    it('has screen reader text for footer links', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      expect(
        screen.getByText('Imprint', { selector: '.sr-only' })
      ).toBeInTheDocument()
      expect(
        screen.getByText('Data Protection', { selector: '.sr-only' })
      ).toBeInTheDocument()
      expect(
        screen.getByText('Follow us on Notion', { selector: '.sr-only' })
      ).toBeInTheDocument()
      expect(
        screen.getByText('GitHub', { selector: '.sr-only' })
      ).toBeInTheDocument()
    })

    it('marks SVG icons as aria-hidden', () => {
      const { container } = render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const svgIcons = container.querySelectorAll('svg[aria-hidden="true"]')
      expect(svgIcons.length).toBeGreaterThan(0)
    })

    it('has visible text alongside screen reader text for footer links', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      // Should have both .sr-only and visible text
      const imprintLinks = screen.getAllByText('Imprint')
      expect(imprintLinks.length).toBe(2) // One sr-only, one visible
    })

    it('footer copyright link has proper link text', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const copyrightLink = screen.getByRole('link', { name: /pschOrr95/i })
      expect(copyrightLink).toBeInTheDocument()
      expect(copyrightLink).toHaveAccessibleName()
    })

    it('all external links have meaningful names', () => {
      render(
        <MinimalLayout>
          <div>Content</div>
        </MinimalLayout>
      )

      const notionLink = screen.getByRole('link', {
        name: /Follow us on Notion/i,
      })
      const githubLink = screen.getByRole('link', { name: /GitHub/i })

      expect(notionLink).toBeInTheDocument()
      expect(githubLink).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles empty string as children', () => {
      render(<MinimalLayout>{''}</MinimalLayout>)

      const main = screen.getByRole('main')
      expect(main).toBeInTheDocument()
    })

    it('handles null children gracefully', () => {
      render(<MinimalLayout>{null}</MinimalLayout>)

      const main = screen.getByRole('main')
      expect(main).toBeInTheDocument()
    })

    it('handles undefined children gracefully', () => {
      render(<MinimalLayout>{undefined}</MinimalLayout>)

      const main = screen.getByRole('main')
      expect(main).toBeInTheDocument()
    })

    it('handles boolean children gracefully', () => {
      render(
        <MinimalLayout>
          {true}
          {false}
        </MinimalLayout>
      )

      const main = screen.getByRole('main')
      expect(main).toBeInTheDocument()
    })

    it('handles conditional rendering in children', () => {
      const showContent = true

      render(
        <MinimalLayout>
          {showContent && <div>Conditional content</div>}
        </MinimalLayout>
      )

      expect(screen.getByText('Conditional content')).toBeInTheDocument()
    })

    it('handles array of children', () => {
      const items = ['Item 1', 'Item 2', 'Item 3']

      render(
        <MinimalLayout>
          {items.map((item, index) => (
            <div key={index}>{item}</div>
          ))}
        </MinimalLayout>
      )

      items.forEach((item) => {
        expect(screen.getByText(item)).toBeInTheDocument()
      })
    })

    it('handles deeply nested children structure', () => {
      render(
        <MinimalLayout>
          <div>
            <div>
              <div>
                <div>Deep content</div>
              </div>
            </div>
          </div>
        </MinimalLayout>
      )

      expect(screen.getByText('Deep content')).toBeInTheDocument()
    })

    it('handles sections prop as empty array', () => {
      render(
        <MinimalLayout sections={[]}>
          <div>Content</div>
        </MinimalLayout>
      )

      const sectionProvider = screen.getByTestId('section-provider')
      expect(sectionProvider).toHaveAttribute('data-sections', '[]')
    })

    it('handles sections prop with many items', () => {
      const sections = Array.from({ length: 20 }, (_, i) => ({
        id: `section-${i}`,
        title: `Section ${i}`,
      }))

      render(
        <MinimalLayout sections={sections}>
          <div>Content</div>
        </MinimalLayout>
      )

      const sectionProvider = screen.getByTestId('section-provider')
      expect(sectionProvider).toHaveAttribute(
        'data-sections',
        JSON.stringify(sections)
      )
    })

    it('handles special characters in children', () => {
      render(
        <MinimalLayout>
          <div>Content with &amp; &lt; &gt; special chars</div>
        </MinimalLayout>
      )

      expect(
        screen.getByText(/Content with.*special chars/)
      ).toBeInTheDocument()
    })

    it('handles component children', () => {
      const CustomComponent = () => <div>Custom component content</div>

      render(
        <MinimalLayout>
          <CustomComponent />
        </MinimalLayout>
      )

      expect(screen.getByText('Custom component content')).toBeInTheDocument()
    })

    it('maintains layout integrity with very long content', () => {
      const longContent = 'A'.repeat(10000)

      render(
        <MinimalLayout>
          <div>{longContent}</div>
        </MinimalLayout>
      )

      const main = screen.getByRole('main')
      expect(main).toBeInTheDocument()
      expect(main).toHaveTextContent(longContent)
    })

    it('handles mixed content types in children', () => {
      render(
        <MinimalLayout>
          Plain text
          <div>Div element</div>
          {null}
          {undefined}
          <span>Span element</span>
          {false}
        </MinimalLayout>
      )

      expect(screen.getByText('Plain text')).toBeInTheDocument()
      expect(screen.getByText('Div element')).toBeInTheDocument()
      expect(screen.getByText('Span element')).toBeInTheDocument()
    })
  })
})

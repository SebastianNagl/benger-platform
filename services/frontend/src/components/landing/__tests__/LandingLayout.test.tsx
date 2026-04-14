import { act, fireEvent, render, screen } from '@testing-library/react'
import { LandingLayout } from '../LandingLayout'

// Mock i18n
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'landing.logo.subtitle': 'Benchmark for German Law',
        'landing.nav.information': 'Information',
        'landing.nav.news': 'News & Publications',
        'landing.nav.people': 'People & Network',
        'landing.nav.license': 'License & Citation',
        'landing.nav.login': 'Login',
        'footer.imprint': 'Impressum',
        'footer.dataProtection': 'Datenschutz',
        'footer.github': 'GitHub',
        'footer.followOnNotion': 'Follow us on Notion',
        'footer.copyright': 'Copyright',
        'footer.allRightsReserved': 'All rights reserved.',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

// Mock Next.js Link component
jest.mock('next/link', () => {
  function Link({ href, className, children }: any) {
    return (
      <a href={href} className={className}>
        {children}
      </a>
    )
  }
  return Link
})

// Mock Logo component
jest.mock('@/components/layout/Logo', () => ({
  Logo: ({ subtitle, className }: any) => (
    <div data-testid="logo" className={className}>
      <span>🤘</span>
      <span>BenGER</span>
      {subtitle && <span data-testid="logo-subtitle">{subtitle}</span>}
    </div>
  ),
}))

// Mock the dependencies
jest.mock('@/components/layout/ThemeToggle', () => {
  function ThemeToggle() {
    return <button data-testid="theme-toggle">Theme Toggle</button>
  }
  return { ThemeToggle }
})

jest.mock('@/components/layout/LanguageSwitcher', () => {
  function LanguageSwitcher() {
    return (
      <select data-testid="language-switcher">
        <option>Language</option>
      </select>
    )
  }
  return { LanguageSwitcher }
})

describe('LandingLayout', () => {
  const TestContent = () => <div data-testid="test-content">Test Content</div>
  TestContent.displayName = 'TestContent'

  beforeEach(() => {
    jest.spyOn(Date.prototype, 'getFullYear').mockReturnValue(2024)
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('layout structure', () => {
    it('renders main layout container with correct styling', () => {
      const { container } = render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const mainContainer = container.firstChild as HTMLElement
      expect(mainContainer).toHaveClass(
        'min-h-screen',
        'bg-white',
        'dark:bg-zinc-900'
      )
    })

    it('renders header, main, and footer sections', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      expect(screen.getByRole('banner')).toBeInTheDocument()
      expect(screen.getByRole('main')).toBeInTheDocument()
      expect(screen.getByRole('contentinfo')).toBeInTheDocument()
    })

    it('renders children content in main section', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const main = screen.getByRole('main')
      expect(main).toContainElement(screen.getByTestId('test-content'))
    })
  })

  describe('header section', () => {
    it('renders sticky header', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const header = screen.getByRole('banner')
      expect(header).toHaveClass('sticky', 'top-0', 'z-50')
    })

    it('renders Logo component without subtitle', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      expect(screen.getByTestId('logo')).toBeInTheDocument()
      expect(screen.queryByTestId('logo-subtitle')).not.toBeInTheDocument()
    })

    it('renders BenGER logo with link to home', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const logoLink = screen.getByRole('link', { name: /BenGER/ })
      expect(logoLink).toHaveAttribute('href', '/')
    })

    it('provides screen reader text for logo', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const srOnlyText = screen.getByText('BenGER', { selector: '.sr-only' })
      expect(srOnlyText).toBeInTheDocument()
    })

    it('renders theme toggle and language switcher', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
      expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
    })
  })

  describe('navigation tabs', () => {
    it('renders four section navigation tabs', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      expect(screen.getByText('Information')).toBeInTheDocument()
      expect(screen.getByText('News & Publications')).toBeInTheDocument()
      expect(screen.getByText('People & Network')).toBeInTheDocument()
      expect(screen.getByText('License & Citation')).toBeInTheDocument()
    })

    it('nav tabs are buttons', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const infoTab = screen.getByText('Information')
      expect(infoTab.tagName).toBe('BUTTON')
    })

    it('applies styling to nav tabs', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const infoTab = screen.getByText('Information')
      expect(infoTab).toHaveClass('text-sm', 'font-medium')
    })

    it('calls scrollIntoView when nav tab is clicked', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const mockScrollIntoView = jest.fn()
      const mockElement = { scrollIntoView: mockScrollIntoView }
      jest.spyOn(document, 'getElementById').mockReturnValue(mockElement as any)

      fireEvent.click(screen.getByText('Information'))

      expect(document.getElementById).toHaveBeenCalledWith('information')
      expect(mockScrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth' })
    })
  })

  describe('footer section', () => {
    it('renders footer with proper styling and border', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const footer = screen.getByRole('contentinfo')
      expect(footer).toHaveClass('bg-white', 'dark:bg-zinc-900')
      expect(footer).toHaveClass(
        'border-t',
        'border-zinc-200',
        'dark:border-zinc-800'
      )
    })

    it('renders legal links (Impressum and Datenschutz)', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const impressumLink = screen.getByRole('link', { name: /Impressum/ })
      expect(impressumLink).toHaveAttribute('href', '/about/imprint')

      const datenschutzLink = screen.getByRole('link', { name: /Datenschutz/ })
      expect(datenschutzLink).toHaveAttribute('href', '/about/data-protection')
    })

    it('renders external social links', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const notionLink = screen.getByRole('link', {
        name: /Follow us on Notion/,
      })
      expect(notionLink).toHaveAttribute('href', 'https://legaltechcolab.com/')

      const githubLink = screen.getByRole('link', { name: /GitHub/ })
      expect(githubLink).toHaveAttribute(
        'href',
        'https://github.com/SebastianNagl/BenGER'
      )
    })

    it('renders copyright notice with current year', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      expect(screen.getByText(/Copyright/)).toBeInTheDocument()
      expect(screen.getByText(/2024/)).toBeInTheDocument()
      expect(screen.getByText(/All rights reserved/)).toBeInTheDocument()

      const pschOrrLink = screen.getByRole('link', { name: 'pschOrr95' })
      expect(pschOrrLink).toHaveAttribute('href', 'https://legalplusplus.net')
    })

    it('renders social media icons with proper accessibility', () => {
      const { container } = render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const socialIcons = container.querySelectorAll('svg[aria-hidden="true"]')
      expect(socialIcons).toHaveLength(2)

      socialIcons.forEach((icon) => {
        expect(icon).toHaveClass('h-6', 'w-6')
        expect(icon).toHaveAttribute('fill', 'currentColor')
      })
    })
  })

  describe('accessibility', () => {
    it('provides proper semantic structure', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      expect(screen.getByRole('banner')).toBeInTheDocument()
      expect(screen.getByRole('main')).toBeInTheDocument()
      expect(screen.getByRole('contentinfo')).toBeInTheDocument()
    })

    it('provides screen reader text for icons and logos', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      expect(
        screen.getByText('BenGER', { selector: '.sr-only' })
      ).toBeInTheDocument()
      expect(
        screen.getByText('Impressum', { selector: '.sr-only' })
      ).toBeInTheDocument()
      expect(
        screen.getByText('Datenschutz', { selector: '.sr-only' })
      ).toBeInTheDocument()
      expect(
        screen.getByText('Follow us on Notion', { selector: '.sr-only' })
      ).toBeInTheDocument()
      expect(
        screen.getByText('GitHub', { selector: '.sr-only' })
      ).toBeInTheDocument()
    })

    it('marks decorative icons as aria-hidden', () => {
      const { container } = render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const decorativeIcons = container.querySelectorAll(
        'svg[aria-hidden="true"]'
      )
      expect(decorativeIcons.length).toBeGreaterThan(0)
    })
  })

  describe('IntersectionObserver', () => {
    let mockObserve: jest.Mock
    let mockDisconnect: jest.Mock
    let observerCallback: IntersectionObserverCallback

    beforeEach(() => {
      mockObserve = jest.fn()
      mockDisconnect = jest.fn()

      ;(global as any).IntersectionObserver = jest.fn((callback: IntersectionObserverCallback) => {
        observerCallback = callback
        return {
          observe: mockObserve,
          disconnect: mockDisconnect,
          unobserve: jest.fn(),
        }
      })
    })

    it('creates IntersectionObserver on mount', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )
      expect(global.IntersectionObserver).toHaveBeenCalled()
    })

    it('observes section elements', () => {
      // Create mock section elements
      const mockElement = document.createElement('div')
      mockElement.id = 'information'
      jest.spyOn(document, 'getElementById').mockImplementation((id) => {
        if (['information', 'news', 'people', 'license'].includes(id)) {
          return mockElement
        }
        return null
      })

      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      // Should observe each section
      expect(mockObserve).toHaveBeenCalled()
    })

    it('disconnects observer on unmount', () => {
      const { unmount } = render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      unmount()
      expect(mockDisconnect).toHaveBeenCalled()
    })

    it('updates active section based on intersection', () => {
      const mockElement = document.createElement('div')
      mockElement.id = 'information'
      jest.spyOn(document, 'getElementById').mockReturnValue(mockElement)

      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      // Simulate an intersection entry becoming visible
      const entry = {
        target: { id: 'information' },
        isIntersecting: true,
      } as unknown as IntersectionObserverEntry

      act(() => {
        observerCallback([entry], {} as IntersectionObserver)
      })

      // The Information tab should get the active class
      const infoTab = screen.getByText('Information')
      expect(infoTab).toHaveClass('bg-emerald-50')
    })

    it('clears active section when section leaves viewport', () => {
      const mockElement = document.createElement('div')
      jest.spyOn(document, 'getElementById').mockReturnValue(mockElement)

      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      // First, make a section visible
      const entry1 = {
        target: { id: 'information' },
        isIntersecting: true,
      } as unknown as IntersectionObserverEntry
      act(() => {
        observerCallback([entry1], {} as IntersectionObserver)
      })

      // Then remove it
      const entry2 = {
        target: { id: 'information' },
        isIntersecting: false,
      } as unknown as IntersectionObserverEntry
      act(() => {
        observerCallback([entry2], {} as IntersectionObserver)
      })

      // Tab should not have active class
      const infoTab = screen.getByText('Information')
      expect(infoTab).not.toHaveClass('bg-emerald-50')
    })
  })

  describe('dark mode support', () => {
    it('applies dark mode classes throughout layout', () => {
      const { container } = render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const mainContainer = container.firstChild as HTMLElement
      expect(mainContainer).toHaveClass('dark:bg-zinc-900')

      const footer = screen.getByRole('contentinfo')
      expect(footer).toHaveClass('dark:bg-zinc-900', 'dark:border-zinc-800')
    })

    it('applies dark mode classes to header', () => {
      render(
        <LandingLayout>
          <TestContent />
        </LandingLayout>
      )

      const header = screen.getByRole('banner')
      expect(header).toHaveClass('dark:bg-zinc-900', 'dark:border-white/10')
    })
  })
})

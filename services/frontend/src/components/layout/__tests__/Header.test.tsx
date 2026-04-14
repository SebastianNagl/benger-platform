/**
 * @jest-environment jsdom
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { Header } from '../Header'

/* eslint-disable react/display-name */

// Mock framer-motion
jest.mock('framer-motion', () => {
  const React = require('react')
  return {
    motion: {
      div: React.forwardRef(({ children, ...props }: any, ref: any) => (
        <div ref={ref} {...props}>
          {children}
        </div>
      )),
    },
  }
})

// Mock Next.js Link
jest.mock('next/link', () => {
  function Link({ href, children, className, ...props }: any) {
    return (
      <a href={href} className={className} {...props}>
        {children}
      </a>
    )
  }
  return Link
})

// Mock useHydration hook
jest.mock('@/hooks/useHydration', () => ({
  useHydration: jest.fn(),
}))

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'header.hideSidebar': 'Hide sidebar',
        'header.showSidebar': 'Show sidebar',
        'navigation.mobile.toggleNavigation': 'Toggle navigation',
      }
      return translations[key] || key
    },
    locale: 'en',
    setLocale: jest.fn(),
  }),
}))

// Mock UI store
jest.mock('@/stores', () => ({
  useUIStore: jest.fn(),
}))

// Mock Logo component
jest.mock('@/components/layout/Logo', () => ({
  Logo: ({ className, ...props }: any) => (
    <div className={className} data-testid="logo" {...props}>
      BenGER Logo
    </div>
  ),
}))

// Mock AuthButton component
jest.mock('@/components/auth/AuthButton', () => ({
  AuthButton: (props: any) => (
    <button data-testid="auth-button" {...props}>
      Auth Button
    </button>
  ),
}))

// Mock LanguageSwitcher component
jest.mock('@/components/layout/LanguageSwitcher', () => ({
  LanguageSwitcher: (props: any) => (
    <button data-testid="language-switcher" {...props}>
      Language
    </button>
  ),
}))

// Mock ThemeToggle component
jest.mock('@/components/layout/ThemeToggle', () => ({
  ThemeToggle: (props: any) => (
    <button data-testid="theme-toggle" {...props}>
      Theme
    </button>
  ),
}))

// Mock NotificationBell component
jest.mock('@/components/layout/NotificationBell', () => ({
  NotificationBell: (props: any) => (
    <button data-testid="notification-bell" {...props}>
      Notifications
    </button>
  ),
}))

// Mock MobileNavigation components
jest.mock('@/components/layout/MobileNavigation', () => ({
  MobileNavigation: (props: any) => (
    <button data-testid="mobile-navigation" {...props}>
      Mobile Nav
    </button>
  ),
  useIsInsideMobileNavigation: jest.fn(),
  useMobileNavigationStore: jest.fn(),
}))

// Mock Search components
jest.mock('@/components/shared/Search', () => ({
  Search: (props: any) => (
    <div data-testid="search" {...props}>
      Search
    </div>
  ),
  MobileSearch: (props: any) => (
    <button data-testid="mobile-search" {...props}>
      Mobile Search
    </button>
  ),
}))

// Mock Headless UI
jest.mock('@headlessui/react', () => ({
  CloseButton: ({ as, children, ...props }: any) => {
    const Component = as || 'button'
    return <Component {...props}>{children}</Component>
  },
}))

const mockUseHydration = require('@/hooks/useHydration').useHydration
const mockUseUIStore = require('@/stores').useUIStore
const mockUseMobileNavigationStore =
  require('@/components/layout/MobileNavigation').useMobileNavigationStore
const mockUseIsInsideMobileNavigation =
  require('@/components/layout/MobileNavigation').useIsInsideMobileNavigation

describe('Header', () => {
  const mockToggleSidebar = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()

    // Default mock implementations
    mockUseHydration.mockReturnValue(true)
    mockUseUIStore.mockReturnValue({
      isSidebarHidden: false,
      toggleSidebar: mockToggleSidebar,
    })
    mockUseMobileNavigationStore.mockReturnValue({
      isOpen: false,
    })
    mockUseIsInsideMobileNavigation.mockReturnValue(false)
  })

  describe('Basic Rendering', () => {
    it('renders the header component', () => {
      const { container } = render(<Header />)
      expect(container.firstChild).toBeInTheDocument()
    })

    it('renders as a motion.div element', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header.tagName).toBe('DIV')
    })

    it('applies base header classes', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass(
        'fixed',
        'top-0',
        'z-50',
        'flex',
        'h-14',
        'items-center',
        'gap-2',
        'transition'
      )
    })

    it('has proper background color classes', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('bg-white', 'dark:bg-zinc-900')
    })

    it('has border bottom styling', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass(
        'border-b',
        'border-zinc-900/10',
        'dark:border-white/10'
      )
    })
  })

  describe('Logo Display', () => {
    it('renders the logo on desktop', () => {
      render(<Header />)
      const logos = screen.getAllByTestId('logo')
      expect(logos.length).toBeGreaterThan(0)
    })

    it('logo links to dashboard', () => {
      render(<Header />)
      const dashboardLinks = screen.getAllByRole('link', { name: 'Dashboard' })
      expect(dashboardLinks[0]).toHaveAttribute('href', '/dashboard')
    })

    it('applies correct logo className', () => {
      render(<Header />)
      const logo = screen.getAllByTestId('logo')[0]
      expect(logo).toHaveClass('h-6')
    })

    it('logo is wrapped in a link with proper accessibility', () => {
      render(<Header />)
      const dashboardLinks = screen.getAllByRole('link', { name: 'Dashboard' })
      expect(dashboardLinks[0]).toHaveAttribute('aria-label', 'Dashboard')
    })
  })

  describe('Navigation Elements', () => {
    it('renders mobile navigation component', () => {
      render(<Header />)
      expect(screen.getByTestId('mobile-navigation')).toBeInTheDocument()
    })

    it('renders desktop search component', () => {
      render(<Header />)
      expect(screen.getByTestId('search')).toBeInTheDocument()
    })

    it('renders mobile search component', () => {
      render(<Header />)
      expect(screen.getByTestId('mobile-search')).toBeInTheDocument()
    })

    it('renders hamburger menu button on desktop', () => {
      render(<Header />)
      const hamburgerButton = screen.getByRole('button', {
        name: /sidebar/i,
      })
      expect(hamburgerButton).toBeInTheDocument()
    })

    it('hamburger button has correct icon', () => {
      const { container } = render(<Header />)
      const hamburgerIcon = container.querySelector('svg[viewBox="0 0 24 24"]')
      expect(hamburgerIcon).toBeInTheDocument()
    })

    it('hamburger icon shows three horizontal lines', () => {
      const { container } = render(<Header />)
      const hamburgerIcon = container.querySelector('svg[viewBox="0 0 24 24"]')
      const path = hamburgerIcon?.querySelector('path')
      expect(path).toHaveAttribute('d', 'M3 6h18M3 12h18M3 18h18')
    })
  })

  describe('User Menu/Actions', () => {
    it('renders auth button', () => {
      render(<Header />)
      expect(screen.getByTestId('auth-button')).toBeInTheDocument()
    })

    it('renders language switcher', () => {
      render(<Header />)
      expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
    })

    it('renders theme toggle', () => {
      render(<Header />)
      expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
    })

    it('renders notification bell', () => {
      render(<Header />)
      expect(screen.getByTestId('notification-bell')).toBeInTheDocument()
    })

    it('renders utility buttons in correct order', () => {
      const { container } = render(<Header />)
      const utilityButtons = container.querySelectorAll('[data-testid]')
      const testIds = Array.from(utilityButtons)
        .map((el) => el.getAttribute('data-testid'))
        .filter((id) =>
          [
            'mobile-search',
            'language-switcher',
            'theme-toggle',
            'notification-bell',
          ].includes(id || '')
        )

      expect(testIds).toEqual([
        'mobile-search',
        'language-switcher',
        'theme-toggle',
        'notification-bell',
      ])
    })
  })

  describe('Responsive Behavior', () => {
    it('desktop elements have correct visibility classes', () => {
      const { container } = render(<Header />)
      const desktopContainer = container.querySelector(
        '.hidden.items-center.gap-3'
      )
      expect(desktopContainer).toHaveClass('lg:flex')
    })

    it('mobile elements have correct visibility classes', () => {
      const { container } = render(<Header />)
      const mobileContainer = container.querySelector(
        '.flex.items-center.gap-5.lg\\:hidden'
      )
      expect(mobileContainer).toBeInTheDocument()
    })

    it('applies responsive padding classes', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('sm:px-6', 'lg:px-8')
    })

    it('applies responsive positioning classes', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('left-0', 'right-0')
    })

    it('applies responsive justification classes', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('justify-start', 'lg:justify-between')
    })

    it('auth button hidden on small screens', () => {
      const { container } = render(<Header />)
      const authContainer = container.querySelector(
        '.hidden.min-\\[416px\\]\\:contents'
      )
      expect(authContainer).toBeInTheDocument()
    })
  })

  describe('Props/Attributes', () => {
    it('applies custom className', () => {
      const { container } = render(<Header className="custom-class" />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('custom-class')
    })

    it('preserves default classes with custom className', () => {
      const { container } = render(<Header className="custom-class" />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('custom-class', 'fixed', 'top-0', 'z-50')
    })

    it('forwards ref correctly', () => {
      const ref = { current: null }
      render(<Header ref={ref as any} />)
      expect(ref.current).toBeInstanceOf(HTMLElement)
    })

    it('forwards motion.div props', () => {
      const { container } = render(
        <Header data-testid="custom-header" id="header-id" />
      )
      const header = container.firstChild as HTMLElement
      expect(header).toHaveAttribute('data-testid', 'custom-header')
      expect(header).toHaveAttribute('id', 'header-id')
    })

    it('applies custom styles', () => {
      const { container } = render(
        <Header style={{ backgroundColor: 'red' }} />
      )
      const header = container.firstChild as HTMLElement
      expect(header).toHaveAttribute('style')
    })
  })

  describe('Accessibility', () => {
    it('hamburger button has proper aria-label when sidebar is visible', () => {
      mockUseHydration.mockReturnValue(true)
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: false,
        toggleSidebar: mockToggleSidebar,
      })

      render(<Header />)
      const hamburger = screen.getByRole('button', { name: 'Hide sidebar' })
      expect(hamburger).toBeInTheDocument()
    })

    it('hamburger button has proper aria-label when sidebar is hidden', () => {
      mockUseHydration.mockReturnValue(true)
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: true,
        toggleSidebar: mockToggleSidebar,
      })

      render(<Header />)
      const hamburger = screen.getByRole('button', { name: 'Show sidebar' })
      expect(hamburger).toBeInTheDocument()
    })

    it('dashboard link has proper aria-label', () => {
      render(<Header />)
      const links = screen.getAllByRole('link', { name: 'Dashboard' })
      expect(links.length).toBeGreaterThan(0)
    })

    it('hamburger button has proper type attribute', () => {
      render(<Header />)
      const hamburger = screen.getByRole('button', { name: /sidebar/i })
      expect(hamburger).toHaveAttribute('type', 'button')
    })

    it('all interactive elements are keyboard accessible', () => {
      render(<Header />)
      const buttons = screen.getAllByRole('button')
      buttons.forEach((button) => {
        expect(button).toBeInTheDocument()
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles undefined className', () => {
      const { container } = render(<Header className={undefined} />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('fixed', 'top-0')
    })

    it('handles empty className', () => {
      const { container } = render(<Header className="" />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('fixed', 'top-0')
    })

    it('handles null ref', () => {
      expect(() => render(<Header ref={null} />)).not.toThrow()
    })

    it('renders correctly before hydration', () => {
      mockUseHydration.mockReturnValue(false)
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: true,
        toggleSidebar: mockToggleSidebar,
      })

      render(<Header />)
      const hamburger = screen.getByRole('button', { name: 'Hide sidebar' })
      expect(hamburger).toBeInTheDocument()
    })

    it('handles mobile navigation open state', () => {
      mockUseMobileNavigationStore.mockReturnValue({
        isOpen: true,
      })

      render(<Header />)
      expect(screen.getByTestId('mobile-navigation')).toBeInTheDocument()
    })

    it('handles inside mobile navigation context', () => {
      mockUseIsInsideMobileNavigation.mockReturnValue(true)

      render(<Header />)
      expect(screen.getByTestId('mobile-navigation')).toBeInTheDocument()
    })
  })

  describe('Sidebar Toggle Functionality', () => {
    it('calls toggleSidebar when hamburger is clicked', () => {
      render(<Header />)
      const hamburger = screen.getByRole('button', { name: /sidebar/i })
      fireEvent.click(hamburger)
      expect(mockToggleSidebar).toHaveBeenCalledTimes(1)
    })

    it('shows correct aria-label based on sidebar state', () => {
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: false,
        toggleSidebar: mockToggleSidebar,
      })

      const { rerender } = render(<Header />)
      expect(
        screen.getByRole('button', { name: 'Hide sidebar' })
      ).toBeInTheDocument()

      mockUseUIStore.mockReturnValue({
        isSidebarHidden: true,
        toggleSidebar: mockToggleSidebar,
      })

      rerender(<Header />)
      expect(
        screen.getByRole('button', { name: 'Show sidebar' })
      ).toBeInTheDocument()
    })

    it('hamburger button has proper styling', () => {
      render(<Header />)
      const hamburger = screen.getByRole('button', { name: /sidebar/i })
      expect(hamburger).toHaveClass(
        'flex',
        'h-8',
        'w-8',
        'items-center',
        'justify-center',
        'rounded-md',
        'text-zinc-600',
        'transition-colors'
      )
    })

    it('hamburger button has hover styles', () => {
      render(<Header />)
      const hamburger = screen.getByRole('button', { name: /sidebar/i })
      expect(hamburger).toHaveClass(
        'hover:bg-zinc-100',
        'hover:text-zinc-900',
        'dark:text-zinc-400',
        'dark:hover:bg-zinc-800',
        'dark:hover:text-white'
      )
    })
  })

  describe('Layout Structure', () => {
    it('desktop section contains logo, hamburger, and search', () => {
      const { container } = render(<Header />)
      const desktopSection = container.querySelector(
        '.hidden.items-center.gap-3.lg\\:flex'
      )
      expect(desktopSection).toBeInTheDocument()
    })

    it('mobile section contains navigation and logo', () => {
      render(<Header />)
      const mobileNav = screen.getByTestId('mobile-navigation')
      const logos = screen.getAllByTestId('logo')
      expect(mobileNav).toBeInTheDocument()
      expect(logos.length).toBeGreaterThan(0)
    })

    it('right section contains utilities and auth', () => {
      render(<Header />)
      expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
      expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
      expect(screen.getByTestId('notification-bell')).toBeInTheDocument()
      expect(screen.getByTestId('auth-button')).toBeInTheDocument()
    })

    it('desktop search has correct container classes', () => {
      const { container } = render(<Header />)
      const searchContainer = container.querySelector(
        '.hidden.flex-1.lg\\:ml-16.lg\\:block'
      )
      expect(searchContainer).toBeInTheDocument()
    })

    it('utilities section has proper gap', () => {
      const { container } = render(<Header />)
      const utilitiesSection = container.querySelector('.flex.gap-4')
      expect(utilitiesSection).toBeInTheDocument()
    })

    it('right section has proper margin and gap classes', () => {
      const { container } = render(<Header />)
      const rightSection = container.querySelector(
        '.ml-auto.flex.items-center.gap-5'
      )
      expect(rightSection).toHaveClass('lg:ml-0')
    })
  })

  describe('Dark Mode Support', () => {
    it('has dark mode background classes', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('bg-white', 'dark:bg-zinc-900')
    })

    it('has dark mode border classes', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('dark:border-white/10')
    })

    it('hamburger button has dark mode text classes', () => {
      render(<Header />)
      const hamburger = screen.getByRole('button', { name: /sidebar/i })
      expect(hamburger).toHaveClass('dark:text-zinc-400')
    })

    it('hamburger button has dark mode hover classes', () => {
      render(<Header />)
      const hamburger = screen.getByRole('button', { name: /sidebar/i })
      expect(hamburger).toHaveClass(
        'dark:hover:bg-zinc-800',
        'dark:hover:text-white'
      )
    })
  })

  describe('Z-Index and Positioning', () => {
    it('has correct z-index for mobile and desktop', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('z-50', 'lg:z-40')
    })

    it('is fixed at the top', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('fixed', 'top-0')
    })

    it('spans full width', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('left-0', 'right-0')
    })

    it('has proper height', () => {
      const { container } = render(<Header />)
      const header = container.firstChild as HTMLElement
      expect(header).toHaveClass('h-14')
    })
  })

  describe('Hydration Handling', () => {
    it('shows sidebar by default before hydration', () => {
      mockUseHydration.mockReturnValue(false)
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: true,
        toggleSidebar: mockToggleSidebar,
      })

      render(<Header />)
      const hamburger = screen.getByRole('button', { name: 'Hide sidebar' })
      expect(hamburger).toBeInTheDocument()
    })

    it('uses actual state after hydration', () => {
      mockUseHydration.mockReturnValue(true)
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: true,
        toggleSidebar: mockToggleSidebar,
      })

      render(<Header />)
      const hamburger = screen.getByRole('button', { name: 'Show sidebar' })
      expect(hamburger).toBeInTheDocument()
    })

    it('prevents layout shift during hydration', () => {
      mockUseHydration.mockReturnValue(false)

      const { container, rerender } = render(<Header />)
      const initialHeight = container.firstChild as HTMLElement
      expect(initialHeight).toHaveClass('h-14')

      mockUseHydration.mockReturnValue(true)
      rerender(<Header />)
      const hydratedHeight = container.firstChild as HTMLElement
      expect(hydratedHeight).toHaveClass('h-14')
    })
  })
})

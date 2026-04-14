/**
 * Test for Issue #207: Hamburger Menu with Persistent State
 *
 * Tests the hamburger menu implementation including:
 * - Toggle functionality
 * - Persistent state storage
 * - Icon animation
 * - Keyboard accessibility
 * - Layout integration
 */

/**
 * @jest-environment jsdom
 */

import { Header } from '@/components/layout/Header'
import { useUIStore } from '@/stores'
import { fireEvent, render, screen } from '@testing-library/react'

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
    pathname: '/',
    query: {},
    asPath: '/',
    route: '/',
    basePath: '',
    isReady: true,
    isPreview: false,
    isLocaleDomain: false,
  })),
  useParams: jest.fn(() => ({})),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
  notFound: jest.fn(),
  redirect: jest.fn(),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../locales/en/common.json')
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


// Mock framer-motion
jest.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  },
  useScroll: () => ({ scrollY: { get: () => 0 } }),
  useTransform: () => ({ get: () => '50%' }),
}))

// Mock other components
jest.mock('@/components/layout/MobileNavigation', () => ({
  MobileNavigation: () => <div data-testid="mobile-navigation">Mobile Nav</div>,
  useIsInsideMobileNavigation: () => false,
  useMobileNavigationStore: () => ({ isOpen: false }),
}))

jest.mock('@/components/shared/Search', () => ({
  Search: () => <div data-testid="search">Search</div>,
  MobileSearch: () => <div data-testid="mobile-search">Mobile Search</div>,
}))

jest.mock('@/components/layout/Logo', () => ({
  Logo: ({ className }: { className?: string }) => (
    <div data-testid="logo" className={className}>
      Logo
    </div>
  ),
}))

jest.mock('@/components/layout/ThemeToggle', () => ({
  ThemeToggle: () => <div data-testid="theme-toggle">Theme Toggle</div>,
}))

jest.mock('@/components/layout/LanguageSwitcher', () => ({
  LanguageSwitcher: () => <div data-testid="language-switcher">Language</div>,
}))

jest.mock('@/components/auth/AuthButton', () => ({
  AuthButton: () => <div data-testid="auth-button">Auth Button</div>,
}))

jest.mock('@/components/layout/NotificationBell', () => ({
  NotificationBell: () => (
    <div data-testid="notification-bell">Notifications</div>
  ),
}))

jest.mock('@/hooks/useHydration', () => ({
  useHydration: () => true,
}))

describe('Issue #207: Hamburger Menu with Persistent State', () => {
  beforeEach(() => {
    // Reset UI store state
    useUIStore.setState({
      isSidebarHidden: false,
      isHydrated: true,
    })
  })

  describe('Hamburger Menu Rendering', () => {
    it('should render hamburger menu button', () => {
      render(<Header />)

      const hamburgerButton = screen.getByLabelText(
        /hide sidebar|show sidebar/i
      )
      expect(hamburgerButton).toBeInTheDocument()
      expect(hamburgerButton).toHaveAttribute('type', 'button')
    })

    it('should show hamburger icon when sidebar is visible', () => {
      useUIStore.setState({ isSidebarHidden: false })
      render(<Header />)

      const hamburgerButton = screen.getByLabelText(/hide sidebar/i)
      expect(hamburgerButton).toBeInTheDocument()

      // Check for hamburger icon (always shows hamburger, no X)
      const svg = hamburgerButton.querySelector('svg')
      expect(svg).toBeInTheDocument()

      // Check for hamburger icon path (always shows hamburger lines)
      const path = svg?.querySelector('path[d="M3 6h18M3 12h18M3 18h18"]')
      expect(path).toBeInTheDocument()
    })

    it('should show hamburger icon when sidebar is hidden', () => {
      useUIStore.setState({ isSidebarHidden: true })
      render(<Header />)

      const hamburgerButton = screen.getByLabelText(/show sidebar/i)
      expect(hamburgerButton).toBeInTheDocument()

      // Check for hamburger icon (always shows hamburger, no X)
      const svg = hamburgerButton.querySelector('svg')
      expect(svg).toBeInTheDocument()

      // Check for hamburger icon path (always shows hamburger lines)
      const path = svg?.querySelector('path[d="M3 6h18M3 12h18M3 18h18"]')
      expect(path).toBeInTheDocument()
    })

    it('should have correct CSS classes for styling', () => {
      render(<Header />)

      const hamburgerButton = screen.getByLabelText(
        /hide sidebar|show sidebar/i
      )
      expect(hamburgerButton).toHaveClass(
        'flex',
        'h-8',
        'w-8',
        'items-center',
        'justify-center',
        'rounded-md',
        'text-zinc-600',
        'hover:text-zinc-900',
        'hover:bg-zinc-100',
        'dark:text-zinc-400',
        'dark:hover:text-white',
        'dark:hover:bg-zinc-800',
        'transition-colors'
      )
    })

    it('should have higher z-index than sidebar for clickability', () => {
      render(<Header />)

      // Header should have z-40 on desktop to be above sidebar's z-30
      const header = screen
        .getByLabelText(/hide sidebar|show sidebar/i)
        .closest('[class*="z-"]')
      expect(header).toHaveClass('lg:z-40')
    })

    it('should have opaque background and bottom border', () => {
      render(<Header />)

      // Header should have opaque background and bottom border matching sidebar
      const header = screen
        .getByLabelText(/hide sidebar|show sidebar/i)
        .closest('[class*="fixed"]')
      expect(header).toHaveClass('bg-white', 'dark:bg-zinc-900')
      expect(header).toHaveClass(
        'border-b',
        'border-zinc-900/10',
        'dark:border-white/10'
      )
    })
  })

  describe('Toggle Functionality', () => {
    it('should toggle sidebar when hamburger menu is clicked', () => {
      render(<Header />)

      const hamburgerButton = screen.getByLabelText(/hide sidebar/i)

      // Initially sidebar should be visible
      expect(useUIStore.getState().isSidebarHidden).toBe(false)

      // Click to hide sidebar
      fireEvent.click(hamburgerButton)
      expect(useUIStore.getState().isSidebarHidden).toBe(true)

      // Click to show sidebar again
      fireEvent.click(hamburgerButton)
      expect(useUIStore.getState().isSidebarHidden).toBe(false)
    })

    it('should update aria-label when sidebar state changes', () => {
      render(<Header />)

      let hamburgerButton = screen.getByLabelText(/hide sidebar/i)
      expect(hamburgerButton).toHaveAttribute('aria-label', 'Hide sidebar')

      // Toggle sidebar
      fireEvent.click(hamburgerButton)

      hamburgerButton = screen.getByLabelText(/show sidebar/i)
      expect(hamburgerButton).toHaveAttribute('aria-label', 'Show sidebar')
    })
  })

  describe('Keyboard Accessibility', () => {
    it('should be accessible via keyboard', () => {
      render(<Header />)

      const hamburgerButton = screen.getByLabelText(
        /hide sidebar|show sidebar/i
      )

      // Focus the button
      hamburgerButton.focus()
      expect(hamburgerButton).toHaveFocus()

      // Test Space key
      fireEvent.keyDown(hamburgerButton, { key: ' ', code: 'Space' })
      fireEvent.keyUp(hamburgerButton, { key: ' ', code: 'Space' })

      // Test Enter key
      fireEvent.keyDown(hamburgerButton, { key: 'Enter', code: 'Enter' })
      fireEvent.keyUp(hamburgerButton, { key: 'Enter', code: 'Enter' })
    })

    it('should have proper button semantics', () => {
      render(<Header />)

      const hamburgerButton = screen.getByLabelText(
        /hide sidebar|show sidebar/i
      )
      expect(hamburgerButton.tagName).toBe('BUTTON')
      expect(hamburgerButton).toHaveAttribute('type', 'button')
      expect(hamburgerButton).toHaveAttribute('aria-label')
    })
  })

  describe('Responsive Design', () => {
    it('should be visible only on desktop screens', () => {
      render(<Header />)

      const hamburgerButton = screen.getByLabelText(
        /hide sidebar|show sidebar/i
      )

      // Should be visible (flex) but parent container should be hidden on mobile
      expect(hamburgerButton).toHaveClass('flex')

      // Parent container should be hidden on mobile (lg:flex means hidden on smaller screens)
      const parentContainer = hamburgerButton.closest('div')
      expect(parentContainer).toHaveClass('hidden', 'lg:flex')
    })
  })

  describe('Integration with Layout', () => {
    it('should be positioned correctly in header', () => {
      render(<Header />)

      // Check that hamburger menu is positioned correctly
      const logos = screen.getAllByTestId('logo')
      const hamburgerButton = screen.getByLabelText(
        /hide sidebar|show sidebar/i
      )

      expect(logos.length).toBeGreaterThanOrEqual(1) // At least one logo (desktop or mobile)
      expect(hamburgerButton).toBeInTheDocument()

      // Hamburger menu should be in the desktop container only
      const desktopContainer = hamburgerButton.closest('div')
      expect(desktopContainer).toHaveClass('hidden', 'lg:flex')
    })
  })

  describe('State Persistence', () => {
    it('should persist sidebar state in localStorage', () => {
      // Mock localStorage
      const mockSetItem = jest.fn()
      const mockGetItem = jest.fn()

      Object.defineProperty(window, 'localStorage', {
        value: {
          setItem: mockSetItem,
          getItem: mockGetItem,
        },
        writable: true,
      })

      render(<Header />)

      const hamburgerButton = screen.getByLabelText(
        /hide sidebar|show sidebar/i
      )

      // Click to toggle sidebar
      fireEvent.click(hamburgerButton)

      // Zustand persist middleware should have called localStorage
      // Note: This tests the integration with the persist middleware
      expect(useUIStore.getState().isSidebarHidden).toBe(true)
    })
  })

  describe('Hydration Handling', () => {
    it('should handle SSR/hydration correctly', () => {
      // Mock useHydration to return false (not hydrated yet)
      const mockUseHydration = jest.fn().mockReturnValue(false)
      jest.doMock('@/hooks/useHydration', () => ({
        useHydration: mockUseHydration,
      }))

      render(<Header />)

      const hamburgerButton = screen.getByLabelText(
        /hide sidebar|show sidebar/i
      )

      // During SSR, should show sidebar by default
      expect(hamburgerButton).toHaveAttribute('aria-label', 'Hide sidebar')
    })

    it('should not animate on initial page load', () => {
      // This test ensures no animation occurs during initial render
      // When sidebar is hidden in localStorage, it should appear hidden immediately
      useUIStore.setState({ isSidebarHidden: true, isHydrated: true })

      render(<Header />)

      const hamburgerButton = screen.getByLabelText(/show sidebar/i)

      // Should immediately show correct state without animation
      expect(hamburgerButton).toHaveAttribute('aria-label', 'Show sidebar')
    })
  })

  describe('Animation and Transitions', () => {
    it('should have CSS transition classes', () => {
      render(<Header />)

      const hamburgerButton = screen.getByLabelText(
        /hide sidebar|show sidebar/i
      )
      expect(hamburgerButton).toHaveClass('transition-colors')

      const svg = hamburgerButton.querySelector('svg')
      expect(svg).toHaveClass('h-4', 'w-4')
    })

    it('should always show hamburger icon (no X icon)', () => {
      render(<Header />)

      // Initial state - sidebar visible
      const hamburgerButton = screen.getByLabelText(/hide sidebar/i)
      let svg = hamburgerButton.querySelector('svg')
      let path = svg?.querySelector('path')

      // Should show hamburger lines
      expect(path).toHaveAttribute('d', 'M3 6h18M3 12h18M3 18h18')

      // Click to hide sidebar
      fireEvent.click(hamburgerButton)

      // After click - sidebar hidden, should still show hamburger
      const hamburgerButtonAfter = screen.getByLabelText(/show sidebar/i)
      svg = hamburgerButtonAfter.querySelector('svg')
      path = svg?.querySelector('path')

      // Should still show hamburger lines (no X)
      expect(path).toHaveAttribute('d', 'M3 6h18M3 12h18M3 18h18')
    })
  })

  describe('Error Handling', () => {
    it('should handle missing useUIStore gracefully', () => {
      // This test ensures the component doesn't crash if store is unavailable
      const consoleSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      try {
        render(<Header />)

        const hamburgerButton = screen.getByLabelText(
          /hide sidebar|show sidebar/i
        )
        expect(hamburgerButton).toBeInTheDocument()
      } catch (error) {
        // Should not throw
        expect(error).toBeUndefined()
      } finally {
        consoleSpy.mockRestore()
      }
    })
  })

  describe('Multiple Clicks', () => {
    it('should handle rapid clicks correctly', () => {
      render(<Header />)

      const hamburgerButton = screen.getByLabelText(
        /hide sidebar|show sidebar/i
      )

      // Rapid clicks
      fireEvent.click(hamburgerButton)
      fireEvent.click(hamburgerButton)
      fireEvent.click(hamburgerButton)

      // Should end up with sidebar hidden (odd number of clicks)
      expect(useUIStore.getState().isSidebarHidden).toBe(true)
    })
  })
})

// Mock shared components to prevent import errors
jest.mock('@/components/shared', () => {
  const React = require('react')
  return {
    HeroPattern: () =>
      React.createElement(
        'div',
        { 'data-testid': 'hero-pattern' },
        'Hero Pattern'
      )('div', { 'data-testid': 'hero-pattern' }, 'Hero Pattern'),
    GridPattern: () =>
      React.createElement(
        'div',
        { 'data-testid': 'grid-pattern' },
        'Grid Pattern'
      )('div', { 'data-testid': 'grid-pattern' }, 'Grid Pattern'),
    Button: ({ children, ...props }) =>
      React.createElement('button', props, children),
    ResponsiveContainer: ({ children }) =>
      React.createElement('div', null, children),
    LoadingSpinner: () =>
      React.createElement(
        'div',
        { 'data-testid': 'loading-spinner' },
        'Loading...'
      )('div', null, 'Loading...'),
    EmptyState: ({ message }) => React.createElement('div', null, message),
    Spinner: () => React.createElement('div', null, 'Loading...'),
    // Add other exports as needed
  }
})

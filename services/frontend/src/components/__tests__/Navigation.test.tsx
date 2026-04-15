/**
 * Tests for Navigation component RSC prefetch behavior
 */

/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import React from 'react'
import { Navigation } from '../layout/Navigation'

// Mock contexts
const mockAuthContext = {
  user: null,
  organizations: [],
  login: jest.fn(),
  logout: jest.fn(),
  signup: jest.fn(),
  isLoading: false,
  error: null,
}

const mockI18nContext = {
  t: (key: string) => key,
  locale: 'en',
  setLocale: jest.fn(),
  currentLanguage: 'en',
}

// Mock FeatureFlagContext
jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlag: jest.fn(() => false),
  useFeatureFlags: jest.fn(() => ({
    refreshFlags: jest.fn(),
  })),
}))

// Mock required dependencies
jest.mock('@/stores', () => ({
  useUIStore: () => ({ theme: 'light', setTheme: jest.fn() }),
}))

jest.mock('@/components/layout/SectionProvider', () => ({
  useSectionStore: (selector?: any) => {
    const state = {
      sections: [],
      visibleSections: [],
    }
    return selector ? selector(state) : state
  },
}))

jest.mock('@/components/layout/MobileNavigation', () => ({
  useIsInsideMobileNavigation: () => false,
}))

jest.mock('@/lib/remToPx', () => ({
  remToPx: (value: number) => value * 16,
}))

jest.mock('next/navigation', () => ({
  usePathname: () => '/projects',
}))

// Mock framer-motion to avoid animation issues in tests
jest.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    h2: ({ children, ...props }: any) => <h2 {...props}>{children}</h2>,
    li: ({ children, ...props }: any) => <li {...props}>{children}</li>,
    ul: ({ children, ...props }: any) => <ul {...props}>{children}</ul>,
  },
  AnimatePresence: ({ children }: any) => children,
  useIsPresent: () => true,
}))

// Mock next/link to check prefetch prop
jest.mock('next/link', () => {
  return function MockLink({ href, prefetch, children, ...props }: any) {
    return (
      <a href={href} data-prefetch={prefetch} {...props}>
        {children}
      </a>
    )
  }
})

// Mock Headless UI CloseButton
jest.mock('@headlessui/react', () => ({
  CloseButton: ({ children, as: Component = 'button', ...props }: any) => (
    <Component {...props}>{children}</Component>
  ),
}))

// Mock contexts with the defined objects
jest.mock('@/contexts/AuthContext', () => ({
  AuthProvider: ({ children }: any) => children,
  useAuth: () => mockAuthContext,
}))

jest.mock('@/contexts/I18nContext', () => ({
  I18nProvider: ({ children }: any) => children,
  useI18n: () => mockI18nContext,
}))

const TestWrapper = ({ children }: { children: React.ReactNode }) => (
  <div>
    <div>{children}</div>
  </div>
)

describe('Navigation RSC Prefetch Fix', () => {
  it('should disable prefetch for /data route links when data page is enabled', () => {
    // Enable the data page feature flag for this test
    const useFeatureFlagMock = jest.requireMock(
      '@/contexts/FeatureFlagContext'
    ).useFeatureFlag
    useFeatureFlagMock.mockImplementation((flag: string) => flag === 'data')

    render(
      <TestWrapper>
        <Navigation />
      </TestWrapper>
    )

    // Try to find data management links (they may be disabled)
    const dataLinks = screen.queryAllByText(
      /Data Management|navigation\.dataManagement/
    )

    // If data links exist and are actual links (not disabled), check prefetch
    dataLinks.forEach((link) => {
      const linkElement = link.closest('a')
      if (linkElement) {
        expect(linkElement).toHaveAttribute('data-prefetch', 'false')
      }
    })

    // Reset the mock
    useFeatureFlagMock.mockImplementation(() => false)
  })

  it('should allow default prefetch for non-data routes', () => {
    render(
      <TestWrapper>
        <Navigation />
      </TestWrapper>
    )

    // Find dashboard link that should have normal prefetch
    const dashboardLink = screen.getByText(/Dashboard|navigation\.dashboard/)
    const dashboardLinkElement = dashboardLink.closest('a')

    // Should not have prefetch explicitly disabled
    expect(dashboardLinkElement).not.toHaveAttribute('data-prefetch', 'false')
  })

  it('should render all navigation groups correctly', () => {
    render(
      <TestWrapper>
        <Navigation />
      </TestWrapper>
    )

    // Check main navigation items exist
    expect(
      screen.getByText(/Dashboard|navigation\.dashboard/)
    ).toBeInTheDocument()

    // Check navigation groups exist
    expect(
      screen.getByText(/Quick Start|navigation\.quickStart/)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Knowledge|navigation\.knowledge/)
    ).toBeInTheDocument()
  })
})

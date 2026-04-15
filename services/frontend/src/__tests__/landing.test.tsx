/**
 * @jest-environment jsdom
 */

import LandingPage from '@/app/page'
import { useAuth } from '@/contexts/AuthContext'
import { render, screen, waitFor } from '@testing-library/react'
import { useRouter } from 'next/navigation'
import React from 'react'

// Mock the dependencies
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

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock the landing components
jest.mock('@/components/landing/LandingLayout', () => ({
  LandingLayout: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="landing-layout">{children}</div>
  ),
}))

jest.mock('@/components/landing/HeroSection', () => ({
  HeroSection: () => <div data-testid="hero-section">Hero Section</div>,
}))

jest.mock('@/components/landing/InformationSection', () => ({
  InformationSection: () => <div data-testid="information-section">Information Section</div>,
}))

jest.mock('@/components/landing/NewsSection', () => ({
  NewsSection: () => <div data-testid="news-section">News Section</div>,
}))

jest.mock('@/components/landing/PeopleSection', () => ({
  PeopleSection: () => <div data-testid="people-section">People Section</div>,
}))

jest.mock('@/components/landing/LicenseCitationSection', () => ({
  LicenseCitationSection: () => <div data-testid="license-citation-section">License Citation Section</div>,
}))

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'common.loading': 'Loading...',
        'common.redirectingToDashboard': 'Redirecting to dashboard...',
        'common.redirecting': 'Redirecting...',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

describe('Landing Page', () => {
  const mockReplace = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({
      replace: mockReplace,
    })
  })

  it('renders landing layout for unauthenticated users', async () => {
    ;(useAuth as jest.Mock).mockReturnValue({
      user: null,
    })

    render(<LandingPage />)

    expect(screen.getByTestId('landing-layout')).toBeInTheDocument()
    expect(screen.getByTestId('hero-section')).toBeInTheDocument()
    expect(mockReplace).not.toHaveBeenCalled()
  })

  it('redirects authenticated users to dashboard', async () => {
    ;(useAuth as jest.Mock).mockReturnValue({
      user: { id: '1', email: 'test@example.com', role: 'user' },
    })

    render(<LandingPage />)

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/dashboard')
    })

    // Should show loading state for authenticated users
    expect(
      screen.getByText('Redirecting to dashboard...')
    ).toBeInTheDocument()
  })

  it('shows loading state while redirecting authenticated users', () => {
    ;(useAuth as jest.Mock).mockReturnValue({
      user: { id: '1', email: 'test@example.com', role: 'user' },
    })

    render(<LandingPage />)

    expect(
      screen.getByText('Redirecting to dashboard...')
    ).toBeInTheDocument()
    expect(screen.queryByTestId('landing-layout')).not.toBeInTheDocument()
  })
})

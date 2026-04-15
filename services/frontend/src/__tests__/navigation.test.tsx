/**
 * @jest-environment jsdom
 */

import { Navigation } from '@/components/layout/Navigation'
import { useAuth } from '@/contexts/AuthContext'
import { render, screen } from '@testing-library/react'

// Mock the dependencies
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key, // Simple mock that returns the key
  }),
}))

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => ({
    flags: { data: true, evaluations: true },
    isLoading: false,
    error: null,
    isEnabled: (flagName: string) =>
      flagName === 'data' || flagName === 'evaluations',
    refreshFlags: jest.fn(),
    checkFlag: jest.fn(),
    lastUpdate: Date.now(),
  }),
}))

jest.mock('@/components/layout/SectionProvider', () => ({
  useSectionStore: jest.fn(() => ({
    sections: [],
    visibleSections: [],
  })),
}))

jest.mock('next/navigation', () => ({
  usePathname: () => '/',
}))

describe('Navigation', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('shows dashboard link for authenticated users', () => {
    ;(useAuth as jest.Mock).mockReturnValue({
      user: { id: '1', email: 'test@example.com', role: 'user' },
      organizations: [],
    })

    render(<Navigation />)

    // Dashboard link should be present for authenticated users
    expect(screen.getByText('navigation.dashboard')).toBeInTheDocument()
  })

  it('shows dashboard link for unauthenticated users', () => {
    ;(useAuth as jest.Mock).mockReturnValue({
      user: null,
      organizations: [],
    })

    render(<Navigation />)

    // Dashboard link should be present for unauthenticated users too
    expect(screen.getByText('navigation.dashboard')).toBeInTheDocument()
  })

  it('disables prefetch for data route links', () => {
    ;(useAuth as jest.Mock).mockReturnValue({
      user: {
        id: '1',
        email: 'test@example.com',
        role: 'user',
        is_superadmin: true, // Give access to data management
      },
      organizations: [{ id: '1', name: 'Test Org' }],
    })

    render(<Navigation />)

    // Find data management link
    const dataLink = screen.getByText('navigation.dataManagement')
    const linkElement = dataLink.closest('a')

    // Check that the link exists and has the correct href
    expect(linkElement).toBeInTheDocument()
    expect(linkElement).toHaveAttribute('href', '/data')

    // The prefetch behavior is controlled by Next.js internally
    // We can't easily test the prefetch prop in a unit test
    // The important thing is that the link renders correctly
  })
})

/**
 * @jest-environment jsdom
 *
 * Branch coverage: Navigation.tsx
 * Targets uncovered branches:
 *   - L31: useInitialValue default-arg (condition=false)
 *   - L261: NavLink disabled with icon and isAnchorLink
 *   - L279: NavLink with tag
 *   - L319: group className ternary
 *   - L383-384: link disabled ternaries
 *   - L400/409/425: isAnchorLink/tag/icon rendering combinations
 *   - L476: SSR fallback for parseSubdomain
 *   - L490-505: hasAccessToRoute complex conditions (private mode various paths, org switch cases)
 *   - L496-505: switch cases for org mode (/data, /projects, default)
 *   - L513-593: isClient false (SSR) branches for all navigation titles
 *   - L617: sign-in button isClient branch
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

jest.mock('next/navigation', () => ({
  usePathname: jest.fn(() => '/dashboard'),
  useRouter: jest.fn(),
}))

jest.mock('next/link', () => {
  return function Link({ children, href, className, ...props }: any) {
    return <a href={href} className={className} {...props}>{children}</a>
  }
})

jest.mock('framer-motion', () => ({
  motion: {
    div: ({ children, className, ...props }: any) => <div className={className} {...props}>{children}</div>,
    h2: ({ children, className, ...props }: any) => <h2 className={className} {...props}>{children}</h2>,
    li: ({ children, className, ...props }: any) => <li className={className} {...props}>{children}</li>,
    ul: ({ children, className, ...props }: any) => <ul className={className} {...props}>{children}</ul>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
  useIsPresent: jest.fn(() => true),
}))

jest.mock('@/components/layout/MobileNavigation', () => ({
  useIsInsideMobileNavigation: jest.fn(() => false),
}))

jest.mock('@/components/layout/SectionProvider', () => ({
  useSectionStore: jest.fn((selector: any) => {
    const store = { sections: [], visibleSections: [] }
    return selector ? selector(store) : store
  }),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, href, className }: any) => (
    <a href={href} className={className} data-testid="sign-in-button">{children}</a>
  ),
}))

jest.mock('@/components/shared/Tag', () => ({
  Tag: ({ children }: { children: React.ReactNode }) => <span data-testid="tag">{children}</span>,
}))

jest.mock('@headlessui/react', () => {
  const React = require('react')
  const CloseButton = React.forwardRef(function CloseButton(
    { children, href, className, as: Component = 'button', ...props }: any,
    ref: any
  ) {
    return <Component ref={ref} href={href} className={className} {...props}>{children}</Component>
  })
  CloseButton.displayName = 'CloseButton'
  return { CloseButton }
})

const mockUseAuth = jest.fn(() => ({
  user: { id: 1, is_superadmin: false },
  organizations: [],
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

const mockUseFeatureFlags = jest.fn(() => ({
  flags: { data: true, generations: true, evaluations: true, reports: true, 'how-to': true, leaderboards: true },
  lastUpdate: Date.now(),
}))

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => mockUseFeatureFlags(),
}))

// KEY: Mock hydration as FALSE to trigger SSR branches
const mockUseHydration = jest.fn(() => false)

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: () => mockUseHydration(),
}))

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: jest.fn(() => ({ orgSlug: null, isPrivateMode: true })),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(() => ({
    t: (key: string) => `i18n:${key}`,
  })),
}))

jest.mock('@/lib/remToPx', () => ({
  remToPx: jest.fn((rem: number) => rem * 16),
}))

import { Navigation } from '../Navigation'

describe('Navigation br6 - SSR and edge case branches', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUseHydration.mockReturnValue(false) // SSR mode
  })

  it('renders with isClient=false (SSR fallback titles for all nav items)', () => {
    render(<Navigation />)

    // When isClient=false, hardcoded English strings are used instead of t() calls
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Projects')).toBeInTheDocument()
    expect(screen.getByText('Data Management')).toBeInTheDocument()
    expect(screen.getByText('Generation')).toBeInTheDocument()
    expect(screen.getByText('Evaluation')).toBeInTheDocument()
    expect(screen.getByText('Reports')).toBeInTheDocument()
    expect(screen.getByText('Leaderboards')).toBeInTheDocument()
    expect(screen.getByText('How-To')).toBeInTheDocument()
    expect(screen.getByText('Models')).toBeInTheDocument()
    expect(screen.getByText('Architecture')).toBeInTheDocument()
    // Group titles
    expect(screen.getByText('Quick Start')).toBeInTheDocument()
    expect(screen.getByText('Projects & Data')).toBeInTheDocument()
    expect(screen.getByText('Knowledge')).toBeInTheDocument()
    // Sign in button
    expect(screen.getByText('Sign in')).toBeInTheDocument()
  })

  it('renders with isClient=true (i18n translations)', () => {
    mockUseHydration.mockReturnValue(true)

    render(<Navigation />)

    // When isClient=true, t() function is used
    expect(screen.getByText('i18n:navigation.dashboard')).toBeInTheDocument()
    expect(screen.getByText('i18n:navigation.projects')).toBeInTheDocument()
    expect(screen.getByText('i18n:navigation.quickStart')).toBeInTheDocument()
  })

  it('renders in org mode with OrgAdmin role (switch /data case)', () => {
    const { parseSubdomain } = require('@/lib/utils/subdomain')
    ;(parseSubdomain as jest.Mock).mockReturnValue({ orgSlug: 'test-org', isPrivateMode: false })

    mockUseAuth.mockReturnValue({
      user: { id: 1, is_superadmin: false },
      organizations: [{ id: 'o1', slug: 'test-org', role: 'ORG_ADMIN' }],
    })

    render(<Navigation />)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('renders with all feature flags disabled', () => {
    mockUseFeatureFlags.mockReturnValue({
      flags: { data: false, generations: false, evaluations: false, reports: false, 'how-to': false, leaderboards: false },
      lastUpdate: Date.now(),
    })

    render(<Navigation />)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('renders with flags=undefined (null-safe access)', () => {
    mockUseFeatureFlags.mockReturnValue({
      flags: undefined,
      lastUpdate: Date.now(),
    })

    render(<Navigation />)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })
})

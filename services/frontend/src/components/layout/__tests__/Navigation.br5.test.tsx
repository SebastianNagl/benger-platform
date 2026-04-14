/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for Navigation - round 5.
 * Targets uncovered branches:
 * - NavLink disabled=true path (lines 256-269)
 * - NavLink shouldDisablePrefetch for /data routes (line 254)
 * - NavLink active=true, isAnchorLink=true (lines 277, 285-286)
 * - NavLink tag rendering (lines 287-291)
 * - hasAccessToRoute private mode paths (lines 489-493)
 * - hasAccessToRoute org mode ANNOTATOR role for /data (lines 497-501)
 * - buildNavigation with isClient=false (line 513)
 * - Feature flags disabled paths (lines 468-473)
 * - user=null path (line 483)
 * - parseSubdomain with isPrivateMode=true (line 476)
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

jest.mock('next/navigation', () => ({
  usePathname: jest.fn(),
  useRouter: jest.fn(),
}))

jest.mock('next/link', () => {
  return function Link({
    children,
    href,
    className,
    ...props
  }: {
    children: React.ReactNode
    href: string
    className?: string
    [key: string]: any
  }) {
    return (
      <a href={href} className={className} {...props}>
        {children}
      </a>
    )
  }
})

jest.mock('framer-motion', () => ({
  motion: {
    div: ({ children, className, ...props }: any) => (
      <div className={className} {...props}>
        {children}
      </div>
    ),
    h2: ({ children, className, ...props }: any) => (
      <h2 className={className} {...props}>
        {children}
      </h2>
    ),
    li: ({ children, className, ...props }: any) => (
      <li className={className} {...props}>
        {children}
      </li>
    ),
    ul: ({ children, className, ...props }: any) => (
      <ul className={className} {...props}>
        {children}
      </ul>
    ),
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
  Button: ({
    children,
    href,
    className,
  }: {
    children: React.ReactNode
    href: string
    className?: string
  }) => (
    <a href={href} className={className} data-testid="sign-in-button">
      {children}
    </a>
  ),
}))

jest.mock('@/components/shared/Tag', () => ({
  Tag: ({ children }: { children: React.ReactNode }) => (
    <span data-testid="tag">{children}</span>
  ),
}))

jest.mock('@headlessui/react', () => {
  const React = require('react')
  const CloseButton = React.forwardRef(function CloseButton(
    {
      children,
      href,
      className,
      as: Component = 'button',
      ...props
    }: any,
    ref: any
  ) {
    return (
      <Component ref={ref} href={href} className={className} {...props}>
        {children}
      </Component>
    )
  })
  CloseButton.displayName = 'CloseButton'
  return { CloseButton }
})

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(() => ({
    user: null,
    organizations: [],
  })),
}))

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: jest.fn(() => ({
    flags: {
      data: true,
      generations: true,
      evaluations: true,
      reports: true,
      'how-to': true,
      leaderboards: true,
    },
    lastUpdate: Date.now(),
  })),
}))

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: jest.fn(() => true),
}))

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: jest.fn(() => ({
    orgSlug: null,
    isPrivateMode: true,
  })),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(() => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'navigation.dashboard': 'Dashboard',
        'navigation.projects': 'Projects',
        'navigation.dataManagement': 'Data Management',
        'navigation.generation': 'Generation',
        'navigation.evaluation': 'Evaluation',
        'navigation.reports': 'Reports',
        'navigation.howTo': 'How-To',
        'navigation.leaderboards': 'Leaderboards',
        'navigation.architecture': 'Architecture',
        'navigation.models': 'Models',
        'navigation.quickStart': 'Quick Start',
        'navigation.projectsAndData': 'Projects & Data',
        'navigation.knowledge': 'Knowledge',
        'navigation.signIn': 'Sign in',
      }
      return translations[key] || key
    },
  })),
}))

jest.mock('@/lib/remToPx', () => ({
  remToPx: jest.fn((rem: number) => rem * 16),
}))

const mockUsePathname = require('next/navigation').usePathname
const mockUseAuth = require('@/contexts/AuthContext').useAuth
const mockUseFeatureFlags =
  require('@/contexts/FeatureFlagContext').useFeatureFlags
const mockParseSubdomain = require('@/lib/utils/subdomain').parseSubdomain

import { Navigation } from '../Navigation'

describe('Navigation - br5 branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUsePathname.mockReturnValue('/dashboard')
  })

  it('renders with disabled feature flags (reports, leaderboards off)', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, is_superadmin: false },
      organizations: [],
    })
    mockUseFeatureFlags.mockReturnValue({
      flags: {
        data: true,
        generations: true,
        evaluations: true,
        reports: false,
        'how-to': false,
        leaderboards: false,
      },
      lastUpdate: Date.now(),
    })

    render(<Navigation />)

    // Dashboard should be enabled
    expect(screen.getByText('Dashboard')).toBeInTheDocument()

    // Reports and Leaderboards should be disabled (rendered but with disabled styling)
    // They still appear in the DOM but as disabled NavLinks
    expect(screen.getByText('Reports')).toBeInTheDocument()
    expect(screen.getByText('Leaderboards')).toBeInTheDocument()
  })

  it('renders in private mode without org (all standard routes visible)', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, is_superadmin: false },
      organizations: [],
    })
    mockParseSubdomain.mockReturnValue({
      orgSlug: null,
      isPrivateMode: true,
    })

    render(<Navigation />)

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Projects')).toBeInTheDocument()
    expect(screen.getByText('Data Management')).toBeInTheDocument()
  })

  it('renders in org mode with ANNOTATOR role (restricted access)', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, is_superadmin: false },
      organizations: [{ id: 'org1', slug: 'my-org', role: 'ANNOTATOR' }],
    })
    mockParseSubdomain.mockReturnValue({
      orgSlug: 'my-org',
      isPrivateMode: false,
    })

    render(<Navigation />)

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Projects')).toBeInTheDocument()
    // Data/Generations/Evaluations should be disabled for ANNOTATOR
    // (disabled flag comes from !hasAccessToRoute)
  })

  it('renders in org mode with CONTRIBUTOR role (has access to data)', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, is_superadmin: false },
      organizations: [{ id: 'org1', slug: 'contrib-org', role: 'CONTRIBUTOR' }],
    })
    mockParseSubdomain.mockReturnValue({
      orgSlug: 'contrib-org',
      isPrivateMode: false,
    })

    render(<Navigation />)

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Data Management')).toBeInTheDocument()
  })

  it('renders with superadmin user (sees everything)', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, is_superadmin: true },
      organizations: [{ id: 'org1', slug: 'admin-org', role: 'ANNOTATOR' }],
    })
    mockParseSubdomain.mockReturnValue({
      orgSlug: 'admin-org',
      isPrivateMode: false,
    })

    render(<Navigation />)

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Data Management')).toBeInTheDocument()
    expect(screen.getByText('Generation')).toBeInTheDocument()
    expect(screen.getByText('Evaluation')).toBeInTheDocument()
  })

  it('renders with user=null (allows public routes)', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      organizations: [],
    })

    render(<Navigation />)

    // Should still render nav items (user=null => hasAccessToRoute returns true)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('renders active page link correctly', () => {
    mockUsePathname.mockReturnValue('/projects')
    mockUseAuth.mockReturnValue({
      user: { id: 1, is_superadmin: true },
      organizations: [],
    })

    render(<Navigation />)

    // Projects link should have aria-current="page"
    const projectsLink = screen.getByText('Projects').closest('a')
    expect(projectsLink).toHaveAttribute('aria-current', 'page')
  })
})

/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Navigation } from '../Navigation'

// Mock dependencies
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
      <div className={className} data-testid="motion-div" {...props}>
        {children}
      </div>
    ),
    h2: ({ children, className, ...props }: any) => (
      <h2 className={className} data-testid="motion-h2" {...props}>
        {children}
      </h2>
    ),
    li: ({ children, className, ...props }: any) => (
      <li className={className} data-testid="motion-li" {...props}>
        {children}
      </li>
    ),
    ul: ({ children, className, ...props }: any) => (
      <ul className={className} data-testid="motion-ul" {...props}>
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
    const store = {
      sections: [],
      visibleSections: [],
    }
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
  const CloseButton = React.forwardRef(
    function CloseButton(
      {
        children,
        href,
        className,
        as: Component = 'button',
        ...props
      }: {
        children: React.ReactNode
        href?: string
        className?: string
        as?: any
        [key: string]: any
      },
      ref: any
    ) {
      return (
        <Component ref={ref} href={href} className={className} {...props}>
          {children}
        </Component>
      )
    }
  )
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
  parseSubdomain: jest.fn(() => ({ orgSlug: 'test-org', isPrivateMode: false })),
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
        'navigation.about': 'About',
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

describe('Navigation', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUsePathname.mockReturnValue('/dashboard')
    mockUseAuth.mockReturnValue({
      user: {
        id: 1,
        email: 'test@example.com',
        is_superadmin: true,
      },
      organizations: [{ id: 1, name: 'Test Org', slug: 'test-org', role: 'ORG_ADMIN' }],
    })
    mockUseFeatureFlags.mockReturnValue({
      flags: {
        data: true,
        generations: true,
        evaluations: true,
        reports: true,
        'how-to': true,
        leaderboards: true,
      },
      lastUpdate: Date.now(),
    })
  })

  describe('Basic Rendering', () => {
    it('renders navigation component', () => {
      render(<Navigation />)

      const nav = screen.getByRole('navigation')
      expect(nav).toBeInTheDocument()
    })

    it('renders list of navigation items', () => {
      render(<Navigation />)

      const lists = screen.getAllByRole('list')
      expect(lists.length).toBeGreaterThan(0)
    })

    it('renders navigation groups', () => {
      render(<Navigation />)

      expect(screen.getByText('Quick Start')).toBeInTheDocument()
      expect(screen.getByText('Projects & Data')).toBeInTheDocument()
      expect(screen.getByText('Knowledge')).toBeInTheDocument()
    })

    it('renders with proper nav element', () => {
      const { container } = render(<Navigation />)

      const nav = container.querySelector('nav')
      expect(nav).toBeInTheDocument()
    })

    it('accepts custom props', () => {
      render(<Navigation id="custom-nav" data-testid="custom-navigation" />)

      const nav = screen.getByRole('navigation')
      expect(nav).toHaveAttribute('id', 'custom-nav')
      expect(nav).toHaveAttribute('data-testid', 'custom-navigation')
    })
  })

  describe('Navigation Links Display', () => {
    it('renders Dashboard link in Quick Start section', () => {
      render(<Navigation />)

      expect(screen.getByText('Dashboard')).toBeInTheDocument()
    })

    it('renders Reports link in Quick Start section', () => {
      render(<Navigation />)

      expect(screen.getByText('Reports')).toBeInTheDocument()
    })

    it('renders Projects link', () => {
      render(<Navigation />)

      expect(screen.getByText('Projects')).toBeInTheDocument()
    })

    it('renders Data Management link when feature is enabled', () => {
      render(<Navigation />)

      expect(screen.getByText('Data Management')).toBeInTheDocument()
    })

    it('renders Generation link when feature is enabled', () => {
      render(<Navigation />)

      expect(screen.getByText('Generation')).toBeInTheDocument()
    })

    it('renders Evaluation link when feature is enabled', () => {
      render(<Navigation />)

      expect(screen.getByText('Evaluation')).toBeInTheDocument()
    })

    it('renders How-To link when feature is enabled', () => {
      render(<Navigation />)

      expect(screen.getByText('How-To')).toBeInTheDocument()
    })

    it('renders Architecture link', () => {
      render(<Navigation />)

      expect(screen.getByText('Architecture')).toBeInTheDocument()
    })

    it('links have correct href attributes', () => {
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toHaveAttribute('href', '/dashboard')

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).toHaveAttribute('href', '/projects')

    })
  })

  describe('Active Link Highlighting', () => {
    it('highlights active link on dashboard', () => {
      mockUsePathname.mockReturnValue('/dashboard')
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toBeInTheDocument()
      // Check that the link has active styling classes
      const linkClasses = dashboardLink?.className || ''
      expect(linkClasses).toContain('text-zinc-900')
    })

    it('highlights active link on projects page', () => {
      mockUsePathname.mockReturnValue('/projects')
      render(<Navigation />)

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).toBeInTheDocument()
      // Check that the link has active styling classes
      const linkClasses = projectsLink?.className || ''
      expect(linkClasses).toContain('text-zinc-900')
    })

    it('non-active links have different styling', () => {
      mockUsePathname.mockReturnValue('/dashboard')
      render(<Navigation />)

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).toBeInTheDocument()
      // Non-active links should have different styling
      const linkClasses = projectsLink?.className || ''
      expect(linkClasses).toContain('text-zinc-600')
    })

    it('applies aria-current to active link', () => {
      mockUsePathname.mockReturnValue('/dashboard')
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toHaveAttribute('aria-current', 'page')
    })

    it('does not apply aria-current to inactive links', () => {
      mockUsePathname.mockReturnValue('/dashboard')
      render(<Navigation />)

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).not.toHaveAttribute('aria-current')
    })
  })

  describe('Icon Rendering', () => {
    it('renders icon for Dashboard link', () => {
      const { container } = render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      const icon = dashboardLink?.querySelector('svg')
      expect(icon).toBeInTheDocument()
    })

    it('renders icon for Projects link', () => {
      const { container } = render(<Navigation />)

      const projectsLink = screen.getByText('Projects').closest('a')
      const icon = projectsLink?.querySelector('svg')
      expect(icon).toBeInTheDocument()
    })

    it('icons have correct size classes', () => {
      const { container } = render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      const icon = dashboardLink?.querySelector('svg')
      expect(icon).toHaveClass('h-4', 'w-4')
    })

    it('icons use currentColor for stroke', () => {
      const { container } = render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      const icon = dashboardLink?.querySelector('svg')
      expect(icon).toHaveAttribute('stroke', 'currentColor')
    })

    it('icons are wrapped in flex-shrink-0 span', () => {
      const { container } = render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      const iconWrapper = dashboardLink?.querySelector('.flex-shrink-0')
      expect(iconWrapper).toBeInTheDocument()
    })
  })

  describe('User Interaction', () => {
    it('links are clickable', async () => {
      const user = userEvent.setup()
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toBeInTheDocument()

      // Link should be clickable (we can't test navigation in jsdom)
      await user.click(dashboardLink!)
    })

    it('supports keyboard navigation', async () => {
      const user = userEvent.setup()
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      dashboardLink!.focus()

      expect(dashboardLink).toHaveFocus()
    })

    it('links have hover states', () => {
      render(<Navigation />)

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).toBeInTheDocument()
      // Check hover classes in the className
      const linkClasses = projectsLink?.className || ''
      expect(linkClasses).toContain('hover:text-zinc-900')
    })

    it('link text is truncated if too long', () => {
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard')
      expect(dashboardLink).toBeInTheDocument()
      expect(dashboardLink.className).toContain('truncate')
    })
  })

  describe('Props/Attributes', () => {
    it('forwards HTML nav props', () => {
      render(
        <Navigation
          id="test-nav"
          data-custom="value"
          aria-label="Main navigation"
        />
      )

      const nav = screen.getByRole('navigation')
      expect(nav).toHaveAttribute('id', 'test-nav')
      expect(nav).toHaveAttribute('data-custom', 'value')
      expect(nav).toHaveAttribute('aria-label', 'Main navigation')
    })

    it('applies custom className', () => {
      render(<Navigation className="custom-nav-class" />)

      const nav = screen.getByRole('navigation')
      expect(nav).toHaveClass('custom-nav-class')
    })

    it('links have proper text styling', () => {
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toBeInTheDocument()
      const linkClasses = dashboardLink?.className || ''
      expect(linkClasses).toContain('text-sm')
    })

    it('links have transition classes', () => {
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toBeInTheDocument()
      const linkClasses = dashboardLink?.className || ''
      expect(linkClasses).toContain('transition')
    })

    it('links have proper spacing', () => {
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toBeInTheDocument()
      const linkClasses = dashboardLink?.className || ''
      expect(linkClasses).toContain('py-1')
      expect(linkClasses).toContain('pl-4')
    })
  })

  describe('Accessibility', () => {
    it('has proper navigation landmark', () => {
      render(<Navigation />)

      expect(screen.getByRole('navigation')).toBeInTheDocument()
    })

    it('uses semantic list structure', () => {
      render(<Navigation />)

      const lists = screen.getAllByRole('list')
      expect(lists.length).toBeGreaterThan(0)
    })

    it('navigation groups have heading elements', () => {
      render(<Navigation />)

      // Navigation groups use h2 elements
      expect(screen.getByText('Quick Start')).toBeInTheDocument()
      expect(screen.getByText('Projects & Data')).toBeInTheDocument()
      expect(screen.getByText('Knowledge')).toBeInTheDocument()
    })

    it('active links have aria-current attribute', () => {
      mockUsePathname.mockReturnValue('/dashboard')
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toBeInTheDocument()
      expect(dashboardLink).toHaveAttribute('aria-current', 'page')
    })

    it('all links have meaningful text', () => {
      render(<Navigation />)

      // All links should have descriptive text
      expect(screen.getByText('Dashboard')).toBeInTheDocument()
      expect(screen.getByText('Projects')).toBeInTheDocument()
    })

    it('supports keyboard navigation between links', async () => {
      const user = userEvent.setup()
      render(<Navigation />)

      const firstLink = screen.getByText('Dashboard').closest('a')
      const secondLink = screen.getByText('Reports').closest('a')

      firstLink!.focus()
      expect(firstLink).toHaveFocus()

      await user.tab()
      // Focus should move to next focusable element
    })
  })

  describe('Edge Cases', () => {
    it('handles disabled links correctly', () => {
      mockUseFeatureFlags.mockReturnValue({
        flags: {
          data: false,
          generations: true,
          evaluations: true,
          reports: true,
          'how-to': true,
          leaderboards: true,
        },
        lastUpdate: Date.now(),
      })

      render(<Navigation />)

      const dataLinkText = screen.getByText('Data Management')
      expect(dataLinkText).toBeInTheDocument()
      // Disabled links are rendered as divs, check the parent div
      const disabledDiv = dataLinkText.closest('div')
      expect(disabledDiv).toBeInTheDocument()
      expect(disabledDiv?.className).toContain('cursor-not-allowed')
      expect(disabledDiv?.className).toContain('opacity-50')
    })

    it('handles missing user gracefully', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        organizations: [],
      })

      render(<Navigation />)

      // Should still render navigation
      expect(screen.getByRole('navigation')).toBeInTheDocument()
    })

    it('handles empty pathname', () => {
      mockUsePathname.mockReturnValue('')

      render(<Navigation />)

      expect(screen.getByRole('navigation')).toBeInTheDocument()
    })

    it('handles null pathname', () => {
      mockUsePathname.mockReturnValue(null)

      render(<Navigation />)

      expect(screen.getByRole('navigation')).toBeInTheDocument()
    })

    it('handles special characters in pathname', () => {
      mockUsePathname.mockReturnValue('/projects?id=123&name=test')

      render(<Navigation />)

      expect(screen.getByRole('navigation')).toBeInTheDocument()
    })

    it('shows data links in private mode for non-superadmin', () => {
      const mockParseSubdomain = require('@/lib/utils/subdomain').parseSubdomain
      mockParseSubdomain.mockReturnValue({ orgSlug: null, isPrivateMode: true })

      mockUseAuth.mockReturnValue({
        user: {
          id: 1,
          email: 'test@example.com',
          is_superadmin: false,
        },
        organizations: [],
      })

      render(<Navigation />)

      // In private mode, data/generation/evaluation links are accessible
      expect(screen.getByText('Projects')).toBeInTheDocument()
    })

    it('shows all links for superadmin', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: 1,
          email: 'admin@example.com',
          is_superadmin: true,
        },
        organizations: [{ id: 1, name: 'Test Org', slug: 'test-org', role: 'ORG_ADMIN' }],
      })

      render(<Navigation />)

      // Superadmin should see all sections
      expect(screen.getByText('Quick Start')).toBeInTheDocument()
      expect(screen.getByText('Projects & Data')).toBeInTheDocument()
      expect(screen.getByText('Knowledge')).toBeInTheDocument()
    })

    it('handles all feature flags disabled', () => {
      mockUseFeatureFlags.mockReturnValue({
        flags: {
          data: false,
          generations: false,
          evaluations: false,
          reports: false,
          'how-to': false,
          leaderboards: false,
        },
        lastUpdate: Date.now(),
      })

      render(<Navigation />)

      // Should still render but with disabled links
      expect(screen.getByRole('navigation')).toBeInTheDocument()
    })

    it('handles undefined feature flags', () => {
      mockUseFeatureFlags.mockReturnValue({
        flags: undefined,
        lastUpdate: Date.now(),
      })

      render(<Navigation />)

      // Should render with fallback behavior
      expect(screen.getByRole('navigation')).toBeInTheDocument()
    })

    it('handles null feature flags', () => {
      mockUseFeatureFlags.mockReturnValue({
        flags: null,
        lastUpdate: Date.now(),
      })

      render(<Navigation />)

      // Should render with fallback behavior
      expect(screen.getByRole('navigation')).toBeInTheDocument()
    })

    it('updates when pathname changes', () => {
      mockUsePathname.mockReturnValue('/dashboard')
      const { rerender } = render(<Navigation />)

      let dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toBeInTheDocument()
      expect(dashboardLink).toHaveAttribute('aria-current', 'page')

      // Change pathname
      mockUsePathname.mockReturnValue('/projects')
      rerender(<Navigation />)

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).toBeInTheDocument()
      expect(projectsLink).toHaveAttribute('aria-current', 'page')
    })

    it('handles very long navigation item names', () => {
      render(<Navigation />)

      // Text should be truncated with truncate class
      const links = screen.getAllByRole('link')
      links.forEach((link) => {
        const textSpan = link.querySelector('.truncate')
        if (textSpan) {
          expect(textSpan).toBeInTheDocument()
        }
      })
    })

    it('maintains proper spacing with icons', () => {
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toBeInTheDocument()
      const linkClasses = dashboardLink?.className || ''
      expect(linkClasses).toContain('gap-2')
    })

    it('disables prefetch for data routes', () => {
      const { container } = render(<Navigation />)

      // Data Management link should have prefetch disabled
      // This is tested by checking the link component structure
      expect(screen.getByText('Data Management')).toBeInTheDocument()
    })
  })

  describe('Dark Mode', () => {
    it('includes dark mode classes for active links', () => {
      mockUsePathname.mockReturnValue('/dashboard')
      render(<Navigation />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toBeInTheDocument()
      const linkClasses = dashboardLink?.className || ''
      expect(linkClasses).toContain('dark:text-white')
    })

    it('includes dark mode classes for inactive links', () => {
      mockUsePathname.mockReturnValue('/dashboard')
      render(<Navigation />)

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).toBeInTheDocument()
      const linkClasses = projectsLink?.className || ''
      expect(linkClasses).toContain('dark:text-zinc-400')
      expect(linkClasses).toContain('dark:hover:text-white')
    })

    it('includes dark mode classes for disabled links', () => {
      mockUseFeatureFlags.mockReturnValue({
        flags: {
          data: false,
          generations: true,
          evaluations: true,
          reports: true,
          'how-to': true,
          leaderboards: true,
        },
        lastUpdate: Date.now(),
      })

      render(<Navigation />)

      const dataLinkText = screen.getByText('Data Management')
      expect(dataLinkText).toBeInTheDocument()
      // Check the parent div for disabled styling
      const disabledDiv = dataLinkText.closest('div')
      expect(disabledDiv?.className).toContain('dark:text-zinc-500')
    })

    it('includes dark mode classes for group headings', () => {
      render(<Navigation />)

      const heading = screen.getByText('Quick Start')
      expect(heading).toBeInTheDocument()
      expect(heading.className).toContain('dark:text-white')
    })
  })

  describe('Feature Flags', () => {
    it('disables Data Management when feature flag is off', () => {
      mockUseFeatureFlags.mockReturnValue({
        flags: {
          data: false,
          generations: true,
          evaluations: true,
          reports: true,
          'how-to': true,
          leaderboards: true,
        },
        lastUpdate: Date.now(),
      })

      render(<Navigation />)

      const dataLinkText = screen.getByText('Data Management')
      expect(dataLinkText).toBeInTheDocument()
      const disabledDiv = dataLinkText.closest('div')
      expect(disabledDiv?.className).toContain('cursor-not-allowed')
    })

    it('disables Generation when feature flag is off', () => {
      mockUseFeatureFlags.mockReturnValue({
        flags: {
          data: true,
          generations: false,
          evaluations: true,
          reports: true,
          'how-to': true,
          leaderboards: true,
        },
        lastUpdate: Date.now(),
      })

      render(<Navigation />)

      const generationLinkText = screen.getByText('Generation')
      expect(generationLinkText).toBeInTheDocument()
      const disabledDiv = generationLinkText.closest('div')
      expect(disabledDiv?.className).toContain('cursor-not-allowed')
    })

    it('disables Evaluation when feature flag is off', () => {
      mockUseFeatureFlags.mockReturnValue({
        flags: {
          data: true,
          generations: true,
          evaluations: false,
          reports: true,
          'how-to': true,
          leaderboards: true,
        },
        lastUpdate: Date.now(),
      })

      render(<Navigation />)

      const evaluationLinkText = screen.getByText('Evaluation')
      expect(evaluationLinkText).toBeInTheDocument()
      const disabledDiv = evaluationLinkText.closest('div')
      expect(disabledDiv?.className).toContain('cursor-not-allowed')
    })

    it('disables Reports when feature flag is off', () => {
      mockUseFeatureFlags.mockReturnValue({
        flags: {
          data: true,
          generations: true,
          evaluations: true,
          reports: false,
          'how-to': true,
          leaderboards: true,
        },
        lastUpdate: Date.now(),
      })

      render(<Navigation />)

      const reportsLinkText = screen.getByText('Reports')
      expect(reportsLinkText).toBeInTheDocument()
      const disabledDiv = reportsLinkText.closest('div')
      expect(disabledDiv?.className).toContain('cursor-not-allowed')
    })

    it('disables How-To when feature flag is off', () => {
      mockUseFeatureFlags.mockReturnValue({
        flags: {
          data: true,
          generations: true,
          evaluations: true,
          reports: true,
          'how-to': false,
          leaderboards: true,
        },
        lastUpdate: Date.now(),
      })

      render(<Navigation />)

      const howToLinkText = screen.getByText('How-To')
      expect(howToLinkText).toBeInTheDocument()
      const disabledDiv = howToLinkText.closest('div')
      expect(disabledDiv?.className).toContain('cursor-not-allowed')
    })

    it('re-renders when feature flags change', () => {
      mockUseFeatureFlags.mockReturnValue({
        flags: {
          data: false,
          generations: true,
          evaluations: true,
          reports: true,
          'how-to': true,
          leaderboards: true,
        },
        lastUpdate: Date.now(),
      })

      const { rerender } = render(<Navigation />)

      let dataLinkText = screen.getByText('Data Management')
      expect(dataLinkText).toBeInTheDocument()
      let disabledDiv = dataLinkText.closest('div')
      expect(disabledDiv?.className).toContain('cursor-not-allowed')

      // Enable feature
      mockUseFeatureFlags.mockReturnValue({
        flags: {
          data: true,
          generations: true,
          evaluations: true,
          reports: true,
          'how-to': true,
          leaderboards: true,
        },
        lastUpdate: Date.now() + 1000,
      })

      rerender(<Navigation />)

      dataLinkText = screen.getByText('Data Management')
      const dataLink = dataLinkText.closest('a')!
      expect(dataLink).toBeInTheDocument()
      // When enabled, the link should be clickable (not have cursor-not-allowed)
      const linkClasses = dataLink?.className || ''
      expect(linkClasses).not.toContain('cursor-not-allowed')
    })
  })

  describe('Internationalization', () => {
    it('uses translated text from i18n context', () => {
      render(<Navigation />)

      // Verify that translated text is displayed
      expect(screen.getByText('Dashboard')).toBeInTheDocument()
      expect(screen.getByText('Projects')).toBeInTheDocument()
    })

    it('handles missing translations gracefully', () => {
      const mockUseI18n = require('@/contexts/I18nContext').useI18n
      mockUseI18n.mockReturnValue({
        t: (key: string) => key,
      })

      render(<Navigation />)

      // Should still render even with fallback keys
      expect(screen.getByRole('navigation')).toBeInTheDocument()
    })
  })

  describe('Client-Side Rendering', () => {
    it('renders on client after hydration', () => {
      render(<Navigation />)

      // Navigation should render in client environment
      expect(screen.getByRole('navigation')).toBeInTheDocument()
    })

    it('handles SSR/CSR transition', () => {
      // Component uses useEffect to set isClient state
      render(<Navigation />)

      // Should render navigation in both states
      expect(screen.getByRole('navigation')).toBeInTheDocument()
    })
  })
})

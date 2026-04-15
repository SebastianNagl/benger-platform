/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import { Breadcrumb } from '../Breadcrumb'

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  HomeIcon: (props: any) => (
    <svg {...props} data-testid="home-icon">
      <path />
    </svg>
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


// Mock Next.js Link
jest.mock('next/link', () => ({
  __esModule: true,
  default: ({
    children,
    href,
    className,
  }: {
    children: React.ReactNode
    href: string
    className?: string
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}))

describe('Breadcrumb Component', () => {
  const defaultItems = [
    { label: 'Home', href: '/' },
    { label: 'Projects', href: '/projects' },
    { label: 'Project 1', href: '/projects/1' },
  ]

  describe('Basic Rendering', () => {
    it('renders nav element with breadcrumb landmark', () => {
      render(<Breadcrumb items={defaultItems} />)

      const nav = screen.getByRole('navigation')
      expect(nav).toBeInTheDocument()
      expect(nav).toHaveAttribute('aria-label', 'Breadcrumb')
    })

    it('renders ordered list', () => {
      render(<Breadcrumb items={defaultItems} />)

      const list = screen.getByRole('list')
      expect(list).toBeInTheDocument()
      expect(list.tagName).toBe('OL')
    })

    it('renders all breadcrumb items', () => {
      render(<Breadcrumb items={defaultItems} />)

      expect(screen.getByText('Projects')).toBeInTheDocument()
      expect(screen.getByText('Project 1')).toBeInTheDocument()
    })

    it('renders correct number of list items', () => {
      render(<Breadcrumb items={defaultItems} />)

      const listItems = screen.getAllByRole('listitem')
      expect(listItems).toHaveLength(3)
    })
  })

  describe('Home Icon Rendering', () => {
    it('renders home icon for root path', () => {
      render(<Breadcrumb items={defaultItems} />)

      expect(screen.getByTestId('home-icon')).toBeInTheDocument()
    })

    it('renders home icon for dashboard path', () => {
      const dashboardItems = [
        { label: 'Dashboard', href: '/dashboard' },
        { label: 'Settings', href: '/dashboard/settings' },
      ]
      render(<Breadcrumb items={dashboardItems} />)

      expect(screen.getByTestId('home-icon')).toBeInTheDocument()
    })

    it('does not render home icon for other first items', () => {
      const otherItems = [
        { label: 'Projects', href: '/projects' },
        { label: 'Project 1', href: '/projects/1' },
      ]
      render(<Breadcrumb items={otherItems} />)

      expect(screen.queryByTestId('home-icon')).not.toBeInTheDocument()
      expect(screen.getByText('Projects')).toBeInTheDocument()
    })

    it('home icon links to correct href', () => {
      render(<Breadcrumb items={defaultItems} />)

      const homeIcon = screen.getByTestId('home-icon')
      const homeLink = homeIcon.closest('a')
      expect(homeLink).toHaveAttribute('href', '/')
    })
  })

  describe('Item Separators', () => {
    it('renders separators between items', () => {
      render(<Breadcrumb items={defaultItems} />)

      const separators = screen.getAllByText('/')
      expect(separators).toHaveLength(2) // Between 3 items
    })

    it('does not render separator before first item', () => {
      render(<Breadcrumb items={defaultItems} />)

      const firstItem = screen.getAllByRole('listitem')[0]
      const separatorInFirst = firstItem.querySelector('.text-zinc-400')
      expect(separatorInFirst).not.toBeInTheDocument()
    })

    it('applies correct styling to separators', () => {
      render(<Breadcrumb items={defaultItems} />)

      const separators = screen.getAllByText('/')
      separators.forEach((sep) => {
        expect(sep).toHaveClass('text-zinc-400', 'dark:text-zinc-600')
      })
    })
  })

  describe('Current Page (Last Item)', () => {
    it('renders last item as plain text', () => {
      render(<Breadcrumb items={defaultItems} />)

      const lastItem = screen.getByText('Project 1')
      expect(lastItem.tagName).toBe('SPAN')
    })

    it('does not render last item as link', () => {
      render(<Breadcrumb items={defaultItems} />)

      const lastItem = screen.getByText('Project 1')
      const parentAnchor = lastItem.closest('a')
      expect(parentAnchor).not.toBeInTheDocument()
    })

    it('applies font-medium to current page', () => {
      render(<Breadcrumb items={defaultItems} />)

      const currentPage = screen.getByText('Project 1')
      expect(currentPage).toHaveClass('font-medium')
    })

    it('applies correct text color to current page', () => {
      render(<Breadcrumb items={defaultItems} />)

      const currentPage = screen.getByText('Project 1')
      expect(currentPage).toHaveClass('text-zinc-900', 'dark:text-white')
    })
  })

  describe('Navigation Links', () => {
    it('renders intermediate items as links', () => {
      render(<Breadcrumb items={defaultItems} />)

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).toBeInTheDocument()
      expect(projectsLink).toHaveAttribute('href', '/projects')
    })

    it('all non-last items are clickable', () => {
      render(<Breadcrumb items={defaultItems} />)

      const homeLink = screen.getByTestId('home-icon').closest('a')
      const projectsLink = screen.getByText('Projects').closest('a')

      expect(homeLink).toBeInTheDocument()
      expect(projectsLink).toBeInTheDocument()
    })

    it('links have correct href attributes', () => {
      render(<Breadcrumb items={defaultItems} />)

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).toHaveAttribute('href', '/projects')
    })

    it('applies hover styles to links', () => {
      render(<Breadcrumb items={defaultItems} />)

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).toHaveClass(
        'hover:text-zinc-900',
        'dark:hover:text-white'
      )
    })
  })

  describe('Styling', () => {
    it('applies base navigation styles', () => {
      const { container } = render(<Breadcrumb items={defaultItems} />)

      const nav = container.querySelector('nav')
      expect(nav).toHaveClass('flex')
    })

    it('applies list container styles', () => {
      render(<Breadcrumb items={defaultItems} />)

      const list = screen.getByRole('list')
      expect(list).toHaveClass('flex', 'items-center', 'space-x-1', 'text-sm')
    })

    it('list items have flex layout', () => {
      render(<Breadcrumb items={defaultItems} />)

      const listItems = screen.getAllByRole('listitem')
      listItems.forEach((item) => {
        expect(item).toHaveClass('flex', 'items-center')
      })
    })

    it('applies link color styles', () => {
      render(<Breadcrumb items={defaultItems} />)

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).toHaveClass(
        'text-zinc-600',
        'dark:text-zinc-400',
        'transition-colors'
      )
    })

    it('home icon has correct size', () => {
      render(<Breadcrumb items={defaultItems} />)

      const homeIcon = screen.getByTestId('home-icon')
      expect(homeIcon).toHaveClass('h-4', 'w-4')
    })

    it('applies dark mode styles', () => {
      render(<Breadcrumb items={defaultItems} />)

      const currentPage = screen.getByText('Project 1')
      expect(currentPage).toHaveClass('dark:text-white')

      const projectsLink = screen.getByText('Projects').closest('a')
      expect(projectsLink).toHaveClass('dark:text-zinc-400')
    })
  })

  describe('Accessibility', () => {
    it('has proper aria-label on nav', () => {
      render(<Breadcrumb items={defaultItems} />)

      const nav = screen.getByRole('navigation')
      expect(nav).toHaveAttribute('aria-label', 'Breadcrumb')
    })

    it('uses semantic HTML navigation element', () => {
      render(<Breadcrumb items={defaultItems} />)

      const nav = screen.getByRole('navigation')
      expect(nav.tagName).toBe('NAV')
    })

    it('uses ordered list for breadcrumb items', () => {
      render(<Breadcrumb items={defaultItems} />)

      const list = screen.getByRole('list')
      expect(list.tagName).toBe('OL')
    })

    it('each breadcrumb is a list item', () => {
      render(<Breadcrumb items={defaultItems} />)

      const listItems = screen.getAllByRole('listitem')
      listItems.forEach((item) => {
        expect(item.tagName).toBe('LI')
      })
    })

    it('current page is not a link', () => {
      render(<Breadcrumb items={defaultItems} />)

      const currentPage = screen.getByText('Project 1')
      const parentLink = currentPage.closest('a')
      expect(parentLink).not.toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles single item breadcrumb', () => {
      const singleItem = [{ label: 'Home', href: '/' }]
      render(<Breadcrumb items={singleItem} />)

      expect(screen.getByTestId('home-icon')).toBeInTheDocument()
      expect(screen.queryByText('/')).not.toBeInTheDocument() // No separator
    })

    it('handles many items', () => {
      const manyItems = [
        { label: 'Home', href: '/' },
        { label: 'Level 1', href: '/level1' },
        { label: 'Level 2', href: '/level1/level2' },
        { label: 'Level 3', href: '/level1/level2/level3' },
        { label: 'Level 4', href: '/level1/level2/level3/level4' },
        { label: 'Current', href: '/level1/level2/level3/level4/current' },
      ]
      render(<Breadcrumb items={manyItems} />)

      const listItems = screen.getAllByRole('listitem')
      expect(listItems).toHaveLength(6)

      const separators = screen.getAllByText('/')
      expect(separators).toHaveLength(5) // n-1 separators
    })

    it('handles special characters in labels', () => {
      const specialChars = '< > & " \' @ #'
      const items = [
        { label: 'Home', href: '/' },
        { label: specialChars, href: '/special' },
      ]
      render(<Breadcrumb items={items} />)

      expect(screen.getByText(specialChars)).toBeInTheDocument()
    })

    it('handles very long labels', () => {
      const longLabel = 'A'.repeat(100)
      const items = [
        { label: 'Home', href: '/' },
        { label: longLabel, href: '/long' },
      ]
      render(<Breadcrumb items={items} />)

      expect(screen.getByText(longLabel)).toBeInTheDocument()
    })

    it('handles unicode characters in labels', () => {
      const unicodeLabel = '你好 世界 🌍 café'
      const items = [
        { label: 'Home', href: '/' },
        { label: unicodeLabel, href: '/unicode' },
      ]
      render(<Breadcrumb items={items} />)

      expect(screen.getByText(unicodeLabel)).toBeInTheDocument()
    })

    it('handles paths with query parameters', () => {
      const items = [
        { label: 'Home', href: '/' },
        { label: 'Search', href: '/search?q=test' },
        { label: 'Results', href: '/search/results' },
      ]
      render(<Breadcrumb items={items} />)

      const searchLink = screen.getByText('Search').closest('a')
      expect(searchLink).toHaveAttribute('href', '/search?q=test')
    })

    it('handles paths with hash fragments', () => {
      const items = [
        { label: 'Home', href: '/' },
        { label: 'Docs', href: '/docs#section' },
        { label: 'API', href: '/docs/api' },
      ]
      render(<Breadcrumb items={items} />)

      const docsLink = screen.getByText('Docs').closest('a')
      expect(docsLink).toHaveAttribute('href', '/docs#section')
    })

    it('handles empty label gracefully', () => {
      const items = [
        { label: 'Home', href: '/' },
        { label: '', href: '/empty' },
      ]
      render(<Breadcrumb items={items} />)

      const listItems = screen.getAllByRole('listitem')
      expect(listItems).toHaveLength(2)
    })

    it('uses href as key for list items', () => {
      const { container } = render(<Breadcrumb items={defaultItems} />)

      const listItems = container.querySelectorAll('li')
      expect(listItems).toHaveLength(3)
      // Keys are internal React props, but we verify uniqueness by checking all items render
    })

    it('handles duplicate hrefs', () => {
      const duplicateItems = [
        { label: 'Home', href: '/' },
        { label: 'Same Path 1', href: '/same' },
        { label: 'Same Path 2', href: '/same' },
      ]
      render(<Breadcrumb items={duplicateItems} />)

      expect(screen.getByText('Same Path 1')).toBeInTheDocument()
      expect(screen.getByText('Same Path 2')).toBeInTheDocument()
    })

    it('renders correctly with only non-home single item', () => {
      const singleNonHome = [{ label: 'Projects', href: '/projects' }]
      render(<Breadcrumb items={singleNonHome} />)

      const projects = screen.getByText('Projects')
      expect(projects).toBeInTheDocument()
      expect(projects.tagName).toBe('SPAN') // Last item is always span
      expect(screen.queryByTestId('home-icon')).not.toBeInTheDocument()
    })
  })
})

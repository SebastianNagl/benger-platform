/**
 * @jest-environment jsdom
 */
import { render, screen, waitFor } from '@testing-library/react'
import { Layout } from '../Layout'
import type { Section } from '../SectionProvider'

 

// Mock framer-motion
jest.mock('framer-motion', () => ({
  motion: {
    div: ({
      children,
      className,
      animate,
      initial,
      transition,
      suppressHydrationWarning,
      ...props
    }: any) => (
      <div className={className} {...props}>
        {children}
      </div>
    ),
    aside: ({
      children,
      className,
      suppressHydrationWarning,
      ...props
    }: any) => (
      <aside className={className} {...props}>
        {children}
      </aside>
    ),
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}))

// Mock Next.js hooks
jest.mock('next/navigation', () => ({
  usePathname: jest.fn(),
}))

// Mock hooks
jest.mock('@/hooks/useHydration', () => ({
  useHydration: jest.fn(),
}))

// Mock stores
jest.mock('@/stores', () => ({
  useUIStore: jest.fn(),
}))

// Mock components
jest.mock('../Header', () => ({
  Header: () => <header data-testid="header">Header</header>,
}))

jest.mock('../Footer', () => ({
  Footer: () => <footer data-testid="footer">Footer</footer>,
}))

jest.mock('../Navigation', () => ({
  Navigation: ({ className }: any) => (
    <nav data-testid="navigation" className={className}>
      Navigation
    </nav>
  ),
}))

jest.mock('../SectionProvider', () => ({
  SectionProvider: ({ children, sections }: any) => (
    <div
      data-testid="section-provider"
      data-sections={JSON.stringify(sections)}
    >
      {children}
    </div>
  ),
}))

const mockUsePathname = require('next/navigation').usePathname
const mockUseHydration = require('@/hooks/useHydration').useHydration
const mockUseUIStore = require('@/stores').useUIStore

describe('Layout', () => {
  const defaultProps = {
    children: <div>Test Content</div>,
    allSections: {
      '/': [{ id: 'section1', title: 'Section 1' }],
      '/dashboard': [{ id: 'section2', title: 'Section 2' }],
    } as Record<string, Array<Section>>,
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockUsePathname.mockReturnValue('/')
    mockUseHydration.mockReturnValue(true)
    mockUseUIStore.mockReturnValue({
      isSidebarHidden: false,
    })

    // Mock timers for animation delays
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
    jest.restoreAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders layout with all main sections', () => {
      render(<Layout {...defaultProps} />)

      expect(screen.getByTestId('section-provider')).toBeInTheDocument()
      expect(screen.getByTestId('header')).toBeInTheDocument()
      expect(screen.getByTestId('navigation')).toBeInTheDocument()
      expect(screen.getByTestId('footer')).toBeInTheDocument()
    })

    it('renders with correct root structure', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const rootDiv = container.querySelector('.flex.h-full.w-full')
      expect(rootDiv).toBeInTheDocument()
    })

    it('renders when sections prop is empty', () => {
      const props = {
        ...defaultProps,
        allSections: {},
      }

      render(<Layout {...props} />)

      expect(screen.getByTestId('section-provider')).toBeInTheDocument()
    })

    it('renders without errors', () => {
      expect(() => render(<Layout {...defaultProps} />)).not.toThrow()
    })
  })

  describe('Header/Footer Integration', () => {
    it('renders Header component', () => {
      render(<Layout {...defaultProps} />)

      const header = screen.getByTestId('header')
      expect(header).toBeInTheDocument()
      expect(header.textContent).toBe('Header')
    })

    it('renders Footer component', () => {
      render(<Layout {...defaultProps} />)

      const footer = screen.getByTestId('footer')
      expect(footer).toBeInTheDocument()
      expect(footer.textContent).toBe('Footer')
    })

    it('renders Header before main content', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const header = screen.getByTestId('header')
      const main = screen.getByRole('main')

      const headerIndex = Array.from(container.querySelectorAll('*')).indexOf(
        header
      )
      const mainIndex = Array.from(container.querySelectorAll('*')).indexOf(
        main
      )

      expect(headerIndex).toBeLessThan(mainIndex)
    })

    it('renders Footer after main content', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const footer = screen.getByTestId('footer')
      const main = screen.getByRole('main')

      const footerIndex = Array.from(container.querySelectorAll('*')).indexOf(
        footer
      )
      const mainIndex = Array.from(container.querySelectorAll('*')).indexOf(
        main
      )

      expect(footerIndex).toBeGreaterThan(mainIndex)
    })
  })

  describe('Sidebar/Navigation', () => {
    it('renders Navigation component in sidebar', () => {
      render(<Layout {...defaultProps} />)

      const navigation = screen.getByTestId('navigation')
      expect(navigation).toBeInTheDocument()
    })

    it('applies correct classes to sidebar when visible', () => {
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: false,
      })

      const { container } = render(<Layout {...defaultProps} />)

      const sidebar = container.querySelector('aside')
      expect(sidebar).toHaveClass(
        'lg:pointer-events-none',
        'lg:fixed',
        'lg:inset-0',
        'lg:z-30',
        'lg:flex'
      )
    })

    it('shows sidebar when isSidebarHidden is false', () => {
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: false,
      })

      const { container } = render(<Layout {...defaultProps} />)

      const mainContentArea = container.querySelector('.min-w-0.flex-1')
      const innerDiv = mainContentArea?.querySelector(
        '.relative.flex.h-full.flex-col'
      )

      expect(innerDiv).toHaveClass('lg:ml-64', 'xl:ml-72', '2xl:ml-80')
    })

    it('hides sidebar when isSidebarHidden is true', () => {
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: true,
      })

      const { container } = render(<Layout {...defaultProps} />)

      const mainContentArea = container.querySelector('.min-w-0.flex-1')
      const innerDiv = mainContentArea?.querySelector(
        '.relative.flex.h-full.flex-col'
      )

      expect(innerDiv).not.toHaveClass('lg:ml-64')
      expect(innerDiv).not.toHaveClass('xl:ml-72')
      expect(innerDiv).not.toHaveClass('2xl:ml-80')
    })

    it('applies hidden classes to navigation on large screens', () => {
      render(<Layout {...defaultProps} />)

      const navigation = screen.getByTestId('navigation')
      expect(navigation).toHaveClass('hidden', 'lg:mt-16', 'lg:block')
    })

    it('sidebar uses correct responsive layout classes', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const sidebarInner = container.querySelector('.lg\\:w-64')
      expect(sidebarInner).toHaveClass(
        'lg:pointer-events-auto',
        'lg:w-64',
        'xl:w-72',
        '2xl:w-80'
      )
    })

    it('sidebar has overflow-y-auto for scrolling', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const sidebarInner = container.querySelector('.lg\\:overflow-y-auto')
      expect(sidebarInner).toBeInTheDocument()
    })

    it('sidebar has correct border and background classes', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const sidebarInner = container.querySelector('.lg\\:border-r')
      expect(sidebarInner).toHaveClass(
        'lg:border-r',
        'lg:border-zinc-900/10',
        'lg:bg-white',
        'lg:dark:border-white/10',
        'lg:dark:bg-zinc-900'
      )
    })

    it('shows sidebar before hydration', () => {
      mockUseHydration.mockReturnValue(false)
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: true, // Hidden in state
      })

      const { container } = render(<Layout {...defaultProps} />)

      // Before hydration, sidebar should be shown to prevent layout shift
      const mainContentArea = container.querySelector('.min-w-0.flex-1')
      const innerDiv = mainContentArea?.querySelector(
        '.relative.flex.h-full.flex-col'
      )

      expect(innerDiv).toHaveClass('lg:ml-64', 'xl:ml-72', '2xl:ml-80')
    })

    it('uses UI store state after hydration', () => {
      mockUseHydration.mockReturnValue(true)
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: true,
      })

      const { container } = render(<Layout {...defaultProps} />)

      const mainContentArea = container.querySelector('.min-w-0.flex-1')
      const innerDiv = mainContentArea?.querySelector(
        '.relative.flex.h-full.flex-col'
      )

      expect(innerDiv).not.toHaveClass('lg:ml-64')
    })
  })

  describe('Main Content Area', () => {
    it('renders main element with correct role', () => {
      render(<Layout {...defaultProps} />)

      const main = screen.getByRole('main')
      expect(main).toBeInTheDocument()
    })

    it('applies correct classes to main content area', () => {
      render(<Layout {...defaultProps} />)

      const main = screen.getByRole('main')
      expect(main).toHaveClass('w-full', 'min-w-0', 'flex-auto')
    })

    it('main content area has correct parent layout', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const main = screen.getByRole('main')
      const parent = main.parentElement

      expect(parent).toHaveClass(
        'relative',
        'flex',
        'h-full',
        'flex-col',
        'pt-14'
      )
    })

    it('main content container has flex-1 class', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const contentContainer = container.querySelector('.min-w-0.flex-1')
      expect(contentContainer).toBeInTheDocument()
    })

    it('adjusts main content margin based on sidebar visibility', () => {
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: false,
      })

      const { container, rerender } = render(<Layout {...defaultProps} />)

      let innerDiv = container.querySelector('.relative.flex.h-full.flex-col')
      expect(innerDiv).toHaveClass('lg:ml-64')

      // Change sidebar state
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: true,
      })

      rerender(<Layout {...defaultProps} />)

      innerDiv = container.querySelector('.relative.flex.h-full.flex-col')
      expect(innerDiv).not.toHaveClass('lg:ml-64')
    })
  })

  describe('Children Rendering', () => {
    it('renders children content inside main element', () => {
      render(<Layout {...defaultProps} />)

      const main = screen.getByRole('main')
      expect(main.textContent).toBe('Test Content')
    })

    it('renders multiple children elements', () => {
      const props = {
        ...defaultProps,
        children: (
          <>
            <div>Child 1</div>
            <div>Child 2</div>
            <div>Child 3</div>
          </>
        ),
      }

      render(<Layout {...props} />)

      expect(screen.getByText('Child 1')).toBeInTheDocument()
      expect(screen.getByText('Child 2')).toBeInTheDocument()
      expect(screen.getByText('Child 3')).toBeInTheDocument()
    })

    it('renders complex nested children', () => {
      const props = {
        ...defaultProps,
        children: (
          <div>
            <section>
              <article>
                <p>Nested Content</p>
              </article>
            </section>
          </div>
        ),
      }

      render(<Layout {...props} />)

      expect(screen.getByText('Nested Content')).toBeInTheDocument()
    })

    it('children are contained within main element', () => {
      render(<Layout {...defaultProps} />)

      const main = screen.getByRole('main')
      const content = screen.getByText('Test Content')

      expect(main).toContainElement(content)
    })
  })

  describe('Props/Attributes', () => {
    it('passes sections to SectionProvider based on pathname', () => {
      mockUsePathname.mockReturnValue('/dashboard')

      render(<Layout {...defaultProps} />)

      const provider = screen.getByTestId('section-provider')
      const sectionsData = JSON.parse(
        provider.getAttribute('data-sections') || '[]'
      )

      expect(sectionsData).toEqual([{ id: 'section2', title: 'Section 2' }])
    })

    it('uses empty sections array when pathname not found', () => {
      mockUsePathname.mockReturnValue('/unknown')

      render(<Layout {...defaultProps} />)

      const provider = screen.getByTestId('section-provider')
      const sectionsData = JSON.parse(
        provider.getAttribute('data-sections') || '[]'
      )

      expect(sectionsData).toEqual([])
    })

    it('handles null pathname gracefully', () => {
      mockUsePathname.mockReturnValue(null)

      render(<Layout {...defaultProps} />)

      const provider = screen.getByTestId('section-provider')
      const sectionsData = JSON.parse(
        provider.getAttribute('data-sections') || '[]'
      )

      // Null pathname defaults to '/' in the component
      expect(sectionsData).toEqual([{ id: 'section1', title: 'Section 1' }])
    })

    it('uses correct sections for root pathname', () => {
      mockUsePathname.mockReturnValue('/')

      render(<Layout {...defaultProps} />)

      const provider = screen.getByTestId('section-provider')
      const sectionsData = JSON.parse(
        provider.getAttribute('data-sections') || '[]'
      )

      expect(sectionsData).toEqual([{ id: 'section1', title: 'Section 1' }])
    })

    it('updates sections when pathname changes', () => {
      mockUsePathname.mockReturnValue('/')

      const { rerender } = render(<Layout {...defaultProps} />)

      let provider = screen.getByTestId('section-provider')
      let sectionsData = JSON.parse(
        provider.getAttribute('data-sections') || '[]'
      )
      expect(sectionsData).toEqual([{ id: 'section1', title: 'Section 1' }])

      // Change pathname
      mockUsePathname.mockReturnValue('/dashboard')

      rerender(<Layout {...defaultProps} />)

      provider = screen.getByTestId('section-provider')
      sectionsData = JSON.parse(provider.getAttribute('data-sections') || '[]')
      expect(sectionsData).toEqual([{ id: 'section2', title: 'Section 2' }])
    })
  })

  describe('Accessibility', () => {
    it('has proper main landmark', () => {
      render(<Layout {...defaultProps} />)

      const main = screen.getByRole('main')
      expect(main).toBeInTheDocument()
    })

    it('has proper navigation landmark in sidebar', () => {
      render(<Layout {...defaultProps} />)

      const navigation = screen.getByTestId('navigation')
      expect(navigation.tagName).toBe('NAV')
    })

    it('header is before main in DOM order', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const allElements = Array.from(container.querySelectorAll('*'))
      const headerIndex = allElements.findIndex(
        (el) => el.getAttribute('data-testid') === 'header'
      )
      const mainIndex = allElements.findIndex((el) => el.tagName === 'MAIN')

      expect(headerIndex).toBeLessThan(mainIndex)
    })

    it('maintains semantic HTML structure', () => {
      const { container } = render(<Layout {...defaultProps} />)

      expect(container.querySelector('header')).toBeInTheDocument()
      expect(container.querySelector('aside')).toBeInTheDocument()
      expect(container.querySelector('main')).toBeInTheDocument()
      expect(container.querySelector('footer')).toBeInTheDocument()
      expect(container.querySelector('nav')).toBeInTheDocument()
    })

    it('all content is keyboard accessible', () => {
      const { container } = render(<Layout {...defaultProps} />)

      // No elements should have tabindex < -1
      const negativeTabIndexElements = container.querySelectorAll('[tabindex]')
      negativeTabIndexElements.forEach((element) => {
        const tabindex = parseInt(element.getAttribute('tabindex') || '0', 10)
        expect(tabindex).toBeGreaterThanOrEqual(-1)
      })
    })
  })

  describe('Edge Cases', () => {
    it('renders with null children', () => {
      const props = {
        ...defaultProps,
        children: null,
      }

      render(<Layout {...props} />)

      const main = screen.getByRole('main')
      expect(main).toBeInTheDocument()
    })

    it('renders with undefined children', () => {
      const props = {
        ...defaultProps,
        children: undefined,
      }

      render(<Layout {...props} />)

      const main = screen.getByRole('main')
      expect(main).toBeInTheDocument()
    })

    it('handles empty string children', () => {
      const props = {
        ...defaultProps,
        children: '',
      }

      render(<Layout {...props} />)

      const main = screen.getByRole('main')
      expect(main).toBeInTheDocument()
    })

    it('renders with empty allSections object', () => {
      const props = {
        ...defaultProps,
        allSections: {},
      }

      render(<Layout {...props} />)

      const provider = screen.getByTestId('section-provider')
      const sectionsData = JSON.parse(
        provider.getAttribute('data-sections') || '[]'
      )

      expect(sectionsData).toEqual([])
    })

    it('renders with very large allSections object', () => {
      const largeSections: Record<string, Array<Section>> = {}
      for (let i = 0; i < 100; i++) {
        largeSections[`/page${i}`] = [
          { id: `section${i}`, title: `Section ${i}` },
        ]
      }

      const props = {
        ...defaultProps,
        allSections: largeSections,
      }

      render(<Layout {...props} />)

      expect(screen.getByTestId('section-provider')).toBeInTheDocument()
    })

    it('handles rapid sidebar toggle state changes', () => {
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: false,
      })

      const { container, rerender } = render(<Layout {...defaultProps} />)

      // Toggle multiple times
      for (let i = 0; i < 5; i++) {
        mockUseUIStore.mockReturnValue({
          isSidebarHidden: i % 2 === 1,
        })
        rerender(<Layout {...defaultProps} />)
      }

      // Should still render correctly
      expect(screen.getByTestId('navigation')).toBeInTheDocument()
    })

    it('handles hydration state changes', () => {
      mockUseHydration.mockReturnValue(false)
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: true,
      })

      const { rerender, container } = render(<Layout {...defaultProps} />)

      // Before hydration, sidebar shown
      let innerDiv = container.querySelector('.relative.flex.h-full.flex-col')
      expect(innerDiv).toHaveClass('lg:ml-64')

      // After hydration
      mockUseHydration.mockReturnValue(true)
      rerender(<Layout {...defaultProps} />)

      innerDiv = container.querySelector('.relative.flex.h-full.flex-col')
      expect(innerDiv).not.toHaveClass('lg:ml-64')
    })

    it('handles pathname changes without errors', () => {
      mockUsePathname.mockReturnValue('/')

      const { rerender } = render(<Layout {...defaultProps} />)

      const pathnames = ['/', '/dashboard', '/unknown', null, '/']
      pathnames.forEach((pathname) => {
        mockUsePathname.mockReturnValue(pathname)
        expect(() => rerender(<Layout {...defaultProps} />)).not.toThrow()
      })
    })

    it('renders deeply nested children correctly', () => {
      const deeplyNested = (
        <div>
          <div>
            <div>
              <div>
                <div>
                  <span>Deep Content</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )

      const props = {
        ...defaultProps,
        children: deeplyNested,
      }

      render(<Layout {...props} />)

      expect(screen.getByText('Deep Content')).toBeInTheDocument()
    })

    it('handles special characters in section IDs', () => {
      const props = {
        ...defaultProps,
        allSections: {
          '/test': [
            { id: 'section-with-dashes', title: 'Test' },
            { id: 'section_with_underscores', title: 'Test' },
            { id: 'section.with.dots', title: 'Test' },
          ],
        },
      }

      mockUsePathname.mockReturnValue('/test')

      render(<Layout {...props} />)

      const provider = screen.getByTestId('section-provider')
      expect(provider).toBeInTheDocument()
    })
  })

  describe('Dark Mode', () => {
    it('sidebar has dark mode classes', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const sidebarInner = container.querySelector('.lg\\:dark\\:bg-zinc-900')
      expect(sidebarInner).toHaveClass(
        'lg:dark:bg-zinc-900',
        'lg:dark:border-white/10'
      )
    })

    it('maintains layout structure in dark mode', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const main = screen.getByRole('main')
      const sidebar = container.querySelector('aside')

      expect(main).toBeInTheDocument()
      expect(sidebar).toBeInTheDocument()
    })
  })

  describe('Responsive Layout', () => {
    it('applies responsive margin classes to main content', () => {
      mockUseUIStore.mockReturnValue({
        isSidebarHidden: false,
      })

      const { container } = render(<Layout {...defaultProps} />)

      const innerDiv = container.querySelector('.relative.flex.h-full.flex-col')
      expect(innerDiv).toHaveClass('lg:ml-64', 'xl:ml-72', '2xl:ml-80')
    })

    it('applies responsive sidebar width classes', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const sidebarInner = container.querySelector('.lg\\:w-64')
      expect(sidebarInner).toHaveClass('lg:w-64', 'xl:w-72', '2xl:w-80')
    })

    it('sidebar is hidden on mobile', () => {
      render(<Layout {...defaultProps} />)

      const navigation = screen.getByTestId('navigation')
      expect(navigation).toHaveClass('hidden', 'lg:block')
    })

    it('applies correct z-index layers', () => {
      const { container } = render(<Layout {...defaultProps} />)

      const header = screen.getByTestId('header')
      const sidebar = container.querySelector('aside')

      // Header should have higher z-index classes visible
      // Sidebar should have z-30
      expect(sidebar).toHaveClass('lg:z-30')
    })
  })

  describe('Animation and Timing', () => {
    it('sets up animation delay timeout on hydration', () => {
      mockUseHydration.mockReturnValue(true)

      const setTimeoutSpy = jest.spyOn(global, 'setTimeout')

      render(<Layout {...defaultProps} />)

      expect(setTimeoutSpy).toHaveBeenCalled()

      setTimeoutSpy.mockRestore()
    })

    it('cleans up timeout on unmount', () => {
      mockUseHydration.mockReturnValue(true)

      const clearTimeoutSpy = jest.spyOn(global, 'clearTimeout')

      const { unmount } = render(<Layout {...defaultProps} />)

      unmount()

      // Component should clean up its timeout
      expect(clearTimeoutSpy).toHaveBeenCalled()

      clearTimeoutSpy.mockRestore()
    })

    it('handles hydration state correctly before timeout completes', async () => {
      mockUseHydration.mockReturnValue(false)

      const { rerender } = render(<Layout {...defaultProps} />)

      mockUseHydration.mockReturnValue(true)

      rerender(<Layout {...defaultProps} />)

      // Should still render correctly before timeout
      expect(screen.getByTestId('navigation')).toBeInTheDocument()

      // Advance timers
      jest.advanceTimersByTime(100)

      await waitFor(() => {
        expect(screen.getByTestId('navigation')).toBeInTheDocument()
      })
    })
  })
})

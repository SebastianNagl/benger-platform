/**
 * @jest-environment jsdom
 */

import { useUIStore } from '@/stores'
import { render, screen } from '@testing-library/react'
import { LegacyContainer, ResponsiveContainer } from '../ResponsiveContainer'

describe('ResponsiveContainer', () => {
  beforeEach(() => {
    useUIStore.setState({ isSidebarHidden: false, isHydrated: true })
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders without crashing', () => {
      const { container } = render(
        <ResponsiveContainer>
          <div>Test content</div>
        </ResponsiveContainer>
      )
      expect(container.firstChild).toBeInTheDocument()
    })

    it('renders as a div element', () => {
      const { container } = render(
        <ResponsiveContainer>
          <div>Test content</div>
        </ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element.tagName).toBe('DIV')
    })

    it('applies transition classes by default', () => {
      const { container } = render(
        <ResponsiveContainer>
          <div>Test content</div>
        </ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('transition-all')
      expect(element).toHaveClass('duration-300')
    })
  })

  describe('Children Rendering', () => {
    it('renders single child correctly', () => {
      render(
        <ResponsiveContainer>
          <p data-testid="child">Test content</p>
        </ResponsiveContainer>
      )
      expect(screen.getByTestId('child')).toBeInTheDocument()
      expect(screen.getByTestId('child')).toHaveTextContent('Test content')
    })

    it('renders multiple children correctly', () => {
      render(
        <ResponsiveContainer>
          <h1 data-testid="heading">Heading</h1>
          <p data-testid="paragraph">Paragraph</p>
          <button data-testid="button">Button</button>
        </ResponsiveContainer>
      )
      expect(screen.getByTestId('heading')).toBeInTheDocument()
      expect(screen.getByTestId('paragraph')).toBeInTheDocument()
      expect(screen.getByTestId('button')).toBeInTheDocument()
    })

    it('renders complex nested children', () => {
      render(
        <ResponsiveContainer>
          <div>
            <div>
              <span data-testid="nested">Nested content</span>
            </div>
          </div>
        </ResponsiveContainer>
      )
      expect(screen.getByTestId('nested')).toBeInTheDocument()
    })

    it('renders text node children', () => {
      render(<ResponsiveContainer>Plain text content</ResponsiveContainer>)
      expect(screen.getByText('Plain text content')).toBeInTheDocument()
    })

    it('renders fragment children', () => {
      render(
        <ResponsiveContainer>
          <>
            <span data-testid="first">First</span>
            <span data-testid="second">Second</span>
          </>
        </ResponsiveContainer>
      )
      expect(screen.getByTestId('first')).toBeInTheDocument()
      expect(screen.getByTestId('second')).toBeInTheDocument()
    })
  })

  describe('Container Width/MaxWidth', () => {
    describe('Size: sm', () => {
      it('applies correct classes when sidebar is visible', () => {
        useUIStore.setState({ isSidebarHidden: false })
        const { container } = render(
          <ResponsiveContainer size="sm">Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-2xl')
        expect(element).toHaveClass('3xl:max-w-3xl')
        expect(element).toHaveClass('4xl:max-w-4xl')
        expect(element).toHaveClass('5xl:max-w-5xl')
      })

      it('applies correct classes when sidebar is hidden', () => {
        useUIStore.setState({ isSidebarHidden: true })
        const { container } = render(
          <ResponsiveContainer size="sm">Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-3xl')
        expect(element).toHaveClass('3xl:max-w-5xl')
        expect(element).toHaveClass('4xl:max-w-6xl')
        expect(element).toHaveClass('5xl:max-w-7xl')
      })

      it('applies non-adaptive classes when adaptToSidebar is false', () => {
        useUIStore.setState({ isSidebarHidden: true })
        const { container } = render(
          <ResponsiveContainer size="sm" adaptToSidebar={false}>
            Content
          </ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-2xl')
        expect(element).toHaveClass('3xl:max-w-3xl')
      })
    })

    describe('Size: md', () => {
      it('applies correct classes when sidebar is visible', () => {
        useUIStore.setState({ isSidebarHidden: false })
        const { container } = render(
          <ResponsiveContainer size="md">Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-3xl')
        expect(element).toHaveClass('3xl:max-w-4xl')
        expect(element).toHaveClass('4xl:max-w-5xl')
        expect(element).toHaveClass('5xl:max-w-6xl')
      })

      it('applies correct classes when sidebar is hidden', () => {
        useUIStore.setState({ isSidebarHidden: true })
        const { container } = render(
          <ResponsiveContainer size="md">Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-5xl')
        expect(element).toHaveClass('3xl:max-w-6xl')
        expect(element).toHaveClass('4xl:max-w-7xl')
        expect(element).toHaveClass('5xl:max-w-8xl')
      })

      it('applies non-adaptive classes when adaptToSidebar is false', () => {
        useUIStore.setState({ isSidebarHidden: true })
        const { container } = render(
          <ResponsiveContainer size="md" adaptToSidebar={false}>
            Content
          </ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-3xl')
        expect(element).toHaveClass('3xl:max-w-4xl')
      })
    })

    describe('Size: lg (default)', () => {
      it('applies correct classes when sidebar is visible', () => {
        useUIStore.setState({ isSidebarHidden: false })
        const { container } = render(
          <ResponsiveContainer>Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-4xl')
        expect(element).toHaveClass('3xl:max-w-5xl')
        expect(element).toHaveClass('4xl:max-w-6xl')
        expect(element).toHaveClass('5xl:max-w-7xl')
      })

      it('applies correct classes when sidebar is hidden', () => {
        useUIStore.setState({ isSidebarHidden: true })
        const { container } = render(
          <ResponsiveContainer>Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-6xl')
        expect(element).toHaveClass('3xl:max-w-7xl')
        expect(element).toHaveClass('4xl:max-w-8xl')
        expect(element).toHaveClass('5xl:max-w-9xl')
      })

      it('applies non-adaptive classes when adaptToSidebar is false', () => {
        useUIStore.setState({ isSidebarHidden: true })
        const { container } = render(
          <ResponsiveContainer adaptToSidebar={false}>
            Content
          </ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-4xl')
        expect(element).toHaveClass('3xl:max-w-5xl')
      })
    })

    describe('Size: xl', () => {
      it('applies correct classes when sidebar is visible', () => {
        useUIStore.setState({ isSidebarHidden: false })
        const { container } = render(
          <ResponsiveContainer size="xl">Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-5xl')
        expect(element).toHaveClass('3xl:max-w-6xl')
        expect(element).toHaveClass('4xl:max-w-7xl')
        expect(element).toHaveClass('5xl:max-w-8xl')
      })

      it('applies correct classes when sidebar is hidden', () => {
        useUIStore.setState({ isSidebarHidden: true })
        const { container } = render(
          <ResponsiveContainer size="xl">Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-7xl')
        expect(element).toHaveClass('3xl:max-w-8xl')
        expect(element).toHaveClass('4xl:max-w-9xl')
        expect(element).toHaveClass('5xl:max-w-none')
      })

      it('applies non-adaptive classes when adaptToSidebar is false', () => {
        useUIStore.setState({ isSidebarHidden: true })
        const { container } = render(
          <ResponsiveContainer size="xl" adaptToSidebar={false}>
            Content
          </ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('max-w-5xl')
        expect(element).toHaveClass('3xl:max-w-6xl')
      })
    })

    describe('Size: full', () => {
      it('does not apply max-width classes', () => {
        const { container } = render(
          <ResponsiveContainer size="full">Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element.className).not.toContain('max-w-')
      })

      it('does not apply mx-auto class', () => {
        const { container } = render(
          <ResponsiveContainer size="full">Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).not.toHaveClass('mx-auto')
      })

      it('ignores sidebar state when size is full', () => {
        useUIStore.setState({ isSidebarHidden: true })
        const { container } = render(
          <ResponsiveContainer size="full">Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element.className).not.toContain('max-w-')
      })
    })

    it('applies mx-auto class for all non-full sizes', () => {
      const sizes = ['sm', 'md', 'lg', 'xl'] as const
      sizes.forEach((size) => {
        const { container } = render(
          <ResponsiveContainer size={size}>Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('mx-auto')
      })
    })
  })

  describe('Padding and Spacing', () => {
    it('applies default padding classes for non-full sizes', () => {
      const { container } = render(
        <ResponsiveContainer>Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('px-4')
      expect(element).toHaveClass('sm:px-6')
      expect(element).toHaveClass('3xl:px-8')
      expect(element).toHaveClass('4xl:px-10')
      expect(element).toHaveClass('5xl:px-12')
    })

    it('does not apply padding classes for full size', () => {
      const { container } = render(
        <ResponsiveContainer size="full">Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element.className).not.toContain('px-')
    })

    it('applies consistent padding across all standard sizes', () => {
      const sizes = ['sm', 'md', 'lg', 'xl'] as const
      sizes.forEach((size) => {
        const { container } = render(
          <ResponsiveContainer size={size}>Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('px-4')
        expect(element).toHaveClass('sm:px-6')
        expect(element).toHaveClass('3xl:px-8')
      })
    })
  })

  describe('Props/Attributes', () => {
    it('applies custom className', () => {
      const { container } = render(
        <ResponsiveContainer className="custom-class">
          Content
        </ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('custom-class')
    })

    it('merges custom className with default classes', () => {
      const { container } = render(
        <ResponsiveContainer className="custom-class">
          Content
        </ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('custom-class')
      expect(element).toHaveClass('transition-all')
      expect(element).toHaveClass('mx-auto')
    })

    it('handles multiple custom classes', () => {
      const { container } = render(
        <ResponsiveContainer className="class-one class-two class-three">
          Content
        </ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('class-one')
      expect(element).toHaveClass('class-two')
      expect(element).toHaveClass('class-three')
    })

    it('defaults to lg size when size prop is not provided', () => {
      const { container } = render(
        <ResponsiveContainer>Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('max-w-4xl')
    })

    it('defaults to adaptToSidebar true when not provided', () => {
      useUIStore.setState({ isSidebarHidden: true })
      const { container } = render(
        <ResponsiveContainer size="sm">Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('max-w-3xl')
    })
  })

  describe('Styling', () => {
    it('applies transition-all duration-300 classes', () => {
      const { container } = render(
        <ResponsiveContainer>Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('transition-all')
      expect(element).toHaveClass('duration-300')
    })

    it('maintains consistent styling across sizes', () => {
      const sizes = ['sm', 'md', 'lg', 'xl'] as const
      sizes.forEach((size) => {
        const { container } = render(
          <ResponsiveContainer size={size}>Content</ResponsiveContainer>
        )
        const element = container.firstChild as HTMLElement
        expect(element).toHaveClass('transition-all')
        expect(element).toHaveClass('duration-300')
      })
    })

    it('allows custom className to override default styles', () => {
      const { container } = render(
        <ResponsiveContainer className="duration-500">
          Content
        </ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('duration-500')
    })
  })

  describe('Edge Cases', () => {
    it('handles empty string children', () => {
      const { container } = render(
        <ResponsiveContainer>{''}</ResponsiveContainer>
      )
      expect(container.firstChild).toBeInTheDocument()
    })

    it('handles zero as children', () => {
      render(<ResponsiveContainer>{0}</ResponsiveContainer>)
      expect(screen.getByText('0')).toBeInTheDocument()
    })

    it('handles boolean children', () => {
      const { container } = render(
        <ResponsiveContainer>{true}</ResponsiveContainer>
      )
      expect(container.firstChild).toBeInTheDocument()
    })

    it('handles null className', () => {
      const { container } = render(
        <ResponsiveContainer className={undefined}>Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toBeInTheDocument()
    })

    it('handles empty string className', () => {
      const { container } = render(
        <ResponsiveContainer className="">Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toBeInTheDocument()
    })

    it('handles multiple consecutive spaces in className', () => {
      const { container } = render(
        <ResponsiveContainer className="class-one class-two">
          Content
        </ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toBeInTheDocument()
    })
  })

  describe('Responsive Breakpoints', () => {
    it('applies responsive classes for sm breakpoint', () => {
      const { container } = render(
        <ResponsiveContainer>Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('sm:px-6')
    })

    it('applies responsive classes for 3xl breakpoint', () => {
      const { container } = render(
        <ResponsiveContainer>Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('3xl:px-8')
      expect(element).toHaveClass('3xl:max-w-5xl')
    })

    it('applies responsive classes for 4xl breakpoint', () => {
      const { container } = render(
        <ResponsiveContainer>Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('4xl:px-10')
      expect(element).toHaveClass('4xl:max-w-6xl')
    })

    it('applies responsive classes for 5xl breakpoint', () => {
      const { container } = render(
        <ResponsiveContainer>Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('5xl:px-12')
      expect(element).toHaveClass('5xl:max-w-7xl')
    })

    it('applies all responsive breakpoints in correct order', () => {
      const { container } = render(
        <ResponsiveContainer size="md">Content</ResponsiveContainer>
      )
      const element = container.firstChild as HTMLElement
      const className = element.className
      expect(className).toContain('px-4')
      expect(className).toContain('sm:px-6')
      expect(className).toContain('3xl:px-8')
      expect(className).toContain('4xl:px-10')
      expect(className).toContain('5xl:px-12')
    })
  })

  describe('Sidebar State Integration', () => {
    it('reacts to sidebar state changes', () => {
      useUIStore.setState({ isSidebarHidden: false })
      const { container, rerender } = render(
        <ResponsiveContainer size="sm">Content</ResponsiveContainer>
      )
      let element = container.firstChild as HTMLElement
      expect(element).toHaveClass('max-w-2xl')

      useUIStore.setState({ isSidebarHidden: true })
      rerender(<ResponsiveContainer size="sm">Content</ResponsiveContainer>)
      element = container.firstChild as HTMLElement
      expect(element).toHaveClass('max-w-3xl')
    })

    it('ignores sidebar state when adaptToSidebar is false', () => {
      useUIStore.setState({ isSidebarHidden: false })
      const { container, rerender } = render(
        <ResponsiveContainer size="sm" adaptToSidebar={false}>
          Content
        </ResponsiveContainer>
      )
      let element = container.firstChild as HTMLElement
      expect(element).toHaveClass('max-w-2xl')

      useUIStore.setState({ isSidebarHidden: true })
      rerender(
        <ResponsiveContainer size="sm" adaptToSidebar={false}>
          Content
        </ResponsiveContainer>
      )
      element = container.firstChild as HTMLElement
      expect(element).toHaveClass('max-w-2xl')
    })
  })

  describe('Multiple Instances', () => {
    it('renders multiple containers independently', () => {
      const { container } = render(
        <>
          <ResponsiveContainer size="sm">
            <div data-testid="container-1">Container 1</div>
          </ResponsiveContainer>
          <ResponsiveContainer size="xl">
            <div data-testid="container-2">Container 2</div>
          </ResponsiveContainer>
        </>
      )

      expect(screen.getByTestId('container-1')).toBeInTheDocument()
      expect(screen.getByTestId('container-2')).toBeInTheDocument()

      const containers = container.querySelectorAll('.transition-all')
      expect(containers).toHaveLength(2)
    })

    it('applies different sizes to multiple containers', () => {
      const { container } = render(
        <>
          <ResponsiveContainer size="sm">Content 1</ResponsiveContainer>
          <ResponsiveContainer size="xl">Content 2</ResponsiveContainer>
        </>
      )

      const containers = container.querySelectorAll('.transition-all')
      expect(containers[0]).toHaveClass('max-w-2xl')
      expect(containers[1]).toHaveClass('max-w-5xl')
    })
  })
})

describe('LegacyContainer', () => {
  describe('Basic Rendering', () => {
    it('renders without crashing', () => {
      const { container } = render(
        <LegacyContainer>
          <div>Test content</div>
        </LegacyContainer>
      )
      expect(container.firstChild).toBeInTheDocument()
    })

    it('renders as a div element', () => {
      const { container } = render(
        <LegacyContainer>
          <div>Test content</div>
        </LegacyContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element.tagName).toBe('DIV')
    })
  })

  describe('Children Rendering', () => {
    it('renders children correctly', () => {
      render(
        <LegacyContainer>
          <p data-testid="child">Legacy content</p>
        </LegacyContainer>
      )
      expect(screen.getByTestId('child')).toBeInTheDocument()
      expect(screen.getByTestId('child')).toHaveTextContent('Legacy content')
    })

    it('renders multiple children', () => {
      render(
        <LegacyContainer>
          <h1 data-testid="heading">Heading</h1>
          <p data-testid="paragraph">Paragraph</p>
        </LegacyContainer>
      )
      expect(screen.getByTestId('heading')).toBeInTheDocument()
      expect(screen.getByTestId('paragraph')).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('applies legacy layout classes', () => {
      const { container } = render(<LegacyContainer>Content</LegacyContainer>)
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('mx-auto')
      expect(element).toHaveClass('max-w-2xl')
      expect(element).toHaveClass('pb-10')
      expect(element).toHaveClass('pt-16')
    })

    it('applies responsive classes', () => {
      const { container } = render(<LegacyContainer>Content</LegacyContainer>)
      const element = container.firstChild as HTMLElement
      expect(element.className).toContain('lg:mx-')
      expect(element.className).toContain('lg:max-w-3xl')
      expect(element.className).toContain('3xl:max-w-4xl')
      expect(element.className).toContain('4xl:max-w-5xl')
      expect(element.className).toContain('5xl:max-w-6xl')
    })

    it('applies custom className', () => {
      const { container } = render(
        <LegacyContainer className="custom-legacy-class">
          Content
        </LegacyContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('custom-legacy-class')
      expect(element).toHaveClass('mx-auto')
    })

    it('merges custom className with default classes', () => {
      const { container } = render(
        <LegacyContainer className="custom-class">Content</LegacyContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toHaveClass('custom-class')
      expect(element).toHaveClass('max-w-2xl')
      expect(element).toHaveClass('pb-10')
    })
  })

  describe('Edge Cases', () => {
    it('handles empty children', () => {
      const { container } = render(<LegacyContainer>{''}</LegacyContainer>)
      expect(container.firstChild).toBeInTheDocument()
    })

    it('handles undefined className', () => {
      const { container } = render(
        <LegacyContainer className={undefined}>Content</LegacyContainer>
      )
      const element = container.firstChild as HTMLElement
      expect(element).toBeInTheDocument()
    })
  })

  describe('Multiple Instances', () => {
    it('renders multiple legacy containers independently', () => {
      const { container } = render(
        <>
          <LegacyContainer>
            <div data-testid="legacy-1">Legacy 1</div>
          </LegacyContainer>
          <LegacyContainer>
            <div data-testid="legacy-2">Legacy 2</div>
          </LegacyContainer>
        </>
      )

      expect(screen.getByTestId('legacy-1')).toBeInTheDocument()
      expect(screen.getByTestId('legacy-2')).toBeInTheDocument()

      const containers = container.querySelectorAll('.max-w-2xl')
      expect(containers.length).toBeGreaterThanOrEqual(2)
    })
  })
})

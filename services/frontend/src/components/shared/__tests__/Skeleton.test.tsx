/**
 * @jest-environment jsdom
 */

import { render } from '@testing-library/react'
import { Skeleton } from '../Skeleton'

describe('Skeleton Component', () => {
  describe('Basic Rendering', () => {
    it('renders div element', () => {
      const { container } = render(<Skeleton />)

      const skeleton = container.firstChild
      expect(skeleton).toBeInTheDocument()
      expect(skeleton?.nodeName).toBe('DIV')
    })

    it('renders with default rectangular variant', () => {
      const { container } = render(<Skeleton />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('rounded-md')
    })

    it('applies pulse animation', () => {
      const { container } = render(<Skeleton />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('animate-pulse')
    })

    it('applies background colors', () => {
      const { container } = render(<Skeleton />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('bg-zinc-200', 'dark:bg-zinc-700')
    })
  })

  describe('Variant - Rectangular', () => {
    it('applies rectangular variant when specified', () => {
      const { container } = render(<Skeleton variant="rectangular" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('rounded-md')
    })

    it('rectangular is the default variant', () => {
      const { container } = render(<Skeleton />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('rounded-md')
    })

    it('does not apply circular or text styles', () => {
      const { container } = render(<Skeleton variant="rectangular" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).not.toHaveClass('rounded-full')
      expect(skeleton).not.toHaveClass('h-4')
      expect(skeleton).not.toHaveClass('w-full')
    })
  })

  describe('Variant - Circular', () => {
    it('applies circular variant styling', () => {
      const { container } = render(<Skeleton variant="circular" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('rounded-full')
    })

    it('does not apply rectangular styling', () => {
      const { container } = render(<Skeleton variant="circular" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).not.toHaveClass('rounded-md')
    })

    it('circular skeleton maintains pulse animation', () => {
      const { container } = render(<Skeleton variant="circular" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('animate-pulse')
    })
  })

  describe('Variant - Text', () => {
    it('applies text variant styling', () => {
      const { container } = render(<Skeleton variant="text" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('h-4', 'w-full', 'rounded')
    })

    it('does not apply other variant styles', () => {
      const { container } = render(<Skeleton variant="text" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).not.toHaveClass('rounded-md')
      expect(skeleton).not.toHaveClass('rounded-full')
    })

    it('text skeleton maintains pulse animation', () => {
      const { container } = render(<Skeleton variant="text" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('animate-pulse')
    })

    it('text skeleton has full width', () => {
      const { container } = render(<Skeleton variant="text" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('w-full')
    })

    it('text skeleton has fixed height', () => {
      const { container } = render(<Skeleton variant="text" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('h-4')
    })
  })

  describe('Custom Styling', () => {
    it('applies custom className', () => {
      const { container } = render(<Skeleton className="custom-skeleton" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('custom-skeleton')
    })

    it('merges custom className with default classes', () => {
      const { container } = render(<Skeleton className="h-20 w-20" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('w-20', 'h-20')
      expect(skeleton).toHaveClass('animate-pulse', 'bg-zinc-200')
    })

    it('custom width and height override defaults', () => {
      const { container } = render(
        <Skeleton variant="text" className="h-8 w-32" />
      )

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('w-32', 'h-8')
    })

    it('supports multiple custom classes', () => {
      const { container } = render(
        <Skeleton className="m-4 p-2 opacity-75 shadow-lg" />
      )

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('m-4', 'p-2', 'shadow-lg', 'opacity-75')
    })

    it('custom border radius can override variant', () => {
      const { container } = render(<Skeleton className="rounded-none" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('rounded-none')
    })
  })

  describe('Dark Mode Support', () => {
    it('applies dark mode background class', () => {
      const { container } = render(<Skeleton />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('dark:bg-zinc-700')
    })

    it('dark mode class present in all variants', () => {
      const { container: rectContainer } = render(
        <Skeleton variant="rectangular" />
      )
      const { container: circContainer } = render(
        <Skeleton variant="circular" />
      )
      const { container: textContainer } = render(<Skeleton variant="text" />)

      expect(rectContainer.firstChild).toHaveClass('dark:bg-zinc-700')
      expect(circContainer.firstChild).toHaveClass('dark:bg-zinc-700')
      expect(textContainer.firstChild).toHaveClass('dark:bg-zinc-700')
    })
  })

  describe('Common Use Cases', () => {
    it('renders avatar skeleton', () => {
      const { container } = render(
        <Skeleton variant="circular" className="h-12 w-12" />
      )

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('rounded-full', 'h-12', 'w-12')
    })

    it('renders text line skeleton', () => {
      const { container } = render(<Skeleton variant="text" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('h-4', 'w-full')
    })

    it('renders card skeleton', () => {
      const { container } = render(<Skeleton className="h-48 w-full" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('h-48', 'w-full', 'rounded-md')
    })

    it('renders button skeleton', () => {
      const { container } = render(<Skeleton className="h-10 w-24" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('h-10', 'w-24')
    })

    it('renders image skeleton', () => {
      const { container } = render(
        <Skeleton variant="rectangular" className="aspect-video w-full" />
      )

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('aspect-video', 'w-full', 'rounded-md')
    })
  })

  describe('Multiple Skeletons', () => {
    it('renders multiple text skeletons', () => {
      const { container } = render(
        <div>
          <Skeleton variant="text" />
          <Skeleton variant="text" />
          <Skeleton variant="text" />
        </div>
      )

      const skeletons = container.querySelectorAll('.animate-pulse')
      expect(skeletons).toHaveLength(3)
    })

    it('renders skeleton list', () => {
      const { container } = render(
        <div>
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="mb-2" />
          ))}
        </div>
      )

      const skeletons = container.querySelectorAll('.animate-pulse')
      expect(skeletons).toHaveLength(5)
    })

    it('combines different variants', () => {
      const { container } = render(
        <div>
          <Skeleton variant="circular" className="h-12 w-12" />
          <Skeleton variant="text" />
          <Skeleton variant="rectangular" className="h-32" />
        </div>
      )

      const skeletons = container.querySelectorAll('.animate-pulse')
      expect(skeletons).toHaveLength(3)

      expect(skeletons[0]).toHaveClass('rounded-full')
      expect(skeletons[1]).toHaveClass('w-full', 'h-4')
      expect(skeletons[2]).toHaveClass('rounded-md')
    })
  })

  describe('Edge Cases', () => {
    it('renders with empty className', () => {
      const { container } = render(<Skeleton className="" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toBeInTheDocument()
      expect(skeleton).toHaveClass('animate-pulse')
    })

    it('handles undefined className', () => {
      const { container } = render(<Skeleton className={undefined} />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toBeInTheDocument()
    })

    it('renders with very small dimensions', () => {
      const { container } = render(<Skeleton className="h-1 w-1" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('h-1', 'w-1')
    })

    it('renders with very large dimensions', () => {
      const { container } = render(<Skeleton className="h-96 w-96" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('h-96', 'w-96')
    })

    it('handles custom aspect ratios', () => {
      const { container } = render(
        <Skeleton className="aspect-square w-full" />
      )

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('aspect-square', 'w-full')
    })

    it('supports custom background color override', () => {
      const { container } = render(<Skeleton className="bg-blue-200" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('bg-blue-200')
    })

    it('supports custom animation override', () => {
      const { container } = render(<Skeleton className="animate-bounce" />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('animate-bounce')
    })

    it('renders without crashing with all props', () => {
      const { container } = render(
        <Skeleton variant="circular" className="h-20 w-20 shadow-xl" />
      )

      expect(container.firstChild).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('renders as div element for screen readers', () => {
      const { container } = render(<Skeleton />)

      const skeleton = container.firstChild
      expect(skeleton?.nodeName).toBe('DIV')
    })

    it('does not interfere with keyboard navigation', () => {
      const { container } = render(
        <div>
          <button>Before</button>
          <Skeleton />
          <button>After</button>
        </div>
      )

      const skeleton = container.querySelector('.animate-pulse')
      expect(skeleton).not.toHaveAttribute('tabIndex')
    })

    it('is purely visual without interactive elements', () => {
      const { container } = render(<Skeleton />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton.tagName).toBe('DIV')
      expect(skeleton).not.toHaveAttribute('role')
      expect(skeleton).not.toHaveAttribute('aria-label')
    })
  })

  describe('Loading Patterns', () => {
    it('renders loading card pattern', () => {
      const { container } = render(
        <div className="space-y-3">
          <Skeleton variant="rectangular" className="h-48 w-full" />
          <Skeleton variant="text" />
          <Skeleton variant="text" className="w-3/4" />
        </div>
      )

      const skeletons = container.querySelectorAll('.animate-pulse')
      expect(skeletons).toHaveLength(3)
    })

    it('renders loading profile pattern', () => {
      const { container } = render(
        <div className="flex items-center space-x-3">
          <Skeleton variant="circular" className="h-12 w-12" />
          <div className="flex-1 space-y-2">
            <Skeleton variant="text" className="w-1/2" />
            <Skeleton variant="text" className="w-1/4" />
          </div>
        </div>
      )

      const skeletons = container.querySelectorAll('.animate-pulse')
      expect(skeletons).toHaveLength(3)
    })

    it('renders loading list pattern', () => {
      const { container } = render(
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center space-x-3">
              <Skeleton variant="circular" className="h-10 w-10" />
              <div className="flex-1">
                <Skeleton variant="text" />
              </div>
            </div>
          ))}
        </div>
      )

      const skeletons = container.querySelectorAll('.animate-pulse')
      expect(skeletons).toHaveLength(6) // 3 circular + 3 text
    })
  })
})

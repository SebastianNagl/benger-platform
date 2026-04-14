import { render, screen } from '@testing-library/react'
import {
  LoadingSpinner,
  LoadingState,
  ModelListSkeleton,
  PromptListSkeleton,
  Skeleton,
} from '../LoadingStates'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'common.loading': 'Loading...',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

describe('LoadingStates Components', () => {
  describe('LoadingSpinner', () => {
    describe('basic rendering', () => {
      it('renders with default props', () => {
        const { container } = render(<LoadingSpinner />)

        const spinner = container.firstChild as HTMLElement
        expect(spinner).toBeInTheDocument()
        expect(spinner).toHaveClass('animate-spin', 'rounded-full', 'border-2')
      })

      it('renders as a div element', () => {
        const { container } = render(<LoadingSpinner />)

        const spinner = container.firstChild as HTMLElement
        expect(spinner.tagName).toBe('DIV')
      })

      it('applies custom className', () => {
        const { container } = render(
          <LoadingSpinner className="custom-spinner" />
        )

        const spinner = container.firstChild as HTMLElement
        expect(spinner).toHaveClass('custom-spinner')
      })
    })

    describe('size variants', () => {
      it('applies small size classes', () => {
        const { container } = render(<LoadingSpinner size="sm" />)

        const spinner = container.firstChild as HTMLElement
        expect(spinner).toHaveClass('h-4', 'w-4')
      })

      it('applies medium size classes by default', () => {
        const { container } = render(<LoadingSpinner />)

        const spinner = container.firstChild as HTMLElement
        expect(spinner).toHaveClass('h-6', 'w-6')
      })

      it('applies large size classes', () => {
        const { container } = render(<LoadingSpinner size="lg" />)

        const spinner = container.firstChild as HTMLElement
        expect(spinner).toHaveClass('h-8', 'w-8')
      })
    })

    describe('styling', () => {
      it('applies base spinner styles', () => {
        const { container } = render(<LoadingSpinner />)

        const spinner = container.firstChild as HTMLElement
        expect(spinner).toHaveClass(
          'animate-spin',
          'rounded-full',
          'border-2',
          'border-zinc-300',
          'border-t-blue-600'
        )
      })

      it('applies dark mode styles', () => {
        const { container } = render(<LoadingSpinner />)

        const spinner = container.firstChild as HTMLElement
        expect(spinner).toHaveClass(
          'dark:border-zinc-600',
          'dark:border-t-blue-400'
        )
      })

      it('combines size and custom className correctly', () => {
        const { container } = render(
          <LoadingSpinner size="lg" className="my-custom-class" />
        )

        const spinner = container.firstChild as HTMLElement
        expect(spinner).toHaveClass('h-8', 'w-8', 'my-custom-class')
      })
    })
  })

  describe('LoadingState', () => {
    describe('basic rendering', () => {
      it('renders with default props', () => {
        render(<LoadingState />)

        expect(screen.getByText('Loading...')).toBeInTheDocument()
      })

      it('renders with custom message', () => {
        render(<LoadingState message="Loading data..." />)

        expect(screen.getByText('Loading data...')).toBeInTheDocument()
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      it('applies custom className', () => {
        const { container } = render(
          <LoadingState className="custom-loading" />
        )

        const loadingContainer = container.firstChild as HTMLElement
        expect(loadingContainer).toHaveClass('custom-loading')
      })
    })

    describe('structure and layout', () => {
      it('has correct layout structure', () => {
        const { container } = render(<LoadingState />)

        const mainContainer = container.firstChild as HTMLElement
        expect(mainContainer).toHaveClass(
          'flex',
          'items-center',
          'justify-center',
          'py-8'
        )

        const innerContainer = mainContainer.querySelector('.text-center')
        expect(innerContainer).toBeInTheDocument()
      })

      it('includes LoadingSpinner with large size', () => {
        const { container } = render(<LoadingState />)

        const spinner = container.querySelector('.animate-spin')
        expect(spinner).toBeInTheDocument()
        expect(spinner).toHaveClass('h-8', 'w-8', 'mx-auto', 'mb-4')
      })

      it('styles message text correctly', () => {
        render(<LoadingState message="Test message" />)

        const message = screen.getByText('Test message')
        expect(message.tagName).toBe('P')
        expect(message).toHaveClass(
          'text-sm',
          'text-zinc-600',
          'dark:text-zinc-400'
        )
      })
    })

    describe('message handling', () => {
      it('handles empty message', () => {
        const { container } = render(<LoadingState message="" />)

        const paragraph = container.querySelector('p')
        expect(paragraph).toBeInTheDocument()
        expect(paragraph).toHaveTextContent('')
      })

      it('handles long messages', () => {
        const longMessage =
          'This is a very long loading message that should still render correctly'
        render(<LoadingState message={longMessage} />)

        expect(screen.getByText(longMessage)).toBeInTheDocument()
      })

      it('handles special characters in message', () => {
        const specialMessage = 'Loading... 50% (α/β) complete!'
        render(<LoadingState message={specialMessage} />)

        expect(screen.getByText(specialMessage)).toBeInTheDocument()
      })
    })
  })

  describe('Skeleton', () => {
    describe('basic rendering', () => {
      it('renders with default props', () => {
        const { container } = render(<Skeleton />)

        const skeleton = container.firstChild as HTMLElement
        expect(skeleton).toBeInTheDocument()
        expect(skeleton.tagName).toBe('DIV')
      })

      it('applies custom className', () => {
        const { container } = render(<Skeleton className="custom-skeleton" />)

        const skeleton = container.firstChild as HTMLElement
        expect(skeleton).toHaveClass('custom-skeleton')
      })
    })

    describe('styling', () => {
      it('applies base skeleton styles', () => {
        const { container } = render(<Skeleton />)

        const skeleton = container.firstChild as HTMLElement
        expect(skeleton).toHaveClass('animate-pulse', 'bg-zinc-200', 'rounded')
      })

      it('applies dark mode styles', () => {
        const { container } = render(<Skeleton />)

        const skeleton = container.firstChild as HTMLElement
        expect(skeleton).toHaveClass('dark:bg-zinc-700')
      })

      it('combines base styles with custom className', () => {
        const { container } = render(<Skeleton className="h-4 w-full" />)

        const skeleton = container.firstChild as HTMLElement
        expect(skeleton).toHaveClass(
          'animate-pulse',
          'bg-zinc-200',
          'rounded',
          'h-4',
          'w-full'
        )
      })
    })
  })

  describe('ModelListSkeleton', () => {
    describe('basic rendering', () => {
      it('renders with default count', () => {
        const { container } = render(<ModelListSkeleton />)

        const items = container.querySelectorAll('.flex.items-center.space-x-3')
        expect(items).toHaveLength(3) // Default count
      })

      it('renders with custom count', () => {
        const { container } = render(<ModelListSkeleton count={5} />)

        const items = container.querySelectorAll('.flex.items-center.space-x-3')
        expect(items).toHaveLength(5)
      })

      it('renders with count of 1', () => {
        const { container } = render(<ModelListSkeleton count={1} />)

        const items = container.querySelectorAll('.flex.items-center.space-x-3')
        expect(items).toHaveLength(1)
      })

      it('handles count of 0', () => {
        const { container } = render(<ModelListSkeleton count={0} />)

        const items = container.querySelectorAll('.flex.items-center.space-x-3')
        expect(items).toHaveLength(0)

        // Should still render the container
        expect(container.firstChild).toHaveClass('space-y-4')
      })
    })

    describe('structure and layout', () => {
      it('has correct outer container structure', () => {
        const { container } = render(<ModelListSkeleton />)

        const outerContainer = container.firstChild as HTMLElement
        expect(outerContainer).toHaveClass('space-y-4')
      })

      it('has correct item structure', () => {
        const { container } = render(<ModelListSkeleton count={1} />)

        const item = container.querySelector('.flex.items-center.space-x-3')
        expect(item).toHaveClass(
          'p-3',
          'border',
          'border-zinc-200',
          'dark:border-zinc-700',
          'rounded-lg'
        )
      })

      it('includes skeleton elements with correct sizing', () => {
        const { container } = render(<ModelListSkeleton count={1} />)

        const skeletons = container.querySelectorAll('.animate-pulse')
        expect(skeletons).toHaveLength(4) // Icon + 2 text lines + status

        // Check specific skeleton sizes
        const iconSkeleton = container.querySelector('.h-5.w-5')
        expect(iconSkeleton).toBeInTheDocument()

        const titleSkeleton = container.querySelector('.h-4.w-24')
        expect(titleSkeleton).toBeInTheDocument()

        const descSkeleton = container.querySelector('.h-3.w-48')
        expect(descSkeleton).toBeInTheDocument()

        const statusSkeleton = container.querySelector('.h-6.w-16')
        expect(statusSkeleton).toBeInTheDocument()
      })

      it('has correct flex layout for content area', () => {
        const { container } = render(<ModelListSkeleton count={1} />)

        const contentArea = container.querySelector('.flex-1.space-y-2')
        expect(contentArea).toBeInTheDocument()
      })
    })

    describe('multiple items', () => {
      it('generates unique keys for each item', () => {
        const { container } = render(<ModelListSkeleton count={3} />)

        const items = container.querySelectorAll('.flex.items-center.space-x-3')
        items.forEach((item, index) => {
          // Each item should be distinct (different DOM nodes)
          expect(item).toBeInTheDocument()
        })

        expect(items).toHaveLength(3)
      })

      it('maintains consistent structure across items', () => {
        const { container } = render(<ModelListSkeleton count={3} />)

        const items = container.querySelectorAll('.flex.items-center.space-x-3')
        items.forEach((item) => {
          expect(item).toHaveClass('p-3', 'border', 'rounded-lg')

          const skeletons = item.querySelectorAll('.animate-pulse')
          expect(skeletons).toHaveLength(4)
        })
      })
    })
  })

  describe('PromptListSkeleton', () => {
    describe('basic rendering', () => {
      it('renders with default count', () => {
        const { container } = render(<PromptListSkeleton />)

        const items = container.querySelectorAll('.border.border-zinc-200')
        expect(items).toHaveLength(2) // Default count
      })

      it('renders with custom count', () => {
        const { container } = render(<PromptListSkeleton count={4} />)

        const items = container.querySelectorAll('.border.border-zinc-200')
        expect(items).toHaveLength(4)
      })

      it('renders with count of 1', () => {
        const { container } = render(<PromptListSkeleton count={1} />)

        const items = container.querySelectorAll('.border.border-zinc-200')
        expect(items).toHaveLength(1)
      })

      it('handles count of 0', () => {
        const { container } = render(<PromptListSkeleton count={0} />)

        const items = container.querySelectorAll('.border.border-zinc-200')
        expect(items).toHaveLength(0)

        // Should still render the container
        expect(container.firstChild).toHaveClass('space-y-4')
      })
    })

    describe('structure and layout', () => {
      it('has correct outer container structure', () => {
        const { container } = render(<PromptListSkeleton />)

        const outerContainer = container.firstChild as HTMLElement
        expect(outerContainer).toHaveClass('space-y-4')
      })

      it('has correct item structure', () => {
        const { container } = render(<PromptListSkeleton count={1} />)

        const item = container.querySelector('.border.border-zinc-200')
        expect(item).toHaveClass(
          'border-zinc-200',
          'dark:border-zinc-700',
          'rounded-lg',
          'p-4'
        )
      })

      it('has correct header structure', () => {
        const { container } = render(<PromptListSkeleton count={1} />)

        const header = container.querySelector(
          '.flex.items-center.justify-between.mb-3'
        )
        expect(header).toBeInTheDocument()

        const headerSkeletons = header?.querySelectorAll('.animate-pulse')
        expect(headerSkeletons).toHaveLength(2) // Title + status
      })

      it('has correct content structure', () => {
        const { container } = render(<PromptListSkeleton count={1} />)

        const content = container.querySelector('.space-y-2')
        expect(content).toBeInTheDocument()

        const contentSkeletons = content?.querySelectorAll('.animate-pulse')
        expect(contentSkeletons).toHaveLength(3) // 3 content lines
      })

      it('includes skeleton elements with correct sizing', () => {
        const { container } = render(<PromptListSkeleton count={1} />)

        // Header skeletons
        const titleSkeleton = container.querySelector('.h-5.w-32')
        expect(titleSkeleton).toBeInTheDocument()

        const statusSkeleton = container.querySelector('.h-4.w-16')
        expect(statusSkeleton).toBeInTheDocument()

        // Content skeletons
        const fullLineSkeleton = container.querySelector('.h-3.w-full')
        expect(fullLineSkeleton).toBeInTheDocument()

        const threeQuarterSkeleton = container.querySelector('.h-3.w-3\\/4')
        expect(threeQuarterSkeleton).toBeInTheDocument()

        const halfLineSkeleton = container.querySelector('.h-3.w-1\\/2')
        expect(halfLineSkeleton).toBeInTheDocument()
      })
    })

    describe('multiple items', () => {
      it('generates unique keys for each item', () => {
        const { container } = render(<PromptListSkeleton count={3} />)

        const items = container.querySelectorAll('.border.border-zinc-200')
        expect(items).toHaveLength(3)

        items.forEach((item) => {
          expect(item).toBeInTheDocument()
        })
      })

      it('maintains consistent structure across items', () => {
        const { container } = render(<PromptListSkeleton count={3} />)

        const items = container.querySelectorAll('.border.border-zinc-200')
        items.forEach((item) => {
          expect(item).toHaveClass('rounded-lg', 'p-4')

          const header = item.querySelector(
            '.flex.items-center.justify-between.mb-3'
          )
          expect(header).toBeInTheDocument()

          const content = item.querySelector('.space-y-2')
          expect(content).toBeInTheDocument()

          const skeletons = item.querySelectorAll('.animate-pulse')
          expect(skeletons).toHaveLength(5) // 2 header + 3 content
        })
      })
    })
  })

  describe('dark mode support', () => {
    it('LoadingSpinner includes dark mode classes', () => {
      const { container } = render(<LoadingSpinner />)

      const spinner = container.firstChild as HTMLElement
      expect(spinner).toHaveClass(
        'dark:border-zinc-600',
        'dark:border-t-blue-400'
      )
    })

    it('LoadingState message includes dark mode classes', () => {
      render(<LoadingState />)

      const message = screen.getByText('Loading...')
      expect(message).toHaveClass('dark:text-zinc-400')
    })

    it('Skeleton includes dark mode classes', () => {
      const { container } = render(<Skeleton />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('dark:bg-zinc-700')
    })

    it('ModelListSkeleton includes dark mode classes', () => {
      const { container } = render(<ModelListSkeleton count={1} />)

      const item = container.querySelector('.border')
      expect(item).toHaveClass('dark:border-zinc-700')
    })

    it('PromptListSkeleton includes dark mode classes', () => {
      const { container } = render(<PromptListSkeleton count={1} />)

      const item = container.querySelector('.border')
      expect(item).toHaveClass('dark:border-zinc-700')
    })
  })

  describe('edge cases and props handling', () => {
    it('handles undefined props gracefully', () => {
      expect(() => {
        render(<LoadingSpinner size={undefined as any} />)
      }).not.toThrow()
    })

    it('handles invalid size prop gracefully', () => {
      expect(() => {
        render(<LoadingSpinner size={'invalid' as any} />)
      }).not.toThrow()
    })

    it('handles very large count values', () => {
      const { container } = render(<ModelListSkeleton count={100} />)

      const items = container.querySelectorAll('.flex.items-center.space-x-3')
      expect(items).toHaveLength(100)
    })

    it('handles negative count values', () => {
      const { container } = render(<PromptListSkeleton count={-1} />)

      const items = container.querySelectorAll('.border.border-zinc-200')
      expect(items).toHaveLength(0) // Array.from with negative length creates empty array
    })
  })

  describe('accessibility', () => {
    it('LoadingSpinner maintains proper visual indicators', () => {
      const { container } = render(<LoadingSpinner />)

      const spinner = container.firstChild as HTMLElement
      expect(spinner).toHaveClass('animate-spin') // Visual loading indicator
    })

    it('LoadingState provides meaningful text', () => {
      render(<LoadingState message="Loading user data" />)

      expect(screen.getByText('Loading user data')).toBeInTheDocument()
    })

    it('Skeleton components provide visual loading feedback', () => {
      const { container } = render(<Skeleton />)

      const skeleton = container.firstChild as HTMLElement
      expect(skeleton).toHaveClass('animate-pulse') // Visual feedback
    })
  })
})

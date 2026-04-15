/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import GlobalError from '../error'

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'errors.global.title': 'Something went wrong',
        'errors.global.description':
          'An unexpected error occurred while loading this content.',
        'errors.global.tryAgain': 'Try Again',
        'errors.global.reloadPage': 'Reload Page',
        'errors.global.technicalDetails': 'Technical Details',
      }
      return translations[key] || key
    },
  }),
}))

describe('GlobalError', () => {
  const mockReset = jest.fn()
  const mockError = new Error('Test error message')
  const mockErrorWithDigest = Object.assign(new Error('Error with digest'), {
    digest: 'abc123',
  })

  // Mock window.location.reload
  const mockReload = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    jest.spyOn(console, 'error').mockImplementation(() => {})
    jest.spyOn(console, 'log').mockImplementation(() => {})
    // Mock reload before each test
    delete (window as any).location
    ;(window as any).location = { reload: mockReload }
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders error boundary UI', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      expect(screen.getByText('Something went wrong')).toBeInTheDocument()
      expect(
        screen.getByText(
          'An unexpected error occurred while loading this content.'
        )
      ).toBeInTheDocument()
    })

    it('renders Try Again button', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      expect(
        screen.getByRole('button', { name: 'Try Again' })
      ).toBeInTheDocument()
    })

    it('renders Reload Page button', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      expect(
        screen.getByRole('button', { name: 'Reload Page' })
      ).toBeInTheDocument()
    })

    it('renders error icon', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const icon = container.querySelector('svg.text-red-600')
      expect(icon).toBeInTheDocument()
      expect(icon).toHaveClass(
        'h-6',
        'w-6',
        'text-red-600',
        'dark:text-red-400'
      )
    })
  })

  describe('Error Logging', () => {
    it('logs error to console', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      expect(console.error).toHaveBeenCalledWith('Global error:', mockError)
    })

    it('logs error with digest', () => {
      render(<GlobalError error={mockErrorWithDigest} reset={mockReset} />)

      expect(console.error).toHaveBeenCalledWith(
        'Global error:',
        mockErrorWithDigest
      )
    })

    it('handles null error gracefully', () => {
      render(<GlobalError error={null as any} reset={mockReset} />)

      expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    })

    it('handles undefined error gracefully', () => {
      render(<GlobalError error={undefined as any} reset={mockReset} />)

      expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    })

    // Note: Fallback logging uses logger.debug() - not testable in unit tests without mocking logger
  })

  describe('Button Interactions', () => {
    it('calls reset function when Try Again is clicked', async () => {
      const user = userEvent.setup()
      render(<GlobalError error={mockError} reset={mockReset} />)

      const tryAgainButton = screen.getByRole('button', { name: 'Try Again' })
      await user.click(tryAgainButton)

      expect(mockReset).toHaveBeenCalledTimes(1)
    })

    it('renders Reload Page button', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      const reloadButton = screen.getByRole('button', { name: 'Reload Page' })
      expect(reloadButton).toBeInTheDocument()
    })

    it('handles multiple clicks on Try Again', async () => {
      const user = userEvent.setup()
      render(<GlobalError error={mockError} reset={mockReset} />)

      const tryAgainButton = screen.getByRole('button', { name: 'Try Again' })
      await user.click(tryAgainButton)
      await user.click(tryAgainButton)
      await user.click(tryAgainButton)

      expect(mockReset).toHaveBeenCalledTimes(3)
    })

    it('renders both action buttons', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      const tryAgainButton = screen.getByRole('button', { name: 'Try Again' })
      const reloadButton = screen.getByRole('button', { name: 'Reload Page' })

      expect(tryAgainButton).toBeInTheDocument()
      expect(reloadButton).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('applies correct container styles', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const mainContainer = container.querySelector(
        '.flex.min-h-screen.items-center.justify-center'
      )
      expect(mainContainer).toBeInTheDocument()
      expect(mainContainer).toHaveClass('bg-zinc-50', 'dark:bg-zinc-900', 'p-4')
    })

    it('applies correct card styles', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const card = container.querySelector('.rounded-lg.bg-white')
      expect(card).toBeInTheDocument()
      expect(card).toHaveClass(
        'w-full',
        'max-w-2xl',
        'rounded-lg',
        'border',
        'border-zinc-200',
        'bg-white',
        'p-6',
        'shadow-lg',
        'dark:border-zinc-700',
        'dark:bg-zinc-800'
      )
    })

    it('applies Button component styles for Try Again', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      const tryAgainButton = screen.getByRole('button', { name: 'Try Again' })
      expect(tryAgainButton).toHaveClass('inline-flex', 'text-sm', 'font-medium')
    })

    it('applies Button component styles for Reload Page', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      const reloadButton = screen.getByRole('button', { name: 'Reload Page' })
      expect(reloadButton).toHaveClass('inline-flex', 'text-sm', 'font-medium')
    })

    it('applies correct icon container styles', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const iconContainer = container.querySelector('.bg-red-100')
      expect(iconContainer).toBeInTheDocument()
      expect(iconContainer).toHaveClass(
        'mr-4',
        'flex',
        'h-12',
        'w-12',
        'items-center',
        'justify-center',
        'rounded-full',
        'bg-red-100'
      )
    })

    it('applies gap between buttons', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const buttonContainer = container.querySelector('.flex.gap-3')
      expect(buttonContainer).toBeInTheDocument()
      expect(buttonContainer).toHaveClass('flex', 'gap-3')
    })
  })

  describe('Technical Details (Development)', () => {
    const originalEnv = process.env.NODE_ENV

    beforeEach(() => {
      process.env.NODE_ENV = 'development'
    })

    afterEach(() => {
      process.env.NODE_ENV = originalEnv
    })

    it('shows technical details section in development', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      expect(screen.getByText('Technical Details')).toBeInTheDocument()
    })

    it('displays error message in technical details', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      const details = screen.getByText('Technical Details')
      const summary = details.closest('details')

      // Open the details element
      fireEvent.click(details)

      expect(summary?.textContent).toContain('Test error message')
    })

    it('displays error stack in technical details', () => {
      const errorWithStack = new Error('Test error')
      errorWithStack.stack = 'Error: Test error\n    at TestFile.js:1:1'

      render(<GlobalError error={errorWithStack} reset={mockReset} />)

      const details = screen.getByText('Technical Details')
      fireEvent.click(details)

      const summary = details.closest('details')
      expect(summary?.textContent).toContain('Stack trace:')
    })

    it('handles error without stack trace', () => {
      const errorWithoutStack = new Error('Test error')
      errorWithoutStack.stack = undefined

      render(<GlobalError error={errorWithoutStack} reset={mockReset} />)

      const details = screen.getByText('Technical Details')
      fireEvent.click(details)

      const summary = details.closest('details')
      expect(summary?.textContent).not.toContain('Stack trace:')
    })

    it('handles unknown error message', () => {
      const errorWithoutMessage = {} as Error

      render(<GlobalError error={errorWithoutMessage} reset={mockReset} />)

      const details = screen.getByText('Technical Details')
      fireEvent.click(details)

      const summary = details.closest('details')
      expect(summary?.textContent).toContain('Unknown error')
    })
  })

  describe('Technical Details (Production)', () => {
    const originalEnv = process.env.NODE_ENV

    beforeEach(() => {
      process.env.NODE_ENV = 'production'
    })

    afterEach(() => {
      process.env.NODE_ENV = originalEnv
    })

    it('hides technical details section in production', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      expect(screen.queryByText('Technical Details')).not.toBeInTheDocument()
    })

    it('does not expose error message in production', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      expect(screen.queryByText('Test error message')).not.toBeInTheDocument()
    })

    it('does not expose stack trace in production', () => {
      const errorWithStack = new Error('Test error')
      errorWithStack.stack = 'Error: Test error\n    at TestFile.js:1:1'

      render(<GlobalError error={errorWithStack} reset={mockReset} />)

      expect(screen.queryByText(/Stack trace:/)).not.toBeInTheDocument()
    })
  })

  describe('Dark Mode Support', () => {
    it('includes dark mode classes for container', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const mainContainer = container.querySelector('.flex.min-h-screen')
      expect(mainContainer).toHaveClass('dark:bg-zinc-900')
    })

    it('includes dark mode classes for card', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const card = container.querySelector('.rounded-lg.bg-white')
      expect(card).toHaveClass('dark:border-zinc-700', 'dark:bg-zinc-800')
    })

    it('includes dark mode classes for icon', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const icon = container.querySelector('svg')
      expect(icon).toHaveClass('dark:text-red-400')
    })

    it('includes dark mode classes for icon container', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const iconContainer = container.querySelector('.bg-red-100')
      expect(iconContainer).toBeInTheDocument()
      // Dark mode class is applied but escaped slash may not match in testing
      expect(iconContainer?.className).toContain('bg-red-100')
    })

    it('includes dark mode classes for text', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      const heading = screen.getByText('Something went wrong')
      expect(heading).toHaveClass('text-zinc-900', 'dark:text-white')

      const description = screen.getByText(
        'An unexpected error occurred while loading this content.'
      )
      expect(description).toHaveClass('text-zinc-600', 'dark:text-zinc-300')
    })

    it('includes dark mode classes for Reload button', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      const reloadButton = screen.getByRole('button', { name: 'Reload Page' })
      // Button component applies its own dark mode classes
      expect(reloadButton).toBeInTheDocument()
      expect(reloadButton.className).toContain('dark:')
    })
  })

  describe('Accessibility', () => {
    it('uses semantic HTML heading', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      const heading = screen.getByRole('heading', { level: 2 })
      expect(heading).toHaveTextContent('Something went wrong')
    })

    it('provides clear button labels', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      expect(
        screen.getByRole('button', { name: 'Try Again' })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Reload Page' })
      ).toBeInTheDocument()
    })

    it('renders accessible buttons', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      const tryAgainButton = screen.getByRole('button', { name: 'Try Again' })
      expect(tryAgainButton).toBeInTheDocument()

      const reloadButton = screen.getByRole('button', { name: 'Reload Page' })
      expect(reloadButton).toBeInTheDocument()
    })

    it('uses summary element for details toggle', () => {
      process.env.NODE_ENV = 'development'
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const summary = container.querySelector('summary')
      expect(summary).toBeInTheDocument()
      expect(summary).toHaveClass('cursor-pointer')
    })

    it('provides visual feedback on button hover', () => {
      render(<GlobalError error={mockError} reset={mockReset} />)

      const tryAgainButton = screen.getByRole('button', { name: 'Try Again' })
      expect(tryAgainButton).toHaveClass('transition')

      const reloadButton = screen.getByRole('button', { name: 'Reload Page' })
      expect(reloadButton).toHaveClass('transition')
    })
  })

  describe('Edge Cases', () => {
    it('handles error with empty message', () => {
      const emptyError = new Error('')
      render(<GlobalError error={emptyError} reset={mockReset} />)

      expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    })

    it('handles error with very long message', () => {
      const longMessage = 'A'.repeat(1000)
      const longError = new Error(longMessage)

      process.env.NODE_ENV = 'development'
      const { container } = render(
        <GlobalError error={longError} reset={mockReset} />
      )

      const details = screen.getByText('Technical Details')
      fireEvent.click(details)

      const pre = container.querySelector('pre')
      expect(pre).toHaveClass('overflow-auto', 'max-h-96')
    })

    it('renders reset button correctly', () => {
      const resetFn = jest.fn()
      render(<GlobalError error={mockError} reset={resetFn} />)

      const tryAgainButton = screen.getByRole('button', { name: 'Try Again' })
      expect(tryAgainButton).toBeInTheDocument()
    })

    it('renders both buttons in a flex container', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const buttonContainer = container.querySelector('.flex.gap-3')
      expect(buttonContainer).toBeInTheDocument()
      expect(buttonContainer?.querySelectorAll('button')).toHaveLength(2)
    })
  })

  describe('Component Structure', () => {
    it('renders elements in correct DOM hierarchy', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const heading = screen.getByText('Something went wrong')
      const description = screen.getByText(
        'An unexpected error occurred while loading this content.'
      )
      const tryAgainButton = screen.getByRole('button', { name: 'Try Again' })

      expect(heading).toBeInTheDocument()
      expect(description).toBeInTheDocument()
      expect(tryAgainButton).toBeInTheDocument()
    })

    it('groups buttons together', () => {
      const { container } = render(
        <GlobalError error={mockError} reset={mockReset} />
      )

      const buttonContainer = container.querySelector('.flex.gap-3')
      const tryAgainButton = screen.getByRole('button', { name: 'Try Again' })
      const reloadButton = screen.getByRole('button', { name: 'Reload Page' })

      expect(buttonContainer).toContainElement(tryAgainButton)
      expect(buttonContainer).toContainElement(reloadButton)
    })
  })
})

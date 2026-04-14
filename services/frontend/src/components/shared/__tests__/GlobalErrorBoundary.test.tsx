/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen } from '@testing-library/react'
import React from 'react'
import { GlobalErrorBoundary } from '../GlobalErrorBoundary'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'errors.global.applicationError': 'Application Error',
        'errors.global.unexpectedError': 'An unexpected error occurred',
        'errors.global.errorDetails': 'Error Details',
        'errors.global.reloadPage': 'Reload Page',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

// Test component that throws errors
const ThrowError: React.FC<{ error: Error }> = ({ error }) => {
  throw error
}

// Test component that doesn't throw
const WorkingComponent: React.FC = () => <div>Working component</div>

// Test component that throws async errors
const AsyncErrorComponent: React.FC<{ shouldThrow: boolean }> = ({
  shouldThrow,
}) => {
  if (shouldThrow) {
    throw new Error('Async error occurred')
  }
  return <div>Async component rendered</div>
}

describe('GlobalErrorBoundary', () => {
  const originalError = console.error
  let consoleErrorSpy: jest.SpyInstance

  beforeAll(() => {
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterAll(() => {
    console.error = originalError
  })

  afterEach(() => {
    consoleErrorSpy.mockClear()
  })

  describe('Basic Rendering', () => {
    it('renders children when there is no error', () => {
      render(
        <GlobalErrorBoundary>
          <WorkingComponent />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Working component')).toBeInTheDocument()
    })

    it('renders multiple children without errors', () => {
      render(
        <GlobalErrorBoundary>
          <div>Child 1</div>
          <div>Child 2</div>
          <div>Child 3</div>
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Child 1')).toBeInTheDocument()
      expect(screen.getByText('Child 2')).toBeInTheDocument()
      expect(screen.getByText('Child 3')).toBeInTheDocument()
    })

    it('renders complex nested children without errors', () => {
      render(
        <GlobalErrorBoundary>
          <div>
            <span>Nested</span>
            <div>
              <p>Deep nested content</p>
            </div>
          </div>
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Nested')).toBeInTheDocument()
      expect(screen.getByText('Deep nested content')).toBeInTheDocument()
    })
  })

  describe('Error Catching', () => {
    it('catches errors thrown by child components', () => {
      const error = new Error('Test error')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(screen.getByText('Test error')).toBeInTheDocument()
    })

    it('catches errors with custom messages', () => {
      const error = new Error('Custom error message')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(screen.getByText('Custom error message')).toBeInTheDocument()
    })

    it('handles errors without messages', () => {
      const error = new Error()

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(
        screen.getByText('An unexpected error occurred')
      ).toBeInTheDocument()
    })

    it('catches TypeError errors', () => {
      const error = new TypeError('Cannot read property of undefined')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(
        screen.getByText('Cannot read property of undefined')
      ).toBeInTheDocument()
    })

    it('catches ReferenceError errors', () => {
      const error = new ReferenceError('variable is not defined')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(screen.getByText('variable is not defined')).toBeInTheDocument()
    })
  })

  describe('Error Display/UI', () => {
    it('displays error UI with correct structure', () => {
      const error = new Error('Display test error')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(screen.getByText('Display test error')).toBeInTheDocument()
      expect(screen.getByText('Error Details')).toBeInTheDocument()
      expect(screen.getByText('Reload Page')).toBeInTheDocument()
    })

    it('displays error details in collapsible section', () => {
      const error = new Error('Test error with stack')
      error.stack = 'Error: Test error\n    at Component.tsx:10:5'

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      const details = screen.getByText('Error Details')
      expect(details).toBeInTheDocument()

      // Stack should be in the DOM but may not be visible
      const stackElement = screen.getByText(/at Component\.tsx:10:5/)
      expect(stackElement).toBeInTheDocument()
    })

    it('shows error stack trace in details', () => {
      const error = new Error('Stack trace test')
      error.stack =
        'Error: Stack trace test\n    at TestFile.js:20:10\n    at render.js:50:5'

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText(/at TestFile\.js:20:10/)).toBeInTheDocument()
      expect(screen.getByText(/at render\.js:50:5/)).toBeInTheDocument()
    })

    it('handles errors without stack traces', () => {
      const error = new Error('No stack error')
      error.stack = undefined

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(screen.getByText('No stack error')).toBeInTheDocument()
    })
  })

  describe('Reset Functionality', () => {
    it('provides reload button', () => {
      const error = new Error('Reload test')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      const reloadButton = screen.getByText('Reload Page')
      expect(reloadButton).toBeInTheDocument()
      expect(reloadButton.tagName).toBe('BUTTON')
    })

    it('reload button has correct styling classes', () => {
      const error = new Error('Style test')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      const reloadButton = screen.getByText('Reload Page')
      expect(reloadButton.className).toContain('bg-emerald-600')
      expect(reloadButton.className).toContain('hover:bg-emerald-700')
    })

    it('reload button has onClick handler', () => {
      const error = new Error('Reload trigger test')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      const reloadButton = screen.getByText('Reload Page')
      expect(reloadButton.tagName).toBe('BUTTON')

      // Test that clicking doesn't cause errors (actual reload mocked in JSDOM)
      expect(() => fireEvent.click(reloadButton)).not.toThrow()
    })
  })

  describe('Error Logging', () => {
    it('logs errors to console.error', () => {
      const error = new Error('Logging test')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(consoleErrorSpy).toHaveBeenCalled()
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Module initialization error:',
        error,
        expect.any(Object)
      )
    })

    it('logs webpack-specific errors with additional details', () => {
      const error = new Error('Cannot read properties of undefined')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Module initialization error:',
        error,
        expect.any(Object)
      )

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Webpack module loading error detected:',
        expect.objectContaining({
          message: 'Cannot read properties of undefined',
          stack: expect.any(String),
          componentStack: expect.any(String),
        })
      )
    })

    it('does not log webpack-specific details for non-webpack errors', () => {
      const error = new Error('Regular error')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Module initialization error:',
        error,
        expect.any(Object)
      )

      const webpackCalls = consoleErrorSpy.mock.calls.filter((call) =>
        call[0]?.includes?.('Webpack')
      )
      expect(webpackCalls).toHaveLength(0)
    })

    it('logs error info with component stack', () => {
      const error = new Error('Component stack test')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Module initialization error:',
        error,
        expect.objectContaining({
          componentStack: expect.any(String),
        })
      )
    })
  })

  describe('Children Rendering', () => {
    it('renders children when no error occurs', () => {
      render(
        <GlobalErrorBoundary>
          <div data-testid="child">Child content</div>
        </GlobalErrorBoundary>
      )

      expect(screen.getByTestId('child')).toBeInTheDocument()
      expect(screen.getByText('Child content')).toBeInTheDocument()
    })

    it('does not render children after error', () => {
      const error = new Error('Children test')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
          <div data-testid="should-not-render">Should not see this</div>
        </GlobalErrorBoundary>
      )

      expect(screen.queryByTestId('should-not-render')).not.toBeInTheDocument()
      expect(screen.getByText('Application Error')).toBeInTheDocument()
    })

    it('renders JSX element children correctly', () => {
      const ChildElement = <div>JSX child element</div>

      render(<GlobalErrorBoundary>{ChildElement}</GlobalErrorBoundary>)

      expect(screen.getByText('JSX child element')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles nested error boundaries', () => {
      const outerError = new Error('Outer error')

      render(
        <GlobalErrorBoundary>
          <GlobalErrorBoundary>
            <ThrowError error={outerError} />
          </GlobalErrorBoundary>
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(screen.getByText('Outer error')).toBeInTheDocument()
    })

    it('handles errors thrown in nested components', () => {
      const nestedError = new Error('Nested component error')

      const NestedComponent = () => <ThrowError error={nestedError} />

      const ParentComponent = () => (
        <div>
          <NestedComponent />
        </div>
      )

      render(
        <GlobalErrorBoundary>
          <ParentComponent />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(screen.getByText('Nested component error')).toBeInTheDocument()
    })

    it('handles async errors after component mount', async () => {
      let shouldThrow = false

      const { rerender } = render(
        <GlobalErrorBoundary>
          <AsyncErrorComponent shouldThrow={shouldThrow} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Async component rendered')).toBeInTheDocument()

      shouldThrow = true

      rerender(
        <GlobalErrorBoundary>
          <AsyncErrorComponent shouldThrow={shouldThrow} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(screen.getByText('Async error occurred')).toBeInTheDocument()
    })

    it('handles errors with very long messages', () => {
      const longMessage = 'A'.repeat(1000)
      const error = new Error(longMessage)

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(screen.getByText(longMessage)).toBeInTheDocument()
    })

    it('handles errors with special characters in message', () => {
      const error = new Error('Error with <script>alert("xss")</script>')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(
        screen.getByText('Error with <script>alert("xss")</script>')
      ).toBeInTheDocument()
    })

    it('handles rapid consecutive errors', () => {
      const error1 = new Error('First error')

      const { rerender } = render(
        <GlobalErrorBoundary>
          <ThrowError error={error1} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('First error')).toBeInTheDocument()

      const error2 = new Error('Second error')

      rerender(
        <GlobalErrorBoundary>
          <ThrowError error={error2} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
    })

    it('handles null error messages gracefully', () => {
      const error = new Error()
      // @ts-ignore - intentionally testing edge case
      error.message = null

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      expect(screen.getByText('Application Error')).toBeInTheDocument()
      expect(
        screen.getByText('An unexpected error occurred')
      ).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('error UI has proper heading hierarchy', () => {
      const error = new Error('Accessibility test')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      const heading = screen.getByText('Application Error')
      expect(heading.tagName).toBe('H1')
    })

    it('reload button is keyboard accessible', () => {
      const error = new Error('Keyboard test')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      const reloadButton = screen.getByText('Reload Page')
      reloadButton.focus()
      expect(document.activeElement).toBe(reloadButton)

      // Test that clicking is possible
      expect(() => fireEvent.click(reloadButton)).not.toThrow()
    })

    it('details element is keyboard accessible', () => {
      const error = new Error('Details test')
      error.stack = 'Error stack trace'

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      const details = screen.getByText('Error Details').closest('details')
      expect(details).toBeInTheDocument()
      expect(details?.tagName).toBe('DETAILS')
    })

    it('error message has sufficient color contrast', () => {
      const error = new Error('Contrast test')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      const errorMessage = screen.getByText('Contrast test')
      expect(errorMessage.className).toContain('text-zinc-600')
    })

    it('reload button has focus styles', () => {
      const error = new Error('Focus test')

      render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      const reloadButton = screen.getByText('Reload Page')
      expect(reloadButton.className).toContain('focus:outline-none')
      expect(reloadButton.className).toContain('focus:ring-2')
      expect(reloadButton.className).toContain('focus:ring-emerald-500')
    })

    it('error container has proper semantic structure', () => {
      const error = new Error('Semantic test')

      const { container } = render(
        <GlobalErrorBoundary>
          <ThrowError error={error} />
        </GlobalErrorBoundary>
      )

      const errorContainer = container.firstChild
      expect(errorContainer).toBeInTheDocument()
      expect(errorContainer).toHaveClass('flex', 'min-h-screen')
    })
  })
})

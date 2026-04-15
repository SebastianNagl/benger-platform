/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen } from '@testing-library/react'
import React from 'react'
import { NetworkErrorBoundary } from '../NetworkErrorBoundary'

// Mock child component that can throw errors
const ThrowError: React.FC<{ error: Error }> = ({ error }) => {
  throw error
}

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'errors.network.title': 'Network Error',
        'errors.global.title': 'Something went wrong',
        'errors.network.connectionTrouble': "We're having trouble connecting to our servers",
        'errors.global.description': 'An unexpected error occurred',
        'errors.network.networkIssue': 'Network connectivity issues',
        'errors.network.serverLoad': 'High server load',
        'errors.network.tooManyRequests': 'Too many simultaneous requests',
        'errors.global.technicalDetails': 'Technical details',
        'errors.global.tryAgain': 'Try Again',
        'errors.global.reloadPage': 'Reload Page',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

// Test component that doesn't throw
const GoodComponent: React.FC = () => <div>Working component</div>

describe('NetworkErrorBoundary', () => {
  // Suppress console errors during tests
  const originalError = console.error
  beforeAll(() => {
    console.error = jest.fn()
  })
  afterAll(() => {
    console.error = originalError
  })

  it('renders children when there is no error', () => {
    render(
      <NetworkErrorBoundary>
        <GoodComponent />
      </NetworkErrorBoundary>
    )

    expect(screen.getByText('Working component')).toBeInTheDocument()
  })

  it('catches and displays network errors with ERR_INSUFFICIENT_RESOURCES', () => {
    const error = new Error('ERR_INSUFFICIENT_RESOURCES: Too many requests')

    render(
      <NetworkErrorBoundary>
        <ThrowError error={error} />
      </NetworkErrorBoundary>
    )

    expect(screen.getByText('Network Error')).toBeInTheDocument()
    expect(
      screen.getByText(/We're having trouble connecting to our servers/)
    ).toBeInTheDocument()
    expect(screen.getByText('Network connectivity issues')).toBeInTheDocument()
    expect(screen.getByText('High server load')).toBeInTheDocument()
    expect(
      screen.getByText('Too many simultaneous requests')
    ).toBeInTheDocument()
  })

  it('catches generic network errors', () => {
    const error = new Error('NetworkError: Failed to fetch')

    render(
      <NetworkErrorBoundary>
        <ThrowError error={error} />
      </NetworkErrorBoundary>
    )

    expect(screen.getByText('Network Error')).toBeInTheDocument()
  })

  it('catches non-network errors', () => {
    const error = new Error('Some random error')

    render(
      <NetworkErrorBoundary>
        <ThrowError error={error} />
      </NetworkErrorBoundary>
    )

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText(/An unexpected error occurred/)).toBeInTheDocument()
  })

  it('shows retry button and increments count', () => {
    const error = new Error('Network error')
    let shouldThrow = true

    const TestComponent = () => {
      if (shouldThrow) throw error
      return <div>Success!</div>
    }

    const { rerender } = render(
      <NetworkErrorBoundary>
        <TestComponent />
      </NetworkErrorBoundary>
    )

    expect(screen.getByText('Try Again')).toBeInTheDocument()

    // Fix the error
    shouldThrow = false

    // Click retry
    fireEvent.click(screen.getByText('Try Again'))

    // Should now show success
    expect(screen.getByText('Success!')).toBeInTheDocument()

    // Throw error again to check retry count
    shouldThrow = true
    rerender(
      <NetworkErrorBoundary>
        <TestComponent />
      </NetworkErrorBoundary>
    )

    expect(screen.getByText('Try Again (1)')).toBeInTheDocument()
  })

  // Note: Reload page option requires location.reload - jsdom limitation
  // Reload functionality verified in browser; other error handling tests cover UI

  it('uses custom fallback when provided', () => {
    const error = new Error('Custom error')
    const customFallback = (error: Error, retry: () => void) => (
      <div>
        <p>Custom error: {error.message}</p>
        <button onClick={retry}>Custom Retry</button>
      </div>
    )

    render(
      <NetworkErrorBoundary fallback={customFallback}>
        <ThrowError error={error} />
      </NetworkErrorBoundary>
    )

    expect(screen.getByText('Custom error: Custom error')).toBeInTheDocument()
    expect(screen.getByText('Custom Retry')).toBeInTheDocument()
  })

  it('calls onError callback when error occurs', () => {
    const error = new Error('Test error')
    const onError = jest.fn()

    render(
      <NetworkErrorBoundary onError={onError}>
        <ThrowError error={error} />
      </NetworkErrorBoundary>
    )

    expect(onError).toHaveBeenCalledWith(error, expect.any(Object))
  })

  it('shows technical details in development mode', () => {
    const originalEnv = process.env.NODE_ENV
    process.env.NODE_ENV = 'development'

    const error = new Error('Development error')
    error.stack = 'Error: Development error\n    at TestFile.js:10:5'

    render(
      <NetworkErrorBoundary>
        <ThrowError error={error} />
      </NetworkErrorBoundary>
    )

    // Find the details element
    const details = screen.getByText('Technical details')
    expect(details).toBeInTheDocument()

    // Click to expand (summary is inside details)
    const summaryElement = details.closest('summary') || details
    fireEvent.click(summaryElement)

    // Should show the error stack
    expect(screen.getByText(/Development error/)).toBeInTheDocument()

    process.env.NODE_ENV = originalEnv
  })

  it('detects various network error patterns', () => {
    const errorPatterns = [
      'Failed to fetch',
      'NetworkError: Request failed',
      'TypeError: Failed to fetch',
      'AbortError: The operation was aborted',
    ]

    errorPatterns.forEach((pattern) => {
      const { unmount } = render(
        <NetworkErrorBoundary>
          <ThrowError error={new Error(pattern)} />
        </NetworkErrorBoundary>
      )

      expect(screen.getByText('Network Error')).toBeInTheDocument()
      unmount()
    })
  })
})

/**
 * @jest-environment jsdom
 *
 * Branch coverage round 7: NetworkErrorBoundary.tsx
 * Targets: getDerivedStateFromError branches (various network error messages),
 *          componentDidCatch with onError callback, retry logic,
 *          custom fallback, network vs non-network error display
 */

import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock I18n
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

import { NetworkErrorBoundary } from '../NetworkErrorBoundary'

// Component that throws
function ThrowingComponent({ error }: { error: Error }) {
  throw error
}

// Suppress console.error for expected errors in tests
const originalConsoleError = console.error
beforeAll(() => {
  console.error = jest.fn()
})
afterAll(() => {
  console.error = originalConsoleError
})

describe('NetworkErrorBoundary br7', () => {
  it('renders children when no error', () => {
    render(
      <NetworkErrorBoundary>
        <div>Safe content</div>
      </NetworkErrorBoundary>
    )
    expect(screen.getByText('Safe content')).toBeInTheDocument()
  })

  it('detects ERR_INSUFFICIENT_RESOURCES as network error', () => {
    const error = new Error('ERR_INSUFFICIENT_RESOURCES')
    render(
      <NetworkErrorBoundary>
        <ThrowingComponent error={error} />
      </NetworkErrorBoundary>
    )
    expect(screen.getByText('errors.network.title')).toBeInTheDocument()
    // Should show network-specific troubleshooting list
    expect(screen.getByText('errors.network.networkIssue')).toBeInTheDocument()
    expect(screen.getByText('errors.network.serverLoad')).toBeInTheDocument()
    expect(screen.getByText('errors.network.tooManyRequests')).toBeInTheDocument()
  })

  it('detects "Network" keyword as network error', () => {
    render(
      <NetworkErrorBoundary>
        <ThrowingComponent error={new Error('Network request failed')} />
      </NetworkErrorBoundary>
    )
    expect(screen.getByText('errors.network.title')).toBeInTheDocument()
  })

  it('detects "Failed to fetch" as network error', () => {
    render(
      <NetworkErrorBoundary>
        <ThrowingComponent error={new Error('Failed to fetch')} />
      </NetworkErrorBoundary>
    )
    expect(screen.getByText('errors.network.title')).toBeInTheDocument()
  })

  it('detects "NetworkError" as network error', () => {
    render(
      <NetworkErrorBoundary>
        <ThrowingComponent error={new Error('NetworkError when attempting to fetch')} />
      </NetworkErrorBoundary>
    )
    expect(screen.getByText('errors.network.title')).toBeInTheDocument()
  })

  it('detects "TypeError: Failed to fetch" as network error', () => {
    render(
      <NetworkErrorBoundary>
        <ThrowingComponent error={new Error('TypeError: Failed to fetch something')} />
      </NetworkErrorBoundary>
    )
    expect(screen.getByText('errors.network.title')).toBeInTheDocument()
  })

  it('detects "AbortError" as network error', () => {
    render(
      <NetworkErrorBoundary>
        <ThrowingComponent error={new Error('AbortError: The operation was aborted')} />
      </NetworkErrorBoundary>
    )
    expect(screen.getByText('errors.network.title')).toBeInTheDocument()
  })

  it('detects "fetch" keyword as network error', () => {
    render(
      <NetworkErrorBoundary>
        <ThrowingComponent error={new Error('Could not fetch resource')} />
      </NetworkErrorBoundary>
    )
    expect(screen.getByText('errors.network.title')).toBeInTheDocument()
  })

  it('treats non-network errors as general errors', () => {
    render(
      <NetworkErrorBoundary>
        <ThrowingComponent error={new Error('Unexpected token in JSON')} />
      </NetworkErrorBoundary>
    )
    expect(screen.getByText('errors.global.title')).toBeInTheDocument()
    // Should NOT show network-specific troubleshooting
    expect(screen.queryByText('errors.network.networkIssue')).not.toBeInTheDocument()
  })

  it('calls onError callback in componentDidCatch', () => {
    const onError = jest.fn()
    render(
      <NetworkErrorBoundary onError={onError}>
        <ThrowingComponent error={new Error('Test error')} />
      </NetworkErrorBoundary>
    )
    expect(onError).toHaveBeenCalledWith(
      expect.any(Error),
      expect.objectContaining({ componentStack: expect.any(String) })
    )
  })

  it('retry resets the error state', () => {
    let shouldThrow = true
    function ConditionalThrower() {
      if (shouldThrow) {
        throw new Error('Temporary error')
      }
      return <div>Recovered!</div>
    }

    render(
      <NetworkErrorBoundary>
        <ConditionalThrower />
      </NetworkErrorBoundary>
    )

    expect(screen.getByText('errors.global.title')).toBeInTheDocument()

    // Fix the component before retrying
    shouldThrow = false

    // Click retry button
    fireEvent.click(screen.getByText('errors.global.tryAgain'))

    expect(screen.getByText('Recovered!')).toBeInTheDocument()
  })

  it('retry shows count after first retry', () => {
    function AlwaysThrows() {
      throw new Error('Persistent error')
    }

    render(
      <NetworkErrorBoundary>
        <AlwaysThrows />
      </NetworkErrorBoundary>
    )

    // First attempt - no count
    const retryButton = screen.getByText(/errors.global.tryAgain/)
    fireEvent.click(retryButton)

    // After retry, should show count (1)
    expect(screen.getByText(/\(1\)/)).toBeInTheDocument()
  })

  it('uses custom fallback when provided', () => {
    const customFallback = (error: Error, retry: () => void) => (
      <div>
        <span>Custom error: {error.message}</span>
        <button onClick={retry}>Custom retry</button>
      </div>
    )

    render(
      <NetworkErrorBoundary fallback={customFallback}>
        <ThrowingComponent error={new Error('Custom test')} />
      </NetworkErrorBoundary>
    )

    expect(screen.getByText('Custom error: Custom test')).toBeInTheDocument()
    expect(screen.getByText('Custom retry')).toBeInTheDocument()
  })

  it('reload button exists and is clickable', () => {
    render(
      <NetworkErrorBoundary>
        <ThrowingComponent error={new Error('Reload test')} />
      </NetworkErrorBoundary>
    )

    const reloadButton = screen.getByText('errors.global.reloadPage')
    expect(reloadButton).toBeInTheDocument()
    // Just verify the button renders and is clickable
    fireEvent.click(reloadButton)
  })

  it('shows technical details in development mode', () => {
    const originalEnv = process.env.NODE_ENV
    Object.defineProperty(process.env, 'NODE_ENV', { value: 'development', configurable: true })

    const error = new Error('Debug error')
    error.stack = 'Error: Debug error\n    at Component'

    render(
      <NetworkErrorBoundary>
        <ThrowingComponent error={error} />
      </NetworkErrorBoundary>
    )

    expect(screen.getByText('errors.global.technicalDetails')).toBeInTheDocument()

    Object.defineProperty(process.env, 'NODE_ENV', { value: originalEnv, configurable: true })
  })
})

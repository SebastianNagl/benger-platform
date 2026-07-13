/**
 * Tests for ApiClientContext — the explicit, org-aware API-client threading
 * introduced to let consumers migrate off the globally-mutated singleton.
 *
 * Covers: provider value pass-through, the throwing useApiClient() guard, and
 * the non-throwing useOptionalApiClient() fallback.
 */
import '@testing-library/jest-dom'
import { render, renderHook } from '@testing-library/react'
import React from 'react'
import {
  ApiClientContextProvider,
  useApiClient,
  useOptionalApiClient,
} from '../ApiClientContext'

// A minimal stand-in for an ApiClient instance — the context only stores and
// returns the reference, so a plain object with a recognizable method suffices.
const makeFakeClient = () =>
  ({ get: jest.fn(), post: jest.fn(), tag: 'fake-client' }) as any

describe('ApiClientContext', () => {
  describe('ApiClientContextProvider', () => {
    it('renders children', () => {
      const { getByText } = render(
        <ApiClientContextProvider client={makeFakeClient()}>
          <div>child</div>
        </ApiClientContextProvider>
      )
      expect(getByText('child')).toBeInTheDocument()
    })

    it('provides the exact client instance passed in', () => {
      const client = makeFakeClient()
      const { result } = renderHook(() => useApiClient(), {
        wrapper: ({ children }) => (
          <ApiClientContextProvider client={client}>
            {children}
          </ApiClientContextProvider>
        ),
      })
      expect(result.current).toBe(client)
    })
  })

  describe('useApiClient', () => {
    it('returns the provided client', () => {
      const client = makeFakeClient()
      const { result } = renderHook(() => useApiClient(), {
        wrapper: ({ children }) => (
          <ApiClientContextProvider client={client}>
            {children}
          </ApiClientContextProvider>
        ),
      })
      expect(result.current).toHaveProperty('post')
      expect(result.current).toBe(client)
    })

    it('throws when used outside a provider', () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()
      expect(() => renderHook(() => useApiClient())).toThrow(
        /must be used within an ApiClientContextProvider/
      )
      consoleError.mockRestore()
    })

    it('returns the same instance across multiple hook calls', () => {
      const client = makeFakeClient()
      // renderHook keeps the render pure (react-hooks/globals + immutability
      // forbid writing to outer bindings/objects from inside a component).
      const { result } = renderHook(
        () => ({ a: useApiClient(), b: useApiClient() }),
        {
          wrapper: ({ children }) => (
            <ApiClientContextProvider client={client}>
              {children}
            </ApiClientContextProvider>
          ),
        }
      )
      expect(result.current.a).toBe(result.current.b)
      expect(result.current.a).toBe(client)
    })
  })

  describe('useOptionalApiClient', () => {
    it('returns the client when inside a provider', () => {
      const client = makeFakeClient()
      const { result } = renderHook(() => useOptionalApiClient(), {
        wrapper: ({ children }) => (
          <ApiClientContextProvider client={client}>
            {children}
          </ApiClientContextProvider>
        ),
      })
      expect(result.current).toBe(client)
    })

    it('returns null when outside a provider (no throw)', () => {
      const { result } = renderHook(() => useOptionalApiClient())
      expect(result.current).toBeNull()
    })
  })
})

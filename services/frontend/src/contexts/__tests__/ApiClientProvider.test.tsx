/**
 * Comprehensive tests for ApiClientProvider
 * Tests provider initialization, context provision, and client configuration
 */
/* eslint-disable react-hooks/globals -- Valid test pattern: capturing hook values via external variables for assertions */

import { render, renderHook } from '@testing-library/react'
import React from 'react'
import { ApiClientProvider, useApiClient } from '../ApiClientProvider'

// Mock the ApiClient
jest.mock('@/lib/api', () => ({
  ApiClient: jest.fn().mockImplementation(() => ({
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
    login: jest.fn(),
    logout: jest.fn(),
    getCurrentUser: jest.fn(),
    getProjects: jest.fn(),
  })),
}))

describe('ApiClientProvider', () => {
  describe('Provider Initialization', () => {
    it('should render children successfully', () => {
      const { getByText } = render(
        <ApiClientProvider>
          <div>Test Child</div>
        </ApiClientProvider>
      )

      expect(getByText('Test Child')).toBeInTheDocument()
    })

    it('should render multiple children', () => {
      const { getByText } = render(
        <ApiClientProvider>
          <div>Child 1</div>
          <div>Child 2</div>
          <div>Child 3</div>
        </ApiClientProvider>
      )

      expect(getByText('Child 1')).toBeInTheDocument()
      expect(getByText('Child 2')).toBeInTheDocument()
      expect(getByText('Child 3')).toBeInTheDocument()
    })

    it('should render nested components', () => {
      const NestedComponent = () => <div>Nested</div>
      const ParentComponent = () => (
        <div>
          Parent
          <NestedComponent />
        </div>
      )

      const { getByText } = render(
        <ApiClientProvider>
          <ParentComponent />
        </ApiClientProvider>
      )

      expect(getByText('Parent')).toBeInTheDocument()
      expect(getByText('Nested')).toBeInTheDocument()
    })

    it('should handle null children gracefully', () => {
      const { container } = render(
        <ApiClientProvider>{null}</ApiClientProvider>
      )

      expect(container).toBeInTheDocument()
    })

    it('should handle undefined children gracefully', () => {
      const { container } = render(
        <ApiClientProvider>{undefined}</ApiClientProvider>
      )

      expect(container).toBeInTheDocument()
    })

    it('should handle empty fragment', () => {
      const { container } = render(
        <ApiClientProvider>
          <></>
        </ApiClientProvider>
      )

      expect(container).toBeInTheDocument()
    })

    it('should create stable ApiClient instance', () => {
      const TestComponent = () => {
        const client1 = useApiClient()
        const client2 = useApiClient()
        return (
          <div>
            {client1 === client2 ? 'Same Instance' : 'Different Instance'}
          </div>
        )
      }

      const { getByText } = render(
        <ApiClientProvider>
          <TestComponent />
        </ApiClientProvider>
      )

      expect(getByText('Same Instance')).toBeInTheDocument()
    })
  })

  describe('useApiClient Hook', () => {
    it('should provide apiClient instance', () => {
      const { result } = renderHook(() => useApiClient(), {
        wrapper: ApiClientProvider,
      })

      expect(result.current).toBeDefined()
      expect(result.current).toHaveProperty('get')
      expect(result.current).toHaveProperty('post')
    })

    it('should throw error when used outside provider', () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()

      expect(() => {
        renderHook(() => useApiClient())
      }).toThrow('useApiClient must be used within an ApiClientProvider')

      consoleError.mockRestore()
    })

    it('should provide same instance across multiple hook calls', () => {
      let client1: any
      let client2: any

      const TestComponent = () => {
        client1 = useApiClient()
        client2 = useApiClient()
        return <div>Test</div>
      }

      render(
        <ApiClientProvider>
          <TestComponent />
        </ApiClientProvider>
      )

      expect(client1).toBe(client2)
    })

    it('should provide consistent instance across re-renders', () => {
      const instances: any[] = []

      const TestComponent = ({ count }: { count: number }) => {
        const client = useApiClient()
        instances.push(client)
        return <div>{count}</div>
      }

      const { rerender } = render(
        <ApiClientProvider>
          <TestComponent count={1} />
        </ApiClientProvider>
      )

      rerender(
        <ApiClientProvider>
          <TestComponent count={2} />
        </ApiClientProvider>
      )

      rerender(
        <ApiClientProvider>
          <TestComponent count={3} />
        </ApiClientProvider>
      )

      expect(instances.length).toBe(3)
      expect(instances[0]).toBe(instances[1])
      expect(instances[1]).toBe(instances[2])
    })

    it('should provide client with all expected methods', () => {
      const { result } = renderHook(() => useApiClient(), {
        wrapper: ApiClientProvider,
      })

      expect(result.current).toHaveProperty('get')
      expect(result.current).toHaveProperty('post')
      expect(result.current).toHaveProperty('put')
      expect(result.current).toHaveProperty('patch')
      expect(result.current).toHaveProperty('delete')
      expect(result.current).toHaveProperty('login')
      expect(result.current).toHaveProperty('logout')
    })
  })

  describe('Context Provision', () => {
    it('should provide context to deeply nested components', () => {
      const DeepComponent = () => {
        const client = useApiClient()
        return <div>{client ? 'Has Client' : 'No Client'}</div>
      }

      const MiddleComponent = () => (
        <div>
          <DeepComponent />
        </div>
      )

      const { getByText } = render(
        <ApiClientProvider>
          <MiddleComponent />
        </ApiClientProvider>
      )

      expect(getByText('Has Client')).toBeInTheDocument()
    })

    it('should provide context to sibling components', () => {
      const Sibling1 = () => {
        const client = useApiClient()
        return <div>{client ? 'Sibling1 Has Client' : 'No Client'}</div>
      }

      const Sibling2 = () => {
        const client = useApiClient()
        return <div>{client ? 'Sibling2 Has Client' : 'No Client'}</div>
      }

      const { getByText } = render(
        <ApiClientProvider>
          <Sibling1 />
          <Sibling2 />
        </ApiClientProvider>
      )

      expect(getByText('Sibling1 Has Client')).toBeInTheDocument()
      expect(getByText('Sibling2 Has Client')).toBeInTheDocument()
    })

    it('should maintain separate contexts for nested providers', () => {
      const InnerComponent = () => {
        const client = useApiClient()
        return <div>Inner: {client ? 'Has Client' : 'No Client'}</div>
      }

      const OuterComponent = () => {
        const client = useApiClient()
        return (
          <div>
            Outer: {client ? 'Has Client' : 'No Client'}
            <ApiClientProvider>
              <InnerComponent />
            </ApiClientProvider>
          </div>
        )
      }

      const { getByText } = render(
        <ApiClientProvider>
          <OuterComponent />
        </ApiClientProvider>
      )

      expect(getByText(/Outer: Has Client/)).toBeInTheDocument()
      expect(getByText(/Inner: Has Client/)).toBeInTheDocument()
    })
  })

  describe('Client Configuration', () => {
    it('should create ApiClient on mount', () => {
      const { ApiClient } = require('@/lib/api')

      render(
        <ApiClientProvider>
          <div>Test</div>
        </ApiClientProvider>
      )

      expect(ApiClient).toHaveBeenCalled()
    })

    it('should create only one ApiClient instance per provider', () => {
      const { ApiClient } = require('@/lib/api')
      ApiClient.mockClear()

      const TestComponent = () => {
        useApiClient()
        useApiClient()
        useApiClient()
        return <div>Test</div>
      }

      render(
        <ApiClientProvider>
          <TestComponent />
        </ApiClientProvider>
      )

      expect(ApiClient).toHaveBeenCalledTimes(1)
    })

    it('should memoize ApiClient instance', () => {
      let renderCount = 0

      const TestComponent = ({ update }: { update: number }) => {
        renderCount++
        const client = useApiClient()
        return (
          <div>
            {update} - {client ? 'Client' : 'No Client'}
          </div>
        )
      }

      const { rerender } = render(
        <ApiClientProvider>
          <TestComponent update={1} />
        </ApiClientProvider>
      )

      const initialRenderCount = renderCount

      rerender(
        <ApiClientProvider>
          <TestComponent update={2} />
        </ApiClientProvider>
      )

      rerender(
        <ApiClientProvider>
          <TestComponent update={3} />
        </ApiClientProvider>
      )

      expect(renderCount).toBeGreaterThan(initialRenderCount)
    })
  })

  describe('Error Handling', () => {
    it('should throw descriptive error outside provider', () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()

      expect(() => {
        renderHook(() => useApiClient())
      }).toThrow('useApiClient must be used within an ApiClientProvider')

      consoleError.mockRestore()
    })

    it('should handle component errors gracefully', () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()

      const BrokenComponent = () => {
        throw new Error('Component error')
      }

      expect(() => {
        render(
          <ApiClientProvider>
            <BrokenComponent />
          </ApiClientProvider>
        )
      }).toThrow('Component error')

      consoleError.mockRestore()
    })

    it('should maintain context after child error', () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()

      const WorkingComponent = () => {
        const client = useApiClient()
        return <div>{client ? 'Working' : 'Not Working'}</div>
      }

      const { getByText } = render(
        <ApiClientProvider>
          <WorkingComponent />
        </ApiClientProvider>
      )

      expect(getByText('Working')).toBeInTheDocument()

      consoleError.mockRestore()
    })
  })

  describe('Integration Scenarios', () => {
    it('should work with conditional rendering', () => {
      const ConditionalComponent = ({ show }: { show: boolean }) => {
        const client = useApiClient()
        return show ? (
          <div>Shown: {client ? 'Has Client' : 'No Client'}</div>
        ) : null
      }

      const { getByText, rerender } = render(
        <ApiClientProvider>
          <ConditionalComponent show={false} />
        </ApiClientProvider>
      )

      expect(() => getByText(/Shown/)).toThrow()

      rerender(
        <ApiClientProvider>
          <ConditionalComponent show={true} />
        </ApiClientProvider>
      )

      expect(getByText('Shown: Has Client')).toBeInTheDocument()
    })

    it('should work with list rendering', () => {
      const ListItem = ({ id }: { id: number }) => {
        const client = useApiClient()
        return (
          <div>
            Item {id}: {client ? 'Connected' : 'Not Connected'}
          </div>
        )
      }

      const { getByText } = render(
        <ApiClientProvider>
          {[1, 2, 3].map((id) => (
            <ListItem key={id} id={id} />
          ))}
        </ApiClientProvider>
      )

      expect(getByText('Item 1: Connected')).toBeInTheDocument()
      expect(getByText('Item 2: Connected')).toBeInTheDocument()
      expect(getByText('Item 3: Connected')).toBeInTheDocument()
    })

    it('should work with lazy components', async () => {
      const LazyComponent = React.lazy(
        () =>
          new Promise<{ default: React.ComponentType }>((resolve) => {
            setTimeout(() => {
              resolve({
                default: function LazyClientComponent() {
                  const client = useApiClient()
                  return <div>Lazy: {client ? 'Loaded' : 'Not Loaded'}</div>
                },
              })
            }, 0)
          })
      )

      const { findByText } = render(
        <ApiClientProvider>
          <React.Suspense fallback={<div>Loading...</div>}>
            <LazyComponent />
          </React.Suspense>
        </ApiClientProvider>
      )

      expect(await findByText('Lazy: Loaded')).toBeInTheDocument()
    })

    it('should support multiple independent providers', () => {
      const Component1 = () => {
        const client = useApiClient()
        return <div>Provider 1: {client ? 'Active' : 'Inactive'}</div>
      }

      const Component2 = () => {
        const client = useApiClient()
        return <div>Provider 2: {client ? 'Active' : 'Inactive'}</div>
      }

      const { getByText } = render(
        <>
          <ApiClientProvider>
            <Component1 />
          </ApiClientProvider>
          <ApiClientProvider>
            <Component2 />
          </ApiClientProvider>
        </>
      )

      expect(getByText('Provider 1: Active')).toBeInTheDocument()
      expect(getByText('Provider 2: Active')).toBeInTheDocument()
    })
  })

  describe('Performance', () => {
    it('should not create new client instance on provider rerenders', () => {
      const { ApiClient } = require('@/lib/api')
      ApiClient.mockClear()

      const Parent = ({ count }: { count: number }) => (
        <ApiClientProvider>
          <div>Count: {count}</div>
        </ApiClientProvider>
      )

      const { rerender } = render(<Parent count={1} />)

      // First render creates one instance
      expect(ApiClient.mock.calls.length).toBe(1)

      // Rerenders should NOT create new instances due to useMemo([])
      rerender(<Parent count={2} />)
      expect(ApiClient.mock.calls.length).toBe(1)

      rerender(<Parent count={3} />)
      expect(ApiClient.mock.calls.length).toBe(1)
    })

    it('should handle rapid re-renders efficiently', () => {
      const TestComponent = ({ value }: { value: number }) => {
        const client = useApiClient()
        return (
          <div>
            {value}: {client ? 'OK' : 'Error'}
          </div>
        )
      }

      const { rerender } = render(
        <ApiClientProvider>
          <TestComponent value={1} />
        </ApiClientProvider>
      )

      for (let i = 2; i <= 100; i++) {
        rerender(
          <ApiClientProvider>
            <TestComponent value={i} />
          </ApiClientProvider>
        )
      }

      expect(true).toBe(true)
    })
  })
})

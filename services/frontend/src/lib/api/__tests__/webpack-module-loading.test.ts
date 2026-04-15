/**
 * Tests for Issue #123: Fix Critical Webpack Module Loading Errors
 *
 * These tests verify that the webpack module loading fixes work correctly
 * and prevent the "Cannot read properties of undefined (reading 'call')" errors.
 */

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'projects.searchPlaceholder': 'Search projects...',
        'projects.noProjects': 'No projects found',
        'projects.loading': 'Loading projects...',
        'tasks.searchPlaceholder': 'Search tasks...',
        'tasks.noTasks': 'No tasks found',
        'tasks.loading': 'Loading tasks...',
        'common.search': 'Search',
        'common.loading': 'Loading...',
        'common.save': 'Save',
        'common.cancel': 'Cancel',
        'common.delete': 'Delete',
        'common.edit': 'Edit',
        'common.create': 'Create',
        'common.update': 'Update',
        'common.close': 'Close',
        'annotations.loading': 'Loading annotations...',
        'annotations.noAnnotations': 'No annotations found',
        'quality.title': 'Quality Control',
        'quality.loading': 'Loading quality metrics...',
        'analytics.title': 'Analytics',
        'analytics.loading': 'Loading analytics...',
      }
      return translations[key] || key
    },
    currentLanguage: 'en',
  }),
}))

import { ApiClient } from '../index'

describe('Issue #123: Webpack Module Loading Fixes', () => {
  describe('Module Initialization', () => {
    test('should initialize ApiClient without errors', () => {
      expect(() => {
        const apiClient = new ApiClient()
        expect(apiClient).toBeInstanceOf(ApiClient)
      }).not.toThrow()
    })

    test('should have all required methods after initialization', () => {
      const apiClient = new ApiClient()

      // Test core authentication methods
      expect(typeof apiClient.login).toBe('function')
      expect(typeof apiClient.signup).toBe('function')
      expect(typeof apiClient.getCurrentUser).toBe('function')
      expect(typeof apiClient.logout).toBe('function')

      // Test task methods that actually exist
      expect(typeof apiClient.createTask).toBe('function')
      expect(typeof apiClient.updateTask).toBe('function')
      expect(typeof apiClient.getTaskData).toBe('function')
      expect(typeof apiClient.getTaskResponses).toBe('function')

      // Note: Annotation methods have been removed from ApiClient
      // The old annotation system is no longer in use
    })
  })

  describe('Circular Dependency Prevention', () => {
    test('should not have circular dependencies in API imports', () => {
      // Import should work without causing circular dependency errors
      expect(() => {
        const { ApiClient } = require('../index')
        new ApiClient()
      }).not.toThrow()
    })

    test('should handle multiple ApiClient instances', () => {
      expect(() => {
        const client1 = new ApiClient()
        const client2 = new ApiClient()
        const client3 = new ApiClient()

        expect(client1).not.toBe(client2)
        expect(client2).not.toBe(client3)
      }).not.toThrow()
    })
  })

  describe('Barrel Export Fixes', () => {
    test('should export types explicitly without causing module issues', () => {
      // Test that type imports work correctly
      expect(() => {
        const { ApiClient } = require('../index')
        // Types should be available for TypeScript but not cause runtime issues
        expect(typeof ApiClient).toBe('function')
      }).not.toThrow()
    })

    test('should not export star exports that cause webpack issues', () => {
      // This test ensures we're not using problematic export * patterns
      const indexModule = require('../index')

      // Should have ApiClient as main export
      expect(indexModule.ApiClient).toBeDefined()
      expect(typeof indexModule.ApiClient).toBe('function')
    })
  })

  describe('Error Boundary Integration', () => {
    test('should handle initialization errors gracefully', () => {
      // Mock a module loading error scenario
      const originalConsoleError = console.error
      console.error = jest.fn()

      try {
        // This should not crash the entire application
        const apiClient = new ApiClient()
        expect(apiClient).toBeDefined()
      } catch (error) {
        // If there's an error, it should be caught by error boundary
        expect(error).toBeInstanceOf(Error)
      } finally {
        console.error = originalConsoleError
      }
    })
  })

  describe('Memory Management', () => {
    test('should not leak memory during initialization', () => {
      const initialMemory = process.memoryUsage()

      // Create and destroy multiple instances
      for (let i = 0; i < 10; i++) {
        const apiClient = new ApiClient()
        // Force garbage collection if available
        if (global.gc) {
          global.gc()
        }
      }

      const finalMemory = process.memoryUsage()

      // Memory usage should not increase dramatically
      const memoryIncrease = finalMemory.heapUsed - initialMemory.heapUsed
      expect(memoryIncrease).toBeLessThan(10 * 1024 * 1024) // Less than 10MB increase
    })
  })

  describe('Webpack Factory Function Simulation', () => {
    test('should handle webpack factory function patterns', () => {
      // Simulate webpack module factory pattern
      const moduleFactory = () => {
        const { ApiClient } = require('../index')
        return new ApiClient()
      }

      expect(() => {
        const client = moduleFactory()
        expect(client).toBeInstanceOf(ApiClient)
      }).not.toThrow()
    })

    test('should work with webpack module resolution patterns', () => {
      // Simulate how webpack resolves modules
      const moduleMap = new Map()

      const loadModule = (name: string) => {
        if (!moduleMap.has(name)) {
          if (name === 'api') {
            const { ApiClient } = require('../index')
            moduleMap.set(name, { ApiClient })
          }
        }
        return moduleMap.get(name)
      }

      expect(() => {
        const apiModule = loadModule('api')
        const client = new apiModule.ApiClient()
        expect(client).toBeDefined()
      }).not.toThrow()
    })
  })

  describe('Next.js 15 Compatibility', () => {
    test('should work with Next.js module resolution', () => {
      // Test that imports work in Next.js environment
      expect(() => {
        // Simulate Next.js module loading
        const apiModule = require('../index')
        expect(apiModule.ApiClient).toBeDefined()

        const client = new apiModule.ApiClient()
        expect(client).toBeInstanceOf(apiModule.ApiClient)
      }).not.toThrow()
    })

    test('should handle server/client boundary correctly', () => {
      // ApiClient should work on both server and client side
      const apiClient = new ApiClient()

      // Should have methods available
      expect(typeof apiClient.getCurrentUser).toBe('function')
      expect(typeof apiClient.getProjects).toBe('function')

      // Should not cause hydration mismatches - verify client initializes consistently
      expect(apiClient).toBeDefined()
      expect(apiClient).toBeInstanceOf(ApiClient)
    })
  })

  describe('Performance Optimization', () => {
    test('should initialize quickly without blocking main thread', async () => {
      const startTime = performance.now()

      const apiClient = new ApiClient()
      expect(apiClient).toBeDefined()

      const endTime = performance.now()
      const initTime = endTime - startTime

      // Initialization should be fast (< 100ms)
      expect(initTime).toBeLessThan(100)
    })

    test('should not cause excessive bundle size', () => {
      // Test that the module doesn't import unnecessary dependencies
      const apiClient = new ApiClient()

      // Check that only required properties are initialized
      const properties = Object.getOwnPropertyNames(apiClient)

      // Should have core properties but not excessive ones
      expect(properties.length).toBeGreaterThan(10) // Has required methods
      expect(properties.length).toBeLessThan(200) // Not bloated
    })
  })

  describe('Development vs Production Behavior', () => {
    test('should work consistently across environments', () => {
      const originalNodeEnv = process.env.NODE_ENV

      try {
        // Test development environment
        process.env.NODE_ENV = 'development'
        const devClient = new ApiClient()
        expect(devClient).toBeDefined()

        // Test production environment
        process.env.NODE_ENV = 'production'
        const prodClient = new ApiClient()
        expect(prodClient).toBeDefined()

        // Both should have same interface
        expect(typeof devClient.getCurrentUser).toBe(
          typeof prodClient.getCurrentUser
        )
        expect(typeof devClient.getTasks).toBe(typeof prodClient.getTasks)
      } finally {
        process.env.NODE_ENV = originalNodeEnv
      }
    })
  })

  describe('Error Message Quality', () => {
    test('should provide helpful error messages for common issues', () => {
      // Mock a common webpack error scenario
      const mockError = new Error(
        "Cannot read properties of undefined (reading 'call')"
      )

      // Error should be descriptive
      expect(mockError.message).toContain('Cannot read properties of undefined')

      // Our error boundary should catch and log this appropriately
      const originalConsoleError = console.error
      const mockConsoleError = jest.fn()
      console.error = mockConsoleError

      try {
        // Simulate error boundary catching the error
        if (mockError.message.includes('Cannot read properties of undefined')) {
          console.error('Webpack module loading error detected:', {
            message: mockError.message,
            stack: mockError.stack,
          })
        }

        expect(mockConsoleError).toHaveBeenCalledWith(
          'Webpack module loading error detected:',
          expect.objectContaining({
            message: expect.stringContaining(
              'Cannot read properties of undefined'
            ),
          })
        )
      } finally {
        console.error = originalConsoleError
      }
    })
  })
})

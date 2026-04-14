/**
 * @jest-environment jsdom
 *
 * DevelopmentLogger Comprehensive Test Suite
 * Tests logging with throttling, auth pattern detection, and message normalization
 */

describe('DevelopmentLogger', () => {
  const originalEnv = process.env
  let consoleLogSpy: jest.SpyInstance
  let consoleWarnSpy: jest.SpyInstance
  let consoleErrorSpy: jest.SpyInstance
  let consoleDebugSpy: jest.SpyInstance

  beforeEach(() => {
    jest.clearAllMocks()
    process.env = { ...originalEnv }

    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation()
    consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation()
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
    consoleDebugSpy = jest.spyOn(console, 'debug').mockImplementation()

    // Clear the internal log cache by creating a new instance
    jest.resetModules()
    jest.useFakeTimers()
  })

  afterEach(() => {
    process.env = originalEnv
    consoleLogSpy.mockRestore()
    consoleWarnSpy.mockRestore()
    consoleErrorSpy.mockRestore()
    consoleDebugSpy.mockRestore()
    jest.useRealTimers()
  })

  describe('log method', () => {
    it('should log message in development', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Test message')

      expect(consoleLogSpy).toHaveBeenCalledWith('Test message')
    })

    it('should log message in production', () => {
      process.env.NODE_ENV = 'production'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Test message')

      expect(consoleLogSpy).toHaveBeenCalledWith('Test message')
    })

    it('should throttle identical messages in development', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Repeated message')
      logger.log('Repeated message')
      logger.log('Repeated message')

      expect(consoleLogSpy).toHaveBeenCalledTimes(1)
    })

    it('should log with count after throttle period', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Repeated message')
      logger.log('Repeated message')
      logger.log('Repeated message')

      jest.advanceTimersByTime(5500)

      logger.log('Repeated message')

      expect(consoleLogSpy).toHaveBeenCalledTimes(2)
      expect(consoleLogSpy).toHaveBeenLastCalledWith(
        'Repeated message (occurred 4 times)'
      )
    })

    it('should handle multiple arguments', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Message', 'arg1', 'arg2')

      expect(consoleLogSpy).toHaveBeenCalledWith('Message', 'arg1', 'arg2')
    })

    it('should handle object arguments', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      const obj = { key: 'value' }
      logger.log('Object:', obj)

      expect(consoleLogSpy).toHaveBeenCalledWith('Object:', obj)
    })

    it('should handle mixed types', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('String', 123, true, null, undefined, { obj: 'value' })

      expect(consoleLogSpy).toHaveBeenCalledWith(
        'String',
        123,
        true,
        null,
        undefined,
        { obj: 'value' }
      )
    })
  })

  describe('warn method', () => {
    it('should warn message in development', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.warn('Warning message')

      expect(consoleWarnSpy).toHaveBeenCalledWith('Warning message')
    })

    it('should warn message in production', () => {
      process.env.NODE_ENV = 'production'
      const { logger } = require('@/lib/utils/logger')

      logger.warn('Warning message')

      expect(consoleWarnSpy).toHaveBeenCalledWith('Warning message')
    })

    it('should throttle identical warnings in development', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.warn('Repeated warning')
      logger.warn('Repeated warning')
      logger.warn('Repeated warning')

      expect(consoleWarnSpy).toHaveBeenCalledTimes(1)
    })

    it('should log with count after throttle period', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.warn('Repeated warning')
      logger.warn('Repeated warning')

      jest.advanceTimersByTime(5500)

      logger.warn('Repeated warning')

      expect(consoleWarnSpy).toHaveBeenCalledTimes(2)
      expect(consoleWarnSpy).toHaveBeenLastCalledWith(
        'Repeated warning (occurred 3 times)'
      )
    })
  })

  describe('error method', () => {
    it('should error message in development', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('Error message')

      expect(consoleErrorSpy).toHaveBeenCalledWith('Error message')
    })

    it('should error message in production', () => {
      process.env.NODE_ENV = 'production'
      const { logger } = require('@/lib/utils/logger')

      logger.error('Error message')

      expect(consoleErrorSpy).toHaveBeenCalledWith('Error message')
    })

    it('should throttle non-auth errors in development', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('Regular error')
      logger.error('Regular error')
      logger.error('Regular error')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(1)
    })

    it('should throttle auth errors with longer delay (30s)', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('401 Unauthorized error')
      logger.error('401 Unauthorized error')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(1)

      jest.advanceTimersByTime(5500)

      logger.error('401 Unauthorized error')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(1)

      jest.advanceTimersByTime(25000)

      logger.error('401 Unauthorized error')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(2)
    })

    it('should detect 401 Unauthorized pattern', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('Request failed: 401 Unauthorized')
      logger.error('Request failed: 401 Unauthorized')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(1)

      jest.advanceTimersByTime(31000)

      logger.error('Request failed: 401 Unauthorized')

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Request failed: 401 Unauthorized (occurred 3 times) (auth-related logs throttled)'
      )
    })

    it('should detect Authentication failed pattern', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('Authentication failed for user')

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Authentication failed for user'
      )
    })

    it('should detect Token refresh pattern', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('Token refresh failed')

      expect(consoleErrorSpy).toHaveBeenCalledWith('Token refresh failed')
    })

    it('should detect auth/me pattern', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('Request to /api/auth/me failed')

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Request to /api/auth/me failed'
      )
    })

    it('should detect triggering logout pattern', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('Triggering logout due to auth failure')

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Triggering logout due to auth failure'
      )
    })

    it('should detect session expired pattern', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('Session expired, please log in again')

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Session expired, please log in again'
      )
    })

    it('should be case insensitive for auth patterns', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('AUTHENTICATION FAILED')
      logger.error('session EXPIRED')
      logger.error('401 unauthorized')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(3)
    })
  })

  describe('debug method', () => {
    it('should log debug message in development', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.debug('Debug message')

      expect(consoleDebugSpy).toHaveBeenCalledWith('Debug message')
    })

    it('should not log debug message in production', () => {
      process.env.NODE_ENV = 'production'
      const { logger } = require('@/lib/utils/logger')

      logger.debug('Debug message')

      expect(consoleDebugSpy).not.toHaveBeenCalled()
    })

    it('should throttle identical debug messages in development', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.debug('Repeated debug')
      logger.debug('Repeated debug')
      logger.debug('Repeated debug')

      expect(consoleDebugSpy).toHaveBeenCalledTimes(1)
    })
  })

  describe('Message normalization for auth patterns', () => {
    it('should normalize API auth URLs', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('Error at /api/auth/me')
      logger.error('Error at /api/auth/login')
      logger.error('Error at /api/auth/logout')

      jest.advanceTimersByTime(31000)

      logger.error('Error at /api/auth/me')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(2)
      expect(consoleErrorSpy).toHaveBeenLastCalledWith(
        'Error at /api/auth/me (occurred 4 times) (auth-related logs throttled)'
      )
    })

    it('should normalize timestamps', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('401 Unauthorized at 2025-01-15T10:30:45')
      logger.error('401 Unauthorized at 2025-01-15T10:30:50')
      logger.error('401 Unauthorized at 2025-01-15T10:31:00')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(1)
    })

    it('should normalize UUIDs', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error(
        '401 Unauthorized for request a1b2c3d4-e5f6-7890-abcd-ef1234567890'
      )
      logger.error(
        '401 Unauthorized for request b2c3d4e5-f6a7-8901-bcde-f12345678901'
      )

      expect(consoleErrorSpy).toHaveBeenCalledTimes(1)
    })

    it('should normalize numbers', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('401 Unauthorized for user 123')
      logger.error('401 Unauthorized for user 456')
      logger.error('401 Unauthorized for user 789')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(1)
    })

    it('should not normalize non-auth messages', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('Error 500 at /api/projects/123')
      logger.error('Error 500 at /api/projects/456')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(2)
    })
  })

  describe('Cache management', () => {
    it('should clean up old entries when cache exceeds 100 items', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      for (let i = 0; i < 110; i++) {
        logger.log(`Message ${i}`)
      }

      jest.advanceTimersByTime(61000)

      logger.log('Trigger cleanup')

      expect(consoleLogSpy).toHaveBeenCalledTimes(111)
    })

    it('should not clean up recent entries', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Recent message')

      jest.advanceTimersByTime(30000)

      for (let i = 0; i < 105; i++) {
        logger.log(`Message ${i}`)
      }

      logger.log('Recent message')

      expect(consoleLogSpy).toHaveBeenCalledWith(
        'Recent message (occurred 2 times)'
      )
    })
  })

  describe('Different log levels with same message', () => {
    it('should track different log levels separately', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Same message')
      logger.warn('Same message')
      logger.error('Same message')
      logger.debug('Same message')

      expect(consoleLogSpy).toHaveBeenCalledTimes(1)
      expect(consoleWarnSpy).toHaveBeenCalledTimes(1)
      expect(consoleErrorSpy).toHaveBeenCalledTimes(1)
      expect(consoleDebugSpy).toHaveBeenCalledTimes(1)
    })
  })

  describe('Production behavior', () => {
    it('should always log in production without throttling', () => {
      process.env.NODE_ENV = 'production'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Repeated message')
      logger.log('Repeated message')
      logger.log('Repeated message')

      expect(consoleLogSpy).toHaveBeenCalledTimes(3)
    })

    it('should not log debug in production', () => {
      process.env.NODE_ENV = 'production'
      const { logger } = require('@/lib/utils/logger')

      logger.debug('Debug message')
      logger.debug('Debug message')

      expect(consoleDebugSpy).not.toHaveBeenCalled()
    })

    it('should log all error levels in production', () => {
      process.env.NODE_ENV = 'production'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Log')
      logger.warn('Warn')
      logger.error('Error')

      expect(consoleLogSpy).toHaveBeenCalledTimes(1)
      expect(consoleWarnSpy).toHaveBeenCalledTimes(1)
      expect(consoleErrorSpy).toHaveBeenCalledTimes(1)
    })
  })

  describe('Complex object serialization', () => {
    it('should serialize objects in message creation', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      const obj = { key: 'value', nested: { prop: 123 } }
      logger.log('Object:', obj)
      logger.log('Object:', obj)

      expect(consoleLogSpy).toHaveBeenCalledTimes(1)
    })

    it('should handle circular references', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      const circular: any = { prop: 'value' }
      circular.self = circular

      // JSON.stringify will throw on circular references
      expect(() => logger.log('Circular:', circular)).toThrow(
        'Converting circular structure to JSON'
      )
    })

    it('should handle arrays', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Array:', [1, 2, 3])
      logger.log('Array:', [1, 2, 3])

      expect(consoleLogSpy).toHaveBeenCalledTimes(1)
    })

    it('should handle null and undefined', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Null:', null)
      logger.log('Undefined:', undefined)

      expect(consoleLogSpy).toHaveBeenCalledTimes(2)
    })
  })

  describe('Throttle timing precision', () => {
    it('should respect exact throttle timing', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Timed message')

      jest.advanceTimersByTime(4999)
      logger.log('Timed message')

      expect(consoleLogSpy).toHaveBeenCalledTimes(1)

      jest.advanceTimersByTime(2)
      logger.log('Timed message')

      expect(consoleLogSpy).toHaveBeenCalledTimes(2)
    })

    it('should respect auth throttle timing (30s)', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.error('401 Unauthorized')

      jest.advanceTimersByTime(29999)
      logger.error('401 Unauthorized')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(1)

      jest.advanceTimersByTime(2)
      logger.error('401 Unauthorized')

      expect(consoleErrorSpy).toHaveBeenCalledTimes(2)
    })
  })

  describe('Count reset behavior', () => {
    it('should reset count after logging with count', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      // First round: 3 logs
      logger.log('Count reset message')
      logger.log('Count reset message')
      logger.log('Count reset message')

      jest.advanceTimersByTime(5500)

      // This triggers logging with count and resets count to 0
      logger.log('Count reset message')

      expect(consoleLogSpy).toHaveBeenLastCalledWith(
        'Count reset message (occurred 4 times)'
      )

      // After count reset, count is 0. Next call makes it 1.
      logger.log('Count reset message')

      jest.advanceTimersByTime(5500)

      // This makes count 2, and after throttle period it logs with count
      logger.log('Count reset message')

      // Count is now 2, so it logs with count
      expect(consoleLogSpy).toHaveBeenLastCalledWith(
        'Count reset message (occurred 2 times)'
      )
    })
  })

  describe('Edge cases', () => {
    it('should handle empty string messages', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('')
      logger.log('')

      expect(consoleLogSpy).toHaveBeenCalledTimes(1)
    })

    it('should handle very long messages', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      const longMessage = 'a'.repeat(10000)
      logger.log(longMessage)
      logger.log(longMessage)

      expect(consoleLogSpy).toHaveBeenCalledTimes(1)
    })

    it('should handle messages with special regex characters', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      logger.log('Message with [brackets] and (parens) and .dots')
      logger.log('Message with [brackets] and (parens) and .dots')

      expect(consoleLogSpy).toHaveBeenCalledTimes(1)
    })

    it('should handle rapid successive logs', () => {
      process.env.NODE_ENV = 'development'
      const { logger } = require('@/lib/utils/logger')

      for (let i = 0; i < 50; i++) {
        logger.log('Rapid log')
      }

      expect(consoleLogSpy).toHaveBeenCalledTimes(1)
    })
  })
})

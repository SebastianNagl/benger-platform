/**
 * Development logger with throttling to prevent console spam
 * Prevents excessive logging during Fast Refresh loops
 */

interface LogEntry {
  message: string
  count: number
  lastLogged: number
}

class DevelopmentLogger {
  private logCache = new Map<string, LogEntry>()
  private readonly throttleMs = 5000 // 5 seconds between identical logs
  private readonly authThrottleMs = 30000 // 30 seconds for auth-related logs
  private readonly isDevelopment = process.env.NODE_ENV === 'development'
  private readonly authPatterns = [
    /401.*Unauthorized/i,
    /Authentication failed/i,
    /Token refresh/i,
    /\/api\/auth\//i,
    /triggering logout/i,
    /session expired/i,
  ]

  private shouldLog(level: string, message: string): boolean {
    // Always log in production
    if (!this.isDevelopment) {
      return true
    }

    // Check if this is an auth-related message
    const isAuthRelated = this.authPatterns.some((pattern) =>
      pattern.test(message)
    )
    const throttleTime = isAuthRelated ? this.authThrottleMs : this.throttleMs

    // Create a normalized key for similar messages
    let key = `${level}:${message}`

    // For auth messages, normalize the key to group similar messages
    if (isAuthRelated) {
      // Remove URLs, timestamps, and request IDs to group similar auth errors
      key = key
        .replace(/\/api\/auth\/[\w\/]+/g, '/api/auth/*')
        .replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/g, '<timestamp>')
        .replace(
          /[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}/gi,
          '<uuid>'
        )
        .replace(/\b\d+\b/g, '<number>')
    }

    const now = Date.now()

    const entry = this.logCache.get(key)
    if (entry) {
      entry.count++

      // Only log if enough time has passed
      if (now - entry.lastLogged >= throttleTime) {
        entry.lastLogged = now
        // Include count in throttled message
        if (entry.count > 1) {
          const suffix = isAuthRelated ? ' (auth-related logs throttled)' : ''
          ;(console as any)[level](
            `${message} (occurred ${entry.count} times)${suffix}`
          )
          entry.count = 0
        }
        return false // We logged with count, don't log original
      }

      return false // Throttled
    }

    // First occurrence
    this.logCache.set(key, {
      message,
      count: 1,
      lastLogged: now,
    })

    // Clean up old entries periodically
    if (this.logCache.size > 100) {
      const cutoff = now - 60000 // 1 minute
      for (const [key, entry] of this.logCache.entries()) {
        if (entry.lastLogged < cutoff) {
          this.logCache.delete(key)
        }
      }
    }

    return true
  }

  log(...args: any[]) {
    const message = args
      .map((arg) =>
        typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
      )
      .join(' ')

    if (this.shouldLog('log', message)) {
      console.log(...args)
    }
  }

  warn(...args: any[]) {
    const message = args
      .map((arg) =>
        typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
      )
      .join(' ')

    if (this.shouldLog('warn', message)) {
      console.warn(...args)
    }
  }

  error(...args: any[]) {
    const message = args
      .map((arg) =>
        typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
      )
      .join(' ')

    // In development, throttle auth errors more aggressively
    if (
      this.isDevelopment &&
      this.authPatterns.some((pattern) => pattern.test(message))
    ) {
      // Use shouldLog for auth errors in development
      if (this.shouldLog('error', message)) {
        console.error(...args)
      }
    } else {
      // Always log non-auth errors
      if (this.shouldLog('error', message)) {
        console.error(...args)
      }
    }
  }

  debug(...args: any[]) {
    // Only log debug in development
    if (!this.isDevelopment) {
      return
    }

    const message = args
      .map((arg) =>
        typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
      )
      .join(' ')

    if (this.shouldLog('debug', message)) {
      console.debug(...args)
    }
  }
}

// Export singleton instance
export const logger = new DevelopmentLogger()

// Export as default for easier imports
export default logger

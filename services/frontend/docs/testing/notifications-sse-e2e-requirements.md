# SSE Notifications Stream - E2E Testing Requirements

## Overview

The notification system uses Server-Sent Events (SSE) for real-time notifications. While unit tests can verify business logic and error handling, the following behaviors require end-to-end testing with browser EventSource API.

## Test Coverage Summary

### Unit Test Coverage (as of 2025-01-17)

- **Notifications Page (`src/app/notifications/page.tsx`)**: 66.84%
- **SSE Stream Route (`src/app/api/notifications/stream/route.ts`)**: 84.61%

### Why E2E Testing is Required

SSE streaming behavior depends on:

1. Browser EventSource API
2. Real HTTP streaming connections
3. Browser-specific connection management
4. Actual network conditions
5. Cookie and authentication flow in browser context

These cannot be adequately tested in Jest's jsdom environment.

## Required E2E Test Scenarios

### 1. EventSource Connection Lifecycle

**What to test:**

- EventSource successfully opens connection to `/api/notifications/stream`
- `onopen` event fires when stream is established
- Connection remains open for extended periods (>5 minutes)
- Connection automatically reconnects on disconnect
- Exponential backoff between reconnection attempts

**Test location:** `e2e/notifications-stream.spec.ts`

**Example:**

```typescript
test('SSE connection establishes and remains open', async () => {
  const page = await browser.newPage()
  await page.goto('http://benger.localhost/notifications')

  const connected = await page.evaluate(() => {
    return new Promise((resolve) => {
      const eventSource = new EventSource('/api/notifications/stream')
      eventSource.onopen = () => resolve(true)
      eventSource.onerror = () => resolve(false)
      setTimeout(() => resolve(false), 5000)
    })
  })

  expect(connected).toBe(true)

  // Verify connection stays open
  await page.waitForTimeout(60000) // 1 minute
  const stillConnected = await page.evaluate(() => {
    return window.eventSource?.readyState === EventSource.OPEN
  })
  expect(stillConnected).toBe(true)
})
```

### 2. Real-time Message Reception

**What to test:**

- Messages are received in real-time as they're sent
- Message data is correctly parsed as JSON
- Multiple messages are received in sequence
- Message types (`new_notification`, `unread_count`, etc.) are handled correctly
- Messages arrive immediately without buffering delays

**Test location:** `e2e/notifications-stream.spec.ts`

**Example:**

```typescript
test('receives notification messages in real-time', async () => {
  const page = await browser.newPage()
  await page.goto('http://benger.localhost/notifications')

  // Set up message collection
  await page.evaluate(() => {
    window.receivedMessages = []
    const eventSource = new EventSource('/api/notifications/stream')
    eventSource.onmessage = (event) => {
      window.receivedMessages.push(JSON.parse(event.data))
    }
  })

  // Wait for proxy_connected message
  await page.waitForFunction(() =>
    window.receivedMessages?.some((m) => m.type === 'proxy_connected')
  )

  // Trigger a notification via API
  await api.createTestNotification({
    type: 'task_created',
    title: 'Test Task',
    message: 'A test task has been created',
  })

  // Verify notification received via SSE
  await page.waitForFunction(
    () =>
      window.receivedMessages?.some(
        (m) =>
          m.type === 'new_notification' && m.notification.title === 'Test Task'
      ),
    { timeout: 5000 }
  )

  const messages = await page.evaluate(() => window.receivedMessages)
  expect(messages.length).toBeGreaterThan(1)
  expect(messages.some((m) => m.type === 'new_notification')).toBe(true)
})
```

### 3. Token Refresh During Active Stream

**What to test:**

- Stream continues when access_token expires mid-stream
- New access_token is obtained via refresh_token
- No notifications are lost during token refresh
- Stream reconnects after token refresh without user intervention

**Test location:** `e2e/notifications-auth.spec.ts`

**Example:**

```typescript
test('handles token expiry during active SSE connection', async () => {
  const page = await browser.newPage()

  // Set up cookies with short-lived access token
  await page.setCookie({
    name: 'access_token',
    value: shortLivedToken,
    domain: 'benger.localhost',
    httpOnly: true,
  })

  await page.goto('http://benger.localhost/notifications')

  // Wait for initial connection
  await page.waitForFunction(
    () => window.eventSource?.readyState === EventSource.OPEN
  )

  // Wait for token to expire (e.g., 30 seconds)
  await page.waitForTimeout(30000)

  // Trigger notification after token expiry
  await api.createTestNotification({ title: 'Post-Expiry Test' })

  // Verify notification still received (stream auto-refreshed)
  await page.waitForFunction(
    () =>
      window.receivedMessages?.some(
        (m) => m.notification?.title === 'Post-Expiry Test'
      ),
    { timeout: 10000 }
  )
})
```

### 4. Cross-Origin Behavior

**What to test:**

- CORS headers allow EventSource from different origins
- Credentials (cookies) are properly sent with requests
- `withCredentials` option works correctly
- Authorization failures are properly handled

**Test location:** `e2e/notifications-cors.spec.ts`

**Example:**

```typescript
test('SSE connection works with CORS credentials', async () => {
  const page = await browser.newPage()

  // Test from different origin
  await page.goto('http://localhost:3000/notifications')

  const connected = await page.evaluate(() => {
    return new Promise((resolve) => {
      // EventSource automatically includes credentials
      const eventSource = new EventSource(
        'http://benger.localhost/api/notifications/stream',
        { withCredentials: true }
      )
      eventSource.onopen = () => resolve(true)
      eventSource.onerror = () => resolve(false)
    })
  })

  expect(connected).toBe(true)
})
```

### 5. Error Handling and Recovery

**What to test:**

- `onerror` event fires on connection errors
- Exponential backoff reconnection works (1s, 2s, 4s, 8s...)
- Stream recovers from temporary backend failures
- Graceful handling of network interruptions
- Maximum reconnection attempts are respected
- User is notified of persistent connection failures

**Test location:** `e2e/notifications-error-handling.spec.ts`

**Example:**

```typescript
test('reconnects with exponential backoff after connection loss', async () => {
  const page = await browser.newPage()
  await page.goto('http://benger.localhost/notifications')

  // Track reconnection attempts
  await page.evaluate(() => {
    window.reconnectAttempts = []
    window.reconnectTimes = []

    const originalEventSource = window.EventSource
    window.EventSource = function (url) {
      const instance = new originalEventSource(url)
      window.reconnectAttempts.push(Date.now())
      return instance
    }
  })

  // Wait for initial connection
  await page.waitForFunction(() => window.reconnectAttempts?.length === 1)

  // Simulate network failure
  await page.setOfflineMode(true)
  await page.waitForTimeout(1000)
  await page.setOfflineMode(false)

  // Verify exponential backoff
  await page.waitForFunction(() => window.reconnectAttempts?.length >= 3, {
    timeout: 10000,
  })

  const attempts = await page.evaluate(() => window.reconnectAttempts)
  const delays = []
  for (let i = 1; i < attempts.length; i++) {
    delays.push(attempts[i] - attempts[i - 1])
  }

  // Verify increasing delays (allowing 10% tolerance)
  for (let i = 1; i < delays.length; i++) {
    expect(delays[i]).toBeGreaterThanOrEqual(delays[i - 1] * 0.9)
  }
})
```

### 6. Performance and Buffering

**What to test:**

- Messages are not buffered by intermediate proxies (nginx, Traefik)
- `X-Accel-Buffering: no` header prevents nginx buffering
- Messages arrive immediately (< 100ms after backend sends)
- Stream handles high message volume (100+ messages/minute)
- No memory leaks on long-running connections (24+ hours)
- CPU usage remains stable during active streaming

**Test location:** `e2e/notifications-performance.spec.ts`

**Example:**

```typescript
test('messages arrive without buffering delays', async () => {
  const page = await browser.newPage()
  await page.goto('http://benger.localhost/notifications')

  await page.evaluate(() => {
    window.messageTimestamps = []
    const eventSource = new EventSource('/api/notifications/stream')
    eventSource.onmessage = (event) => {
      window.messageTimestamps.push({
        received: Date.now(),
        data: JSON.parse(event.data),
      })
    }
  })

  // Send notification and measure delivery time
  const sendTime = Date.now()
  await api.createTestNotification({ title: 'Latency Test' })

  await page.waitForFunction(() =>
    window.messageTimestamps?.some(
      (m) => m.data.notification?.title === 'Latency Test'
    )
  )

  const timestamps = await page.evaluate(() => window.messageTimestamps)
  const latencyTestMsg = timestamps.find(
    (m) => m.data.notification?.title === 'Latency Test'
  )

  const latency = latencyTestMsg.received - sendTime
  expect(latency).toBeLessThan(500) // Should arrive within 500ms
})

test('handles high message volume without performance degradation', async () => {
  const page = await browser.newPage()
  await page.goto('http://benger.localhost/notifications')

  await page.evaluate(() => {
    window.messageCount = 0
    const eventSource = new EventSource('/api/notifications/stream')
    eventSource.onmessage = () => {
      window.messageCount++
    }
  })

  // Send 100 notifications rapidly
  for (let i = 0; i < 100; i++) {
    await api.createTestNotification({ title: `Msg ${i}` })
  }

  // Verify all messages received within reasonable time
  await page.waitForFunction(() => window.messageCount >= 100, {
    timeout: 30000,
  })

  const messageCount = await page.evaluate(() => window.messageCount)
  expect(messageCount).toBeGreaterThanOrEqual(100)
})
```

### 7. Cleanup and Resource Management

**What to test:**

- `EventSource.close()` properly terminates connection
- Server-side resources are cleaned up on disconnect
- No memory leaks on long-running connections
- AbortController properly cancels fetch requests
- Multiple EventSource instances don't interfere with each other
- Page navigation cleans up active connections

**Test location:** `e2e/notifications-cleanup.spec.ts`

**Example:**

```typescript
test('properly cleans up on EventSource close', async () => {
  const page = await browser.newPage()
  await page.goto('http://benger.localhost/notifications')

  // Create and close EventSource
  await page.evaluate(() => {
    window.eventSource = new EventSource('/api/notifications/stream')
    return new Promise((resolve) => {
      window.eventSource.onopen = resolve
    })
  })

  await page.evaluate(() => {
    window.eventSource.close()
  })

  // Verify connection is closed
  const state = await page.evaluate(() => window.eventSource.readyState)
  expect(state).toBe(EventSource.CLOSED)

  // Verify no more messages received
  await page.evaluate(() => {
    window.afterCloseMessages = []
    // Try to listen for messages (should not receive any)
    setTimeout(() => {}, 2000)
  })

  await api.createTestNotification({ title: 'After Close' })
  await page.waitForTimeout(3000)

  const afterCloseMessages = await page.evaluate(
    () => window.afterCloseMessages?.length || 0
  )
  expect(afterCloseMessages).toBe(0)
})
```

## Test Framework Recommendations

### Primary: Puppeteer with MCP Integration

Use Puppeteer via the MCP (Model Context Protocol) integration for automated E2E tests:

**Advantages:**

- Full Chrome automation
- Real browser EventSource API
- Cookie and credential handling
- Network simulation (offline mode, throttling)
- Performance profiling
- Memory leak detection

**Setup:**

```bash
# Tests run against Docker environment
cd infra/
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Run E2E tests
npm run test:e2e
```

### Alternative: Playwright

For cross-browser testing (Chrome, Firefox, Safari):

```typescript
import { test, expect } from '@playwright/test'

test('SSE connection in multiple browsers', async ({ browserName }) => {
  // Test SSE behavior across browsers
})
```

## Integration with CI/CD

Add E2E tests to GitHub Actions workflow:

```yaml
- name: Run SSE E2E Tests
  run: |
    docker-compose up -d
    npm run test:e2e:sse
  env:
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD: false
```

## Monitoring and Metrics

For production monitoring, track:

- SSE connection success rate
- Average message latency
- Reconnection frequency
- Connection duration
- Message loss rate
- Browser compatibility issues

## Known Limitations

1. **Jest Environment**: Cannot fully test SSE streaming due to lack of browser EventSource
2. **Mock Limitations**: `request.signal.addEventListener` requires Next.js runtime
3. **Token Refresh**: Complex state machine best tested in real browser
4. **Network Conditions**: Buffering behavior varies by infrastructure

## References

- [EventSource API Documentation](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [SSE Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [Puppeteer Documentation](https://pptr.dev/)
- [Playwright Documentation](https://playwright.dev/)

## Last Updated

2025-01-17 - Initial E2E requirements documentation

# Auth Route E2E Testing Requirements

## Overview

Cookie handling in Next.js API routes requires a real HTTP context and cannot be fully tested in unit tests. This document outlines the E2E testing requirements for authentication routes using Puppeteer.

## Cookie Limitations in Unit Tests

### The Problem

- `NextResponse.headers.append()` for Set-Cookie headers is not available in Jest test environment
- `NextResponse.headers.getSetCookie()` is not implemented in test mocks
- Cookie manipulation requires a real browser/HTTP context

### Solution

- Unit tests focus on business logic (API calls, validation, error handling)
- Cookie behavior is validated in E2E tests with Puppeteer
- Tests run at `http://benger.localhost` in desktop screen resolution

## E2E Test Coverage Required

### 1. Signup Flow Cookie Tests

**Test: Signup sets authentication cookies**

```typescript
// Navigate to signup page
await page.goto('http://benger.localhost/register')

// Fill signup form
await page.fill('[name="email"]', 'test@example.com')
await page.fill('[name="password"]', 'SecurePass123!')
await page.fill('[name="username"]', 'testuser')

// Submit and wait for navigation
await page.click('button[type="submit"]')
await page.waitForNavigation()

// Verify cookies in browser
const cookies = await page.context().cookies()

const accessToken = cookies.find((c) => c.name === 'access_token')
const refreshToken = cookies.find((c) => c.name === 'refresh_token')

// Verify cookies exist
expect(accessToken).toBeDefined()
expect(refreshToken).toBeDefined()

// Verify cookie attributes
expect(accessToken.httpOnly).toBe(true)
expect(accessToken.path).toBe('/')
expect(accessToken.sameSite).toBe('Lax')

// Verify cookies are sent on subsequent requests
const response = await page.goto('http://benger.localhost/dashboard')
const requestCookies = await response.request().headers()['cookie']
expect(requestCookies).toContain('access_token')
```

**Test: Cookie attribute modifications**

```typescript
// Mock backend response with Domain attribute
// Verify Domain is stripped
// Verify SameSite=Lax is added
// Verify Secure is removed for dev environment
```

### 2. Logout Flow Cookie Tests

**Test: Logout clears authentication cookies**

```typescript
// Login first
await page.goto('http://benger.localhost/login')
await page.fill('[name="email"]', 'admin@example.com')
await page.fill('[name="password"]', 'admin')
await page.click('button[type="submit"]')
await page.waitForNavigation()

// Verify cookies are set
let cookies = await page.context().cookies()
expect(cookies.find((c) => c.name === 'access_token')).toBeDefined()

// Logout
await page.click('[data-testid="logout-button"]')
await page.waitForNavigation()

// Verify cookies are cleared
cookies = await page.context().cookies()

const accessToken = cookies.find((c) => c.name === 'access_token')
const refreshToken = cookies.find((c) => c.name === 'refresh_token')

// Cookies should either not exist or have expired
if (accessToken) {
  expect(accessToken.value).toBe('')
  expect(new Date(accessToken.expires * 1000) < new Date()).toBe(true)
}

if (refreshToken) {
  expect(refreshToken.value).toBe('')
  expect(new Date(refreshToken.expires * 1000) < new Date()).toBe(true)
}

// Verify subsequent requests don't include tokens
const response = await page.goto('http://benger.localhost/dashboard')
const requestCookies = (await response.request().headers()['cookie']) || ''
expect(requestCookies).not.toContain('access_token')
expect(requestCookies).not.toContain('refresh_token')

// Should redirect to login
expect(page.url()).toContain('/login')
```

**Test: Logout cookie attributes**

```typescript
// Verify Max-Age=0 in Set-Cookie headers
// Verify HttpOnly flag is preserved
// Verify Path=/ is set
```

### 3. Network Tab Verification

**Test: Inspect Set-Cookie headers**

```typescript
// Enable network inspection
await page.route('**/*', (route) => {
  route.continue()
})

const responses: any[] = []
page.on('response', (response) => {
  responses.push({
    url: response.url(),
    headers: response.headers(),
  })
})

// Perform signup
await page.goto('http://benger.localhost/register')
await page.fill('[name="email"]', 'test@example.com')
await page.fill('[name="password"]', 'SecurePass123!')
await page.fill('[name="username"]', 'testuser')
await page.click('button[type="submit"]')
await page.waitForNavigation()

// Find signup response
const signupResponse = responses.find((r) => r.url.includes('/api/auth/signup'))

// Verify Set-Cookie headers
const setCookieHeaders = signupResponse.headers['set-cookie']
expect(setCookieHeaders).toBeDefined()
expect(setCookieHeaders).toContain('access_token')
expect(setCookieHeaders).toContain('refresh_token')
expect(setCookieHeaders).toContain('HttpOnly')
expect(setCookieHeaders).toContain('Path=/')
expect(setCookieHeaders).toContain('SameSite=Lax')
```

## Test Environment Setup

### Prerequisites

1. Development environment running at `http://benger.localhost`
2. Puppeteer installed and configured
3. Desktop screen resolution (1920x1080)

### Running E2E Tests

```bash
# Start development environment
cd infra/
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Run E2E tests
npm run test:e2e -- --grep "auth cookies"
```

## Implementation Checklist

- [ ] Create Puppeteer test suite for signup cookie handling
- [ ] Create Puppeteer test suite for logout cookie clearing
- [ ] Verify cookie attributes in Network tab
- [ ] Test cookie persistence across page navigation
- [ ] Test cookie expiration on logout
- [ ] Verify HttpOnly cookies are not accessible via JavaScript
- [ ] Test SameSite attribute prevents CSRF
- [ ] Document any environment-specific cookie behavior

## References

- Unit test files with skipped cookie tests:
  - `/services/frontend/src/app/api/auth/logout/__tests__/route.test.ts`
  - `/services/frontend/src/app/api/auth/signup/__tests__/route.test.ts`
- Implementation files:
  - `/services/frontend/src/app/api/auth/logout/route.ts`
  - `/services/frontend/src/app/api/auth/signup/route.ts`

# Authentication API Routes - E2E Testing Requirements

## Overview

This document outlines the E2E test requirements for authentication API routes that cannot be tested with Jest/testApiHandler due to Cookie API limitations.

**Test Environment**: Use Puppeteer (MCP available) on `benger.localhost` with desktop screen resolution.

**Why E2E Required**: Jest and testApiHandler cannot access browser Cookie APIs (`response.headers.getSetCookie()`, `response.headers.append()`) which are essential for verifying cookie management in these routes.

## Test Files Location

- Login: `/services/frontend/src/app/api/auth/login/__tests__/route.test.ts`
- Logout: `/services/frontend/src/app/api/auth/logout/__tests__/route.test.ts`
- Refresh: `/services/frontend/src/app/api/auth/refresh/__tests__/route.test.ts`
- Signup: `/services/frontend/src/app/api/auth/signup/__tests__/route.test.ts`

---

## 1. Login Route (`/api/auth/login`)

### E2E Test Requirements

#### 1.1 Backend Cookie Handling and Modification

**Test**: Verify cookies from backend are modified correctly for frontend

**Steps**:

1. Navigate to `http://benger.localhost/login`
2. Submit login form with valid credentials
3. Intercept API response and verify cookies

**Expected**:

- Domain attribute is removed from cookies
- Path is set to `/`
- SameSite is set (preferably `Lax`)
- Secure flag is removed for development

**Related Unit Test**: `should handle backend cookies and modify them for frontend`

---

#### 1.2 Test Cookie Verification

**Test**: Verify test cookie is set for cookie support detection

**Steps**:

1. Perform login action
2. Check browser cookies

**Expected**:

- Cookie named `test_cookie` with value `working` is set
- Has `Path=/`
- Has `SameSite=Lax`

**Related Unit Test**: `should set test cookie for verification`

---

#### 1.3 Multiple Cookies Forwarding

**Test**: Verify multiple cookies from backend are forwarded correctly

**Steps**:

1. Mock backend to return multiple Set-Cookie headers
2. Perform login
3. Verify all cookies are present in browser

**Expected**:

- All cookies from backend are set in browser
- Each cookie has proper attributes (Path, SameSite)
- Minimum 3 cookies (access_token, refresh_token, test_cookie)

**Related Unit Test**: `should forward multiple cookies from backend`

---

#### 1.4 Cookie Path Enforcement

**Test**: Verify all cookies have Path set

**Steps**:

1. Mock backend returning cookies without Path attribute
2. Perform login
3. Inspect cookies in browser

**Expected**:

- All cookies have `Path=/` even if not present in backend response

**Related Unit Test**: `should ensure all cookies have Path set`

---

#### 1.5 Cookie SameSite Enforcement

**Test**: Verify all cookies have SameSite attribute

**Steps**:

1. Mock backend returning cookies without SameSite attribute
2. Perform login
3. Inspect cookies in browser

**Expected**:

- All cookies have `SameSite` attribute added

**Related Unit Test**: `should ensure all cookies have SameSite set`

---

#### 1.6 Secure Flag Removal

**Test**: Verify Secure flag is removed in development

**Steps**:

1. Mock backend returning cookies with Secure flag
2. Perform login (on non-HTTPS environment)
3. Inspect cookies in browser

**Expected**:

- Secure flag is removed from all cookies in development

**Related Unit Test**: `should remove Secure flag for development`

---

## 2. Logout Route (`/api/auth/logout`)

### E2E Test Requirements

#### 2.1 Cookie Clearing on Logout

**Test**: Verify cookies are cleared on successful logout

**Steps**:

1. Login to set cookies
2. Perform logout action
3. Verify cookies are cleared

**Expected**:

- Response status is 204
- `access_token` cookie is cleared (Max-Age=0)
- `refresh_token` cookie is cleared (Max-Age=0)
- Both cookies have HttpOnly flag

**Related Unit Test**: `should logout successfully and clear cookies`

---

#### 2.2 Backend Response Handling

**Test**: Verify cookies are cleared regardless of backend status

**Steps**:

1. Mock backend to return 200 instead of 204
2. Perform logout
3. Verify frontend still clears cookies

**Expected**:

- Cookies are cleared even if backend returns different status

**Related Unit Test**: `should handle backend returning 200 OK`

---

#### 2.3 Cookie Clearing Without Existing Cookies

**Test**: Verify logout works when no cookies are present

**Steps**:

1. Ensure no auth cookies exist
2. Perform logout
3. Verify response

**Expected**:

- Logout succeeds (204 status)
- Cookie-clearing headers are still sent

**Related Unit Test**: `should clear cookies even without existing cookies`

---

#### 2.4 Cookie Security Attributes

**Test**: Verify cleared cookies have correct security attributes

**Steps**:

1. Perform logout
2. Inspect Set-Cookie headers

**Expected**:

- All cookies have HttpOnly flag
- All cookies have Path=/
- All cookies have Max-Age=0

**Related Unit Test**: `should set correct cookie attributes for security`

---

#### 2.5 Independent Cookie Clearing

**Test**: Verify access_token and refresh_token are cleared separately

**Steps**:

1. Perform logout
2. Inspect Set-Cookie headers

**Expected**:

- Separate Set-Cookie header for access_token
- Separate Set-Cookie header for refresh_token
- Both are independent operations

**Related Unit Test**: `should clear both access_token and refresh_token independently`

---

#### 2.6 Backend 401 Handling

**Test**: Verify cookies are cleared even with backend 401

**Steps**:

1. Mock backend to return 401
2. Perform logout
3. Verify cookies are still cleared

**Expected**:

- Frontend clears cookies regardless of backend error

**Related Unit Test**: `should handle backend 401 (already logged out)`

---

#### 2.7 Invalid Token Handling

**Test**: Verify cookies are cleared with invalid token

**Steps**:

1. Set invalid/expired token cookie
2. Perform logout
3. Verify cookies are cleared

**Expected**:

- Cookies are cleared regardless of token validity

**Related Unit Test**: `should clear cookies even with invalid token`

---

#### 2.8 Partial Cookie Handling

**Test**: Verify both cookies are cleared even if only one exists

**Steps**:

1. Set only access_token (no refresh_token)
2. Perform logout
3. Verify both cookies are cleared

**Expected**:

- Both cookie-clearing headers are sent
- Logout succeeds even with partial cookies

**Related Unit Tests**:

- `should handle cookie with only access_token`
- `should handle cookie with only refresh_token`

---

## 3. Refresh Route (`/api/auth/refresh`)

### E2E Test Requirements

#### 3.1 Token Refresh with Cookies

**Test**: Verify token refresh succeeds and sets cookies

**Steps**:

1. Set valid refresh_token cookie
2. Call refresh endpoint
3. Verify response and cookies

**Expected**:

- Token refresh succeeds (200 status)
- Backend is called with correct parameters
- New access_token cookie is set

**Related Unit Test**: `should refresh token successfully`

---

#### 3.2 New Cookie Setting

**Test**: Verify new access_token cookie is set on refresh

**Steps**:

1. Perform token refresh
2. Inspect cookies in browser

**Expected**:

- New access_token cookie is present
- Cookie has proper attributes

**Related Unit Test**: `should set new access_token cookie`

---

#### 3.3 Cookie Modification

**Test**: Verify cookies from backend are modified properly

**Steps**:

1. Mock backend returning cookies with Domain, Secure attributes
2. Perform token refresh
3. Inspect modified cookies

**Expected**:

- Domain attribute is removed
- Path=/ is set
- SameSite=Lax is added
- Secure flag is removed

**Related Unit Test**: `should modify cookies properly (remove Domain, ensure Path)`

---

#### 3.4 Multiple Set-Cookie Headers

**Test**: Verify multiple cookies are handled correctly

**Steps**:

1. Mock backend returning multiple cookies (access_token, refresh_token, session_id)
2. Perform token refresh
3. Verify all cookies

**Expected**:

- All 3 cookies are set
- All cookies have SameSite=Lax

**Related Unit Test**: `should handle multiple Set-Cookie headers`

---

## 4. Signup Route (`/api/auth/signup`)

### E2E Test Requirements

#### 4.1 Cookie Forwarding from Backend

**Test**: Verify cookies from backend are forwarded on signup

**Steps**:

1. Submit signup form with valid data
2. Verify response and cookies

**Expected**:

- Signup succeeds (201 status)
- Cookies are forwarded from backend
- Domain attribute is removed
- Path is set to /
- SameSite=Lax is added
- Secure flag is removed for development

**Related Unit Test**: `should forward cookies from backend when signup succeeds`

---

#### 4.2 Cookie Domain Stripping

**Test**: Verify Domain attribute is stripped from cookies

**Steps**:

1. Mock backend returning cookies with Domain=.example.com
2. Perform signup
3. Inspect cookies

**Expected**:

- Domain attribute is not present in browser cookies

**Related Unit Test**: `should strip Domain attribute from cookies`

---

#### 4.3 SameSite Attribute Addition

**Test**: Verify SameSite=Lax is added if not present

**Steps**:

1. Mock backend returning cookies without SameSite
2. Perform signup
3. Inspect cookies

**Expected**:

- All cookies have SameSite=Lax

**Related Unit Test**: `should add SameSite=Lax if not present`

---

## Test Summary Statistics

### Total Tests by Route

| Route     | Total Tests | Cookie Tests | E2E Required | Passing Unit Tests |
| --------- | ----------- | ------------ | ------------ | ------------------ |
| Login     | 60          | 8            | 8            | 52                 |
| Logout    | 42          | 10           | 10           | 32                 |
| Refresh   | 10          | 5            | 5            | 5                  |
| Signup    | 27          | 3            | 3            | 24                 |
| **Total** | **139**     | **26**       | **26**       | **113**            |

### Test Status

- **Passing Unit Tests**: 113 (tests that don't require Cookie API)
- **Skipped Tests**: 26 (require E2E testing with Puppeteer)
- **E2E Tests Needed**: 26 (documented in this file)

---

## Implementation Priority

### High Priority (Core Authentication Flow)

1. Login cookie modification and setting
2. Logout cookie clearing
3. Token refresh with cookies

### Medium Priority (Security & Edge Cases)

4. Cookie security attributes (HttpOnly, SameSite, Path)
5. Multiple cookie handling
6. Domain/Secure flag removal

### Low Priority (Edge Cases)

7. Partial cookie scenarios
8. Empty cookie arrays
9. Backend error handling with cookies

---

## Testing Guidelines

### Setup

1. Use Puppeteer MCP tool
2. Test on `benger.localhost` (Docker environment)
3. Use desktop screen resolution
4. Ensure backend services are running

### Common Test Patterns

#### Pattern 1: Cookie Inspection

```javascript
// After action, get cookies from browser
const cookies = await page.cookies()
const accessToken = cookies.find((c) => c.name === 'access_token')
```

#### Pattern 2: Network Interception

```javascript
// Intercept Set-Cookie headers
await page.setRequestInterception(true)
page.on('response', (response) => {
  const headers = response.headers()['set-cookie']
  // Verify headers
})
```

#### Pattern 3: Cookie Attributes

```javascript
// Verify cookie attributes
expect(cookie.httpOnly).toBe(true)
expect(cookie.path).toBe('/')
expect(cookie.sameSite).toBe('Lax')
expect(cookie.secure).toBe(false) // dev environment
```

---

## Related Documentation

- [Jest Unit Tests](../../../src/app/api/auth/)
- [Cookie Management Strategy](../../architecture/cookie-management.md)
- [Authentication Flow](../../architecture/authentication.md)

---

## Maintenance Notes

**Last Updated**: 2025-10-17

**Status**: All cookie tests have been properly skipped with E2E documentation references

**Next Steps**:

1. Implement Puppeteer E2E tests based on this documentation
2. Add E2E tests to CI/CD pipeline
3. Update this document as new cookie-related tests are added

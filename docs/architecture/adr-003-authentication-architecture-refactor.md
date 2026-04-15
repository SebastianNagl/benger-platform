# ADR-003: Authentication Architecture Refactor (2025)

## Status
Accepted (January 2025)

## Context

The BenGER application had a critical authentication bug where superadmin users (admin/admin in local dev) couldn't access project data pages. Investigation revealed a dual authentication system conflict that affected ALL user roles, not just superadmin.

### Issues Identified

1. **Dual Authentication System Conflict**:
   - `AuthContext` (working) - using HttpOnly cookies
   - `authStore` (broken) - expecting localStorage tokens, returning `user: null`

2. **Authentication Loops**:
   - Console warnings: "User changed from [id] to null - clearing cache" repeating 3 times
   - Caused by authStore initialization issues

3. **Monolithic AuthContext**:
   - 776-line AuthContext file handling everything
   - Mixed concerns: session management, organization handling, development utilities

4. **Security Concerns**:
   - No 2025 security best practices for cookies
   - Missing proper SameSite, HttpOnly configurations

## Decision

**We decided to refactor the existing AuthContext system instead of migrating to React Query**, based on analysis that React Query provides no significant advantages for authentication state management.

### Architecture Changes Made

#### 1. Remove Dual Authentication System
- **Deleted**: `authStore.ts` (broken Zustand store)
- **Migrated**: All 23 components from `authStore` to `AuthContext`
- **Result**: Single source of truth for authentication

#### 2. Extract Service Modules from AuthContext
- **`sessionManager.ts`**: Session tracking, user switching detection, cache management
- **`organizationManager.ts`**: Organization context and switching logic  
- **`devAuthHelper.ts`**: Development auto-login utilities
- **Result**: AuthContext reduced from 776 to 566 lines

#### 3. Add Security Enhancements
- **`cookieConfig.ts`**: 2025 cookie security best practices
  - SameSite=strict in production, lax in development
  - HttpOnly cookies for XSS protection
  - Secure cookie prefixes (`__Host-`, `__Secure-`)
  - Environment-specific configurations

#### 4. Comprehensive Test Coverage
- **Unit tests**: sessionManager (20 tests), organizationManager (16 tests), cookieConfig (17 tests)
- **Integration tests**: 15 tests for cross-component coordination
- **Security tests**: Cookie authentication and HTTP-only flows

### React Query Alternative Analysis

We evaluated migrating authentication to React Query but decided against it because:

1. **No Clear Benefits**: Auth state is simple user/loading/organizations - doesn't benefit from React Query's caching/refetching
2. **Architecture Mismatch**: React Query is designed for server state, not client authentication state
3. **Unnecessary Complexity**: Would require additional adapters between React Query and our auth patterns
4. **Working System**: The refactored AuthContext is clean, testable, and functional

## Implementation Details

### Service Module Responsibilities

#### SessionManager
```typescript
- trackUserSession(user): Track authenticated user
- detectUserSwitch(currentUser): Detect when different user logs in
- handleUserSwitch(): Clear old user data, update session
- clearSession(): Full logout cleanup
- isLoginInProgress(): Prevent race conditions
```

#### OrganizationManager  
```typescript
- setOrganizations(orgs): Set available organizations
- setCurrentOrganization(org): Switch active organization
- getOrganizationContext(): Get current org ID for API headers
- fetchOrganizations(): Async organization loading
```

#### DevAuthHelper
```typescript
- shouldAttemptAutoLogin(): Check if dev auto-login is enabled
- attemptDevAutoLogin(): Perform development authentication
- Benefits: Isolated from production code
```

### Security Improvements

#### Cookie Configuration
```typescript
// Production
{
  sameSite: 'strict',
  secure: true,
  httpOnly: true,
  maxAge: 7 * 24 * 60 * 60 // 7 days
}

// Development  
{
  sameSite: 'lax',
  secure: false,
  httpOnly: true,
  maxAge: 30 * 24 * 60 * 60 // 30 days
}
```

#### Cookie Names with Security Prefixes
```typescript
{
  ACCESS_TOKEN: '__Host-access-token',
  REFRESH_TOKEN: '__Secure-refresh-token', 
  CSRF_TOKEN: '__Host-csrf-token',
  SESSION_ID: '__Host-session-id'
}
```

### Test Coverage Added

#### Unit Tests (53 tests total)
- **sessionManager**: 20 tests covering session tracking, user switching, cache management
- **organizationManager**: 16 tests covering org context, switching, API integration
- **cookieConfig**: 17 tests covering security configurations, validation

#### Integration Tests (32 tests total)
- **authArchitecture**: 15 tests covering cross-component coordination
- **cookieAuth**: 17 tests covering HTTP-only authentication flows

## Consequences

### Positive
- ✅ **Bug Fixed**: All user roles can now access project data pages
- ✅ **Authentication Loops Resolved**: No more cache clearing loops
- ✅ **Single Source of Truth**: Eliminated dual authentication system
- ✅ **Improved Security**: 2025 cookie security best practices implemented
- ✅ **Better Separation of Concerns**: Extracted services from monolithic AuthContext
- ✅ **Comprehensive Testing**: 85 total tests covering all authentication flows
- ✅ **TypeScript Errors Resolved**: Fixed all 15 TypeScript errors
- ✅ **Maintainable**: Clear module boundaries and responsibilities

### Technical Debt Resolved
- ❌ Removed broken authStore
- ❌ Eliminated authentication state inconsistencies  
- ❌ Fixed user switching cache contamination
- ❌ Resolved development/production environment detection issues

### Future Maintenance
- 🔧 **Clear Module Boundaries**: Easy to modify individual auth components
- 🔧 **Test Coverage**: Comprehensive tests prevent regressions
- 🔧 **Security**: Cookie configurations adapt to security requirements
- 🔧 **Development Experience**: Isolated dev utilities don't affect production

## Files Changed

### Deleted
```
src/stores/authStore.ts (broken authentication store)
```

### Created  
```
src/lib/auth/sessionManager.ts (session tracking)
src/lib/auth/organizationManager.ts (org management)
src/lib/auth/devAuthHelper.ts (dev utilities)
src/lib/security/cookieConfig.ts (security configs)
src/__tests__/auth/sessionManager.test.ts (20 tests)
src/__tests__/auth/organizationManager.test.ts (16 tests) 
src/__tests__/security/cookieConfig.test.ts (17 tests)
src/__tests__/auth/authArchitecture.integration.test.tsx (15 tests)
src/__tests__/security/cookieAuth.integration.test.ts (17 tests)
```

### Modified
```
src/contexts/AuthContext.tsx (776→566 lines, uses extracted services)
src/types/labelStudio.ts (added metadata property)
23 components migrated from authStore to AuthContext
```

## Verification

All requirements completed successfully:

- [x] **Critical Bug Fixed**: Superadmin (and all roles) can access project data pages
- [x] **Authentication Loops Resolved**: No more "User changed from [id] to null" warnings  
- [x] **Test Suite Updated**: 85 total tests, all passing
- [x] **TypeScript Errors Fixed**: All 15 errors resolved
- [x] **Integration Tests Added**: Comprehensive cross-component testing
- [x] **Security Enhanced**: 2025 cookie security best practices
- [x] **Architecture Documented**: This ADR captures decisions and rationale

## Related Documents

- [GitHub Issue #635](https://github.com/user/repo/issues/635): Authentication Architecture Refactor Plan
- [Cookie Security Best Practices 2025](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies)
- [OWASP Authentication Guidelines](https://owasp.org/www-project-authentication/)

---

**Author**: Development Team  
**Date**: January 2025  
**Stakeholders**: Development Team, Security Team  
**Next Review**: When adding new authentication features or security requirements change
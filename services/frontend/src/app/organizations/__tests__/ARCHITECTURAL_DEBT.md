# Architectural Debt: Organizations Page Test Suite

## Problem Summary

The `invitation-error-handling.test.tsx` test file contains 11 failing tests that cannot be fixed with simple mock adjustments. These tests are testing **deprecated/removed code**.

## Root Cause

### What Happened

1. **Original Implementation** (tested by these tests):
   - File: `src/app/organizations/page.tsx`
   - Functionality: Full-featured organizations management page with invitation UI
   - Status: **Deprecated and replaced**

2. **Current Implementation**:
   - Same file now contains only a redirect: `router.push('/admin/users-organizations')`
   - Comment on line 67: `// Always redirect to unified interface`
   - The page **never renders any UI** - it immediately redirects

3. **New Implementation**:
   - File: `src/app/admin/users-organizations/components/OrganizationsTab.tsx`
   - Contains the actual invitation functionality
   - Uses the same `organizationsAPI` but in a different component structure

### Why Tests Fail

The tests expect to find UI elements like:

- "Test Organization" text
- "Invite Member" button
- "colleague@example.com" placeholder input
- Invitation modals and forms

But the page being tested **never renders these elements** because it redirects immediately on mount.

## Evidence

### Page Code (lines 67-69)

```typescript
// Always redirect to unified interface
useEffect(() => {
  router.push('/admin/users-organizations')
}, [router])
```

### Test Errors

```
Unable to find an element with the text: Test Organization
Unable to find an element with the text: Invite Member
Unable to find an element with the placeholder text of: colleague@example.com
```

### Verification

All 11 tests in the file fail with "Unable to find element" errors despite having:

- ✅ Correct mocks for `organizationsAPI`
- ✅ Correct mock return values
- ✅ Correct test assertions
- ❌ Wrong component being tested (deprecated redirect page instead of new OrganizationsTab)

## Impact

**Current Test Status**: 11 failing tests / 1 suite
**Pass Rate**: 98.0% (3198/3209 tests)

These 11 tests represent the only remaining failures in the frontend test suite after comprehensive fixes to other test files.

## Solutions

### Option 1: Delete Deprecated Tests (Quick Fix)

**Pros:**

- Achieves 100% test pass rate immediately
- Removes tests for code that no longer exists

**Cons:**

- Loses test coverage for invitation error handling
- No tests for the important error handling logic

### Option 2: Rewrite Tests for New Component (Proper Fix)

**Pros:**

- Maintains test coverage for invitation functionality
- Tests the actual production code

**Cons:**

- Requires rewriting all 11 tests (~600 lines)
- Need to test `OrganizationsTab` component instead
- Requires understanding new component structure

### Option 3: Mark as Skipped with Documentation (Interim)

**Pros:**

- Documents the issue clearly
- Allows progress on other work
- Skipped tests counted separately from failures

**Cons:**

- Tests still exist but don't run
- Coverage gap until tests are rewritten

## Recommendation

**Immediate Action**: Option 3 (Mark as skipped)

- Add `describe.skip` to mark the test suite as intentionally skipped
- Keep this documentation file
- Add comment in test file referencing this document

**Future Action**: Option 2 (Rewrite for OrganizationsTab)

- Create `OrganizationsTab.invitation-error-handling.test.tsx`
- Test the same scenarios against the new component
- Remove the old test file

## Test Scenarios to Preserve

When rewriting tests, ensure these scenarios are covered:

1. **Duplicate Invitation Prevention**
   - Check for existing invitations before sending
   - Allow sending invitation to new email

2. **API Error Message Display**
   - Duplicate invitation error from API
   - Rate limit error message
   - Network error message
   - Generic error for unknown errors

3. **Form State Management**
   - Clear email field when modal reopens
   - Reset role to ANNOTATOR when modal reopens
   - Reload members list after successful invitation

4. **Loading States**
   - Show loading state while sending invitation

5. **Email Validation**
   - Prevent invalid email format submission

## Files Involved

### Deprecated (Redirects Only)

- `/src/app/organizations/page.tsx`
- `/src/app/organizations/__tests__/invitation-error-handling.test.tsx` ← **This test file**

### Current Implementation

- `/src/app/admin/users-organizations/page.tsx`
- `/src/app/admin/users-organizations/components/OrganizationsTab.tsx` ← **Should be tested instead**
- `/src/app/admin/users-organizations/components/GlobalUsersTab.tsx`

### Shared Dependencies (Still Valid)

- `/src/lib/api/organizations.ts` - OrganizationsClient
- `/src/lib/api/types.ts` - TypeScript types

## Related Issues

- GitHub Issue #761: Comprehensive Test Coverage Improvements
  - This represents the last blocking issue for 100% frontend test pass rate
  - All other test suites have been fixed (98.0% pass rate achieved)

## Timeline

- **Identified**: 2025-10-16
- **Status**: Documented as architectural debt
- **Action Required**: Decision needed on skip vs. rewrite

## Notes

The functionality being tested (invitation error handling) is **still important and still exists** in the production code. It's just in a different component now. This is purely a technical debt issue from refactoring the UI without updating the tests.

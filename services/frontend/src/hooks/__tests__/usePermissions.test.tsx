/**
 * Tests for usePermissions — the thin hook that binds the current
 * authenticated user (from useAuth) to every predicate in
 * `@/utils/permissions`.
 *
 * The hook itself is pure plumbing: it pre-applies `user` to each helper and
 * memoises the bundle keyed on `user`. These tests drive the bound predicates
 * across the role matrix (superadmin / ORG_ADMIN / CONTRIBUTOR / ANNOTATOR /
 * null), confirm per-project arguments still thread through, verify the
 * `summary` bundle, and that the returned object is referentially stable while
 * `user` is unchanged and changes when `user` changes.
 *
 * @jest-environment jsdom
 */

import type { User } from '@/lib/api'
import { renderHook } from '@testing-library/react'

import { useAuth } from '@/contexts/AuthContext'
import { usePermissions } from '../usePermissions'

// useAuth is globally mocked in setupTests.ts as a jest.fn() returning
// { user: null, ... }. Re-cast it here so we can drive `user` per test.
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>

const makeUser = (overrides: Partial<User> = {}): User =>
  ({
    id: 'user-1',
    username: 'tester',
    email: 'tester@example.com',
    name: 'Tester',
    is_superadmin: false,
    is_active: true,
    created_at: '2024-01-01T00:00:00Z',
    role: undefined,
    ...overrides,
  }) as User

/** Set the user the next render of useAuth() returns. */
const setUser = (user: User | null) => {
  mockUseAuth.mockReturnValue({
    user,
    login: jest.fn(),
    signup: jest.fn(),
    logout: jest.fn(),
    updateUser: jest.fn(),
    isLoading: false,
    refreshAuth: jest.fn(),
    apiClient: {} as any,
    organizations: [],
    currentOrganization: null,
    setCurrentOrganization: jest.fn(),
    refreshOrganizations: jest.fn(),
  } as any)
}

// A minimal project shape accepted by the per-project predicates.
const project = (overrides: Record<string, any> = {}) => ({
  created_by: 'owner-id',
  is_public: false,
  public_role: null,
  ...overrides,
})

afterEach(() => {
  jest.clearAllMocks()
})

describe('usePermissions', () => {
  describe('unauthenticated (user = null)', () => {
    beforeEach(() => setUser(null))

    it('exposes the raw null user', () => {
      const { result } = renderHook(() => usePermissions())
      expect(result.current.user).toBeNull()
    })

    it('denies every predicate', () => {
      const { result } = renderHook(() => usePermissions())
      const p = result.current
      expect(p.canCreateProjects()).toBe(false)
      expect(p.canAccessProjectData()).toBe(false)
      expect(p.canEditTaskData()).toBe(false)
      expect(p.canDeleteProjects()).toBe(false)
      expect(p.canStartGeneration()).toBe(false)
      expect(p.canAccessReports()).toBe(false)
      expect(p.canMakeProjectPublic(project())).toBe(false)
      expect(p.getEffectiveProjectRole(project())).toBeNull()
      expect(p.isAnnotatorOnly()).toBe(false)
    })

    it('still allows private-mode project creation when unauthenticated check short-circuits to false', () => {
      const { result } = renderHook(() => usePermissions())
      // user is null → even isPrivateMode cannot grant create
      expect(result.current.canCreateProjects({ isPrivateMode: true })).toBe(
        false
      )
    })

    it('summary reports the unauthenticated bundle', () => {
      const { result } = renderHook(() => usePermissions())
      expect(result.current.summary).toEqual({
        canCreate: false,
        canAccessData: false,
        canDelete: false,
        canStartGeneration: false,
        canAccessReports: false,
        isAnnotatorOnly: false,
        role: 'none',
        isAuthenticated: false,
      })
    })
  })

  describe('superadmin', () => {
    beforeEach(() => setUser(makeUser({ is_superadmin: true })))

    it('grants everything', () => {
      const { result } = renderHook(() => usePermissions())
      const p = result.current
      expect(p.canCreateProjects()).toBe(true)
      expect(p.canAccessProjectData()).toBe(true)
      expect(p.canEditTaskData()).toBe(true)
      expect(p.canDeleteProjects()).toBe(true)
      expect(p.canStartGeneration()).toBe(true)
      expect(p.canAccessReports()).toBe(true)
      expect(p.canMakeProjectPublic(project())).toBe(true)
      expect(p.isAnnotatorOnly()).toBe(false)
    })

    it('resolves effective project role to ORG_ADMIN', () => {
      const { result } = renderHook(() => usePermissions())
      expect(result.current.getEffectiveProjectRole(project())).toBe(
        'ORG_ADMIN'
      )
    })

    it('summary marks superadmin role + authenticated', () => {
      const { result } = renderHook(() => usePermissions())
      expect(result.current.summary).toMatchObject({
        role: 'superadmin',
        isAuthenticated: true,
        canCreate: true,
        canDelete: true,
        canAccessReports: true,
        isAnnotatorOnly: false,
      })
    })
  })

  describe('ORG_ADMIN', () => {
    beforeEach(() => setUser(makeUser({ role: 'ORG_ADMIN' })))

    it('can create, access data, edit task data, start generation, access reports', () => {
      const { result } = renderHook(() => usePermissions())
      const p = result.current
      expect(p.canCreateProjects()).toBe(true)
      expect(p.canAccessProjectData()).toBe(true)
      expect(p.canEditTaskData()).toBe(true)
      expect(p.canStartGeneration()).toBe(true)
      expect(p.canAccessReports()).toBe(true)
    })

    it('cannot delete projects (superadmin only)', () => {
      const { result } = renderHook(() => usePermissions())
      expect(result.current.canDeleteProjects()).toBe(false)
    })

    it('is not annotator-only', () => {
      const { result } = renderHook(() => usePermissions())
      expect(result.current.isAnnotatorOnly()).toBe(false)
    })

    it('summary reflects ORG_ADMIN', () => {
      const { result } = renderHook(() => usePermissions())
      expect(result.current.summary).toMatchObject({
        role: 'ORG_ADMIN',
        canAccessReports: true,
        canDelete: false,
        isAuthenticated: true,
      })
    })
  })

  describe('CONTRIBUTOR', () => {
    beforeEach(() => setUser(makeUser({ role: 'CONTRIBUTOR' })))

    it('can create + access data + start generation', () => {
      const { result } = renderHook(() => usePermissions())
      const p = result.current
      expect(p.canCreateProjects()).toBe(true)
      expect(p.canAccessProjectData()).toBe(true)
      expect(p.canStartGeneration()).toBe(true)
    })

    it('cannot edit task data without an ORG_ADMIN-effective project', () => {
      const { result } = renderHook(() => usePermissions())
      // no project arg → falls back to org-context role, which is CONTRIBUTOR
      expect(result.current.canEditTaskData()).toBe(false)
    })

    it('cannot access reports', () => {
      const { result } = renderHook(() => usePermissions())
      expect(result.current.canAccessReports()).toBe(false)
    })

    it('summary reflects CONTRIBUTOR (no reports, no delete)', () => {
      const { result } = renderHook(() => usePermissions())
      expect(result.current.summary).toMatchObject({
        role: 'CONTRIBUTOR',
        canCreate: true,
        canAccessReports: false,
        canDelete: false,
      })
    })
  })

  describe('ANNOTATOR', () => {
    beforeEach(() => setUser(makeUser({ role: 'ANNOTATOR' })))

    it('cannot create / access data / start generation / access reports', () => {
      const { result } = renderHook(() => usePermissions())
      const p = result.current
      expect(p.canCreateProjects()).toBe(false)
      expect(p.canAccessProjectData()).toBe(false)
      expect(p.canStartGeneration()).toBe(false)
      expect(p.canAccessReports()).toBe(false)
      expect(p.canEditTaskData()).toBe(false)
    })

    it('is annotator-only', () => {
      const { result } = renderHook(() => usePermissions())
      expect(result.current.isAnnotatorOnly()).toBe(true)
    })

    it('private-mode lets an annotator create + access their own data', () => {
      const { result } = renderHook(() => usePermissions())
      expect(
        result.current.canCreateProjects({ isPrivateMode: true })
      ).toBe(true)
      expect(
        result.current.canAccessProjectData({ isPrivateMode: true })
      ).toBe(true)
    })

    it('summary marks annotator-only', () => {
      const { result } = renderHook(() => usePermissions())
      expect(result.current.summary).toMatchObject({
        role: 'ANNOTATOR',
        isAnnotatorOnly: true,
        canCreate: false,
      })
    })
  })

  describe('per-project argument threading', () => {
    it('canEditTaskData: project creator (non-superadmin) is treated as ORG_ADMIN-effective', () => {
      setUser(makeUser({ id: 'owner-id', role: 'CONTRIBUTOR' }))
      const { result } = renderHook(() => usePermissions())
      // created_by matches the user id → effective role ORG_ADMIN → can edit
      expect(
        result.current.canEditTaskData(project({ created_by: 'owner-id' }))
      ).toBe(true)
    })

    it('canEditTaskData: non-creator contributor cannot edit a given project', () => {
      setUser(makeUser({ id: 'someone-else', role: 'CONTRIBUTOR' }))
      const { result } = renderHook(() => usePermissions())
      expect(
        result.current.canEditTaskData(project({ created_by: 'owner-id' }))
      ).toBe(false)
    })

    it('canAccessProjectData: public-tier visitor inherits public_role CONTRIBUTOR', () => {
      setUser(makeUser({ id: 'visitor', role: 'ANNOTATOR' }))
      const { result } = renderHook(() => usePermissions())
      expect(
        result.current.canAccessProjectData({
          project: project({
            created_by: 'owner-id',
            is_public: true,
            public_role: 'CONTRIBUTOR',
          }),
        })
      ).toBe(true)
    })

    it('canStartGeneration: public CONTRIBUTOR fallback grants generation', () => {
      setUser(makeUser({ id: 'visitor', role: 'ANNOTATOR' }))
      const { result } = renderHook(() => usePermissions())
      expect(
        result.current.canStartGeneration(
          project({
            created_by: 'owner-id',
            is_public: true,
            public_role: 'CONTRIBUTOR',
          })
        )
      ).toBe(true)
    })

    it('canMakeProjectPublic: only the creator (non-superadmin) qualifies', () => {
      setUser(makeUser({ id: 'owner-id' }))
      const { result } = renderHook(() => usePermissions())
      expect(
        result.current.canMakeProjectPublic({ created_by: 'owner-id' })
      ).toBe(true)
      expect(
        result.current.canMakeProjectPublic({ created_by: 'somebody' })
      ).toBe(false)
    })

    it('getEffectiveProjectRole: explicit orgRole wins over public_role', () => {
      setUser(makeUser({ id: 'visitor', role: 'ANNOTATOR' }))
      const { result } = renderHook(() => usePermissions())
      expect(
        result.current.getEffectiveProjectRole(
          project({ is_public: true, public_role: 'CONTRIBUTOR' }),
          'ANNOTATOR'
        )
      ).toBe('ANNOTATOR')
    })

    it('getEffectiveProjectRole: returns null when no role path applies', () => {
      setUser(makeUser({ id: 'visitor', role: 'ANNOTATOR' }))
      const { result } = renderHook(() => usePermissions())
      expect(
        result.current.getEffectiveProjectRole(
          project({ created_by: 'owner-id', is_public: false })
        )
      ).toBeNull()
    })
  })

  describe('memoisation', () => {
    it('returns a stable object across re-renders while user is unchanged', () => {
      const user = makeUser({ role: 'CONTRIBUTOR' })
      setUser(user)
      const { result, rerender } = renderHook(() => usePermissions())
      const first = result.current
      rerender()
      expect(result.current).toBe(first)
    })

    it('returns a new object when the user changes', () => {
      const userA = makeUser({ id: 'a', role: 'CONTRIBUTOR' })
      setUser(userA)
      const { result, rerender } = renderHook(() => usePermissions())
      const first = result.current

      const userB = makeUser({ id: 'b', role: 'ORG_ADMIN' })
      setUser(userB)
      rerender()

      expect(result.current).not.toBe(first)
      expect(result.current.user).toBe(userB)
      expect(result.current.canAccessReports()).toBe(true) // ORG_ADMIN now
    })
  })
})

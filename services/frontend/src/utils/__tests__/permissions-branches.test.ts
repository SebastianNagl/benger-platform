/**
 * Branch coverage tests for permissions.ts
 *
 * Targets all conditional branches in each permission function.
 */

import {
  canCreateProjects,
  canAccessProjectData,
  canDeleteProjects,
  isAnnotatorOnly,
  canAccessReports,
  getUserPermissions,
  hasOrganization,
} from '../permissions'

const superadmin = { id: '1', name: 'SA', is_superadmin: true, role: 'ORG_ADMIN' } as any
const orgAdmin = { id: '2', name: 'OA', is_superadmin: false, role: 'ORG_ADMIN' } as any
const contributor = { id: '3', name: 'C', is_superadmin: false, role: 'CONTRIBUTOR' } as any
const annotator = { id: '4', name: 'A', is_superadmin: false, role: 'ANNOTATOR' } as any

describe('canCreateProjects', () => {
  it('should return false for null user', () => {
    expect(canCreateProjects(null)).toBe(false)
  })
  it('should return true for superadmin', () => {
    expect(canCreateProjects(superadmin)).toBe(true)
  })
  it('should return true in private mode for any user', () => {
    expect(canCreateProjects(annotator, { isPrivateMode: true })).toBe(true)
  })
  it('should return true for ORG_ADMIN', () => {
    expect(canCreateProjects(orgAdmin)).toBe(true)
  })
  it('should return true for CONTRIBUTOR', () => {
    expect(canCreateProjects(contributor)).toBe(true)
  })
  it('should return false for ANNOTATOR in org mode', () => {
    expect(canCreateProjects(annotator)).toBe(false)
  })
})

describe('canAccessProjectData', () => {
  it('should return false for null user', () => {
    expect(canAccessProjectData(null)).toBe(false)
  })
  it('should return true for superadmin', () => {
    expect(canAccessProjectData(superadmin)).toBe(true)
  })
  it('should return true in private mode', () => {
    expect(canAccessProjectData(annotator, { isPrivateMode: true })).toBe(true)
  })
  it('should return true for ORG_ADMIN', () => {
    expect(canAccessProjectData(orgAdmin)).toBe(true)
  })
  it('should return true for CONTRIBUTOR', () => {
    expect(canAccessProjectData(contributor)).toBe(true)
  })
  it('should return false for ANNOTATOR', () => {
    expect(canAccessProjectData(annotator)).toBe(false)
  })
})

describe('canDeleteProjects', () => {
  it('should return false for null user', () => {
    expect(canDeleteProjects(null)).toBe(false)
  })
  it('should return true for superadmin', () => {
    expect(canDeleteProjects(superadmin)).toBe(true)
  })
  it('should return false for non-superadmin', () => {
    expect(canDeleteProjects(orgAdmin)).toBe(false)
  })
})

describe('isAnnotatorOnly', () => {
  it('should return false for null user', () => {
    expect(isAnnotatorOnly(null)).toBe(false)
  })
  it('should return false for superadmin', () => {
    expect(isAnnotatorOnly(superadmin)).toBe(false)
  })
  it('should return true for annotator', () => {
    expect(isAnnotatorOnly(annotator)).toBe(true)
  })
  it('should return false for contributor', () => {
    expect(isAnnotatorOnly(contributor)).toBe(false)
  })
})

describe('canAccessReports', () => {
  it('should return false for null user', () => {
    expect(canAccessReports(null)).toBe(false)
  })
  it('should return true for superadmin', () => {
    expect(canAccessReports(superadmin)).toBe(true)
  })
  it('should return true for ORG_ADMIN', () => {
    expect(canAccessReports(orgAdmin)).toBe(true)
  })
  it('should return false for contributor', () => {
    expect(canAccessReports(contributor)).toBe(false)
  })
  it('should return false for annotator', () => {
    expect(canAccessReports(annotator)).toBe(false)
  })
})

describe('getUserPermissions', () => {
  it('should return all-false for null user', () => {
    const p = getUserPermissions(null)
    expect(p.isAuthenticated).toBe(false)
    expect(p.canCreate).toBe(false)
    expect(p.canDelete).toBe(false)
    expect(p.role).toBe('none')
  })

  it('should return superadmin permissions', () => {
    const p = getUserPermissions(superadmin)
    expect(p.isAuthenticated).toBe(true)
    expect(p.canDelete).toBe(true)
    expect(p.role).toBe('superadmin')
  })

  it('should return annotator permissions', () => {
    const p = getUserPermissions(annotator)
    expect(p.isAnnotatorOnly).toBe(true)
    expect(p.canCreate).toBe(false)
    expect(p.role).toBe('ANNOTATOR')
  })

  it('should handle user with no role', () => {
    const noRole = { id: '5', name: 'NR', is_superadmin: false } as any
    const p = getUserPermissions(noRole)
    expect(p.role).toBe('unknown')
  })
})

describe('hasOrganization', () => {
  it('should return false for empty array', () => {
    expect(hasOrganization([])).toBe(false)
  })
  it('should return true for non-empty array', () => {
    expect(hasOrganization([{ id: '1' }] as any)).toBe(true)
  })
})

/**
 * The expert-route list that keeps the expert layout for a user in student
 * mode (see `lib/utils/routeSurface.ts` and the shell branch in
 * `components/layout/Layout.tsx`).
 */
import { EXPERT_ONLY_ROUTE_PREFIXES, isExpertOnlyRoute } from '../routeSurface'

describe('isExpertOnlyRoute', () => {
  it('matches every listed prefix and its children', () => {
    for (const prefix of EXPERT_ONLY_ROUTE_PREFIXES) {
      expect(isExpertOnlyRoute(prefix)).toBe(true)
      expect(isExpertOnlyRoute(`${prefix}/abc`)).toBe(true)
      expect(isExpertOnlyRoute(`${prefix}/`)).toBe(true)
    }
  })

  it('keeps the student shell for student and shared routes', () => {
    for (const path of [
      '/',
      '/student',
      '/student/exams',
      '/student/exams/abc',
      '/student/decks',
      '/shares/tok',
      '/profile',
      '/settings',
      '/notifications',
      '/changelog',
      '/about',
      '/reports',
      '/reports/abc',
      '/login',
      '/vertretbar',
    ]) {
      expect(isExpertOnlyRoute(path)).toBe(false)
    }
  })

  it('does not match a route that merely starts with the same letters', () => {
    expect(isExpertOnlyRoute('/dataset')).toBe(false)
    expect(isExpertOnlyRoute('/projectsomething')).toBe(false)
    expect(isExpertOnlyRoute('/modelsx')).toBe(false)
  })

  it('is safe on empty input', () => {
    expect(isExpertOnlyRoute(null)).toBe(false)
    expect(isExpertOnlyRoute(undefined)).toBe(false)
    expect(isExpertOnlyRoute('')).toBe(false)
  })
})

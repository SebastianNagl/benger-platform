/**
 * Which surface a route belongs to.
 *
 * The shell is chosen by the user's UI mode, not by the route
 * (`useResolvedUiMode`), so a user in student mode carries the student shell
 * onto every page they open. That is right for the shared pages (profile,
 * changelog, legal) but wrong for the expert workbench: opening a project on
 * a student-locked host used to render the project page inside the student
 * sidebar, which offers no way back to it and belongs to a different product
 * surface entirely.
 *
 * Routes listed here always render the expert layout, whatever the mode. They
 * stay permission-gated as before; this only decides the chrome around them.
 */

/**
 * Expert-workbench route prefixes. A path matches when it equals the prefix
 * or continues with `/` — `/data` and `/data/x` match, `/dataset` does not.
 *
 * Deliberately NOT here: `/profile`, `/settings`, `/notifications`,
 * `/changelog`, `/about`, `/reports`, `/shares`, the auth pages and the
 * landing pages. Those are shared or student-facing and keep the student
 * shell for a student.
 */
export const EXPERT_ONLY_ROUTE_PREFIXES = [
  '/admin',
  '/architecture',
  '/dashboard',
  '/data',
  '/evaluations',
  '/generations',
  '/how-to',
  '/leaderboards',
  '/models',
  '/organizations',
  '/projects',
  '/runs',
  '/users-organizations',
] as const

export function isExpertOnlyRoute(
  pathname: string | null | undefined,
): boolean {
  if (!pathname) return false
  // Normalise a trailing slash so `/projects/` matches too.
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  return EXPERT_ONLY_ROUTE_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  )
}

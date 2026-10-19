/**
 * The legal system an organization teaches and examines in (mirrors
 * services/shared/org_jurisdiction.py). `/auth/me/contexts` reports it per
 * organization; the project wizard uses it to offer jurisdiction-specific
 * project types and templates (e.g. the French exam types the extended
 * edition registers for 'FR').
 */

export const JURISDICTIONS = ['DE', 'FR'] as const
export type Jurisdiction = (typeof JURISDICTIONS)[number]
export const DEFAULT_JURISDICTION: Jurisdiction = 'DE'

export function isJurisdiction(value: unknown): value is Jurisdiction {
  return (
    typeof value === 'string' &&
    (JURISDICTIONS as readonly string[]).includes(value)
  )
}

/** An organization's jurisdiction; unknown or missing values are German. */
export function orgJurisdiction(
  org: { jurisdiction?: unknown } | null | undefined,
): Jurisdiction {
  return isJurisdiction(org?.jurisdiction)
    ? org.jurisdiction
    : DEFAULT_JURISDICTION
}

/**
 * The jurisdictions a new project is created for: those of the target
 * organizations when the project goes to organizations, otherwise those of
 * every organization the user belongs to (a private project can still be
 * shared into any of them later). Never empty.
 */
export function wizardJurisdictions(
  organizations: ReadonlyArray<{ id: string; jurisdiction?: unknown }>,
  targetOrganizationIds: ReadonlyArray<string> | null,
): Jurisdiction[] {
  const pool =
    targetOrganizationIds && targetOrganizationIds.length > 0
      ? organizations.filter((o) => targetOrganizationIds.includes(o.id))
      : organizations
  const found = new Set<Jurisdiction>(pool.map(orgJurisdiction))
  if (found.size === 0) found.add(DEFAULT_JURISDICTION)
  return JURISDICTIONS.filter((j) => found.has(j))
}

/** Is an entry restricted to `jurisdictions` offered for `active`? */
export function offeredFor(
  restrictedTo: ReadonlyArray<string> | undefined,
  active: ReadonlyArray<Jurisdiction>,
): boolean {
  return !restrictedTo || restrictedTo.some((j) => active.includes(j as any))
}

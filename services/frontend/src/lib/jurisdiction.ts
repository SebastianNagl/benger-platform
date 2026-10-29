/**
 * The legal system an organization teaches and examines in (mirrors
 * services/shared/org_jurisdiction.py). `/auth/me/contexts` reports it per
 * organization, plus the overrides of its groups (`group_jurisdictions`,
 * group id -> jurisdiction; groups without one follow the organization).
 * The project wizard uses it to offer jurisdiction-specific project types
 * and templates (e.g. the French exam types the extended edition registers
 * for 'FR').
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

type JurisdictionOrg = {
  id: string
  jurisdiction?: unknown
  group_jurisdictions?: Record<string, unknown>
  groups?: ReadonlyArray<{ id: string }>
}

/** A group's jurisdiction: its own override, else its organization's. */
export function groupJurisdiction(
  org: JurisdictionOrg,
  groupId: string | null | undefined,
): Jurisdiction {
  const own = groupId ? org.group_jurisdictions?.[groupId] : undefined
  return isJurisdiction(own) ? own : orgJurisdiction(org)
}

/**
 * The jurisdictions a new project is created for: those of the target
 * organizations when the project goes to organizations (the target group's
 * where one is picked), otherwise those of every organization the user
 * belongs to and of their groups there (a private project can still be
 * shared into any of them later). Never empty.
 */
export function wizardJurisdictions(
  organizations: ReadonlyArray<JurisdictionOrg>,
  targetOrganizationIds: ReadonlyArray<string> | null,
  targetGroupIds: Readonly<Record<string, string | null>> = {},
): Jurisdiction[] {
  const found = new Set<Jurisdiction>()
  if (targetOrganizationIds && targetOrganizationIds.length > 0) {
    for (const org of organizations) {
      if (targetOrganizationIds.includes(org.id)) {
        found.add(groupJurisdiction(org, targetGroupIds[org.id]))
      }
    }
  } else {
    for (const org of organizations) {
      found.add(orgJurisdiction(org))
      for (const group of org.groups ?? []) {
        found.add(groupJurisdiction(org, group.id))
      }
    }
  }
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

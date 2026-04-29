/**
 * Organization Management Service
 *
 * Handles organization context and switching logic.
 * Extracted from AuthContext to separate concerns.
 */

import { ApiClient, Organization } from '@/lib/api'

interface OrganizationState {
  organizations: Organization[]
  currentOrganization: Organization | null
}

export class OrganizationManager {
  private state: OrganizationState = {
    organizations: [],
    currentOrganization: null,
  }

  /**
   * Get current organizations
   */
  getOrganizations(): Organization[] {
    return this.state.organizations
  }

  /**
   * Get current organization
   */
  getCurrentOrganization(): Organization | null {
    return this.state.currentOrganization
  }

  /**
   * Set organizations list.
   *
   * NOTE: This intentionally does NOT auto-select the first org. The caller
   * (AuthContext) is the source of truth for `currentOrganization` and decides
   * whether to enter private mode (null) or pick a specific org based on the
   * subdomain / persisted state. Auto-picking here used to silently flip the
   * API-side org context to the alphabetically-first org while the UI still
   * displayed "Privat", causing 403s on org-only endpoints.
   */
  setOrganizations(organizations: Organization[]): void {
    this.state.organizations = organizations
  }

  /**
   * Set current organization
   */
  setCurrentOrganization(organization: Organization | null): void {
    this.state.currentOrganization = organization
  }

  /**
   * Fetch organizations for a user
   */
  async fetchOrganizations(apiClient: ApiClient): Promise<Organization[]> {
    try {
      const orgs = await apiClient.getOrganizations()
      this.setOrganizations(orgs)
      return orgs
    } catch (error) {
      console.warn('Failed to fetch organizations:', error)
      this.state.organizations = []
      this.state.currentOrganization = null
      return []
    }
  }

  /**
   * Clear organization state
   */
  clear(): void {
    this.state.organizations = []
    this.state.currentOrganization = null
  }

  /**
   * Get organization context for API calls.
   * Returns org ID when in org mode, 'private' when in private mode (no org selected).
   */
  getOrganizationContext(): string | null {
    return this.state.currentOrganization?.id || 'private'
  }
}

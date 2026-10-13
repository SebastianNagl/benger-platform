/**
 * Access keys (`bgr_...`) for the public /api/v1: management client for
 * organization keys, personal keys and the superadmin overview
 * (services/api/routers/access_keys.py).
 *
 * The full key appears once, in the create response. Lists only carry the
 * key prefix. Mutations clear the 30 s GET cache so the next list is fresh.
 */

import { BaseApiClient } from './base'
import type {
  AccessKey,
  AccessKeyCreate,
  AccessKeyCreated,
  AccessKeyOwnerType,
  AccessKeyPage,
  AccessKeyStatus,
  AccessKeyTestResult,
  AccessKeyUpdate,
  AccessKeyUsageEventPage,
  AccessKeyUsageSummary,
  AccessKeyWhoAmI,
  ScopeCatalog,
} from './types'

export interface AccessKeyUsageQuery {
  from?: string
  to?: string
  granularity?: 'day' | 'route'
}

export interface AdminAccessKeyQuery {
  organization_id?: string
  owner_type?: AccessKeyOwnerType
  status?: AccessKeyStatus
  cursor?: string
  limit?: number
}

/** Public path of the "who am I" call a key answers on. */
export const ACCESS_KEY_WHOAMI_PATH = '/api/v1/me'

function query(params: Record<string, string | number | undefined | null>) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      search.append(key, String(value))
    }
  }
  const s = search.toString()
  return s ? `?${s}` : ''
}

const orgBase = (orgId: string) =>
  `/organizations/${encodeURIComponent(orgId)}/access-keys`
const ME_BASE = '/users/me/access-keys'
const ADMIN_BASE = '/admin/access-keys'

export class AccessKeysClient extends BaseApiClient {
  /** Scope definitions (German and English) and the presets. */
  async scopes(): Promise<ScopeCatalog> {
    return this.get('/access-keys/scopes')
  }

  // ---- Organization keys -------------------------------------------------

  async listOrgKeys(orgId: string): Promise<AccessKey[]> {
    return (await this.get(orgBase(orgId))) ?? []
  }

  async createOrgKey(
    orgId: string,
    body: AccessKeyCreate,
  ): Promise<AccessKeyCreated> {
    const created = await this.post(orgBase(orgId), body)
    this.clearCache()
    return created
  }

  async updateOrgKey(
    orgId: string,
    keyId: string,
    body: AccessKeyUpdate,
  ): Promise<AccessKey> {
    const key = await this.patch(`${orgBase(orgId)}/${keyId}`, body)
    this.clearCache()
    return key
  }

  async revokeOrgKey(
    orgId: string,
    keyId: string,
    reason?: string | null,
  ): Promise<AccessKey> {
    const key = await this.post(`${orgBase(orgId)}/${keyId}/revoke`, {
      reason: reason || null,
    })
    this.clearCache()
    return key
  }

  async orgKeyUsage(
    orgId: string,
    keyId: string,
    params: AccessKeyUsageQuery = {},
  ): Promise<AccessKeyUsageSummary> {
    return this.get(`${orgBase(orgId)}/${keyId}/usage${query({ ...params })}`)
  }

  async orgKeyUsageEvents(
    orgId: string,
    keyId: string,
    params: { cursor?: number; limit?: number } = {},
  ): Promise<AccessKeyUsageEventPage> {
    return this.get(
      `${orgBase(orgId)}/${keyId}/usage/events${query({ ...params })}`,
    )
  }

  /** Browser URL of the org's usage CSV (the Next proxy streams it). */
  orgUsageExportUrl(
    orgId: string,
    params: { from?: string; to?: string } = {},
  ): string {
    return `/api${orgBase(orgId)}/usage/export.csv${query({ ...params })}`
  }

  // ---- Personal keys -----------------------------------------------------

  async listMyKeys(): Promise<AccessKey[]> {
    return (await this.get(ME_BASE)) ?? []
  }

  async createMyKey(body: AccessKeyCreate): Promise<AccessKeyCreated> {
    const created = await this.post(ME_BASE, body)
    this.clearCache()
    return created
  }

  async revokeMyKey(keyId: string, reason?: string | null): Promise<AccessKey> {
    const key = await this.post(`${ME_BASE}/${keyId}/revoke`, {
      reason: reason || null,
    })
    this.clearCache()
    return key
  }

  async myKeyUsage(
    keyId: string,
    params: AccessKeyUsageQuery = {},
  ): Promise<AccessKeyUsageSummary> {
    return this.get(`${ME_BASE}/${keyId}/usage${query({ ...params })}`)
  }

  // ---- Superadmin --------------------------------------------------------

  async adminListKeys(
    params: AdminAccessKeyQuery = {},
  ): Promise<AccessKeyPage> {
    const page = await this.get(`${ADMIN_BASE}${query({ ...params })}`)
    return page ?? { items: [], next_cursor: null }
  }

  async adminRevokeKey(
    keyId: string,
    reason?: string | null,
  ): Promise<AccessKey> {
    const key = await this.post(`${ADMIN_BASE}/${keyId}/revoke`, {
      reason: reason || null,
    })
    this.clearCache()
    return key
  }

  adminUsageExportUrl(
    params: { from?: string; to?: string; organization_id?: string } = {},
  ): string {
    return `/api${ADMIN_BASE}/usage/export.csv${query({ ...params })}`
  }

  // ---- Connection test ---------------------------------------------------

  /**
   * Call GET /api/v1/me with the key, exactly as a script would. Plain fetch
   * on purpose: no session cookie (the key alone must authenticate), no
   * cache, and a 401 must not trigger the session refresh/logout of the
   * base client.
   */
  async testConnection(secret: string): Promise<AccessKeyTestResult> {
    let response: Response
    try {
      response = await fetch(ACCESS_KEY_WHOAMI_PATH, {
        method: 'GET',
        credentials: 'omit',
        cache: 'no-store',
        headers: {
          Authorization: `Bearer ${secret}`,
          Accept: 'application/json',
        },
      })
    } catch (error) {
      return {
        ok: false,
        status: 0,
        code: 'network_error',
        message: error instanceof Error ? error.message : String(error),
      }
    }
    let body: any = null
    try {
      body = await response.json()
    } catch {
      body = null
    }
    if (response.ok && body && body.principal) {
      return { ok: true, me: body as AccessKeyWhoAmI }
    }
    const detail = body?.detail
    const code =
      (detail && typeof detail === 'object' && detail.code) ||
      body?.code ||
      null
    const message =
      (detail && typeof detail === 'object' && detail.message) ||
      (typeof detail === 'string' ? detail : null) ||
      body?.message ||
      `HTTP ${response.status}`
    return { ok: false, status: response.status, code, message }
  }
}

export const accessKeysAPI = new AccessKeysClient()

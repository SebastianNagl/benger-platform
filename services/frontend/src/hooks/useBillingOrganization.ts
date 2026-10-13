'use client'

/**
 * useBillingOrganization: which organization pays for generation and
 * evaluation runs on a project ("billed to").
 *
 * The options come from `/users/api-keys/billing-options`: the orgs attached
 * to the project that provide keys there and that the caller may bill. With
 * more than one option the dialogs show a choice; the pick is remembered per
 * project in this browser and shared by every component on the page (model
 * lists, the generation and evaluation dialogs, single-cell re-runs). A pick
 * that is no longer an option is ignored, so the server's default rule
 * applies (`billingOrganizationId` null).
 */

import { api } from '@/lib/api'
import type { BillingOption } from '@/lib/api/evaluations'
import { useEffect, useState, useSyncExternalStore } from 'react'

const STORAGE_PREFIX = 'benger:billing-org:'
const memory = new Map<string, string>()
const listeners = new Set<() => void>()

function readChoice(projectId: string): string | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_PREFIX + projectId)
    if (stored !== null) return stored || null
  } catch {
    // Storage blocked: fall back to the in-memory copy.
  }
  return memory.get(projectId) ?? null
}

function writeChoice(projectId: string, orgId: string | null) {
  if (orgId) memory.set(projectId, orgId)
  else memory.delete(projectId)
  try {
    if (orgId) window.localStorage.setItem(STORAGE_PREFIX + projectId, orgId)
    else window.localStorage.removeItem(STORAGE_PREFIX + projectId)
  } catch {
    // Storage blocked: the in-memory copy still syncs this page.
  }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export interface UseBillingOrganizationReturn {
  options: BillingOption[]
  /** The org the default rule bills (null = personal keys). */
  defaultOrganizationId: string | null
  /** The explicit pick, if it is still an option; null = the default rule. */
  billingOrganizationId: string | null
  setBillingOrganizationId: (orgId: string | null) => void
  loading: boolean
}

export function useBillingOrganization(
  projectId?: string | null,
): UseBillingOrganizationReturn {
  // The fetched answer, keyed by its project so a project switch never
  // shows the previous project's options.
  const [fetched, setFetched] = useState<{
    projectId: string
    options: BillingOption[]
    defaultOrganizationId: string | null
  } | null>(null)
  const choice = useSyncExternalStore(
    subscribe,
    () => (projectId ? readChoice(projectId) : null),
    () => null,
  )

  useEffect(() => {
    if (!projectId || typeof api.getBillingOptions !== 'function') return
    let cancelled = false
    const settle = (
      options: BillingOption[],
      defaultOrganizationId: string | null,
    ) => {
      if (!cancelled) setFetched({ projectId, options, defaultOrganizationId })
    }
    Promise.resolve(api.getBillingOptions(projectId))
      .then((data) =>
        settle(
          Array.isArray(data?.options) ? data.options : [],
          data?.default_organization_id ?? null,
        ),
      )
      // No choice offered; runs use the default rule.
      .catch(() => settle([], null))
    return () => {
      cancelled = true
    }
  }, [projectId])

  const current = fetched && fetched.projectId === projectId ? fetched : null
  const options = current?.options ?? []
  const defaultOrganizationId = current?.defaultOrganizationId ?? null
  const loading =
    !!projectId && !current && typeof api.getBillingOptions === 'function'
  const billingOrganizationId =
    choice && options.some((o) => o.id === choice) ? choice : null

  return {
    options,
    defaultOrganizationId,
    billingOrganizationId,
    setBillingOrganizationId: (orgId) => {
      if (projectId) writeChoice(projectId, orgId)
    },
    loading,
  }
}

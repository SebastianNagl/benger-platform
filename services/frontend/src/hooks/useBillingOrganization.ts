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
import { useEffect, useSyncExternalStore } from 'react'

const STORAGE_PREFIX = 'benger:billing-org:'
const memory = new Map<string, string>()
const listeners = new Set<() => void>()

interface FetchedOptions {
  options: BillingOption[]
  defaultOrganizationId: string | null
}

// The fetched options, shared by every component on the page. Each copy of
// the hook kept its own before: the generation dialog's provider is mounted
// with the page and loaded the options once, the "Billed to" select loads
// them when the dialog opens. An org attached in between showed up in the
// select but not in the copy that built the request, so the pick was
// dropped and the run went to the default payer.
const fetchedOptions = new Map<string, FetchedOptions>()

function notify() {
  listeners.forEach((listener) => listener())
}

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
  notify()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Test hook: forget the shared options between tests. */
export function resetBillingOptionsCache() {
  fetchedOptions.clear()
  memory.clear()
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
  const choice = useSyncExternalStore(
    subscribe,
    () => (projectId ? readChoice(projectId) : null),
    () => null,
  )
  const current = useSyncExternalStore(
    subscribe,
    () => (projectId ? (fetchedOptions.get(projectId) ?? null) : null),
    () => null,
  )

  // Every mount refreshes the shared copy, so opening a dialog updates the
  // options for every component on the page, not only for itself.
  useEffect(() => {
    if (!projectId || typeof api.getBillingOptions !== 'function') return
    let cancelled = false
    const settle = (
      options: BillingOption[],
      defaultOrganizationId: string | null,
    ) => {
      if (cancelled) return
      fetchedOptions.set(projectId, { options, defaultOrganizationId })
      notify()
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

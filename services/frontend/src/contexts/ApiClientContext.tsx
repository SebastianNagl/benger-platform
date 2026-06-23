'use client'

/**
 * ApiClientContext — explicit, org-aware API-client threading.
 *
 * Background: `@/lib/api`'s default export is a module-level singleton whose
 * organization context + auth-failure handler are configured by GLOBAL
 * MUTATION (`setOrganizationContextProvider` / `setAuthFailureHandler`). That
 * singleton is load-bearing — many components import it directly and a number
 * of module-level resource clients (projects, etc.) rely on whoever last
 * mutated it having set the right provider. We are NOT ripping that out.
 *
 * This context is the backward-compatible *alternative*: it threads a concrete
 * `ApiClient` instance (already wired with the current org context + auth
 * failure handler) down the tree, so a consumer can do
 *
 *     const api = useApiClient()
 *
 * instead of importing the global singleton and trusting global mutation
 * order. Consumers migrate to it incrementally; everything still on the
 * singleton keeps working untouched.
 *
 * The provider value is supplied by {@link AuthContext}, which owns the
 * org-context source of truth (the `OrganizationManager`) and constructs its
 * client via `createApiClient({ orgContextProvider, onAuthFailure })`.
 *
 * NOTE: this is intentionally separate from the older
 * `contexts/ApiClientProvider.tsx`, which builds a *bare* (un-org-wired)
 * client and is kept for its existing consumers/tests. New, org-aware call
 * sites should use THIS context.
 */

import type { ApiClient } from '@/lib/api'
import { createContext, useContext, type ReactNode } from 'react'

const ApiClientContext = createContext<ApiClient | null>(null)

export interface ApiClientContextProviderProps {
  /**
   * The org-wired API client to expose to descendants. Typically the instance
   * AuthContext maintains (built via `createApiClient` and kept in sync with
   * the current organization), so consumers transparently get the right
   * `X-Organization-Context` header and auth-failure behavior.
   */
  client: ApiClient
  children: ReactNode
}

/**
 * Provides an explicitly-threaded {@link ApiClient} to the subtree. Mounted by
 * AuthContext so the value tracks the authenticated org context.
 */
export function ApiClientContextProvider({
  client,
  children,
}: ApiClientContextProviderProps) {
  return (
    <ApiClientContext.Provider value={client}>
      {children}
    </ApiClientContext.Provider>
  )
}

/**
 * Returns the org-aware {@link ApiClient} from context.
 *
 * Use this in new code instead of `import apiClient from '@/lib/api'` so the
 * organization context is threaded explicitly rather than read off the
 * globally-mutated singleton. Throws if no provider is mounted, which surfaces
 * accidental use outside the authenticated tree at dev time.
 */
export function useApiClient(): ApiClient {
  const client = useContext(ApiClientContext)
  if (!client) {
    throw new Error(
      'useApiClient must be used within an ApiClientContextProvider ' +
        '(mounted by AuthProvider). For un-authenticated/standalone usage, ' +
        'import the singleton from "@/lib/api" instead.'
    )
  }
  return client
}

/**
 * Non-throwing variant: returns the context client when available, otherwise
 * `null`. Useful for shared components that may render both inside and outside
 * the authenticated tree and want to fall back to the singleton themselves.
 */
export function useOptionalApiClient(): ApiClient | null {
  return useContext(ApiClientContext)
}

export { ApiClientContext }

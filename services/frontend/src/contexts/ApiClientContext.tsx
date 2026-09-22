'use client'

/**
 * ApiClientContext — explicit API-client threading.
 *
 * Background: `@/lib/api`'s default export is a module-level singleton whose
 * auth-failure handler is configured by GLOBAL MUTATION
 * (`setAuthFailureHandler`). That singleton is load-bearing — many
 * components import it directly and a number of module-level resource
 * clients (projects, etc.) rely on it. We are NOT ripping that out.
 *
 * This context is the backward-compatible *alternative*: it threads a concrete
 * `ApiClient` instance (already wired with the auth failure handler) down the
 * tree, so a consumer can do
 *
 *     const api = useApiClient()
 *
 * instead of importing the global singleton and trusting global mutation
 * order. Consumers migrate to it incrementally; everything still on the
 * singleton keeps working untouched.
 *
 * The provider value is supplied by {@link AuthContext}, which constructs its
 * client via `createApiClient()`. Since core 2.22 no request carries a
 * selected organization: the API decides access per project from every
 * membership.
 *
 * NOTE: this is intentionally separate from the older
 * `contexts/ApiClientProvider.tsx`, which builds a bare client and is kept
 * for its existing consumers/tests. New call sites should use THIS context.
 */

import type { ApiClient } from '@/lib/api'
import { createContext, useContext, type ReactNode } from 'react'

const ApiClientContext = createContext<ApiClient | null>(null)

export interface ApiClientContextProviderProps {
  /**
   * The API client to expose to descendants. Typically the instance
   * AuthContext maintains (built via `createApiClient`), so consumers
   * transparently get the auth-failure behavior.
   */
  client: ApiClient
  children: ReactNode
}

/**
 * Provides an explicitly-threaded {@link ApiClient} to the subtree. Mounted by
 * AuthContext.
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
 * Returns the {@link ApiClient} from context.
 *
 * Use this in new code instead of `import apiClient from '@/lib/api'` so the
 * client is threaded explicitly rather than read off the globally-mutated
 * singleton. Throws if no provider is mounted, which surfaces accidental use
 * outside the authenticated tree at dev time.
 */
export function useApiClient(): ApiClient {
  const client = useContext(ApiClientContext)
  if (!client) {
    throw new Error(
      'useApiClient must be used within an ApiClientContextProvider ' +
        '(mounted by AuthProvider). For un-authenticated/standalone usage, ' +
        'import the singleton from "@/lib/api" instead.',
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

'use client'

/**
 * ModelScopeContext: which keys the model pickers below it list.
 *
 * `useModels` reads `/users/api-keys/available-models`, which answers per
 * scope: the org a run on a PROJECT dispatches with (`projectId`), the
 * creation target of the project wizard (`organizationId`), or, without
 * either, the caller's personal keys. The project pages and the wizard
 * mount this provider so every picker inside them shows exactly the models
 * the worker can run there; a picker outside any provider lists the
 * personal keys.
 */

import { createContext, useContext, useMemo, type ReactNode } from 'react'

export interface ModelScope {
  projectId?: string | null
  organizationId?: string | null
}

const ModelScopeContext = createContext<ModelScope>({})

export function ModelScopeProvider({
  projectId,
  organizationId,
  children,
}: ModelScope & { children: ReactNode }) {
  const value = useMemo(
    () => ({
      projectId: projectId ?? null,
      organizationId: organizationId ?? null,
    }),
    [projectId, organizationId],
  )
  return (
    <ModelScopeContext.Provider value={value}>
      {children}
    </ModelScopeContext.Provider>
  )
}

export function useModelScope(): ModelScope {
  return useContext(ModelScopeContext)
}

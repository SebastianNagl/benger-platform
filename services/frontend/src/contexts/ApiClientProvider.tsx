'use client'

import { ApiClient } from '@/lib/api'
import React, { createContext, useContext, useMemo } from 'react'

interface ApiClientContextType {
  apiClient: ApiClient
}

const ApiClientContext = createContext<ApiClientContextType | null>(null)

export function ApiClientProvider({ children }: { children: React.ReactNode }) {
  // Create stable ApiClient instance
  const apiClient = useMemo(() => new ApiClient(), [])

  return (
    <ApiClientContext.Provider value={{ apiClient }}>
      {children}
    </ApiClientContext.Provider>
  )
}

export function useApiClient() {
  const context = useContext(ApiClientContext)
  if (!context) {
    throw new Error('useApiClient must be used within an ApiClientProvider')
  }
  return context.apiClient
}

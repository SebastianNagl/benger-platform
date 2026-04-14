'use client'

import { useAuth } from '@/components/auth/SimpleAuth'
import React, { createContext, useContext, useMemo, useState } from 'react'

interface FeatureFlagContextType {
  flags: Record<string, boolean>
  isLoading: boolean
  isEnabled: (flagName: string) => boolean
  toggleFlag: (flagName: string) => void
}

const FeatureFlagContext = createContext<FeatureFlagContextType | null>(null)

export function useFeatureFlag(flagName: string): boolean {
  const context = useContext(FeatureFlagContext)
  if (!context) {
    return false // Default to disabled if no provider
  }
  return context.isEnabled(flagName)
}

export function useFeatureFlags() {
  const context = useContext(FeatureFlagContext)
  if (!context) {
    throw new Error('useFeatureFlags must be used within a FeatureFlagProvider')
  }
  return context
}

export function SimpleFeatureFlagProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const { user } = useAuth()
  // Store only user-toggled overrides
  const [flagOverrides, setFlagOverrides] = useState<Record<string, boolean>>({})
  const [isLoading] = useState(false)

  // Base flags derived from user role
  const baseFlags = useMemo(() => ({
    new_ui: true,
    beta_features: false,
    advanced_analytics: user?.role === 'admin',
    experimental_features: false,
  }), [user?.role])

  // Combine base flags with overrides (overrides take precedence)
  const flags = useMemo(() => ({
    ...baseFlags,
    ...flagOverrides,
  }), [baseFlags, flagOverrides])

  const isEnabled = (flagName: string): boolean => {
    // Check overrides first, then base flags
    if (flagName in flagOverrides) {
      return flagOverrides[flagName]
    }
    return baseFlags[flagName as keyof typeof baseFlags] ?? false
  }

  const toggleFlag = (flagName: string) => {
    setFlagOverrides((prev) => ({
      ...prev,
      [flagName]: !isEnabled(flagName),
    }))
  }

  return (
    <FeatureFlagContext.Provider
      value={{
        flags,
        isLoading,
        isEnabled,
        toggleFlag,
      }}
    >
      {children}
    </FeatureFlagContext.Provider>
  )
}

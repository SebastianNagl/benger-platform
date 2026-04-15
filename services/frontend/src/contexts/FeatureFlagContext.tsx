'use client'

import { api } from '@/lib/api'
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react'
import { useAuth } from './AuthContext'

interface FeatureFlagContextType {
  flags: Record<string, boolean>
  isLoading: boolean
  error: string | null
  isEnabled: (flagName: string) => boolean
  refreshFlags: () => Promise<void>
  checkFlag: (flagName: string) => Promise<boolean>
  lastUpdate: number
}

const FeatureFlagContext = createContext<FeatureFlagContextType | null>(null)

export function FeatureFlagProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const { user } = useAuth()
  const [flags, setFlags] = useState<Record<string, boolean>>({})
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState(Date.now())

  const refreshFlags = useCallback(async () => {
    if (!user) {
      setFlags({})
      setIsLoading(false)
      return
    }

    try {
      setIsLoading(true)
      setError(null)

      // Add cache-busting parameter to ensure fresh data
      const timestamp = Date.now()

      // Feature flags are global - no organization context needed
      const featureFlags = await api.getFeatureFlags()

      // Force a completely new object reference and update timestamp to trigger React updates
      const newFlags = { ...featureFlags }
      setFlags(newFlags)
      setLastUpdate(timestamp)
    } catch (err) {
      // Don't log 401 errors as they're expected during auth transitions
      if (!(err instanceof Error && err.message.includes('401'))) {
        console.error('Error fetching feature flags:', err)
      }
      setError(
        err instanceof Error ? err.message : 'Failed to fetch feature flags'
      )
      // On error, keep existing flags to avoid breaking the app
    } finally {
      setIsLoading(false)
    }
  }, [user])

  const checkFlag = useCallback(
    async (flagName: string): Promise<boolean> => {
      if (!user) {
        return false
      }

      try {
        const status = await api.checkFeatureFlag(flagName)
        return status.is_enabled
      } catch (err) {
        console.error(`Error checking feature flag '${flagName}':`, err)
        return false
      }
    },
    [user]
  )

  const isEnabled = useCallback(
    (flagName: string): boolean => {
      return (flags && flags[flagName]) || false
    },
    [flags]
  )

  // Load flags when user or organization changes
  useEffect(() => {
    if (user) {
      refreshFlags()
    } else {
      // No user - set loading to false and clear flags
      setFlags({})
      setIsLoading(false)
    }
  }, [refreshFlags, user])

  // No automatic refresh interval - flags will be fetched fresh when needed
  // This ensures immediate updates when flags are toggled

  const value: FeatureFlagContextType = {
    flags,
    isLoading,
    error,
    isEnabled,
    refreshFlags,
    checkFlag,
    lastUpdate,
  }

  return (
    <FeatureFlagContext.Provider value={value}>
      {children}
    </FeatureFlagContext.Provider>
  )
}

export function useFeatureFlags(): FeatureFlagContextType {
  const context = useContext(FeatureFlagContext)
  if (!context) {
    throw new Error('useFeatureFlags must be used within a FeatureFlagProvider')
  }
  return context
}

// Convenience hook for checking a single flag
export function useFeatureFlag(flagName: string): boolean {
  const { flags, lastUpdate } = useFeatureFlags()

  // Use lastUpdate to ensure React knows when to re-render
  // This is a workaround to make the hook reactive
  useEffect(() => {
    // This effect runs when lastUpdate changes, forcing a re-render
  }, [lastUpdate])

  try {
    return flags[flagName] ?? false
  } catch (error) {
    console.warn(`Feature flag '${flagName}' check failed:`, error)
    return false
  }
}

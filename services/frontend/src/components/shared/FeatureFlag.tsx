'use client'

import { useFeatureFlag, useFeatureFlags } from '@/contexts/FeatureFlagContext'
import React, { ReactNode, useEffect, useState } from 'react'

interface FeatureFlagProps {
  flag: string
  children: ReactNode
  fallback?: ReactNode
  loading?: ReactNode
}

/**
 * Component wrapper for conditional rendering based on feature flags
 *
 * @param flag - The name of the feature flag to check
 * @param children - Content to render when the flag is enabled
 * @param fallback - Content to render when the flag is disabled (optional)
 * @param loading - Content to render while loading (optional)
 */
export function FeatureFlag({
  flag,
  children,
  fallback = null,
  loading = null,
}: FeatureFlagProps) {
  const { isLoading } = useFeatureFlags()
  const isEnabled = useFeatureFlag(flag)

  if (isLoading && loading) {
    return <>{loading}</>
  }

  if (isEnabled) {
    return <>{children}</>
  }

  return <>{fallback}</>
}

interface AsyncFeatureFlagProps {
  flag: string
  children: ReactNode
  fallback?: ReactNode
  loading?: ReactNode
}

/**
 * Component wrapper that checks feature flags asynchronously
 * Useful for server-side rendering or when you need real-time flag checking
 */
export function AsyncFeatureFlag({
  flag,
  children,
  fallback = null,
  loading = null,
}: AsyncFeatureFlagProps) {
  const { checkFlag } = useFeatureFlags()
  const [isEnabled, setIsEnabled] = useState<boolean | null>(null)

  useEffect(() => {
    let mounted = true

    async function check() {
      try {
        const enabled = await checkFlag(flag)
        if (mounted) {
          setIsEnabled(enabled)
        }
      } catch (error) {
        console.error(`Error checking feature flag '${flag}':`, error)
        if (mounted) {
          setIsEnabled(false) // Default to disabled on error
        }
      }
    }

    check()

    return () => {
      mounted = false
    }
  }, [flag, checkFlag])

  if (isEnabled === null && loading) {
    return <>{loading}</>
  }

  if (isEnabled === null) {
    return <>{fallback}</>
  }

  if (isEnabled) {
    return <>{children}</>
  }

  return <>{fallback}</>
}

interface FeatureFlagDebugProps {
  flag: string
  showDetails?: boolean
}

/**
 * Debug component to show feature flag status
 * Only shows in development environment
 */
export function FeatureFlagDebug({
  flag,
  showDetails = false,
}: FeatureFlagDebugProps) {
  const { flags, isLoading, error } = useFeatureFlags()
  const isEnabled = useFeatureFlag(flag)

  // Only show in development
  if (process.env.NODE_ENV !== 'development') {
    return null
  }

  return (
    <div className="inline-block rounded border bg-gray-100 px-2 py-1 text-xs dark:bg-gray-800">
      <span className="font-mono">
        🚩 {flag}: {isLoading ? '⏳' : isEnabled ? '✅' : '❌'}
      </span>
      {showDetails && (
        <div className="mt-1 text-gray-600 dark:text-gray-400">
          {error && <div className="text-red-500">Error: {error}</div>}
          <div>All flags: {Object.keys(flags).length}</div>
        </div>
      )}
    </div>
  )
}

// Higher-order component for feature flag protection
export function withFeatureFlag<P extends object>(
  Component: React.ComponentType<P>,
  flagName: string,
  fallback?: ReactNode
) {
  return function FeatureFlagWrappedComponent(props: P) {
    return (
      <FeatureFlag flag={flagName} fallback={fallback}>
        <Component {...props} />
      </FeatureFlag>
    )
  }
}

// Hook for imperative feature flag checking with error handling
export function useFeatureFlagWithFallback(
  flagName: string,
  fallback: boolean = false
): boolean {
  const { isEnabled, error } = useFeatureFlags()

  if (error) {
    console.warn(
      `Feature flag '${flagName}' check failed, using fallback: ${fallback}`
    )
    return fallback
  }

  return isEnabled(flagName)
}

// Utility component for feature flag boundaries
interface FeatureFlagBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
}

export function FeatureFlagBoundary({
  children,
  fallback,
}: FeatureFlagBoundaryProps) {
  const { error } = useFeatureFlags()

  if (error) {
    console.error('Feature flag system error:', error)
    return <>{fallback || children}</>
  }

  return <>{children}</>
}

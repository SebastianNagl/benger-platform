'use client'

/**
 * FeatureFlagGate: renders its children only while `flag` is on for the
 * viewer. While the answer loads it renders nothing; with the flag off it
 * renders the app's not-found page, which is what the route showed before
 * the feature existed. The API refuses the feature's routes the same way
 * (404 `feature_disabled`), so a page never shows what the server will
 * not serve.
 */

import type { ReactNode } from 'react'

import NotFound from '@/app/not-found'
import { type FeatureFlagName, useFeatureFlagStatus } from '@/lib/featureFlags'

export function FeatureFlagGate({
  flag,
  children,
}: {
  flag: FeatureFlagName
  children: ReactNode
}) {
  const status = useFeatureFlagStatus(flag)
  if (status === 'loading') return null
  if (status === 'off') return <NotFound />
  return <>{children}</>
}

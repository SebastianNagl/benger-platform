'use client'

/**
 * usePublicApiEnabled: is the public API (access keys + /api/v1) switched on
 * for the current user (feature flag `public_api`)?
 *
 * Returns `null` while unknown (auth still loading or the availability call
 * in flight) and callers treat that like `false`, so the feature never
 * flickers in. The answer is cached per user id in module scope: the many
 * consumers (profile, org admin, nav search, how-to, changelog) share one
 * request, and a login or user switch asks again. Errors count as off.
 */

import { useEffect, useState } from 'react'

import { useAuth } from '@/contexts/AuthContext'
import { getPublicApiAvailability } from '@/lib/api/accessKeys'

const ANONYMOUS = '__anonymous__'

const cache = new Map<string, boolean>()
const inflight = new Map<string, Promise<boolean>>()

function load(key: string): Promise<boolean> {
  const pending = inflight.get(key)
  if (pending) return pending
  const promise = getPublicApiAvailability()
    .then((res) => res?.enabled === true)
    .catch(() => false)
    .then((enabled) => {
      cache.set(key, enabled)
      inflight.delete(key)
      return enabled
    })
  inflight.set(key, promise)
  return promise
}

/** Forget every cached answer (tests, or after an admin flips the flag). */
export function resetPublicApiAvailabilityCache() {
  cache.clear()
  inflight.clear()
}

export function usePublicApiEnabled(): boolean | null {
  const { user, isLoading } = useAuth()
  const key = isLoading ? null : (user?.id ?? ANONYMOUS)
  const [, setTick] = useState(0)

  useEffect(() => {
    if (key === null || cache.has(key)) return
    let alive = true
    load(key).then(() => {
      if (alive) setTick((t) => t + 1)
    })
    return () => {
      alive = false
    }
  }, [key])

  if (key === null) return null
  return cache.has(key) ? (cache.get(key) as boolean) : null
}

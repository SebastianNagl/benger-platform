/**
 * Extension slot registry for BenGER extended features.
 *
 * Extended features register React components into named slots.
 * Core code renders slots via useSlot() hook which re-renders
 * when slots are registered (handles async loading) and when the set of
 * active overlays changes (runtime master flags, see ./active.ts).
 *
 * Every owner keeps its own registration per slot; the slot resolves to the
 * newest registration whose owner is active. An overlay overriding another
 * overlay's slot therefore falls back to the one below it when it is
 * switched off.
 */

import { type ComponentType, useCallback, useSyncExternalStore } from 'react'
import { isOwnerActive, subscribeActiveExtensions } from './active'
import {
  type RegistrationOwners,
  type RegistrationStacks,
  pushRegistration,
  recordRegistration,
  resolveRegistration,
} from './owner'

const slots: RegistrationStacks<ComponentType<any>> = new Map()
const slotOwners: RegistrationOwners = new Map()
const listeners: Set<() => void> = new Set()

function notifyListeners() {
  listeners.forEach((fn) => fn())
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  const unsubscribeActive = subscribeActiveExtensions(listener)
  return () => {
    listeners.delete(listener)
    unsubscribeActive()
  }
}

/**
 * Register a React component for a named slot.
 * Called by an overlay's registerAll() during initialization. A different
 * owner registering the same slot logs a warning (see ./owner.ts) and takes
 * precedence while it is active. Notifies all useSlot() hooks to re-render.
 */
export function registerSlot(name: string, component: ComponentType<any>) {
  recordRegistration(slotOwners, 'slot', name)
  pushRegistration(slots, name, component)
  notifyListeners()
}

/**
 * Get the component registered for a slot by an active owner, or null.
 * For non-React contexts (e.g. build-time checks).
 */
export function getSlot(name: string): ComponentType<any> | null {
  return resolveRegistration(slots, name, isOwnerActive) ?? null
}

/**
 * React hook that returns the component for a slot.
 * Re-renders when slots are registered (handles async loadExtended) and when
 * the active overlays change.
 */
export function useSlot(name: string): ComponentType<any> | null {
  const snapshot = useCallback(() => getSlot(name), [name])
  return useSyncExternalStore(subscribe, snapshot, snapshot)
}

/**
 * Check if a slot has a component registered by an active owner.
 */
export function hasSlot(name: string): boolean {
  return getSlot(name) !== null
}

/**
 * Extension slot registry for BenGER extended features.
 *
 * Extended features register React components into named slots.
 * Core code renders slots via useSlot() hook which re-renders
 * when slots are registered (handles async loading).
 */

import { type ComponentType, useEffect, useState } from 'react'
import { type RegistrationOwners, recordRegistration } from './owner'

const slots: Record<string, ComponentType<any>> = {}
const slotOwners: RegistrationOwners = new Map()
const listeners: Set<() => void> = new Set()

function notifyListeners() {
  listeners.forEach((fn) => fn())
}

/**
 * Register a React component for a named slot.
 * Called by an overlay's registerAll() during initialization. The last
 * registration wins; a different owner overwriting a slot logs a warning
 * (see ./owner.ts). Notifies all useSlot() hooks to re-render.
 */
export function registerSlot(name: string, component: ComponentType<any>) {
  recordRegistration(slotOwners, 'slot', name)
  slots[name] = component
  notifyListeners()
}

/**
 * Get the component registered for a slot, or null if none.
 * For non-React contexts (e.g. build-time checks).
 */
export function getSlot(name: string): ComponentType<any> | null {
  return slots[name] ?? null
}

/**
 * React hook that returns the component for a slot.
 * Re-renders when slots are registered (handles async loadExtended).
 */
export function useSlot(name: string): ComponentType<any> | null {
  const [, setTick] = useState(0)

  useEffect(() => {
    const listener = () => setTick((t) => t + 1)
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }, [])

  return slots[name] ?? null
}

/**
 * Check if a slot has a component registered.
 */
export function hasSlot(name: string): boolean {
  return name in slots
}

/**
 * Extension slot registry for BenGER extended features.
 *
 * Extended features register React components into named slots.
 * Core code renders slots via getSlot() -- if no component is
 * registered (community edition), the slot returns null.
 */

import type { ComponentType } from 'react'

const slots: Record<string, ComponentType<any>> = {}

/**
 * Register a React component for a named slot.
 * Called by the extended package during initialization.
 */
export function registerSlot(name: string, component: ComponentType<any>) {
  slots[name] = component
}

/**
 * Get the component registered for a slot, or null if none.
 * Core code uses this to conditionally render extended features.
 */
export function getSlot(name: string): ComponentType<any> | null {
  return slots[name] ?? null
}

/**
 * Check if a slot has a component registered.
 */
export function hasSlot(name: string): boolean {
  return name in slots
}

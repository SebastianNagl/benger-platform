/**
 * Centralized State Management for BenGER Frontend
 *
 * This module provides standardized state management patterns using Zustand
 * for consistent, performant, and type-safe state handling.
 *
 * All stores follow the same patterns:
 * - Zustand for state management
 * - DevTools integration for debugging
 * - Persistence where appropriate
 * - TypeScript types for all state
 * - Consistent naming conventions
 */

export { useNotificationStore } from './notificationStore'
export { useUIStore } from './uiStore'

// Re-export Zustand types for convenience
export type { StateCreator, StoreApi } from 'zustand'

// Note: Authentication state is now managed by AuthContext, not Zustand stores

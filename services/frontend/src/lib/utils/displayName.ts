/**
 * Display name utilities for pseudonymization support
 *
 * Provides helper functions to display user names based on their pseudonym preference.
 * Implements GDPR-compliant privacy protection (Issue #790).
 */

import type { User } from '@/lib/api/types'

/**
 * Get the appropriate display name for a user based on their pseudonym preference.
 *
 * Respects user's privacy preference:
 * - If use_pseudonym is true and pseudonym exists: returns pseudonym
 * - Otherwise: returns real name
 *
 * @param user - User object with name, pseudonym, and use_pseudonym fields
 * @returns The display name (pseudonym or real name) or 'Unknown User' if user is null
 *
 * @example
 * ```ts
 * const user = { name: 'John Doe', pseudonym: 'WiseScholar', use_pseudonym: true }
 * getUserDisplayName(user) // Returns: 'WiseScholar'
 *
 * const user2 = { name: 'Jane Smith', pseudonym: 'BoldJudge', use_pseudonym: false }
 * getUserDisplayName(user2) // Returns: 'Jane Smith'
 * ```
 */
export function getUserDisplayName(user: User | null | undefined): string {
  if (!user) {
    return 'Unknown User'
  }

  // Respect user's privacy preference
  if (user.use_pseudonym && user.pseudonym) {
    return user.pseudonym
  }

  // Fall back to real name
  return user.name || user.username || 'Unknown User'
}

/**
 * Batch version for efficiently processing multiple users.
 *
 * Useful for displaying lists of users while respecting privacy preferences.
 *
 * @param users - Array of User objects
 * @returns Map of user IDs to display names
 *
 * @example
 * ```ts
 * const users = [
 *   { id: '1', name: 'John Doe', pseudonym: 'WiseScholar', use_pseudonym: true },
 *   { id: '2', name: 'Jane Smith', pseudonym: 'BoldJudge', use_pseudonym: false },
 * ]
 * const displayNames = getUserDisplayNames(users)
 * displayNames.get('1') // Returns: 'WiseScholar'
 * displayNames.get('2') // Returns: 'Jane Smith'
 * ```
 */
export function getUserDisplayNames(users: User[]): Map<string, string> {
  const displayNames = new Map<string, string>()

  users.forEach((user) => {
    displayNames.set(user.id, getUserDisplayName(user))
  })

  return displayNames
}

/**
 * Check if a user is currently using their pseudonym.
 *
 * @param user - User object
 * @returns true if user has pseudonym preference enabled, false otherwise
 */
export function isUsingPseudonym(user: User | null | undefined): boolean {
  if (!user) {
    return false
  }

  return Boolean(user.use_pseudonym && user.pseudonym)
}

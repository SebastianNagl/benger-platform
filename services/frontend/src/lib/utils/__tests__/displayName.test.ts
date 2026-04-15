/**
 * Tests for display name utilities
 */

import {
  getUserDisplayName,
  getUserDisplayNames,
  isUsingPseudonym,
} from '../displayName'

// Minimal User type matching the function signatures
const createUser = (overrides: Record<string, any> = {}) => ({
  id: 'user-1',
  name: 'John Doe',
  username: 'johndoe',
  email: 'john@example.com',
  pseudonym: undefined as string | undefined,
  use_pseudonym: false,
  is_superadmin: false,
  is_active: true,
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
  ...overrides,
})

describe('getUserDisplayName', () => {
  it('should return "Unknown User" for null user', () => {
    expect(getUserDisplayName(null)).toBe('Unknown User')
  })

  it('should return "Unknown User" for undefined user', () => {
    expect(getUserDisplayName(undefined)).toBe('Unknown User')
  })

  it('should return real name when use_pseudonym is false', () => {
    const user = createUser({ name: 'Jane Smith', use_pseudonym: false })
    expect(getUserDisplayName(user as any)).toBe('Jane Smith')
  })

  it('should return pseudonym when use_pseudonym is true and pseudonym exists', () => {
    const user = createUser({
      name: 'John Doe',
      pseudonym: 'WiseScholar',
      use_pseudonym: true,
    })
    expect(getUserDisplayName(user as any)).toBe('WiseScholar')
  })

  it('should return real name when use_pseudonym is true but pseudonym is empty', () => {
    const user = createUser({
      name: 'John Doe',
      pseudonym: '',
      use_pseudonym: true,
    })
    expect(getUserDisplayName(user as any)).toBe('John Doe')
  })

  it('should return real name when use_pseudonym is true but pseudonym is undefined', () => {
    const user = createUser({
      name: 'John Doe',
      pseudonym: undefined,
      use_pseudonym: true,
    })
    expect(getUserDisplayName(user as any)).toBe('John Doe')
  })

  it('should fall back to username when name is empty', () => {
    const user = createUser({ name: '', username: 'johndoe' })
    expect(getUserDisplayName(user as any)).toBe('johndoe')
  })

  it('should return "Unknown User" when both name and username are empty', () => {
    const user = createUser({ name: '', username: '' })
    expect(getUserDisplayName(user as any)).toBe('Unknown User')
  })
})

describe('getUserDisplayNames', () => {
  it('should return a map of user IDs to display names', () => {
    const users = [
      createUser({ id: '1', name: 'Alice', use_pseudonym: false }),
      createUser({
        id: '2',
        name: 'Bob',
        pseudonym: 'Scholar',
        use_pseudonym: true,
      }),
    ]
    const result = getUserDisplayNames(users as any)
    expect(result.get('1')).toBe('Alice')
    expect(result.get('2')).toBe('Scholar')
  })

  it('should return empty map for empty array', () => {
    const result = getUserDisplayNames([])
    expect(result.size).toBe(0)
  })

  it('should handle multiple users with same names', () => {
    const users = [
      createUser({ id: '1', name: 'John' }),
      createUser({ id: '2', name: 'John' }),
    ]
    const result = getUserDisplayNames(users as any)
    expect(result.size).toBe(2)
    expect(result.get('1')).toBe('John')
    expect(result.get('2')).toBe('John')
  })
})

describe('isUsingPseudonym', () => {
  it('should return false for null user', () => {
    expect(isUsingPseudonym(null)).toBe(false)
  })

  it('should return false for undefined user', () => {
    expect(isUsingPseudonym(undefined)).toBe(false)
  })

  it('should return true when use_pseudonym is true and pseudonym exists', () => {
    const user = createUser({ use_pseudonym: true, pseudonym: 'Scholar' })
    expect(isUsingPseudonym(user as any)).toBe(true)
  })

  it('should return false when use_pseudonym is false', () => {
    const user = createUser({ use_pseudonym: false, pseudonym: 'Scholar' })
    expect(isUsingPseudonym(user as any)).toBe(false)
  })

  it('should return false when pseudonym is empty', () => {
    const user = createUser({ use_pseudonym: true, pseudonym: '' })
    expect(isUsingPseudonym(user as any)).toBe(false)
  })

  it('should return false when pseudonym is undefined', () => {
    const user = createUser({ use_pseudonym: true, pseudonym: undefined })
    expect(isUsingPseudonym(user as any)).toBe(false)
  })
})

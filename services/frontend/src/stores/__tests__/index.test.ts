/**
 * Tests for stores index exports
 */

import { useNotificationStore, useUIStore } from '../index'

describe('stores index', () => {
  it('should export useNotificationStore', () => {
    expect(useNotificationStore).toBeDefined()
    expect(typeof useNotificationStore).toBe('function')
  })

  it('should export useUIStore', () => {
    expect(useUIStore).toBeDefined()
    expect(typeof useUIStore).toBe('function')
  })
})

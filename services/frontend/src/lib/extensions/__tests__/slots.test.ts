import { registerSlot, getSlot, hasSlot } from '../slots'

describe('Extension Slots', () => {
  test('getSlot returns null for unregistered slot', () => {
    expect(getSlot('NonExistentSlot')).toBeNull()
  })

  test('registerSlot then getSlot returns component', () => {
    const MockComponent = (() => null) as any
    registerSlot('TestSlot', MockComponent)
    expect(getSlot('TestSlot')).toBe(MockComponent)
  })

  test('hasSlot returns false for unregistered slot', () => {
    expect(hasSlot('MissingSlot')).toBe(false)
  })

  test('hasSlot returns true after registration', () => {
    const MockComponent = (() => null) as any
    registerSlot('RegisteredSlot', MockComponent)
    expect(hasSlot('RegisteredSlot')).toBe(true)
  })
})

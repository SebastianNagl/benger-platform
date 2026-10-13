import { setRegistrationOwner } from '../owner'
import { getSlot, hasSlot, registerSlot } from '../slots'

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

describe('Extension Slots owner attribution', () => {
  let warn: jest.SpyInstance

  beforeEach(() => {
    setRegistrationOwner(null)
    warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
  })

  afterEach(() => {
    setRegistrationOwner(null)
    warn.mockRestore()
  })

  test('the same owner re-registers a slot silently', () => {
    const First = (() => null) as any
    setRegistrationOwner('extended')
    registerSlot('OwnedSlot', First)
    registerSlot('OwnedSlot', First)
    expect(warn).not.toHaveBeenCalled()
    expect(getSlot('OwnedSlot')).toBe(First)
  })

  test('a different owner overwriting a slot warns and still wins', () => {
    const First = (() => null) as any
    const Second = (() => null) as any
    setRegistrationOwner('extended')
    registerSlot('ContestedSlot', First)
    setRegistrationOwner('compliance')
    registerSlot('ContestedSlot', Second)
    expect(warn).toHaveBeenCalledTimes(1)
    expect(warn).toHaveBeenCalledWith(
      '[extensions] slot "ContestedSlot" registered by compliance replaces extended',
    )
    expect(getSlot('ContestedSlot')).toBe(Second)
  })

  test('platform code overwriting an overlay slot is labelled platform', () => {
    const First = (() => null) as any
    const Second = (() => null) as any
    setRegistrationOwner('extended')
    registerSlot('PlatformOverwrittenSlot', First)
    setRegistrationOwner(null)
    registerSlot('PlatformOverwrittenSlot', Second)
    expect(warn).toHaveBeenCalledWith(
      '[extensions] slot "PlatformOverwrittenSlot" registered by platform replaces extended',
    )
  })
})

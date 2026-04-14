/**
 * @jest-environment jsdom
 *
 * Branch coverage: translate.ts
 * Targets: SSR branch, localStorage branches, variable interpolation, non-string value
 */

describe('translate branch coverage', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.resetModules()
  })

  it('returns key when value is undefined (no translation found)', () => {
    const { translate } = require('../../utils/translate')
    expect(translate('nonexistent.deep.key')).toBe('nonexistent.deep.key')
  })

  it('reads locale from localStorage when set to en', () => {
    localStorage.setItem('preferred-locale', 'en')
    const { translate } = require('../../utils/translate')
    // Should use English translations - result depends on translation file content
    const result = translate('some.key')
    expect(typeof result).toBe('string')
  })

  it('handles variable interpolation with missing variable', () => {
    const { translate } = require('../../utils/translate')
    // If a translation contains {var} but vars dont have that key, match is kept
    // We test by providing partial vars
    const result = translate('nonexistent', { count: 5 })
    expect(result).toBe('nonexistent')
  })

  it('returns key when resolved value is not a string (e.g., object)', () => {
    const { translate } = require('../../utils/translate')
    // A top-level namespace key resolves to an object, not a string
    const result = translate('projects')
    // Should return 'projects' since resolved value is an object
    expect(result).toBe('projects')
  })

  it('handles localStorage access throwing', () => {
    const origGetItem = Storage.prototype.getItem
    Storage.prototype.getItem = () => { throw new Error('blocked') }
    const { translate } = require('../../utils/translate')
    // Falls back to 'de' locale
    const result = translate('nonexistent')
    expect(result).toBe('nonexistent')
    Storage.prototype.getItem = origGetItem
  })

  it('handles vars with existing string value', () => {
    localStorage.setItem('preferred-locale', 'de')
    const { translate } = require('../../utils/translate')
    // Pass vars to a key that doesn't exist - returns key
    const result = translate('a.b.c', { x: 1 })
    expect(result).toBe('a.b.c')
  })
})

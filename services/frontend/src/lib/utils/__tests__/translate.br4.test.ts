/**
 * @jest-environment jsdom
 *
 * Branch coverage: translate.ts variable interpolation.
 *
 * translate.br3.test.ts covers the SSR-key / object-value / throwing-locale
 * fallbacks. The variable-interpolation path (a resolved STRING value that
 * contains {placeholders}) and the plain string-return path were uncovered.
 * We drive them through real locale keys so the replacement actually fires.
 */

describe('translate · variable interpolation', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.resetModules()
    // Pin English so the keys below resolve to the known English strings.
    localStorage.setItem('preferred-locale', 'en')
  })

  it('interpolates a provided variable into a resolved string', () => {
    const { translate } = require('../translate')
    const result = translate('projects.bulkActions.archiveSuccess', { count: 3 })
    expect(result).toBe('Archived 3 projects successfully')
  })

  it('leaves an unfilled placeholder untouched when its var is missing', () => {
    const { translate } = require('../translate')
    // Pass an unrelated var; the {count} placeholder has no matching key, so
    // the original {count} token is kept verbatim.
    const result = translate('projects.bulkActions.archiveSuccess', {
      somethingElse: 9,
    })
    expect(result).toBe('Archived {count} projects successfully')
  })

  it('interpolates a string variable (filename) into the resolved string', () => {
    const { translate } = require('../translate')
    const result = translate(
      'projects.creation.wizard.step2.upload.selectedFile',
      { filename: 'cases.csv' }
    )
    expect(result).toBe('Selected: cases.csv')
  })

  it('returns the plain resolved string when no vars are supplied', () => {
    const { translate } = require('../translate')
    const result = translate('navigation.next')
    expect(result).toBe('Next')
  })

  it('returns the plain string even when vars are supplied but the value has no placeholders', () => {
    const { translate } = require('../translate')
    const result = translate('navigation.previous', { count: 1 })
    expect(result).toBe('Previous')
  })
})

/**
 * Labels of the analysis views (`@/lib/analysis/labels`): system keys split
 * and shortened, middle-cut chart labels and level texts.
 */

import { levelText, shortenLabel, systemLabels, systemParts } from '../labels'

describe('systemParts', () => {
  it('splits a key at its last @', () => {
    expect(systemParts('org/model@abc123')).toEqual({
      model: 'org/model',
      profile: 'abc123',
    })
    expect(systemParts('model')).toEqual({ model: 'model', profile: null })
    expect(systemParts('@abc')).toEqual({ model: '@abc', profile: null })
    expect(systemParts(null)).toEqual({ model: '', profile: null })
  })
})

describe('systemLabels', () => {
  it('keeps the profile only where two keys share a model', () => {
    const labels = systemLabels([
      'a@1111111111',
      'a@2222222222',
      'b@3333333333',
      'c',
      null,
    ])
    expect(labels.get('a@1111111111')).toBe('a@111111')
    expect(labels.get('a@2222222222')).toBe('a@222222')
    expect(labels.get('b@3333333333')).toBe('b')
    expect(labels.get('c')).toBe('c')
    expect(labels.get('')).toBe('')
  })
})

describe('shortenLabel', () => {
  it('cuts the middle and keeps an @profile suffix whole', () => {
    expect(shortenLabel('short', 10)).toBe('short')
    expect(shortenLabel('abcdefghijkl', 7)).toBe('abc…jkl')
    expect(shortenLabel('a-very-long-model@abc123', 14)).toBe('a-v…del@abc123')
    expect(shortenLabel('abcdef@xyz', 3)).toBe('a…f@xyz')
  })
})

describe('levelText', () => {
  it('names levels as the engine does', () => {
    expect(levelText(null)).toBe('')
    expect(levelText(undefined)).toBe('')
    expect(levelText(true)).toBe('true')
    expect(levelText(false)).toBe('false')
    expect(levelText(3)).toBe('3')
    expect(levelText('x')).toBe('x')
  })
})

import {
  BUNDESLAENDER,
  BUNDESLAND_CODES,
  bundeslandName,
  isBundeslandCode,
} from '../bundeslaender'

describe('bundeslaender codebook', () => {
  it('has exactly the 16 states, each with a name', () => {
    expect(BUNDESLAND_CODES).toHaveLength(16)
    expect(Object.keys(BUNDESLAENDER).sort()).toEqual(
      [...BUNDESLAND_CODES].sort(),
    )
  })

  it('validates codes', () => {
    expect(isBundeslandCode('NW')).toBe(true)
    expect(isBundeslandCode('nw')).toBe(false)
    expect(isBundeslandCode('XX')).toBe(false)
    expect(isBundeslandCode(null)).toBe(false)
  })

  it('names states per locale', () => {
    expect(bundeslandName('BY', 'de')).toBe('Bayern')
    expect(bundeslandName('BY', 'en')).toBe('Bavaria')
    expect(bundeslandName('BY', null)).toBe('Bayern')
  })
})

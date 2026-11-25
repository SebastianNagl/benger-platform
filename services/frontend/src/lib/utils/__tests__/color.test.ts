import { getContrastColor } from '../color'

describe('getContrastColor', () => {
  it('picks black text on light and white text on dark backgrounds', () => {
    expect(getContrastColor('#ffffff')).toBe('#000000')
    expect(getContrastColor('#FFEAA7')).toBe('#000000')
    expect(getContrastColor('#000000')).toBe('#ffffff')
    expect(getContrastColor('#1e3a8a')).toBe('#ffffff')
  })

  it('accepts the colour without a hash and ignores an alpha channel', () => {
    expect(getContrastColor('ffffff')).toBe('#000000')
    expect(getContrastColor('#00000080')).toBe('#ffffff')
  })

  it('expands the three-digit form', () => {
    expect(getContrastColor('#fff')).toBe('#000000')
    expect(getContrastColor('#123')).toBe('#ffffff')
  })

  it('falls back to black text for anything that is not a hex colour', () => {
    expect(getContrastColor('')).toBe('#000000')
    expect(getContrastColor('red')).toBe('#000000')
    expect(getContrastColor('#12')).toBe('#000000')
    expect(getContrastColor('#gggggg')).toBe('#000000')
    expect(getContrastColor(undefined as unknown as string)).toBe('#000000')
  })

  it('splits at mid brightness', () => {
    // 0.299*128 + 0.587*128 + 0.114*128 = 128 -> 128/255 > 0.5
    expect(getContrastColor('#808080')).toBe('#000000')
    // 127/255 < 0.5
    expect(getContrastColor('#7f7f7f')).toBe('#ffffff')
  })
})

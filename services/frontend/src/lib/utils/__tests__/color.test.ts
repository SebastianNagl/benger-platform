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

  it('reads any other CSS colour the way the browser does', () => {
    // CSS Color 4 named colours: blue = #0000ff, red = #ff0000,
    // yellow = #ffff00, white = #ffffff.
    expect(getContrastColor('blue')).toBe('#ffffff')
    expect(getContrastColor('red')).toBe('#ffffff')
    expect(getContrastColor('yellow')).toBe('#000000')
    expect(getContrastColor('White')).toBe('#000000')
    expect(getContrastColor('rgb(255, 255, 255)')).toBe('#000000')
    expect(getContrastColor('rgba(0, 0, 0, 0.3)')).toBe('#ffffff')
    expect(getContrastColor('hsl(60, 100%, 50%)')).toBe('#000000')
    expect(getContrastColor('hsl(240, 100%, 50%)')).toBe('#ffffff')
  })

  it('falls back to white text for anything that is not a colour', () => {
    expect(getContrastColor('')).toBe('#ffffff')
    expect(getContrastColor('not-a-colour')).toBe('#ffffff')
    expect(getContrastColor('#12')).toBe('#ffffff')
    expect(getContrastColor('#gggggg')).toBe('#ffffff')
    expect(getContrastColor(undefined as unknown as string)).toBe('#ffffff')
  })

  it('splits at mid brightness', () => {
    // 0.299*128 + 0.587*128 + 0.114*128 = 128 -> 128/255 > 0.5
    expect(getContrastColor('#808080')).toBe('#000000')
    // 127/255 < 0.5
    expect(getContrastColor('#7f7f7f')).toBe('#ffffff')
  })
})

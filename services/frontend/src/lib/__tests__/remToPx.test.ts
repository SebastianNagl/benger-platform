/**
 * @jest-environment jsdom
 */

import { remToPx } from '../remToPx'

describe('remToPx', () => {
  beforeEach(() => {
    // Set a known font size on the root element for consistent testing
    document.documentElement.style.fontSize = '16px'
  })

  it('should convert rem to px using root font size', () => {
    const result = remToPx(1)
    expect(result).toBe(16)
  })

  it('should handle 0 rem', () => {
    expect(remToPx(0)).toBe(0)
  })

  it('should scale linearly with input', () => {
    expect(remToPx(2)).toBe(32)
  })

  it('should handle fractional rem values', () => {
    expect(remToPx(0.5)).toBe(8)
  })
})

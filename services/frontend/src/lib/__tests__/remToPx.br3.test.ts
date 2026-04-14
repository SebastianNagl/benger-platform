/**
 * @jest-environment jsdom
 *
 * Branch coverage: remToPx.ts
 * Target: window is defined path (browser environment) - br0[0] L4
 */

import { remToPx } from '../remToPx'

describe('remToPx branch coverage', () => {
  it('uses computed font size from document when window is defined', () => {
    // In jsdom, getComputedStyle may return empty string. Mock it.
    const spy = jest.spyOn(window, 'getComputedStyle').mockReturnValue({
      fontSize: '16px',
    } as any)
    const result = remToPx(2)
    expect(result).toBe(32)
    spy.mockRestore()
  })
})

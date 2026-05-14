/**
 * @jest-environment node
 *
 * SSR (no-DOM) behavior of fastRefreshDetector. Lives in a separate file
 * because JSDOM 21+ makes `window` non-configurable, so the "simulate SSR
 * by deleting global.window" pattern no longer works. Using the node test
 * environment gives us `typeof window === 'undefined'` naturally.
 */

import { fastRefreshDetector } from '@/lib/utils/fastRefreshDetector'

describe('FastRefreshDetector (SSR)', () => {
  it('isActive returns false on server-side', () => {
    expect(fastRefreshDetector.isActive()).toBe(false)
  })

  it('getTimeSinceLastRefresh returns Infinity on server-side', () => {
    expect(fastRefreshDetector.getTimeSinceLastRefresh()).toBe(Infinity)
  })

  it('markHandled does not throw on server-side', () => {
    expect(() =>
      fastRefreshDetector.markHandled('TestComponent')
    ).not.toThrow()
  })

  it('hasBeenHandled returns false on server-side', () => {
    expect(fastRefreshDetector.hasBeenHandled('TestComponent')).toBe(false)
  })
})

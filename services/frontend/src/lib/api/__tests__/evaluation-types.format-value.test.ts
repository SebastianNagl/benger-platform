/**
 * Fixed-point tests for `formatValueForScale` — the display-arithmetic that
 * turns a raw metric score into the string shown on the PUBLIC LLM
 * leaderboard.
 *
 * Why this file exists: a bug here is a wrong displayed benchmark number on a
 * research-grade legal-LLM leaderboard (e.g. 0.85 rendered as "8.5%" instead
 * of "85.0%"). The function used to be an untested nested closure inside
 * `LLMLeaderboardTable.tsx`; it was hoisted to a module-level export in
 * `evaluation-types.ts` (co-located with `getMetricScale`) precisely so its
 * branch + precision contract can be pinned exactly here and mutation-covered.
 *
 * Each block targets a specific class of mutant:
 *  - the ×100 multiply on '0-1' (drop / wrong constant)
 *  - the toFixed precision (1 vs 2 decimals; 0-1/0-100 use 1, sums/raw use 2)
 *  - the NP suffix + the sum/non-sum split inside '0-18'
 *  - the generic `sum` short-circuit (its presence AND its position before the
 *    '0-100' / '0-1' percent checks)
 *  - the '0-18'-before-`sum` precedence
 *  - the raw / unknown-scale fallback
 */

import { formatValueForScale } from '../evaluation-types'

describe("formatValueForScale — '0-1' scale (×100 to percent, 1 decimal)", () => {
  // Kills the ×100 drop and any wrong-precision mutant.
  it.each([
    [0.85, '85.0%'],
    [0.5, '50.0%'],
    [1, '100.0%'],
    [0, '0.0%'],
  ])('formats %p as %p', (value, expected) => {
    expect(formatValueForScale(value, '0-1', false)).toBe(expected)
  })

  it('rounds to exactly one decimal (not two, not zero)', () => {
    // 0.12345 ×100 = 12.345 -> "12.3%" pins toFixed(1) specifically.
    expect(formatValueForScale(0.12345, '0-1', false)).toBe('12.3%')
  })
})

describe("formatValueForScale — '0-100' scale (as-is percent, NO ×100)", () => {
  // Kills routing '0-100' through the '0-1' ×100 path: 85 must stay "85.0%",
  // never "8500.0%".
  it('renders 85 as "85.0%" without multiplying by 100', () => {
    expect(formatValueForScale(85, '0-100', false)).toBe('85.0%')
  })

  it.each([
    [0, '0.0%'],
    [100, '100.0%'],
    [42.5, '42.5%'],
  ])('formats %p as %p', (value, expected) => {
    expect(formatValueForScale(value, '0-100', false)).toBe(expected)
  })

  it('uses one-decimal precision', () => {
    // 12.345 -> "12.3%" (toFixed(1)), not "12.35%" or "12%".
    expect(formatValueForScale(12.345, '0-100', false)).toBe('12.3%')
  })
})

describe("formatValueForScale — '0-18' Notenpunkte scale", () => {
  // Kills the NP suffix mutant and the sum/non-sum branch swap.
  it('non-sum renders "X.x / 18 NP"', () => {
    expect(formatValueForScale(12.3, '0-18', false)).toBe('12.3 / 18 NP')
  })

  it('sum renders "X.x NP" (no "/ 18")', () => {
    expect(formatValueForScale(12.3, '0-18', true)).toBe('12.3 NP')
  })

  it('uses one-decimal precision for both forms', () => {
    expect(formatValueForScale(7.25, '0-18', false)).toBe('7.3 / 18 NP')
    expect(formatValueForScale(7.25, '0-18', true)).toBe('7.3 NP')
  })

  it('handles the boundary values 0 and 18', () => {
    expect(formatValueForScale(0, '0-18', false)).toBe('0.0 / 18 NP')
    expect(formatValueForScale(18, '0-18', false)).toBe('18.0 / 18 NP')
  })
})

describe('formatValueForScale — sum short-circuit on percentage scales', () => {
  // Kills the sum branch being dropped OR being placed AFTER the '0-100' /
  // '0-1' percent checks. A summed percentage-shaped metric is dimensionless:
  // raw value.toFixed(2), NO % sign, NO ×100.
  it("'0-1' + sum returns raw toFixed(2) with no % and no ×100", () => {
    expect(formatValueForScale(5, '0-1', true)).toBe('5.00')
    expect(formatValueForScale(0.85, '0-1', true)).toBe('0.85')
  })

  it("'0-100' + sum returns raw toFixed(2) with no %", () => {
    expect(formatValueForScale(5, '0-100', true)).toBe('5.00')
    expect(formatValueForScale(250.5, '0-100', true)).toBe('250.50')
  })

  it("'raw' + sum returns raw toFixed(2)", () => {
    expect(formatValueForScale(5, 'raw', true)).toBe('5.00')
  })

  it('the sum result contains no percent sign', () => {
    expect(formatValueForScale(0.85, '0-1', true)).not.toContain('%')
    expect(formatValueForScale(85, '0-100', true)).not.toContain('%')
  })
})

describe('formatValueForScale — raw / unknown scale fallback', () => {
  // Kills the fallback precision / suffix.
  it.each([
    [0.85, '0.85'],
    [5, '5.00'],
    [12.345, '12.35'],
    [0, '0.00'],
  ])("'raw' formats %p as %p (toFixed(2), no unit)", (value, expected) => {
    expect(formatValueForScale(value, 'raw', false)).toBe(expected)
  })

  it("'raw' output carries no % suffix", () => {
    expect(formatValueForScale(0.85, 'raw', false)).not.toContain('%')
  })
})

describe('formatValueForScale — branch precedence', () => {
  // The '0-18' check runs BEFORE the generic `sum` short-circuit, so a summed
  // Notenpunkte metric must still render the NP form — NOT the dimensionless
  // toFixed(2). This pins the ordering: were the `sum` branch moved above the
  // '0-18' check, this would return "12.30".
  it("'0-18' + sum yields the NP form, not the dimensionless sum form", () => {
    expect(formatValueForScale(12.3, '0-18', true)).toBe('12.3 NP')
    expect(formatValueForScale(12.3, '0-18', true)).not.toBe('12.30')
  })

  it("'0-100' percent check runs only when not a sum (sum wins for '0-100')", () => {
    // Non-sum -> percent; sum -> dimensionless. Pins that the '0-100' branch
    // sits AFTER the sum short-circuit.
    expect(formatValueForScale(85, '0-100', false)).toBe('85.0%')
    expect(formatValueForScale(85, '0-100', true)).toBe('85.00')
  })

  it("'0-1' percent check runs only when not a sum (sum wins for '0-1')", () => {
    expect(formatValueForScale(0.85, '0-1', false)).toBe('85.0%')
    expect(formatValueForScale(0.85, '0-1', true)).toBe('0.85')
  })
})

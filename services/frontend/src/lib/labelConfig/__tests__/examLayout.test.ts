/**
 * Tests for the exam layout contract module: the total preference resolver
 * and the exam-shaped-config predicate.
 */

import {
  CLASSIC_LAYOUT,
  isExamShapedConfig,
  MODERN_EXAM_LAYOUT_SLOT,
  resolveExamLayoutPrefs,
} from '../examLayout'
import type { ParsedComponent } from '../parser'

const node = (
  type: string,
  children: ParsedComponent[] = []
): ParsedComponent => ({ type, props: {}, children })

describe('CLASSIC_LAYOUT', () => {
  it('is the classic default with the documented placements', () => {
    expect(CLASSIC_LAYOUT).toEqual({
      mode: 'classic',
      case_position: 'left',
      notes_position: 'right',
      outline_position: 'right',
    })
  })

  it('is frozen so callers cannot mutate the shared default', () => {
    expect(Object.isFrozen(CLASSIC_LAYOUT)).toBe(true)
  })
})

describe('resolveExamLayoutPrefs', () => {
  it.each([null, undefined, 'modern', 42, true, []])(
    'resolves non-object input %p to CLASSIC_LAYOUT',
    (raw) => {
      expect(resolveExamLayoutPrefs(raw)).toEqual(CLASSIC_LAYOUT)
    }
  )

  it('resolves an empty object to classic defaults', () => {
    expect(resolveExamLayoutPrefs({})).toEqual(CLASSIC_LAYOUT)
  })

  it('fills defaults for a minimal modern object', () => {
    expect(resolveExamLayoutPrefs({ mode: 'modern' })).toEqual({
      mode: 'modern',
      case_position: 'left',
      notes_position: 'right',
      outline_position: 'right',
    })
  })

  it('passes a fully valid object through verbatim', () => {
    const prefs = {
      mode: 'modern',
      case_position: 'right',
      notes_position: 'none',
      outline_position: 'left',
    }
    expect(resolveExamLayoutPrefs(prefs)).toEqual(prefs)
  })

  it('falls back per-field on invalid values without rejecting the rest', () => {
    expect(
      resolveExamLayoutPrefs({
        mode: 'sideways',
        case_position: 'top',
        notes_position: 'left',
        outline_position: 'nowhere',
      })
    ).toEqual({
      mode: 'classic',
      case_position: 'left',
      notes_position: 'left',
      outline_position: 'right',
    })
  })

  it('keeps stored placements when mode is classic (round-trip survival)', () => {
    expect(
      resolveExamLayoutPrefs({
        mode: 'classic',
        case_position: 'right',
        notes_position: 'none',
        outline_position: 'left',
      })
    ).toEqual({
      mode: 'classic',
      case_position: 'right',
      notes_position: 'none',
      outline_position: 'left',
    })
  })

  it("rejects 'none' for the case (the exam text is mandatory)", () => {
    expect(
      resolveExamLayoutPrefs({ mode: 'modern', case_position: 'none' })
        .case_position
    ).toBe('left')
  })

  it('drops unknown keys from the resolved object', () => {
    const resolved = resolveExamLayoutPrefs({
      mode: 'modern',
      zoom_level: 2,
    }) as Record<string, unknown>
    expect(Object.keys(resolved).sort()).toEqual([
      'case_position',
      'mode',
      'notes_position',
      'outline_position',
    ])
  })

  it('passes valid panel widths through and clamps out-of-range ones', () => {
    expect(
      resolveExamLayoutPrefs({ mode: 'modern', left_panel_width: 500 })
        .left_panel_width
    ).toBe(500)
    expect(
      resolveExamLayoutPrefs({ mode: 'modern', left_panel_width: 100 })
        .left_panel_width
    ).toBe(260)
    expect(
      resolveExamLayoutPrefs({ mode: 'modern', right_panel_width: 9999 })
        .right_panel_width
    ).toBe(720)
    // Invalid types are omitted entirely — the key never appears.
    const resolved = resolveExamLayoutPrefs({
      mode: 'modern',
      left_panel_width: '400',
      right_panel_width: NaN,
    })
    expect('left_panel_width' in resolved).toBe(false)
    expect('right_panel_width' in resolved).toBe(false)
  })
})

describe('isExamShapedConfig', () => {
  it('is false for null/undefined', () => {
    expect(isExamShapedConfig(null)).toBe(false)
    expect(isExamShapedConfig(undefined)).toBe(false)
  })

  it('is true when a Loesung field is a direct child', () => {
    expect(
      isExamShapedConfig(node('View', [node('Header'), node('Loesung')]))
    ).toBe(true)
  })

  it('is true when Loesung is nested deeper in the tree', () => {
    expect(
      isExamShapedConfig(node('View', [node('View', [node('Loesung')])]))
    ).toBe(true)
  })

  it('is true when the root itself is a Loesung node', () => {
    expect(isExamShapedConfig(node('Loesung'))).toBe(true)
  })

  it('is false for a generic annotation config', () => {
    expect(
      isExamShapedConfig(
        node('View', [node('Text'), node('TextArea'), node('Choices')])
      )
    ).toBe(false)
  })

  it('tolerates nodes with missing children arrays', () => {
    const malformed = { type: 'View', props: {} } as ParsedComponent
    expect(isExamShapedConfig(malformed)).toBe(false)
  })
})

describe('MODERN_EXAM_LAYOUT_SLOT', () => {
  it('is the frozen slot-name contract with the extended edition', () => {
    expect(MODERN_EXAM_LAYOUT_SLOT).toBe('ModernExamLayout')
  })
})

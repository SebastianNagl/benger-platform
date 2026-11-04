/**
 * Tests for the exam layout contract module: the total preference resolver
 * and the exam-shaped-config predicate.
 */

import {
  CLASSIC_LAYOUT,
  isExamShapedConfig,
  MODERN_EXAM_LAYOUT_SLOT,
  PANEL_WIDTH_MAX,
  resolveExamLayoutPrefs,
  resolveToolPlacements,
  TOOL_FLOAT_MIN,
  TOOL_ORDER_MAX,
  TOOL_PLACEMENTS_MAX,
} from '../examLayout'
import type { ParsedComponent } from '../parser'

const node = (
  type: string,
  children: ParsedComponent[] = [],
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
    },
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
      }),
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
      }),
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
        .case_position,
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
        .left_panel_width,
    ).toBe(500)
    expect(
      resolveExamLayoutPrefs({ mode: 'modern', left_panel_width: 100 })
        .left_panel_width,
    ).toBe(260)
    expect(
      resolveExamLayoutPrefs({ mode: 'modern', right_panel_width: 9999 })
        .right_panel_width,
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

describe('resolveExamLayoutPrefs: state mode', () => {
  it('keeps mode state with a valid Bundesland code and its display settings', () => {
    expect(
      resolveExamLayoutPrefs({
        mode: 'state',
        state_code: 'BW',
        state_ui: {
          align: 'justify',
          hide_time: true,
          theme: 'contrast',
          spellcheck: false,
        },
      }),
    ).toEqual({
      ...CLASSIC_LAYOUT,
      mode: 'state',
      state_code: 'BW',
      state_ui: {
        align: 'justify',
        hide_time: true,
        theme: 'contrast',
        spellcheck: false,
      },
    })
  })

  it('falls back to classic when the state code is missing or invalid', () => {
    expect(resolveExamLayoutPrefs({ mode: 'state' }).mode).toBe('classic')
    const resolved = resolveExamLayoutPrefs({ mode: 'state', state_code: 'XX' })
    expect(resolved.mode).toBe('classic')
    expect('state_code' in resolved).toBe(false)
  })

  it('drops invalid state_ui fields and omits an empty state_ui', () => {
    expect(
      resolveExamLayoutPrefs({
        mode: 'state',
        state_code: 'BW',
        state_ui: {
          align: 'sideways',
          hide_time: false,
          theme: 'neon',
          spellcheck: 'yes',
        },
      }).state_ui,
    ).toEqual({ hide_time: false })
    const resolved = resolveExamLayoutPrefs({
      mode: 'state',
      state_code: 'BW',
      state_ui: { align: 'sideways' },
    })
    expect('state_ui' in resolved).toBe(false)
  })

  it('keeps state settings while another mode is selected', () => {
    const resolved = resolveExamLayoutPrefs({
      mode: 'modern',
      state_code: 'BW',
      state_ui: { hide_time: true },
    })
    expect(resolved.mode).toBe('modern')
    expect(resolved.state_code).toBe('BW')
    expect(resolved.state_ui).toEqual({ hide_time: true })
  })
})

describe('isExamShapedConfig', () => {
  it('is false for null/undefined', () => {
    expect(isExamShapedConfig(null)).toBe(false)
    expect(isExamShapedConfig(undefined)).toBe(false)
  })

  it('is true when a Loesung field is a direct child', () => {
    expect(
      isExamShapedConfig(node('View', [node('Header'), node('Loesung')])),
    ).toBe(true)
  })

  it('is true when Loesung is nested deeper in the tree', () => {
    expect(
      isExamShapedConfig(node('View', [node('View', [node('Loesung')])])),
    ).toBe(true)
  })

  it('is true when the root itself is a Loesung node', () => {
    expect(isExamShapedConfig(node('Loesung'))).toBe(true)
  })

  it('is false for a generic annotation config', () => {
    expect(
      isExamShapedConfig(
        node('View', [node('Text'), node('TextArea'), node('Choices')]),
      ),
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

describe('resolveToolPlacements (core 2.50)', () => {
  it('keeps valid placements and drops invalid ones', () => {
    expect(
      resolveToolPlacements({
        law_texts: { zone: 'right', order: 1, width: 500 },
        calculator: { zone: 'float', x: 10, y: 20, w: 30, h: 40 },
        notes: { zone: 'nowhere' },
        'Bad-Id': { zone: 'left' },
        calendar: 'left',
      }),
    ).toEqual({
      law_texts: { zone: 'right', order: 1, width: 500 },
      calculator: { zone: 'float', x: 10, y: 20, w: 30, h: 40 },
    })
  })

  it('clamps numbers so a floating window fits the viewport', () => {
    expect(
      resolveToolPlacements({
        calculator: { zone: 'float', x: 95, y: -5, w: 2, h: 400, order: 99 },
        law_texts: { zone: 'left', width: 5000 },
      }),
    ).toEqual({
      calculator: {
        zone: 'float',
        order: TOOL_ORDER_MAX,
        x: 100 - TOOL_FLOAT_MIN,
        y: 0,
        w: TOOL_FLOAT_MIN,
        h: 100,
      },
      law_texts: { zone: 'left', width: PANEL_WIDTH_MAX },
    })
  })

  it('returns undefined for non-objects and empty results', () => {
    for (const raw of [null, undefined, 'x', [], {}, { a: { zone: 'x' } }]) {
      expect(resolveToolPlacements(raw)).toBeUndefined()
    }
  })

  it('caps the number of placements', () => {
    const raw: Record<string, unknown> = {}
    for (let i = 0; i < TOOL_PLACEMENTS_MAX + 5; i++) {
      raw[`tool_${'a'.repeat((i % 20) + 1)}${i < 20 ? '' : 'b'}`] = {
        zone: 'hidden',
      }
    }
    expect(
      Object.keys(resolveToolPlacements(raw) ?? {}).length,
    ).toBeLessThanOrEqual(TOOL_PLACEMENTS_MAX)
  })

  it('is carried by resolveExamLayoutPrefs', () => {
    const prefs = resolveExamLayoutPrefs({
      mode: 'modern',
      tool_placements: { notes: { zone: 'left', order: 0 } },
    })
    expect(prefs.tool_placements).toEqual({ notes: { zone: 'left', order: 0 } })
    expect(
      'tool_placements' in resolveExamLayoutPrefs({ mode: 'modern' }),
    ).toBe(false)
  })
})

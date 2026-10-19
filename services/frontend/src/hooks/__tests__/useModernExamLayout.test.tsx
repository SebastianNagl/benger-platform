/**
 * @jest-environment jsdom
 *
 * Tests for useModernExamLayout — the single predicate for whether the modern
 * exam layout renders. Mirrors the useViewModeSwitch test setup: edition env
 * key mutated per test, AuthContext mocked with a mutable user, slots module
 * mocked with a mutable registry (the real module's subscription behavior is
 * its own concern; this hook just calls useSlot every render).
 */

import { renderHook } from '@testing-library/react'

import { CLASSIC_LAYOUT } from '@/lib/labelConfig/examLayout'

const EDITION_KEY = 'NEXT_PUBLIC_BENGER_EDITION'
const originalEdition = process.env[EDITION_KEY]

let mockUser: any = null
let mockSlotComponents: Record<string, unknown> = {}

const FakeLayout = () => null

jest.mock('@/contexts/AuthContext', () => ({
  useOptionalAuth: () => ({ user: mockUser }),
}))
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockSlotComponents[name] ?? null,
  hasSlot: (name: string) => !!mockSlotComponents[name],
  registerSlot: (name: string, component: unknown) => {
    mockSlotComponents[name] = component
  },
}))

// Runtime master flag extension.extended (lib/featureFlags).
let mockExtendedActive = true
jest.mock('@/lib/featureFlags', () => ({
  useExtensionActive: (id: string) => id === 'extended' && mockExtendedActive,
}))

import { useModernExamLayout } from '../useModernExamLayout'

const EXAM_CONFIG = `
  <View>
    <Header value="Angabe"/>
    <Angabe name="angabe" value="$sachverhalt" toName="sachverhalt"/>
    <Header value="Loesung"/>
    <Loesung name="loesung" toName="sachverhalt" required="true"/>
  </View>
`
const GENERIC_CONFIG = `
  <View>
    <Text name="text" value="$text"/>
    <TextArea name="answer" toName="text"/>
  </View>
`

const MODERN_PREFS = {
  mode: 'modern',
  case_position: 'left',
  notes_position: 'right',
  outline_position: 'none',
}

function setup({
  edition = 'extended' as string | null,
  slotRegistered = true,
  user = { id: 'u1', exam_layout_prefs: MODERN_PREFS },
  labelConfig = EXAM_CONFIG as string | null | undefined,
} = {}) {
  // null = community edition (env var absent). NOTE: undefined would trigger
  // the parameter default and silently test the extended edition instead.
  if (edition === null) {
    delete process.env[EDITION_KEY]
  } else {
    process.env[EDITION_KEY] = edition
  }
  mockSlotComponents = slotRegistered ? { ModernExamLayout: FakeLayout } : {}
  mockUser = user
  return renderHook(({ config }) => useModernExamLayout(config), {
    initialProps: { config: labelConfig },
  })
}

describe('useModernExamLayout', () => {
  afterEach(() => {
    if (originalEdition === undefined) {
      delete process.env[EDITION_KEY]
    } else {
      process.env[EDITION_KEY] = originalEdition
    }
  })

  it('is active when edition, slot, preference, and config all line up', () => {
    const { result } = setup()
    expect(result.current.active).toBe(true)
    expect(result.current.Layout).toBe(FakeLayout)
    expect(result.current.prefs).toEqual(MODERN_PREFS)
  })

  it('reports state=false for the modern preference', () => {
    expect(setup().result.current.state).toBe(false)
  })

  it('is active with state=true for a state-specific preference', () => {
    const { result } = setup({
      user: {
        id: 'u1',
        exam_layout_prefs: { ...MODERN_PREFS, mode: 'state', state_code: 'BW' },
      },
    })
    expect(result.current.active).toBe(true)
    expect(result.current.state).toBe(true)
    expect(result.current.prefs.state_code).toBe('BW')
  })

  it('stays classic for a state preference without a state code', () => {
    const { result } = setup({
      user: { id: 'u1', exam_layout_prefs: { ...MODERN_PREFS, mode: 'state' } },
    })
    expect(result.current.active).toBe(false)
    expect(result.current.state).toBe(false)
  })

  it('reports state=false when the state layout cannot render (community)', () => {
    const { result } = setup({
      edition: null,
      user: {
        id: 'u1',
        exam_layout_prefs: { ...MODERN_PREFS, mode: 'state', state_code: 'BW' },
      },
    })
    expect(result.current.state).toBe(false)
  })

  it('is inactive in the community edition even with everything else set', () => {
    const { result } = setup({ edition: null })
    expect(result.current.active).toBe(false)
  })

  it('is inactive while extended is switched off at runtime', () => {
    mockExtendedActive = false
    try {
      const { result } = setup()
      expect(result.current.active).toBe(false)
    } finally {
      mockExtendedActive = true
    }
  })

  it('is inactive while the slot is not registered, exposing Layout=null', () => {
    const { result } = setup({ slotRegistered: false })
    expect(result.current.active).toBe(false)
    expect(result.current.Layout).toBeNull()
  })

  it('is inactive when the user preference is classic', () => {
    const { result } = setup({
      user: {
        id: 'u1',
        exam_layout_prefs: { ...MODERN_PREFS, mode: 'classic' },
      },
    })
    expect(result.current.active).toBe(false)
  })

  it('resolves a missing/invalid preference to classic and stays inactive', () => {
    const missing = setup({ user: { id: 'u1' } })
    expect(missing.result.current.active).toBe(false)
    expect(missing.result.current.prefs).toEqual(CLASSIC_LAYOUT)

    const invalid = setup({
      user: { id: 'u1', exam_layout_prefs: 'garbage' },
    })
    expect(invalid.result.current.prefs).toEqual(CLASSIC_LAYOUT)
  })

  it('handles a logged-out user (no user object) as classic', () => {
    const { result } = setup({ user: null })
    expect(result.current.active).toBe(false)
    expect(result.current.prefs).toEqual(CLASSIC_LAYOUT)
  })

  it('is inactive for a non-exam-shaped config', () => {
    const { result } = setup({ labelConfig: GENERIC_CONFIG })
    expect(result.current.active).toBe(false)
  })

  it('is inactive for a missing or unparseable config', () => {
    expect(setup({ labelConfig: null }).result.current.active).toBe(false)
    expect(setup({ labelConfig: '<View' }).result.current.active).toBe(false)
  })

  it('flips active once the slot registers (late loadExtended)', () => {
    const { result, rerender } = setup({ slotRegistered: false })
    expect(result.current.active).toBe(false)

    mockSlotComponents.ModernExamLayout = FakeLayout
    rerender({ config: EXAM_CONFIG })

    expect(result.current.active).toBe(true)
    expect(result.current.Layout).toBe(FakeLayout)
  })
})

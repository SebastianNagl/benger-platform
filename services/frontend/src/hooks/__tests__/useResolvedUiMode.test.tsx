/**
 * @jest-environment jsdom
 *
 * useResolvedUiMode: the build-time overlay gate (isExtensionEnabled /
 * isExtendedEdition) and the shell precedence it feeds.
 */

import { renderHook } from '@testing-library/react'

const EXT = 'NEXT_PUBLIC_BENGER_EXTENSIONS'
const EDITION = 'NEXT_PUBLIC_BENGER_EDITION'
const original = { ext: process.env[EXT], edition: process.env[EDITION] }

let mockAuth: any = { user: null }
let mockLocalMode: 'student' | 'expert' | null = null
let mockLocked = false
let mockShell: any = null
let mockExtendedActive = true

jest.mock('@/contexts/AuthContext', () => ({ useAuth: () => mockAuth }))
jest.mock('@/stores', () => ({
  useUIStore: (selector: any) => selector({ uiMode: mockLocalMode }),
}))
jest.mock('@/lib/utils/subdomain', () => ({
  isStudentLockedHost: () => mockLocked,
}))
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: () => mockShell,
  hasSlot: () => mockShell !== null,
}))

// Runtime master flag extension.extended (lib/featureFlags).
jest.mock('@/lib/featureFlags', () => ({
  useExtensionActive: (id: string) => id === 'extended' && mockExtendedActive,
}))

import {
  isExtendedEdition,
  isExtensionEnabled,
  useResolvedUiMode,
} from '../useResolvedUiMode'

function setEnv(key: string, value: string | undefined) {
  if (value === undefined) delete process.env[key]
  else process.env[key] = value
}

const StudentShell = () => null

beforeEach(() => {
  setEnv(EXT, undefined)
  setEnv(EDITION, undefined)
  mockAuth = { user: null }
  mockLocalMode = null
  mockLocked = false
  mockShell = null
  mockExtendedActive = true
})

afterAll(() => {
  setEnv(EXT, original.ext)
  setEnv(EDITION, original.edition)
})

describe('isExtensionEnabled / isExtendedEdition', () => {
  test('community build: nothing enabled', () => {
    expect(isExtensionEnabled('extended')).toBe(false)
    expect(isExtensionEnabled('compliance')).toBe(false)
    expect(isExtendedEdition()).toBe(false)
  })

  test('legacy edition flag enables extended only', () => {
    setEnv(EDITION, 'extended')
    expect(isExtensionEnabled('extended')).toBe(true)
    expect(isExtensionEnabled('compliance')).toBe(false)
    expect(isExtendedEdition()).toBe(true)
  })

  test('the overlay list decides, in any order', () => {
    setEnv(EXT, 'compliance,extended')
    expect(isExtensionEnabled('extended')).toBe(true)
    expect(isExtensionEnabled('compliance')).toBe(true)
    expect(isExtendedEdition()).toBe(true)
  })

  test('a list without extended is not the extended edition', () => {
    setEnv(EDITION, 'extended')
    setEnv(EXT, 'compliance')
    expect(isExtensionEnabled('compliance')).toBe(true)
    expect(isExtensionEnabled('extended')).toBe(false)
    expect(isExtendedEdition()).toBe(false)
  })

  test('unknown names never count as enabled', () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
    try {
      setEnv(EXT, 'bogus')
      expect(isExtensionEnabled('bogus')).toBe(false)
      expect(isExtendedEdition()).toBe(false)
    } finally {
      warn.mockRestore()
    }
  })
})

describe('useResolvedUiMode', () => {
  test('community build renders the expert shell even on a locked host', () => {
    mockLocked = true
    mockShell = StudentShell
    const { result } = renderHook(() => useResolvedUiMode())
    expect(result.current).toBe('expert')
  })

  test('extended build without a StudentShell falls back to expert', () => {
    setEnv(EXT, 'extended')
    mockLocked = true
    const { result } = renderHook(() => useResolvedUiMode())
    expect(result.current).toBe('expert')
  })

  test('extended switched off at runtime renders the expert shell', () => {
    setEnv(EXT, 'extended')
    mockShell = StudentShell
    mockLocked = true
    mockExtendedActive = false
    mockAuth = { user: { id: 'u1', preferred_ui_mode: 'student' } }
    expect(renderHook(() => useResolvedUiMode()).result.current).toBe('expert')
  })

  test('anonymous visitors follow the host default', () => {
    setEnv(EXT, 'extended,compliance')
    mockShell = StudentShell
    mockLocked = true
    expect(renderHook(() => useResolvedUiMode()).result.current).toBe('student')
    mockLocked = false
    expect(renderHook(() => useResolvedUiMode()).result.current).toBe('expert')
  })

  test('a signed-in user: local switch, then saved preference, then host', () => {
    setEnv(EDITION, 'extended')
    mockShell = StudentShell
    mockLocked = true
    mockAuth = { user: { id: 'u1', preferred_ui_mode: 'expert' } }
    expect(renderHook(() => useResolvedUiMode()).result.current).toBe('expert')
    mockLocalMode = 'student'
    expect(renderHook(() => useResolvedUiMode()).result.current).toBe('student')
    mockLocalMode = null
    mockAuth = { user: { id: 'u1' } }
    expect(renderHook(() => useResolvedUiMode()).result.current).toBe('student')
  })
})

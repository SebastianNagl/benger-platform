/**
 * Extension loader: env list parsing, sequential overlay loading and owner
 * attribution. The overlay packages are virtual Jest mocks because nothing
 * under node_modules/@benger exists in the platform checkout.
 */

const mockCalls: string[] = []
const mockOwnerSeen: Record<string, string | null> = {}

jest.mock(
  '@benger/extended',
  () => ({
    registerAll: jest.fn(() => {
      mockCalls.push('extended')
      mockOwnerSeen.extended = (
        jest.requireActual('../owner') as typeof import('../owner')
      ).getRegistrationOwner()
    }),
  }),
  { virtual: true },
)
jest.mock(
  '@benger/compliance',
  () => ({
    registerAll: jest.fn(() => {
      mockCalls.push('compliance')
      mockOwnerSeen.compliance = (
        jest.requireActual('../owner') as typeof import('../owner')
      ).getRegistrationOwner()
    }),
  }),
  { virtual: true },
)

import { registerAll as complianceRegisterAll } from '@benger/compliance'
import { registerAll as extendedRegisterAll } from '@benger/extended'
import {
  _resetExtensionsForTests,
  enabledExtensions,
  getRegistrationOwner,
  isExtendedLoaded,
  isExtensionEnabled,
  isExtensionLoaded,
  loadExtended,
  loadExtensions,
} from '../index'

const extendedMock = extendedRegisterAll as jest.Mock
const complianceMock = complianceRegisterAll as jest.Mock

const EXT = 'NEXT_PUBLIC_BENGER_EXTENSIONS'
const EDITION = 'NEXT_PUBLIC_BENGER_EDITION'
const original = { ext: process.env[EXT], edition: process.env[EDITION] }

function setEnv(key: string, value: string | undefined) {
  if (value === undefined) delete process.env[key]
  else process.env[key] = value
}

let warn: jest.SpyInstance

beforeEach(() => {
  setEnv(EXT, undefined)
  setEnv(EDITION, undefined)
  mockCalls.length = 0
  delete mockOwnerSeen.extended
  delete mockOwnerSeen.compliance
  extendedMock.mockClear()
  complianceMock.mockClear()
  _resetExtensionsForTests()
  warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
})

afterEach(() => {
  warn.mockRestore()
})

afterAll(() => {
  setEnv(EXT, original.ext)
  setEnv(EDITION, original.edition)
})

describe('enabledExtensions', () => {
  test('nothing set: no overlays', () => {
    expect(enabledExtensions()).toEqual([])
    expect(isExtensionEnabled('extended')).toBe(false)
    expect(isExtensionEnabled('compliance')).toBe(false)
  })

  test('legacy edition flag enables the extended overlay alone', () => {
    setEnv(EDITION, 'extended')
    expect(enabledExtensions()).toEqual(['extended'])
    expect(isExtensionEnabled('extended')).toBe(true)
    expect(isExtensionEnabled('compliance')).toBe(false)
  })

  test('any other edition value enables nothing', () => {
    setEnv(EDITION, 'community')
    expect(enabledExtensions()).toEqual([])
  })

  test('parses the comma list in the given order, trimming names', () => {
    setEnv(EXT, ' extended , compliance ')
    expect(enabledExtensions()).toEqual(['extended', 'compliance'])
    setEnv(EXT, 'compliance,extended')
    expect(enabledExtensions()).toEqual(['compliance', 'extended'])
  })

  test('an explicit list wins over the legacy flag', () => {
    setEnv(EDITION, 'extended')
    setEnv(EXT, 'compliance')
    expect(enabledExtensions()).toEqual(['compliance'])
    expect(isExtensionEnabled('extended')).toBe(false)
  })

  test('a blank list falls back to the legacy flag', () => {
    setEnv(EDITION, 'extended')
    setEnv(EXT, '')
    expect(enabledExtensions()).toEqual(['extended'])
    setEnv(EXT, '   ')
    expect(enabledExtensions()).toEqual(['extended'])
    setEnv(EDITION, undefined)
    expect(enabledExtensions()).toEqual([])
  })

  test('drops empty segments and repeats', () => {
    setEnv(EXT, 'extended,,extended, ,compliance,extended')
    expect(enabledExtensions()).toEqual(['extended', 'compliance'])
  })

  test('ignores unknown names with one warning per value', () => {
    setEnv(EXT, 'bogus,extended,other')
    expect(enabledExtensions()).toEqual(['extended'])
    expect(enabledExtensions()).toEqual(['extended'])
    expect(warn).toHaveBeenCalledTimes(1)
    expect(warn).toHaveBeenCalledWith(
      '[extensions] unknown extension(s) ignored in NEXT_PUBLIC_BENGER_EXTENSIONS: bogus, other',
    )
    // A different value warns again.
    setEnv(EXT, 'extended,typo')
    expect(enabledExtensions()).toEqual(['extended'])
    expect(warn).toHaveBeenCalledTimes(2)
  })
})

describe('loadExtensions', () => {
  test('loads the enabled overlays one after another in list order', async () => {
    setEnv(EXT, 'extended,compliance')
    await expect(loadExtensions()).resolves.toEqual(['extended', 'compliance'])
    expect(mockCalls).toEqual(['extended', 'compliance'])
    expect(isExtensionLoaded('extended')).toBe(true)
    expect(isExtensionLoaded('compliance')).toBe(true)
    expect(isExtendedLoaded()).toBe(true)
    expect(warn).not.toHaveBeenCalled()
  })

  test('follows the list order when compliance comes first', async () => {
    setEnv(EXT, 'compliance,extended')
    await expect(loadExtensions()).resolves.toEqual(['compliance', 'extended'])
    expect(mockCalls).toEqual(['compliance', 'extended'])
  })

  test('loads only the overlays in the list', async () => {
    setEnv(EXT, 'compliance')
    await expect(loadExtensions()).resolves.toEqual(['compliance'])
    expect(extendedMock).not.toHaveBeenCalled()
    expect(isExtensionLoaded('extended')).toBe(false)
    expect(isExtendedLoaded()).toBe(false)
  })

  test('loads nothing in the community edition', async () => {
    await expect(loadExtensions()).resolves.toEqual([])
    expect(mockCalls).toEqual([])
    expect(isExtensionLoaded('extended')).toBe(false)
  })

  test('sets the registration owner around each registerAll()', async () => {
    setEnv(EXT, 'extended,compliance')
    await loadExtensions()
    expect(mockOwnerSeen).toEqual({
      extended: 'extended',
      compliance: 'compliance',
    })
    expect(getRegistrationOwner()).toBeNull()
  })

  test('a failing overlay does not block the next one', async () => {
    setEnv(EXT, 'extended,compliance')
    extendedMock.mockImplementationOnce(() => {
      throw new Error('boom')
    })
    await expect(loadExtensions()).resolves.toEqual(['compliance'])
    expect(isExtensionLoaded('extended')).toBe(false)
    expect(isExtensionLoaded('compliance')).toBe(true)
    expect(mockOwnerSeen.compliance).toBe('compliance')
    // The owner is cleared even when registerAll() throws.
    expect(getRegistrationOwner()).toBeNull()
    expect(warn).toHaveBeenCalledWith(
      '[extensions] overlay "extended" failed to load',
      expect.any(Error),
    )
  })

  test('retries a failed overlay on the next call', async () => {
    setEnv(EXT, 'extended')
    extendedMock.mockImplementationOnce(() => {
      throw new Error('boom')
    })
    await expect(loadExtensions()).resolves.toEqual([])
    await expect(loadExtensions()).resolves.toEqual(['extended'])
    expect(extendedMock).toHaveBeenCalledTimes(2)
    expect(isExtensionLoaded('extended')).toBe(true)
  })

  test('registers each overlay once across repeated calls', async () => {
    setEnv(EXT, 'extended,compliance')
    await loadExtensions()
    await expect(loadExtensions()).resolves.toEqual(['extended', 'compliance'])
    expect(extendedMock).toHaveBeenCalledTimes(1)
    expect(complianceMock).toHaveBeenCalledTimes(1)
  })

  test('concurrent calls share one load per overlay', async () => {
    setEnv(EXT, 'extended,compliance')
    const results = await Promise.all([loadExtensions(), loadExtensions()])
    expect(results).toEqual([
      ['extended', 'compliance'],
      ['extended', 'compliance'],
    ])
    expect(extendedMock).toHaveBeenCalledTimes(1)
    expect(complianceMock).toHaveBeenCalledTimes(1)
  })

  test('reset forgets loaded overlays', async () => {
    setEnv(EXT, 'extended')
    await loadExtensions()
    _resetExtensionsForTests()
    expect(isExtensionLoaded('extended')).toBe(false)
    await loadExtensions()
    expect(extendedMock).toHaveBeenCalledTimes(2)
  })
})

describe('loadExtended (legacy entry point)', () => {
  test('resolves true once the extended overlay registered', async () => {
    setEnv(EDITION, 'extended')
    await expect(loadExtended()).resolves.toBe(true)
    expect(mockCalls).toEqual(['extended'])
    expect(isExtendedLoaded()).toBe(true)
    expect(complianceMock).not.toHaveBeenCalled()
  })

  test('resolves false in the community edition', async () => {
    await expect(loadExtended()).resolves.toBe(false)
    expect(isExtendedLoaded()).toBe(false)
  })

  test('resolves false when only another overlay is enabled', async () => {
    setEnv(EXT, 'compliance')
    await expect(loadExtended()).resolves.toBe(false)
    expect(isExtensionLoaded('compliance')).toBe(true)
  })
})

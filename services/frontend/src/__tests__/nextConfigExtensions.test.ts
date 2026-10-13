/**
 * @jest-environment node
 */

/**
 * next.config.js overlay resolution.
 *
 * NEXT_PUBLIC_BENGER_EXTENSIONS (with the legacy NEXT_PUBLIC_BENGER_EDITION
 * fallback) decides which `@benger/<name>` packages are transpiled and where
 * each alias points: the overlay tree when present, node_modules when the
 * overlay is enabled but not copied in, and the community stub when it is
 * disabled. The same rule lives in src/lib/extensions/enabled.ts for the
 * runtime; src/lib/extensions/__tests__/index.test.ts covers that side.
 */

import fs from 'fs'

type Config = {
  transpilePackages: string[]
  turbopack: { resolveAlias: Record<string, string> }
}

const STUB = './src/lib/extensions/community-stub.ts'
const KEYS = ['NEXT_PUBLIC_BENGER_EXTENSIONS', 'NEXT_PUBLIC_BENGER_EDITION']

function loadConfig(
  env: Record<string, string | undefined>,
  treesPresent: string[] = [],
): Config {
  const previous = KEYS.map((key) => process.env[key])
  for (const key of KEYS) {
    if (env[key] === undefined) delete process.env[key]
    else process.env[key] = env[key]
  }
  const log = jest.spyOn(console, 'log').mockImplementation(() => undefined)
  const exists = jest
    .spyOn(fs, 'existsSync')
    .mockImplementation((p) =>
      treesPresent.some((dir) => String(p) === `./${dir}/index.ts`),
    )
  try {
    let config: Config | undefined
    jest.isolateModules(() => {
      config = require('../../next.config.js')
    })
    return config as Config
  } finally {
    KEYS.forEach((key, i) => {
      if (previous[i] === undefined) delete process.env[key]
      else process.env[key] = previous[i]
    })
    log.mockRestore()
    exists.mockRestore()
  }
}

describe('next.config.js extension overlays', () => {
  test('community build: nothing transpiled, every overlay is the stub', () => {
    const config = loadConfig({})
    expect(config.transpilePackages).toEqual([])
    expect(config.turbopack.resolveAlias).toEqual({
      '@benger/extended': STUB,
      '@benger/compliance': STUB,
    })
  })

  test('legacy edition flag enables the extended overlay from node_modules', () => {
    const config = loadConfig({ NEXT_PUBLIC_BENGER_EDITION: 'extended' })
    expect(config.transpilePackages).toEqual(['@benger/extended'])
    expect(config.turbopack.resolveAlias).toEqual({
      '@benger/extended': './node_modules/@benger/extended',
      '@benger/compliance': STUB,
    })
  })

  test('an enabled overlay whose tree was copied in resolves to that tree', () => {
    const config = loadConfig({ NEXT_PUBLIC_BENGER_EDITION: 'extended' }, [
      'benger-extended-frontend',
    ])
    expect(config.turbopack.resolveAlias['@benger/extended']).toBe(
      './benger-extended-frontend',
    )
  })

  test('the overlay list enables several overlays in order', () => {
    const config = loadConfig(
      { NEXT_PUBLIC_BENGER_EXTENSIONS: ' extended , compliance ' },
      ['benger-extended-frontend', 'benger-compliance-frontend'],
    )
    expect(config.transpilePackages).toEqual([
      '@benger/extended',
      '@benger/compliance',
    ])
    expect(config.turbopack.resolveAlias).toEqual({
      '@benger/extended': './benger-extended-frontend',
      '@benger/compliance': './benger-compliance-frontend',
    })
  })

  test('an explicit list wins over the legacy flag', () => {
    const config = loadConfig({
      NEXT_PUBLIC_BENGER_EDITION: 'extended',
      NEXT_PUBLIC_BENGER_EXTENSIONS: 'compliance',
    })
    expect(config.transpilePackages).toEqual(['@benger/compliance'])
    expect(config.turbopack.resolveAlias).toEqual({
      '@benger/extended': STUB,
      '@benger/compliance': './node_modules/@benger/compliance',
    })
  })

  test('a blank list falls back to the legacy flag (unset Docker build arg)', () => {
    const config = loadConfig({
      NEXT_PUBLIC_BENGER_EDITION: 'extended',
      NEXT_PUBLIC_BENGER_EXTENSIONS: '',
    })
    expect(config.transpilePackages).toEqual(['@benger/extended'])
  })

  test('unknown names are ignored with a warning, repeats collapse', () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
    try {
      const config = loadConfig({
        NEXT_PUBLIC_BENGER_EXTENSIONS: 'bogus,compliance,,compliance',
      })
      expect(config.transpilePackages).toEqual(['@benger/compliance'])
      expect(Object.keys(config.turbopack.resolveAlias).sort()).toEqual([
        '@benger/compliance',
        '@benger/extended',
      ])
      expect(warn).toHaveBeenCalledTimes(1)
      expect(warn).toHaveBeenCalledWith(
        '[extensions] unknown extension "bogus" in NEXT_PUBLIC_BENGER_EXTENSIONS ignored',
      )
    } finally {
      warn.mockRestore()
    }
  })
})

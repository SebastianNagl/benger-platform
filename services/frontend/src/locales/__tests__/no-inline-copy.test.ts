/**
 * Guard for the catalog-only rule: user-visible copy lives in the locale
 * JSONs (src/locales/<locale>/), never inline in source. Catches the
 * patterns that used to slip in: `t(key, 'inline default')`, `{ de, en }`
 * copy pairs and locale ternaries that only know German and English.
 * Formatting goes through intlTag()/dateFnsLocale() in lib/i18n/locales.
 */

import fs from 'fs'
import path from 'path'

const SRC = path.join(__dirname, '..', '..')

const ALLOWED = new Set([path.join(SRC, 'lib', 'i18n', 'locales.ts')])

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (
        ['__tests__', '__mocks__', 'locales', 'test-utils'].includes(entry.name)
      )
        continue
      sourceFiles(full, out)
    } else if (
      /\.(ts|tsx)$/.test(entry.name) &&
      !/\.(test|spec)\.(ts|tsx)$/.test(entry.name) &&
      !entry.name.endsWith('.d.ts')
    ) {
      out.push(full)
    }
  }
  return out
}

const RULES: Array<[string, RegExp]> = [
  ['t() with an inline default', /\bt\(\s*(['"`])[\w.-]+\1\s*,\s*['"`]/],
  ['{ de, en } copy pair', /\bde:\s*['"`][^'"`]*['"`],?\s*\n?\s*en:\s*['"`]/],
  ['de/en-only locale branch', /locale\s*===?\s*['"](de|en)['"]/],
  ["'de' | 'en' type", /['"]de['"]\s*\|\s*['"]en['"]/],
  [
    'browser-locale formatting (pass intlTag(locale))',
    /\.toLocale(String|DateString|TimeString)\(\)/,
  ],
]

describe('no inline copy in source', () => {
  const files = sourceFiles(SRC).filter((file) => !ALLOWED.has(file))

  it.each(RULES)('no %s', (_label, pattern) => {
    const offenders = files
      .filter((file) => pattern.test(fs.readFileSync(file, 'utf8')))
      .map((file) => path.relative(SRC, file))
    expect(offenders).toEqual([])
  })
})

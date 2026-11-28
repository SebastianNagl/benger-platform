/**
 * Lint-style guard over the platform source, not a behavior test: every
 * literal key a platform source file passes to t() must exist in the catalog
 * of every locale the platform ships (src/locales/<locale>/). t() returns a
 * missing key itself, so a typo or a key that was moved shows up on screen as
 * `some.raw.key` instead of copy. Keys built at runtime (template strings,
 * variables) are not covered; the pages' render tests check their copy.
 */

import fs from 'fs'
import path from 'path'

import { hasTranslation } from '@/lib/i18n/catalog'
import { LOCALES } from '@/lib/i18n/locales'

const SRC = path.join(__dirname, '..', '..')

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

// t('a.b.c') or t("a.b.c"), not someObject.t(...) or format(...).
const LITERAL_KEY =
  /(?<![\w.$])t\(\s*(['"])([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+)\1/g

describe('literal translation keys (lint-style source guard)', () => {
  it('exist in the catalog of every shipped locale', () => {
    const missing: string[] = []
    for (const file of sourceFiles(SRC)) {
      const text = fs.readFileSync(file, 'utf8')
      for (const match of text.matchAll(LITERAL_KEY)) {
        const key = match[2]
        for (const locale of LOCALES) {
          if (!hasTranslation(locale, key)) {
            missing.push(`${path.relative(SRC, file)}: ${key} (${locale})`)
          }
        }
      }
    }
    expect(missing).toEqual([])
  })
})

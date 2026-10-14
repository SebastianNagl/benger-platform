/**
 * Every locale carries every key: same tree, same list lengths, same
 * {placeholders}. A key that exists in only one language would silently
 * fall back (fr -> en -> de) instead of showing the user their language.
 */

import fs from 'fs'
import path from 'path'

const LOCALES = ['de', 'en', 'fr'] as const
const FILES = ['common.json', 'howto.json', 'changelog.json']
const ROOT = path.join(__dirname, '..')

type Leaf = string | number | boolean | null | Leaf[]

function leaves(
  tree: unknown,
  prefix = '',
  out = new Map<string, Leaf>(),
): Map<string, Leaf> {
  if (tree && typeof tree === 'object' && !Array.isArray(tree)) {
    for (const [key, value] of Object.entries(tree)) {
      leaves(value, prefix ? `${prefix}.${key}` : key, out)
    }
  } else {
    out.set(prefix, tree as Leaf)
  }
  return out
}

const placeholders = (value: Leaf): string =>
  JSON.stringify(
    [...new Set(JSON.stringify(value).match(/\{\w+\}/g) ?? [])].sort(),
  )

describe.each(FILES)('locale catalog %s', (file) => {
  const trees = Object.fromEntries(
    LOCALES.map((locale) => [
      locale,
      leaves(
        JSON.parse(fs.readFileSync(path.join(ROOT, locale, file), 'utf8')),
      ),
    ]),
  )

  it.each(['en', 'fr'] as const)('%s has exactly the German keys', (locale) => {
    const de = [...trees.de.keys()]
    const other = [...trees[locale].keys()]
    expect(other.filter((key) => !trees.de.has(key))).toEqual([])
    expect(de.filter((key) => !trees[locale].has(key))).toEqual([])
  })

  it.each(['en', 'fr'] as const)(
    '%s keeps list lengths and placeholders',
    (locale) => {
      const mismatches: string[] = []
      for (const [key, de] of trees.de) {
        const other = trees[locale].get(key)
        if (other === undefined) continue
        if (Array.isArray(de) !== Array.isArray(other)) {
          mismatches.push(`${key}: list vs string`)
        } else if (
          Array.isArray(de) &&
          // Guide keywords are per-language synonym lists, not translations.
          !key.endsWith('.keywords') &&
          de.length !== (other as Leaf[]).length
        ) {
          mismatches.push(`${key}: list length`)
        } else if (placeholders(de) !== placeholders(other)) {
          mismatches.push(`${key}: placeholders`)
        }
      }
      expect(mismatches).toEqual([])
    },
  )

  it('has no empty French strings where German has text', () => {
    const empty = [...trees.de]
      .filter(
        ([key, de]) =>
          typeof de === 'string' &&
          de.trim() !== '' &&
          trees.fr.get(key) === '',
      )
      .map(([key]) => key)
    expect(empty).toEqual([])
  })
})

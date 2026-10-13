/**
 * The access-key strings exist in both catalogs with the same keys and the
 * same placeholders, and the German copy addresses the reader with "du".
 */

import de from '../de/common.json'
import en from '../en/common.json'

type Tree = { [key: string]: string | Tree }

function leaves(tree: Tree, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') out[path] = value
    else Object.assign(out, leaves(value, path))
  }
  return out
}

const pick = (root: Tree) => ({
  ...leaves(root.accessKeys as Tree, 'accessKeys'),
  'admin.organizations.accessKeys': ((root.admin as Tree).organizations as Tree)
    .accessKeys as string,
  'profile.accessKeys': (root.profile as Tree).accessKeys as string,
  ...leaves(
    ((root.search as Tree).pages as Tree).adminAccessKeys as Tree,
    'search.pages.adminAccessKeys',
  ),
})

const placeholders = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort()

describe('access-key locale strings', () => {
  const deLeaves = pick(de as unknown as Tree)
  const enLeaves = pick(en as unknown as Tree)

  it('has the same keys in German and English', () => {
    expect(Object.keys(deLeaves).sort()).toEqual(Object.keys(enLeaves).sort())
    expect(Object.keys(deLeaves).length).toBeGreaterThan(100)
  })

  it('uses the same placeholders in both languages', () => {
    for (const key of Object.keys(deLeaves)) {
      expect([key, placeholders(deLeaves[key])]).toEqual([
        key,
        placeholders(enLeaves[key]),
      ])
    }
  })

  it('addresses the reader with du, never Sie', () => {
    for (const text of Object.values(deLeaves)) {
      expect(text).not.toMatch(/\b(Sie|Ihre?[nmrs]?|Ihnen)\b/)
    }
  })

  it('carries the show-once warning verbatim', () => {
    expect(deLeaves['accessKeys.secret.warning']).toBe(
      'Kopiere den Schlüssel jetzt, er wird dir nur einmal angezeigt.',
    )
  })
})

/**
 * Mutation kills for the FIELD_SYNONYMS dictionary rows that had no killing
 * assertions (nightly Stryker survivors on fieldMapping.ts L40-42: the
 * `created` / `updated` / `tags` rows — StringLiteral + ArrayDeclaration
 * mutants). A surviving mutant here means one of these German/English column
 * names silently stops auto-mapping in the import wizard.
 *
 * Each synonym is asserted through BOTH resolution arms of the public API:
 *   - synonym source → canonical target (SYNONYM_TO_CANONICAL lookup)
 *   - synonym source → SIBLING-synonym target (FIELD_SYNONYMS[canonical]
 *     .includes(target) — only reachable synonym-to-synonym)
 * so mutating a string literal or the whole array to `[]` flips at least one
 * assertion away from the exact `semantic`/0.9 shape (a fallback fuzzy match,
 * e.g. created_at⊂created at 0.85, still fails the pinned confidence/type).
 */

import { suggestFieldMappings } from '../fieldMapping'

const semanticPairs: Array<[string, string]> = [
  // created row (L40)
  ['erstellt', 'created'],
  ['created_at', 'created'],
  ['angelegt', 'created'],
  // updated row (L41)
  ['aktualisiert', 'updated'],
  ['updated_at', 'updated'],
  ['geändert', 'updated'],
  // tags row (L42)
  ['schlagwörter', 'tags'],
  ['keywords', 'tags'],
  ['labels', 'tags'],
]

describe('fieldMapping kills · FIELD_SYNONYMS created/updated/tags rows (L40-42)', () => {
  it.each(semanticPairs)(
    'maps synonym source %s → canonical target %s as semantic/0.9',
    (synonym, canonical) => {
      const { mappings } = suggestFieldMappings([synonym], [canonical])
      expect(mappings).toEqual([
        {
          source: synonym,
          target: canonical,
          confidence: 0.9,
          type: 'semantic',
        },
      ])
    }
  )

  const siblingPairs: Array<[string, string]> = [
    ['erstellt', 'created_at'],
    ['created_at', 'angelegt'],
    ['aktualisiert', 'updated_at'],
    ['updated_at', 'geändert'],
    ['schlagwörter', 'keywords'],
    ['keywords', 'labels'],
  ]

  it.each(siblingPairs)(
    'maps synonym source %s → sibling synonym target %s (includes() arm)',
    (source, target) => {
      // Source resolves its canonical via the map; the target is NOT the
      // canonical itself, so matching must go through
      // FIELD_SYNONYMS[canonical].includes(target).
      const { mappings } = suggestFieldMappings([source], [target])
      expect(mappings).toEqual([
        {
          source,
          target,
          confidence: 0.9,
          type: 'semantic',
        },
      ])
    }
  )
})

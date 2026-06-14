/**
 * Branch coverage: fieldMapping.ts content-based matching.
 *
 * The exact / synonym / fuzzy paths are covered by fieldMapping.test.ts, but
 * the Step-4 content-analysis path (findMatchByContent / detectValuePatterns)
 * and a few skip/boost branches were uncovered. These drive the "guess the
 * column from its values" behaviour in the import wizard, so we exercise each
 * value-pattern branch (numeric / boolean / long-text) plus the skip guards.
 */

import { suggestFieldMappings } from '../fieldMapping'

describe('suggestFieldMappings · content-based (Step 4) matching', () => {
  it('matches a numeric column to a "number" target by value pattern', () => {
    const source = ['col_a'] // no name overlap with target
    const target = ['item_number']
    const data = [
      { col_a: 42 },
      { col_a: 7 },
      { col_a: 100 },
    ]
    const out = suggestFieldMappings(source, target, data)
    const m = out.mappings.find((x) => x.source === 'col_a')
    expect(m).toBeTruthy()
    expect(m?.target).toBe('item_number')
    expect(m?.type).toBe('semantic')
    expect(m?.confidence).toBe(0.75)
  })

  it('matches a boolean-valued column to a status/active/enabled target', () => {
    const source = ['xyz']
    const target = ['is_active']
    // Pure string booleans: `true` would count as numeric (Number(true)===1),
    // so use the German/English string forms that fail the numeric check.
    const data = [
      { xyz: 'false' },
      { xyz: 'ja' },
      { xyz: 'nein' },
    ]
    const out = suggestFieldMappings(source, target, data)
    const m = out.mappings.find((x) => x.source === 'xyz')
    expect(m).toBeTruthy()
    expect(m?.target).toBe('is_active')
    expect(m?.confidence).toBe(0.75)
  })

  it('matches a long-text column to a description/text/content target', () => {
    const longText = 'x'.repeat(150)
    const source = ['zzz']
    const target = ['body_text']
    const data = [{ zzz: longText }, { zzz: longText }]
    const out = suggestFieldMappings(source, target, data)
    const m = out.mappings.find((x) => x.source === 'zzz')
    expect(m).toBeTruthy()
    expect(m?.target).toBe('body_text')
    expect(m?.confidence).toBe(0.7)
  })

  it('skips a source whose sample values are all null/undefined', () => {
    const source = ['empties']
    const target = ['some_number']
    const data = [{ empties: null }, { empties: undefined }]
    const out = suggestFieldMappings(source, target, data)
    // No content to match on → stays unmapped.
    expect(out.mappings.find((x) => x.source === 'empties')).toBeUndefined()
    expect(out.unmappedSource).toContain('empties')
  })

  it('does not re-run content matching on a source already mapped exactly', () => {
    // 'question' matches exactly in Step 1; even with content data the Step-4
    // guard (mappedSources.has(source)) skips it, leaving a single mapping.
    const source = ['question']
    const target = ['question', 'description']
    const data = [{ question: 'x'.repeat(200) }]
    const out = suggestFieldMappings(source, target, data)
    const qMappings = out.mappings.filter((x) => x.source === 'question')
    expect(qMappings).toHaveLength(1)
    expect(qMappings[0].type).toBe('exact')
  })

  it('does not match content when no value pattern fits any target', () => {
    // Short non-numeric, non-boolean, non-date strings against an unrelated
    // target → findMatchByContent returns null → field stays unmapped.
    const source = ['mystery']
    const target = ['unrelated_label']
    const data = [{ mystery: 'qq' }, { mystery: 'zz' }]
    const out = suggestFieldMappings(source, target, data)
    expect(out.mappings.find((x) => x.source === 'mystery')).toBeUndefined()
    expect(out.unmappedSource).toContain('mystery')
  })
})

describe('suggestFieldMappings · fuzzy tie-breaking', () => {
  it('keeps the strictly-better fuzzy target when a later candidate scores higher', () => {
    // Two viable fuzzy targets for one source, with the SECOND scoring higher
    // than the first (0.85 contains-match vs 0.8 edit-distance), exercising the
    // "score > bestMatch.score" replacement branch in the Step-3 loop.
    const source = ['colorfield']
    const target = ['colourfeld', 'colorfield_extra']
    const out = suggestFieldMappings(source, target)
    const m = out.mappings.find((x) => x.source === 'colorfield')
    expect(m).toBeTruthy()
    expect(m?.type).toBe('fuzzy')
    // The higher-scoring 'colorfield_extra' (contains match) wins.
    expect(m?.target).toBe('colorfield_extra')
  })
})

describe('suggestFieldMappings · medium quality classification', () => {
  it('classifies a partially-mapped high-confidence set as medium quality', () => {
    // One exact match out of two sources → mappingRate 0.5 but avgConfidence
    // 1.0 → medium branch (avgConfidence > 0.7).
    const out = suggestFieldMappings(
      ['question', 'totally_unrelated_xyz'],
      ['question', 'another_unrelated_abc']
    )
    expect(out.quality).toBe('medium')
  })
})

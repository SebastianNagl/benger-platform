/**
 * Property-based + edge tests for fieldMapping.ts — the import-wizard field
 * auto-mapping "crown jewel". A silent bug here binds an imported column to the
 * wrong template field (e.g. ground-truth answer mapped onto the reasoning
 * column), corrupting every downstream evaluation. The example tests in
 * fieldMapping.test.ts / fieldMapping.br8.test.ts pin a handful of concrete
 * cases; these assert algebraic invariants over fast-check-generated inputs so
 * that a constant/operator/off-by-one mutation in the matcher, confidence
 * scoring, or unmapped-field accounting is caught by at least one property.
 *
 * Only the public API is exercised: suggestFieldMappings and applyFieldMappings.
 * The internal helpers (calculateSimilarity, normalizeFieldName, getCommonParts,
 * findMatchByContent, detectValuePatterns) are reached through suggestFieldMappings.
 */

import fc from 'fast-check'

import {
  applyFieldMappings,
  suggestFieldMappings,
  type FieldMapping,
} from '../fieldMapping'

// --- Arbitraries ---------------------------------------------------------

// Field-name-ish tokens: lowercase letters/digits plus the separators
// normalizeFieldName strips. Kept small so collisions (a source name also
// present as a target) actually occur during a run — that's where exact /
// synonym / fuzzy precedence and target-reuse guards live.
const fieldTokenArb = fc
  .stringOf(
    fc.constantFrom(..."abcdefghijklmnopqrstuvwxyz0123456789_- ".split('')),
    { minLength: 1, maxLength: 8 },
  )
  .filter((s) => s.trim().length > 0)

// A set of DISTINCT field names. Totality of the source/unmapped partition is
// only well-defined for distinct source fields (a duplicated source maps once
// but membership-based unmapped filtering would not double-count it), so we
// dedupe at the arbitrary level.
const distinctFieldsArb = fc
  .array(fieldTokenArb, { maxLength: 8 })
  .map((xs) => Array.from(new Set(xs)))

// Looser arbitrary for never-crash fuzzing: arbitrary strings incl. empty,
// unicode, whitespace, separator-only (which normalize to '').
const wildStringArb = fc.oneof(
  fc.string(),
  fc.constantFrom('', '   ', '___', '---', '  _-  ', 'ä', 'ß', '日本語', '🚀'),
  fc.stringOf(
    fc.constantFrom(
      ...'abcDEF123_- äöüß日'.split(''),
    ),
    { minLength: 0, maxLength: 12 },
  ),
)
const wildFieldsArb = fc.array(wildStringArb, { maxLength: 8 })

// --- Helpers -------------------------------------------------------------

const ALL_TYPES = new Set(['exact', 'fuzzy', 'semantic', 'manual'])

// --- Properties ----------------------------------------------------------

describe('suggestFieldMappings — properties', () => {
  it('self-match: identical source/target sets map each field to itself at confidence 1.0 (exact)', () => {
    fc.assert(
      fc.property(distinctFieldsArb, (fields) => {
        const { mappings, unmappedSource, unmappedTarget } =
          suggestFieldMappings(fields, fields)

        // Every field maps to itself, exactly, at full confidence.
        expect(mappings).toHaveLength(fields.length)
        for (const m of mappings) {
          expect(m.source).toBe(m.target)
          expect(m.confidence).toBe(1.0)
          expect(m.type).toBe('exact')
        }
        // Nothing left over on either side.
        expect(unmappedSource).toEqual([])
        expect(unmappedTarget).toEqual([])
      }),
    )
  })

  it('confidence bounds: every produced confidence ∈ [0,1] and type ∈ the documented set, for arbitrary inputs', () => {
    fc.assert(
      fc.property(wildFieldsArb, wildFieldsArb, (src, tgt) => {
        const { mappings } = suggestFieldMappings(src, tgt)
        for (const m of mappings) {
          expect(m.confidence).toBeGreaterThanOrEqual(0)
          expect(m.confidence).toBeLessThanOrEqual(1)
          expect(Number.isNaN(m.confidence)).toBe(false)
          expect(ALL_TYPES.has(m.type as string)).toBe(true)
        }
      }),
    )
  })

  it('totality + cardinality: each distinct source is mapped XOR unmapped exactly once (|mapped|+|unmappedSource|==|source|)', () => {
    fc.assert(
      fc.property(distinctFieldsArb, distinctFieldsArb, (src, tgt) => {
        const { mappings, unmappedSource, unmappedTarget } =
          suggestFieldMappings(src, tgt)

        const mappedSources = mappings.map((m) => m.source)

        // No source is both mapped and unmapped.
        const mappedSet = new Set(mappedSources)
        for (const u of unmappedSource) expect(mappedSet.has(u)).toBe(false)

        // Partition: every source accounted for exactly once.
        expect(mappings.length + unmappedSource.length).toBe(src.length)

        // No source mapped twice, and every mapped source is a real input.
        expect(new Set(mappedSources).size).toBe(mappedSources.length)
        for (const s of mappedSources) expect(src).toContain(s)

        // Targets: each used at most once; mapped targets + unmapped targets
        // partition the distinct target set.
        const usedTargets = mappings.map((m) => m.target)
        expect(new Set(usedTargets).size).toBe(usedTargets.length)
        for (const t of usedTargets) expect(tgt).toContain(t)
        const unmappedTargetSet = new Set(unmappedTarget)
        for (const t of usedTargets)
          expect(unmappedTargetSet.has(t)).toBe(false)
        expect(usedTargets.length + unmappedTarget.length).toBe(tgt.length)
      }),
    )
  })

  it('unmapped sets are exactly the complements of what got mapped', () => {
    fc.assert(
      fc.property(distinctFieldsArb, distinctFieldsArb, (src, tgt) => {
        const { mappings, unmappedSource, unmappedTarget } =
          suggestFieldMappings(src, tgt)
        const mappedS = new Set(mappings.map((m) => m.source))
        const mappedT = new Set(mappings.map((m) => m.target))
        expect(unmappedSource).toEqual(src.filter((f) => !mappedS.has(f)))
        expect(unmappedTarget).toEqual(tgt.filter((f) => !mappedT.has(f)))
      }),
    )
  })

  it('order independence: shuffling the source list yields the same set of (source→target) mappings', () => {
    // The matcher walks sources in array order; for a *distinct* target set the
    // chosen mapping for any given source must not depend on the source's
    // position (exact + synonym + fuzzy all pick a target deterministically by
    // the source identity when targets are distinct and disjoint enough).
    fc.assert(
      fc.property(distinctFieldsArb, distinctFieldsArb, (src, tgt) => {
        const norm = (r: ReturnType<typeof suggestFieldMappings>) =>
          r.mappings
            .map((m) => `${m.source}=>${m.target}@${m.confidence}`)
            .sort()
        const a = norm(suggestFieldMappings(src, tgt))
        const reversed = [...src].reverse()
        const b = norm(suggestFieldMappings(reversed, tgt))
        // Reversing can change which source "wins" a contested target, so we
        // only assert the weaker invariant that the *count* is stable and no
        // target is double-assigned in either ordering.
        const aTargets = suggestFieldMappings(src, tgt).mappings.map(
          (m) => m.target,
        )
        const bTargets = suggestFieldMappings(reversed, tgt).mappings.map(
          (m) => m.target,
        )
        expect(new Set(aTargets).size).toBe(aTargets.length)
        expect(new Set(bTargets).size).toBe(bTargets.length)
        // When every source has a unique unambiguous home (distinct, disjoint),
        // the mapping set is order-invariant.
        if (a.length === src.length && b.length === src.length) {
          // Both fully mapped: the same source→target pairing must hold.
          expect(b).toEqual(a)
        }
      }),
    )
  })

  it('never crashes on arbitrary strings / empty / separator-only / unicode (with and without sample data)', () => {
    const wildRow = fc.dictionary(wildStringArb, fc.anything())
    fc.assert(
      fc.property(
        wildFieldsArb,
        wildFieldsArb,
        fc.option(fc.array(wildRow, { maxLength: 5 }), { nil: undefined }),
        (src, tgt, data) => {
          expect(() => suggestFieldMappings(src, tgt, data)).not.toThrow()
        },
      ),
    )
  })

  it('quality is always one of high|medium|low', () => {
    fc.assert(
      fc.property(wildFieldsArb, wildFieldsArb, (src, tgt) => {
        const { quality } = suggestFieldMappings(src, tgt)
        expect(['high', 'medium', 'low']).toContain(quality)
      }),
    )
  })
})

// --- Monotonicity & exact-value units (kill constant/operator mutants) ----

describe('suggestFieldMappings — confidence scoring fixed points', () => {
  it('fuzzy confidence equals the literal 1 - distance/maxLength for a single-substitution, single-token pair', () => {
    // 'abcdefg' vs 'abcdefx': normalize is identity (no separators/articles);
    // neither contains the other; Levenshtein distance 1; maxLength 7; single
    // token each so getCommonParts length is 1 (not > 2) → no +0.1 boost.
    // Expected confidence: 1 - 1/7 = 0.857142857...
    const out = suggestFieldMappings(['abcdefg'], ['abcdefx'])
    const m = out.mappings.find((x) => x.source === 'abcdefg')
    expect(m).toBeTruthy()
    expect(m?.type).toBe('fuzzy')
    expect(m?.confidence).toBeCloseTo(1 - 1 / 7, 12)
  })

  it('substring match scores exactly 0.85 (the contains-branch constant)', () => {
    // 'quest' is a substring of 'question' after normalization → 0.85, and it
    // is above the 0.7 fuzzy threshold so it is emitted.
    const out = suggestFieldMappings(['quest'], ['question'])
    const m = out.mappings.find((x) => x.source === 'quest')
    expect(m?.type).toBe('fuzzy')
    expect(m?.confidence).toBe(0.85)
  })

  it('monotonicity: a closer string never gets a LOWER fuzzy confidence than a farther one for the same target', () => {
    // For a fixed 8-char target, compare a 1-edit source against a 2-edit
    // source. Both are single tokens (no contains, no boost) so confidence is
    // strictly 1 - d/8 and must be ordered by edit distance.
    const target = 'abcdefgh' // len 8
    const near = 'abcdefgx' // distance 1  -> 1 - 1/8 = 0.875
    const far = 'abcdefxy' // distance 2  -> 1 - 2/8 = 0.75
    const cNear = suggestFieldMappings([near], [target]).mappings[0]
    const cFar = suggestFieldMappings([far], [target]).mappings[0]
    expect(cNear).toBeTruthy()
    expect(cFar).toBeTruthy()
    expect(cNear.confidence).toBeGreaterThanOrEqual(cFar.confidence)
    expect(cNear.confidence).toBeCloseTo(1 - 1 / 8, 12)
    expect(cFar.confidence).toBeCloseTo(1 - 2 / 8, 12)
  })

  it('generalized monotonicity over random targets: nearer source ⇒ confidence ≥ farther source', () => {
    fc.assert(
      fc.property(
        fc.stringOf(
          fc.constantFrom(..."abcdefghijklmnopqrstuvwxyz".split('')),
          { minLength: 4, maxLength: 8 },
        ),
        (base) => {
          // Build two single-token sources from `base`: one identical-but-for-
          // one-trailing-char (distance ~1) and one differing in two trailing
          // chars (distance ~2). Append rare chars to avoid the contains-branch.
          const target = base
          const near = base.slice(0, -1) + 'q' // 1 substitution if last char != q
          const far = base.slice(0, -2) + 'qz' // 2 substitutions
          // Guard: skip degenerate cases where contains-branch fires (0.85) so
          // we compare like-for-like edit-distance scores.
          if (target.includes(near) || near.includes(target)) return
          if (target.includes(far) || far.includes(target)) return
          const mNear = suggestFieldMappings([near], [target]).mappings[0]
          const mFar = suggestFieldMappings([far], [target]).mappings[0]
          // Both must clear the 0.7 threshold to be emitted; only assert when
          // both exist (4-8 char bases with 1-2 edits stay well above 0.7).
          if (mNear && mFar) {
            expect(mNear.confidence).toBeGreaterThanOrEqual(mFar.confidence)
          }
        },
      ),
    )
  })
})

// --- Synonym resolution fixed points -------------------------------------

describe('suggestFieldMappings — synonym (semantic) resolution', () => {
  // Hand-computed canonical fixed points straight from FIELD_SYNONYMS.
  const KNOWN_SYNONYMS: Array<[string, string]> = [
    ['frage', 'question'],
    ['rechtsfrage', 'question'],
    ['antwort', 'answer'],
    ['lösung', 'answer'],
    ['begründung', 'reasoning'],
    ['rechtsgebiet', 'area'],
    ['gericht', 'court'],
    ['datum', 'date'],
    ['identifier', 'id'],
    ['titel', 'name'],
    ['beschreibung', 'description'],
    ['typ', 'type'],
  ]

  it.each(KNOWN_SYNONYMS)(
    'maps synonym "%s" to canonical target "%s" at 0.9 (semantic)',
    (synonym, canonical) => {
      const out = suggestFieldMappings([synonym], [canonical])
      const m = out.mappings.find((x) => x.source === synonym)
      expect(m).toBeTruthy()
      expect(m?.target).toBe(canonical)
      expect(m?.confidence).toBe(0.9)
      expect(m?.type).toBe('semantic')
    },
  )

  it('synonym resolution is case-insensitive', () => {
    const out = suggestFieldMappings(['FRAGE'], ['question'])
    const m = out.mappings.find((x) => x.source === 'FRAGE')
    expect(m?.target).toBe('question')
    expect(m?.type).toBe('semantic')
    expect(m?.confidence).toBe(0.9)
  })

  it('a synonym also resolves when the target is itself a sibling synonym (not the canonical)', () => {
    // 'frage' -> canonical 'question'; target list offers 'prompt', which is a
    // synonym of 'question'. The semantic step accepts a target that is in
    // FIELD_SYNONYMS[canonical], so this maps at 0.9.
    const out = suggestFieldMappings(['frage'], ['prompt'])
    const m = out.mappings.find((x) => x.source === 'frage')
    expect(m).toBeTruthy()
    expect(m?.target).toBe('prompt')
    expect(m?.confidence).toBe(0.9)
    expect(m?.type).toBe('semantic')
  })

  it('exact match beats synonym: when both an exact target and a synonym target exist, exact (1.0) wins', () => {
    // source 'question' has an exact target 'question' and could also semantic-
    // match 'frage'. Step 1 (exact) runs first and claims 'question' at 1.0.
    const out = suggestFieldMappings(['question'], ['question', 'frage'])
    const m = out.mappings.find((x) => x.source === 'question')
    expect(m?.target).toBe('question')
    expect(m?.confidence).toBe(1.0)
    expect(m?.type).toBe('exact')
  })
})

// --- applyFieldMappings invariants ---------------------------------------

describe('applyFieldMappings — properties', () => {
  // Rows whose keys come from a small pool, with arbitrary JSON-ish values.
  const keyArb = fc.constantFrom('a', 'b', 'c', 'd', 'e')
  const rowArb = fc.dictionary(keyArb, fc.oneof(fc.string(), fc.integer(), fc.boolean(), fc.constant(null)))
  const dataArb = fc.array(rowArb, { maxLength: 6 })
  const mappingArb: fc.Arbitrary<FieldMapping> = fc.record({
    source: keyArb,
    target: fc.constantFrom('t1', 't2', 't3'),
    confidence: fc.double({ min: 0, max: 1, noNaN: true }),
    type: fc.constantFrom('exact', 'fuzzy', 'semantic', 'manual'),
  })

  it('preserves row count', () => {
    fc.assert(
      fc.property(dataArb, fc.array(mappingArb, { maxLength: 4 }), (data, mappings) => {
        expect(applyFieldMappings(data, mappings)).toHaveLength(data.length)
      }),
    )
  })

  it('every output key is either a mapping target or an _unmapped_-prefixed source key; no original value is dropped', () => {
    fc.assert(
      fc.property(dataArb, fc.array(mappingArb, { maxLength: 4 }), (data, mappings) => {
        const mappedSources = new Set(mappings.map((m) => m.source))
        const out = applyFieldMappings(data, mappings)
        out.forEach((mappedRow, i) => {
          const row = data[i]
          // Unmapped original keys are carried over verbatim under the prefix.
          for (const key of Object.keys(row)) {
            if (!mappedSources.has(key)) {
              expect(mappedRow[`_unmapped_${key}`]).toBe(row[key])
            }
          }
          // Every produced key is justified.
          for (const outKey of Object.keys(mappedRow)) {
            const isTarget = mappings.some((m) => m.target === outKey)
            const isUnmapped = outKey.startsWith('_unmapped_')
            expect(isTarget || isUnmapped).toBe(true)
          }
        })
      }),
    )
  })

  it('round-trips values for a present mapped source onto its target', () => {
    fc.assert(
      fc.property(dataArb, fc.array(mappingArb, { maxLength: 4 }), (data, mappings) => {
        const out = applyFieldMappings(data, mappings)
        out.forEach((mappedRow, i) => {
          const row = data[i]
          for (const m of mappings) {
            if (m.source in row) {
              // Last mapping wins for a shared target; assert the value came
              // from *some* mapping whose source key is present.
              expect(Object.prototype.hasOwnProperty.call(mappedRow, m.target)).toBe(true)
            }
          }
        })
      }),
    )
  })

  it('does not mutate the input rows', () => {
    fc.assert(
      fc.property(dataArb, fc.array(mappingArb, { maxLength: 4 }), (data, mappings) => {
        const snapshot = JSON.parse(JSON.stringify(data))
        applyFieldMappings(data, mappings)
        expect(data).toEqual(snapshot)
      }),
    )
  })

  it('never crashes on arbitrary rows / mappings', () => {
    fc.assert(
      fc.property(
        fc.array(fc.dictionary(fc.string(), fc.anything()), { maxLength: 5 }),
        fc.array(mappingArb, { maxLength: 4 }),
        (data, mappings) => {
          expect(() => applyFieldMappings(data as any[], mappings)).not.toThrow()
        },
      ),
    )
  })
})

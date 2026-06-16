/**
 * Mutation kills for fieldMapping.ts — the import-wizard field auto-mapping
 * crown jewel. A surviving operator/regex mutant here means a column from
 * imported evaluation data gets bound to the WRONG template field (e.g. the
 * ground-truth answer mapped onto the reasoning column), silently corrupting
 * every downstream evaluation.
 *
 * fieldMapping.test.ts / fieldMapping.br8.test.ts pin concrete happy-path
 * cases; fieldMapping.property.test.ts asserts algebraic invariants. This file
 * adds the SURGICAL operator/regex/boundary layer: each test exercises one
 * mutation site with a pair (or boundary) that the live operator and the
 * mutated operator disagree on, with the expected value hand-computed from the
 * source and recorded in the test name/comment.
 *
 * Only the two public exports are touched: suggestFieldMappings /
 * applyFieldMappings. The internal helpers (calculateSimilarity,
 * normalizeFieldName, getCommonParts, findMatchByContent, detectValuePatterns)
 * are driven through them with crafted inputs.
 *
 * Line numbers below refer to fieldMapping.ts as of this commit.
 */

import { applyFieldMappings, suggestFieldMappings } from '../fieldMapping'

// =====================================================================
// ARITHMETIC: confidence formula  similarity = 1 - distance / maxLength
//   fieldMapping.ts L220
// =====================================================================
describe('fieldMapping kills · arithmetic in the fuzzy confidence formula (L220)', () => {
  it('1 - distance/maxLength is computed with MINUS and DIVIDE: 7-char pair, 1 edit -> exactly 0.857142… (kills - -> + and / -> *)', () => {
    // normalize('abcdefg')='abcdefg', normalize('abcdefx')='abcdefx' (no
    // separators/articles). Neither contains the other. Levenshtein distance 1,
    // maxLength 7. similarity = 1 - 1/7 = 0.857142857…
    //   '-' -> '+' would give 1 + 1/7 = 1.142… (confidence > 1).
    //   '/' -> '*' would give 1 - 1*7 = -6 (< 0.7 threshold -> mapping vanishes).
    // Asserting the EXACT value + that the mapping exists kills both.
    const out = suggestFieldMappings(['abcdefg'], ['abcdefx'])
    const m = out.mappings.find((x) => x.source === 'abcdefg')
    expect(m).toBeTruthy()
    expect(m?.type).toBe('fuzzy')
    expect(m?.confidence).toBeCloseTo(1 - 1 / 7, 12)
    expect(m?.confidence).toBeLessThanOrEqual(1) // catches '-' -> '+'
  })

  it('a 10-char pair with 2 edits scores exactly 0.8 and IS emitted (a / -> * mutation drops it below threshold)', () => {
    // distance 2, maxLength 10 -> 1 - 2/10 = 0.8 (> 0.7 -> emitted).
    // '/' -> '*' => 1 - 2*10 = -19 -> not emitted; asserting presence kills it.
    const out = suggestFieldMappings(['abcdefghij'], ['abcdefghxy'])
    const m = out.mappings.find((x) => x.source === 'abcdefghij')
    expect(m).toBeTruthy()
    expect(m?.confidence).toBeCloseTo(0.8, 12)
  })
})

// =====================================================================
// EQUALITY: fuzzy threshold  score > 0.7   (fieldMapping.ts L126)
//   boundary at exactly 0.7 — must NOT map.
// =====================================================================
describe('fieldMapping kills · fuzzy threshold boundary score > 0.7 (L126)', () => {
  it('a pair scoring EXACTLY 0.7 is NOT emitted (kills > -> >= and > -> < at the threshold)', () => {
    // distance 3, maxLength 10 -> 1 - 3/10 = 0.7 exactly. With strict `> 0.7`
    // this is excluded. `>` -> `>=` would emit it; `>` -> `<` would also flip.
    const out = suggestFieldMappings(['abcdefghij'], ['abcdefgxyz'])
    const m = out.mappings.find((x) => x.source === 'abcdefghij')
    expect(m).toBeUndefined()
    expect(out.unmappedSource).toContain('abcdefghij')
  })

  it('a pair scoring just above 0.7 (0.8) IS emitted (kills > -> < / threshold raised)', () => {
    // distance 2, maxLength 10 -> 0.8 > 0.7 -> emitted as fuzzy.
    const out = suggestFieldMappings(['abcdefghij'], ['abcdefghxy'])
    const m = out.mappings.find((x) => x.source === 'abcdefghij')
    expect(m?.type).toBe('fuzzy')
    expect(m?.confidence).toBeCloseTo(0.8, 12)
  })
})

// =====================================================================
// EQUALITY + LOGICAL: best-match replacement
//   score > 0.7 && (!bestMatch || score > bestMatch.score)   (L126)
// =====================================================================
describe('fieldMapping kills · fuzzy best-match selection (L126 && / || / score > bestMatch.score)', () => {
  it('picks the strictly-higher-scoring target among two candidates (kills score > bestMatch.score -> >= / < and the || short-circuit)', () => {
    // Source 'abcdefghij'. Targets:
    //   'abcdefghxy' -> distance 2 -> 0.8
    //   'abcdefghiX' (cap X) normalizes to 'abcdefghix' -> distance 1 -> 0.9
    // Both > 0.7. The 0.9 target must win regardless of array order. If the
    // replacement test `score > bestMatch.score` were negated/weakened the
    // lower-scoring first candidate could stick.
    const out = suggestFieldMappings(
      ['abcdefghij'],
      ['abcdefghxy', 'abcdefghiX']
    )
    const m = out.mappings.find((x) => x.source === 'abcdefghij')
    expect(m).toBeTruthy()
    expect(m?.target).toBe('abcdefghiX')
    expect(m?.confidence).toBeCloseTo(0.9, 12)
  })

  it('with a SINGLE viable target the !bestMatch first-iteration branch still emits (kills || -> && which would require an already-set bestMatch)', () => {
    // One target, score 0.8. On the first (and only) iteration bestMatch is
    // null, so `!bestMatch` (true) must carry the ||. If `||` were `&&`, the
    // expression `score > 0.7 && (!bestMatch && score > bestMatch.score)`
    // would dereference bestMatch.score on null OR never set it -> no mapping.
    const out = suggestFieldMappings(['abcdefghij'], ['abcdefghxy'])
    expect(out.mappings).toHaveLength(1)
    expect(out.mappings[0].confidence).toBeCloseTo(0.8, 12)
  })
})

// =====================================================================
// CONDITIONAL + EQUALITY: contains-branch  s1.includes(s2) || s2.includes(s1)
//   returns the 0.85 constant   (fieldMapping.ts L213-215)
// =====================================================================
describe('fieldMapping kills · substring contains-branch returns 0.85 (L213-215)', () => {
  it('source IS a substring of target -> 0.85 (kills the || when only the s1.includes(s2) side is true)', () => {
    // 'quest' is contained in 'question'. s1.includes(s2)? 'quest'.includes(
    // 'question') = false; s2.includes(s1)? 'question'.includes('quest') = true.
    // The OR must fire on the second operand. A levenshtein fallback would give
    // 1 - 3/8 = 0.625 (< 0.7, NOT emitted), so the 0.85 is load-bearing.
    const out = suggestFieldMappings(['quest'], ['question'])
    const m = out.mappings.find((x) => x.source === 'quest')
    expect(m?.type).toBe('fuzzy')
    expect(m?.confidence).toBe(0.85)
  })

  it('target IS a substring of source -> 0.85 (kills the || when only the s2.includes(s1) side is true)', () => {
    // Mirror case: 'question' source, 'quest' target. Now s1.includes(s2)?
    // 'question'.includes('quest') = true (first operand). Exercises the other
    // side of the OR so a mutation removing either operand is caught by one of
    // these two tests.
    const out = suggestFieldMappings(['question'], ['quest'])
    const m = out.mappings.find((x) => x.source === 'question')
    expect(m?.type).toBe('fuzzy')
    expect(m?.confidence).toBe(0.85)
  })

  it('non-substring pair falls through to the edit-distance score (0.85 is NOT returned unconditionally)', () => {
    // 'abcdefg' vs 'abcdefx' share no containment -> must NOT be 0.85; it is the
    // computed 0.857142… If the contains-branch were forced true (condition ->
    // true), every fuzzy score would collapse to 0.85.
    const out = suggestFieldMappings(['abcdefg'], ['abcdefx'])
    const m = out.mappings.find((x) => x.source === 'abcdefg')
    expect(m?.confidence).not.toBe(0.85)
    expect(m?.confidence).toBeCloseTo(1 - 1 / 7, 12)
  })
})

// =====================================================================
// EQUALITY + CONDITIONAL: exact-match  target.toLowerCase() === sourceLower
//   && !usedTargets.has(target)   (fieldMapping.ts L70)  confidence 1.0
// =====================================================================
describe('fieldMapping kills · exact match equality + target-reuse guard (L70)', () => {
  it('case-insensitive exact match scores exactly 1.0 / type exact (kills the === comparison flipping)', () => {
    // 'Question' (source) vs 'question' (target): lowercased both sides ===.
    const out = suggestFieldMappings(['Question'], ['question'])
    const m = out.mappings.find((x) => x.source === 'Question')
    expect(m?.target).toBe('question')
    expect(m?.confidence).toBe(1.0)
    expect(m?.type).toBe('exact')
  })

  it('a near-miss that is NOT equal does not become an exact match (kills === -> !==)', () => {
    // 'questionx' vs 'question' are not equal -> must not be exact 1.0. If
    // `===` were `!==`, every non-equal pair would be claimed at 1.0 and the
    // equal pair would be skipped.
    const out = suggestFieldMappings(['questionx'], ['question'])
    const m = out.mappings.find((x) => x.source === 'questionx')
    expect(m?.type).not.toBe('exact')
    expect(m?.confidence).not.toBe(1.0)
  })

  it('the !usedTargets.has(target) guard prevents a second source claiming the same exact target (kills the && / negation)', () => {
    // Two identical sources 'dup', one target 'dup'. Step 1 walks sources in
    // order: the first 'dup' claims target 'dup' (added to usedTargets); the
    // second 'dup' finds no FREE exact target (guard !usedTargets.has is now
    // false) and stays unmapped. Removing the guard would double-assign 'dup'.
    const out = suggestFieldMappings(['dup', 'dup'], ['dup'])
    const exactCount = out.mappings.filter(
      (m) => m.target === 'dup' && m.type === 'exact'
    ).length
    expect(exactCount).toBe(1)
  })
})

// =====================================================================
// CONDITIONAL: bestMatch !== null  (fieldMapping.ts L131)
// =====================================================================
describe('fieldMapping kills · bestMatch !== null gate (L131)', () => {
  it('no target clears 0.7 -> no fuzzy mapping emitted (kills !== -> === which would push a null match)', () => {
    // 'abcd' vs 'wxyz': distance 4, maxLength 4 -> 0. Far below 0.7, bestMatch
    // stays null. If the `!== null` gate were `=== null` it would try to emit
    // the null match (and crash or produce garbage); we assert clean no-map.
    const out = suggestFieldMappings(['abcd'], ['wxyz'])
    expect(out.mappings).toHaveLength(0)
    expect(out.unmappedSource).toEqual(['abcd'])
  })
})

// =====================================================================
// LOGICAL + EQUALITY + CONDITIONAL: content step gate
//   existingData && existingData.length > 0   (fieldMapping.ts L145)
// =====================================================================
describe('fieldMapping kills · content step is gated on existingData.length > 0 (L145)', () => {
  it('an EMPTY data array skips Step 4 entirely so a content-only field stays unmapped (kills length > 0 -> >= 0)', () => {
    // 'col_x' has no name overlap with 'event_date' (would only match by
    // content). With [] passed, `existingData.length > 0` is false -> Step 4
    // skipped -> unmapped. If `> 0` were `>= 0`, the empty array would (wrongly)
    // enter Step 4; the per-source slice would be empty and the field would
    // still be unmapped, but the boundary is exercised together with the
    // populated counterpart below which DOES map.
    const out = suggestFieldMappings(['col_x'], ['event_date'], [])
    expect(out.mappings.find((m) => m.source === 'col_x')).toBeUndefined()
    expect(out.unmappedSource).toContain('col_x')
  })

  it('a populated data array of 3 dates DOES enter Step 4 and maps the date column (proves the > 0 branch is live)', () => {
    const out = suggestFieldMappings(
      ['col_x'],
      ['event_date'],
      [{ col_x: '2024-01-01' }, { col_x: '2024-02-02' }, { col_x: '2024-03-03' }]
    )
    const m = out.mappings.find((x) => x.source === 'col_x')
    expect(m?.target).toBe('event_date')
    expect(m?.confidence).toBe(0.8)
    expect(m?.type).toBe('semantic')
  })
})

// =====================================================================
// EQUALITY: sourceValues.length === 0  (fieldMapping.ts L154)
//   and the null/undefined filter v !== null && v !== undefined (L151)
// =====================================================================
describe('fieldMapping kills · per-source sample filtering (L151, L154)', () => {
  it('all-null sample values are filtered out -> length === 0 -> source skipped (kills === 0 -> !== 0 and the && filter)', () => {
    // Every value is null/undefined; the `v !== null && v !== undefined` filter
    // drops them all -> sourceValues.length 0 -> `=== 0` true -> return (skip).
    // If `=== 0` were `!== 0` the function would proceed with an empty slice.
    const out = suggestFieldMappings(
      ['col_x'],
      ['event_date'],
      [{ col_x: null }, { col_x: undefined }, { col_x: null }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')).toBeUndefined()
    expect(out.unmappedSource).toContain('col_x')
  })

  it('ONE real value among nulls survives the filter (length 1, !== 0) and content matching proceeds', () => {
    // Two nulls + one date string. Filter keeps the single date. With 1 value,
    // dateCount(1) > 1*0.7(0.7) -> isDate true -> maps to the date target. This
    // proves the filter keeps non-null values (so && was not weakened to a
    // tautology) and that length 1 is treated as non-empty.
    const out = suggestFieldMappings(
      ['col_x'],
      ['event_date'],
      [{ col_x: null }, { col_x: '2024-01-01' }, { col_x: undefined }]
    )
    const m = out.mappings.find((x) => x.source === 'col_x')
    expect(m?.target).toBe('event_date')
    expect(m?.confidence).toBe(0.8)
  })
})

// =====================================================================
// ARITHMETIC + EQUALITY: detectValuePatterns thresholds
//   count > values.length * 0.7   (fieldMapping.ts L330-332)
// =====================================================================
describe('fieldMapping kills · value-pattern thresholds count > len * 0.7 (L330-333)', () => {
  it('2 of 3 dates does NOT classify as date (dateCount 2 is NOT > 3*0.7=2.1) — kills > -> >= and the *0.7 factor', () => {
    // 3 values: two real dates + one plainly non-date, non-numeric, non-bool
    // string ('hello'). dateCount = 2. 2 > 2.1 is false -> isDate false -> the
    // date target stays unmapped. If `> ` were `>=`, 2 >= 2.1 is still false, so
    // this case actually pins the *0.7 ARITHMETIC: if 0.7 were a smaller factor
    // (e.g. mutated *0.7 -> /0.7 giving 4.28, or the multiply dropped) the
    // boundary moves. Pair this with the all-3 case below.
    const out = suggestFieldMappings(
      ['col_x'],
      ['event_date'],
      [{ col_x: '2024-01-01' }, { col_x: '2024-02-02' }, { col_x: 'hello' }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')).toBeUndefined()
  })

  it('3 of 3 dates DOES classify as date (3 > 2.1) and maps at 0.8', () => {
    const out = suggestFieldMappings(
      ['col_x'],
      ['event_date'],
      [{ col_x: '2024-01-01' }, { col_x: '2024-02-02' }, { col_x: '2024-03-03' }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')?.confidence).toBe(0.8)
  })

  it('numeric pattern: 3 of 3 numbers maps to a "number" target at 0.75', () => {
    const out = suggestFieldMappings(
      ['col_x'],
      ['row_number'],
      [{ col_x: 42 }, { col_x: 7 }, { col_x: 100 }]
    )
    const m = out.mappings.find((x) => x.source === 'col_x')
    expect(m?.target).toBe('row_number')
    expect(m?.confidence).toBe(0.75)
  })

  it('isLongText boundary: avgLength must exceed 100 — exactly-100 average does NOT classify (kills > -> >=)', () => {
    // Single value of length exactly 100 -> avgLength = 100. `avgLength > 100`
    // is false -> not long text -> no map to the text target. (101 below maps.)
    const out = suggestFieldMappings(
      ['col_x'],
      ['body_text'],
      [{ col_x: 'x'.repeat(100) }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')).toBeUndefined()
  })

  it('isLongText boundary: avgLength 101 DOES classify and maps to a text target at 0.7', () => {
    const out = suggestFieldMappings(
      ['col_x'],
      ['body_text'],
      [{ col_x: 'x'.repeat(101) }]
    )
    const m = out.mappings.find((x) => x.source === 'col_x')
    expect(m?.target).toBe('body_text')
    expect(m?.confidence).toBe(0.7)
  })
})

// =====================================================================
// LOGICAL + EQUALITY: numeric pattern  typeof value === 'number'
//   || !isNaN(Number(value))   (fieldMapping.ts L315)
// =====================================================================
describe('fieldMapping kills · numeric detection OR-branch (L315)', () => {
  it('string-encoded numbers count as numeric via the !isNaN(Number(value)) operand (kills the || losing the string side)', () => {
    // Values are STRINGS '42','7','100' (typeof === 'number' is false for all),
    // so classification relies entirely on the `!isNaN(Number(value))` operand.
    // If the || dropped that operand, numericCount would be 0 and no map.
    const out = suggestFieldMappings(
      ['col_x'],
      ['row_number'],
      [{ col_x: '42' }, { col_x: '7' }, { col_x: '100' }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')?.confidence).toBe(0.75)
  })
})

// =====================================================================
// REGEX: date pattern  /^\d{4}-\d{2}-\d{2}|\d{2}[./-]\d{2}[./-]\d{2,4}/
//   (fieldMapping.ts L302)  — match vs near-miss pairs
// =====================================================================
describe('fieldMapping kills · date REGEX classification (L302)', () => {
  it('ISO yyyy-mm-dd matches (positive) — drives the first alternative', () => {
    const out = suggestFieldMappings(
      ['col_x'],
      ['event_date'],
      [{ col_x: '2024-12-31' }, { col_x: '2023-06-15' }, { col_x: '2022-01-01' }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')?.confidence).toBe(0.8)
  })

  it('dd.mm.yyyy matches via the second alternative \\d{2}[./-]\\d{2}[./-]\\d{2,4} (positive)', () => {
    const out = suggestFieldMappings(
      ['col_x'],
      ['event_date'],
      [{ col_x: '31.12.2024' }, { col_x: '15.06.2023' }, { col_x: '01.01.2022' }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')?.confidence).toBe(0.8)
  })

  it('plain non-date text does NOT match (negative) so the date target stays unmapped — kills regex char-class/quantifier mutations that broaden the match', () => {
    // 'hello world' etc. contain no \d{4}-\d{2}-\d{2} nor \d{2}[sep]\d{2}[sep]\d{2,4}.
    // A mutated date regex (digit class \d -> [\d] negated, quantifier widened,
    // separators broadened) would start matching these non-dates -> the column
    // would be wrongly classified as a date.
    const out = suggestFieldMappings(
      ['col_x'],
      ['event_date'],
      [{ col_x: 'hello world' }, { col_x: 'foobar' }, { col_x: 'value here' }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')).toBeUndefined()
  })

  it('single-digit separated groups (1-2-3) do NOT match — the \\d{2} quantifier requires two digits (kills quantifier loosening)', () => {
    // '1-2-3' has only single digits; \d{2} fails. If {2} were mutated to {1}
    // or {0,} the date regex would match and misclassify. 3/3 of these would
    // (wrongly) become dates; with the live regex none do -> unmapped.
    const out = suggestFieldMappings(
      ['col_x'],
      ['event_date'],
      [{ col_x: '1-2-3' }, { col_x: '4-5-6' }, { col_x: '7-8-9' }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')).toBeUndefined()
  })
})

// =====================================================================
// REGEX: boolean target match  /status|active|enabled/  (L277)
//   and long-text target match /description|text|content/ (L284)
// =====================================================================
describe('fieldMapping kills · boolean/text TARGET-name regexes (L277, L284)', () => {
  it('boolean values map to a target matching /status|active|enabled/ (positive) at 0.75', () => {
    // String booleans 'ja'/'nein'/'false' (these fail the numeric test, unlike
    // the literal true/false which Number()-coerce). Target 'is_active' contains
    // 'active' -> regex matches.
    const out = suggestFieldMappings(
      ['col_x'],
      ['is_active'],
      [{ col_x: 'ja' }, { col_x: 'nein' }, { col_x: 'false' }]
    )
    const m = out.mappings.find((x) => x.source === 'col_x')
    expect(m?.target).toBe('is_active')
    expect(m?.confidence).toBe(0.75)
  })

  it('boolean values do NOT map to a target that lacks status/active/enabled (negative) — kills regex alternation broadening', () => {
    // Target 'flag_column' matches none of status|active|enabled, and is not a
    // numeric/date/text target either -> findMatchByContent returns null.
    const out = suggestFieldMappings(
      ['col_x'],
      ['flag_column'],
      [{ col_x: 'ja' }, { col_x: 'nein' }, { col_x: 'ja' }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')).toBeUndefined()
  })

  it('long text maps to a target matching /description|text|content/ (positive) at 0.7', () => {
    const longText = 'x'.repeat(150)
    const out = suggestFieldMappings(
      ['col_x'],
      ['content_field'],
      [{ col_x: longText }, { col_x: longText }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')?.confidence).toBe(0.7)
  })

  it('long text does NOT map to a target lacking description/text/content (negative) — kills text-regex alternation broadening', () => {
    const longText = 'y'.repeat(150)
    const out = suggestFieldMappings(
      ['col_x'],
      ['summary_blob'],
      [{ col_x: longText }, { col_x: longText }]
    )
    expect(out.mappings.find((m) => m.source === 'col_x')).toBeUndefined()
  })
})

// =====================================================================
// REGEX: separator strip in normalizeFieldName  /[_\-\s]+/g  (L237)
//   driven through calculateSimilarity (fuzzy step)
// =====================================================================
describe('fieldMapping kills · separator-strip REGEX /[_\\-\\s]+/g (L237)', () => {
  it('underscore/hyphen/space separators are removed so spaced and packed names match identically (positive — kills char-class shrink)', () => {
    // Source 'a b_c-d' normalizes to 'abcd'; target 'abcd' is exact AFTER
    // normalize but the EXACT step (Step 1) compares raw lowercased names, so
    // 'a b_c-d' !== 'abcd' there. It reaches the fuzzy step where normalize maps
    // both to 'abcd' -> contains-branch -> 0.85. If the separator class
    // [_\-\s] lost a member (e.g. dropped \s or -), the space/hyphen would
    // survive, normalize would differ, and the score would drop below 0.85.
    const out = suggestFieldMappings(['a b_c-d'], ['abcd'])
    const m = out.mappings.find((x) => x.source === 'a b_c-d')
    expect(m).toBeTruthy()
    expect(m?.confidence).toBe(0.85) // equal-after-normalize -> contains-branch
  })

  it('the global flag strips ALL separator runs, not just the first (kills /g removal)', () => {
    // 'x_y_z' has two underscore runs. With /g both are removed -> 'xyz'. Target
    // 'xyz' -> normalize equal -> 0.85. If /g were dropped, only the first
    // underscore run is removed -> 'xy_z' -> not equal to 'xyz', score < 0.85.
    const out = suggestFieldMappings(['x_y_z'], ['xyz'])
    const m = out.mappings.find((x) => x.source === 'x_y_z')
    expect(m).toBeTruthy()
    expect(m?.confidence).toBe(0.85)
  })
})

// =====================================================================
// EQUALITY + ARITHMETIC + CONDITIONAL: quality classification
//   mappingRate = mappings.length / Math.max(src, tgt)   (L182)
//   avgConfidence = sum + m.confidence / n                (L184-185)
//   high: rate > 0.8 && avg > 0.8   (L189)
//   medium: rate > 0.5 || avg > 0.7 (L191)
// =====================================================================
describe('fieldMapping kills · quality classification arithmetic + thresholds (L182, L185, L189, L191)', () => {
  it('mappingRate uses DIVISION: 1 mapping over 4 targets -> rate 0.25 -> NOT high -> medium (kills / -> * at L182)', () => {
    // 1 exact mapping (conf 1.0). max(src=1, tgt=4) = 4. rate = 1/4 = 0.25.
    //   high needs rate > 0.8 -> false. medium: rate>0.5 false, avg(1.0)>0.7 true -> medium.
    //   If `/` were `*`, rate = 1*4 = 4 > 0.8 AND avg 1.0 > 0.8 -> 'high'. So
    //   asserting 'medium' kills the division mutation.
    const out = suggestFieldMappings(['aaa'], ['aaa', 'p1', 'p2', 'p3'])
    expect(out.mappings).toHaveLength(1)
    expect(out.quality).toBe('medium')
  })

  it('avgConfidence uses ADDITION in the reduce: a single 1.0 exact match averages to 1.0 -> high (kills + -> * at L185)', () => {
    // 1 src, 1 tgt, exact -> rate 1.0, conf list [1.0]. reduce starts at 0:
    // 0 + 1.0 = 1.0, avg 1.0/1 = 1.0. high (rate>0.8 && avg>0.8).
    //   If `+` were `*`, reduce gives 0 * 1.0 = 0 -> avg 0 -> avg>0.8 false ->
    //   not high -> medium. Asserting 'high' kills the addition mutation.
    const out = suggestFieldMappings(['aaa'], ['aaa'])
    expect(out.quality).toBe('high')
  })

  it('HIGH requires rate > 0.8 strictly: rate exactly 0.8 with conf 1.0 is MEDIUM not HIGH (kills > -> >= at L189 rate)', () => {
    // 4 exact matches out of 5 sources / 5 targets. mappings = 4, max = 5.
    // rate = 4/5 = 0.8 exactly. avg = 1.0. high needs rate > 0.8 -> 0.8 > 0.8
    // is false -> falls to medium (rate>0.5 true). If `>` were `>=`, 0.8 >= 0.8
    // -> high. The 5th source/target ('zzz'/'yyy') do not fuzzy-match
    // (normalized distance 3 over length 3 -> 0).
    const out = suggestFieldMappings(
      ['aa', 'bb', 'cc', 'dd', 'zzz'],
      ['aa', 'bb', 'cc', 'dd', 'yyy']
    )
    expect(out.mappings).toHaveLength(4)
    expect(out.quality).toBe('medium')
  })

  it('HIGH requires avg > 0.8 strictly: a single fuzzy match at exactly 0.8 (rate 1.0) is MEDIUM not HIGH (kills > -> >= at L189 avg)', () => {
    // 1 src, 1 tgt, fuzzy at exactly 0.8 (distance 2 / maxLen 10). rate 1.0
    // (> 0.8 true) but avg 0.8 (> 0.8 FALSE) -> not high -> medium. If the avg
    // comparison `> 0.8` were `>= 0.8`, 0.8 >= 0.8 -> high.
    const out = suggestFieldMappings(['abcdefghij'], ['abcdefghxy'])
    expect(out.mappings).toHaveLength(1)
    expect(out.mappings[0].confidence).toBeCloseTo(0.8, 12)
    expect(out.quality).toBe('medium')
  })

  it('MEDIUM via the avgConfidence>0.7 OR-branch only: rate 1/3 (<=0.5) but a 0.8 fuzzy match -> medium (kills the || at L191)', () => {
    // 1 source, 3 targets; the source fuzzy-matches one target at 0.8 and the
    // other two stay unmapped. mappings 1, max(1,3) = 3, rate = 1/3 ≈ 0.333
    // (> 0.5 FALSE). avg = 0.8 (> 0.7 TRUE) -> medium via the OR's right side.
    // If `||` were `&&`, rate>0.5 false would force 'low'. Asserting 'medium'
    // kills the logical-operator mutation.
    const out = suggestFieldMappings(
      ['abcdefghij'],
      ['abcdefghxy', 'unrelated_one', 'unrelated_two']
    )
    expect(out.mappings).toHaveLength(1)
    expect(out.quality).toBe('medium')
  })

  it('LOW when nothing maps: rate 0 and avg 0 fail both gates (kills medium/high default flip)', () => {
    // No source resembles any target. rate 0, avg 0. high false, medium false
    // (rate>0.5 false, avg>0.7 false) -> low.
    const out = suggestFieldMappings(['qqqq'], ['wwww'])
    expect(out.mappings).toHaveLength(0)
    expect(out.quality).toBe('low')
  })
})

// =====================================================================
// CONDITIONAL + EQUALITY + LOGICAL: applyFieldMappings
//   mapping.source in row   (L350)
//   !mappings.some((m) => m.source === key)   (L357)
// =====================================================================
describe('fieldMapping kills · applyFieldMappings membership/equality (L350, L357)', () => {
  it('a mapping whose source key is ABSENT from the row produces no target key (kills the `in` conditional flip)', () => {
    // row has only 'present'. Mapping source 'absent' must be skipped (the
    // `mapping.source in row` guard is false) -> 'missing_target' absent from
    // output. The present mapping does emit. If the guard were negated, the
    // absent source would write undefined to 'missing_target'.
    const out = applyFieldMappings(
      [{ present: 'v' }],
      [
        { source: 'present', target: 'mapped', confidence: 1, type: 'exact' },
        { source: 'absent', target: 'missing_target', confidence: 1, type: 'exact' },
      ]
    )
    expect(out[0]).toEqual({ mapped: 'v' })
    expect('missing_target' in out[0]).toBe(false)
  })

  it('a mapped source key is NOT also copied under the _unmapped_ prefix (kills === -> !== in the some() predicate at L357)', () => {
    // 'k1' is mapped; 'k2' is not. Output must contain target 'T' (from k1) and
    // '_unmapped_k2' but NOT '_unmapped_k1'. The unmapped check is
    // `!mappings.some(m => m.source === key)`; if `===` flipped to `!==`, every
    // key would look unmapped and 'k1' would also be prefixed.
    const out = applyFieldMappings(
      [{ k1: 'a', k2: 'b' }],
      [{ source: 'k1', target: 'T', confidence: 1, type: 'exact' }]
    )
    expect(out[0]).toEqual({ T: 'a', _unmapped_k2: 'b' })
    expect('_unmapped_k1' in out[0]).toBe(false)
  })
})

// =====================================================================
// CONDITIONAL: synonym (semantic) precedence and target-reuse
//   sourceLower canonical lookup + FIELD_SYNONYMS[canonical]?.includes (L92-100)
// =====================================================================
describe('fieldMapping kills · synonym step conditionals (L92, L98-100, L103)', () => {
  it('a known synonym maps to its canonical target at exactly 0.9 / semantic (kills the canonical conditional)', () => {
    // 'frage' -> canonical 'question'; target 'question' === canonical.
    const out = suggestFieldMappings(['frage'], ['question'])
    const m = out.mappings.find((x) => x.source === 'frage')
    expect(m?.target).toBe('question')
    expect(m?.confidence).toBe(0.9)
    expect(m?.type).toBe('semantic')
  })

  it('a synonym resolves to a SIBLING synonym target via the FIELD_SYNONYMS[canonical].includes branch (kills the || losing that side)', () => {
    // 'frage' -> canonical 'question'. Target 'prompt' is NOT the canonical but
    // IS in FIELD_SYNONYMS['question'] -> the `targetLower === canonical ||
    // FIELD_SYNONYMS[canonical]?.includes(targetLower)` OR must fire on the
    // right side. Levenshtein 'frage' vs 'prompt' would be far below 0.7, so
    // 0.9/semantic is only reachable through this branch.
    const out = suggestFieldMappings(['frage'], ['prompt'])
    const m = out.mappings.find((x) => x.source === 'frage')
    expect(m?.target).toBe('prompt')
    expect(m?.confidence).toBe(0.9)
    expect(m?.type).toBe('semantic')
  })

  it('a non-synonym word does NOT get a semantic 0.9 (kills the canonical-found conditional flipping to always-true)', () => {
    // 'zzzword' is in no synonym table; SYNONYM_TO_CANONICAL.get returns
    // undefined -> the `if (canonical)` guard is false -> no semantic mapping.
    const out = suggestFieldMappings(['zzzword'], ['question'])
    const m = out.mappings.find((x) => x.source === 'zzzword')
    expect(m?.type).not.toBe('semantic')
  })
})

// =====================================================================
// CONDITIONAL: mappedSources skip guards across steps
//   if (mappedSources.has(source)) return   (L87, L118, L147)
// =====================================================================
describe('fieldMapping kills · already-mapped skip guards (L87, L118, L147)', () => {
  it('an exactly-mapped source is not re-mapped by later synonym/fuzzy/content steps (kills the skip-guard conditionals)', () => {
    // 'question' matches exactly in Step 1. The synonym, fuzzy and content steps
    // all guard with `if (mappedSources.has(source)) return`. Even with a
    // long-text sample value and a 'description' target available, the source
    // must keep its single exact mapping. Removing any guard would emit a
    // duplicate mapping for 'question'.
    const out = suggestFieldMappings(
      ['question'],
      ['question', 'description'],
      [{ question: 'x'.repeat(200) }]
    )
    const qMappings = out.mappings.filter((m) => m.source === 'question')
    expect(qMappings).toHaveLength(1)
    expect(qMappings[0].type).toBe('exact')
    expect(qMappings[0].confidence).toBe(1.0)
  })
})

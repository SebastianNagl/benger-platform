/**
 * Surgical mutant-killing layer for annotationDiff.ts.
 *
 * The existing example/property tests pin status *branches* and algebraic
 * invariants. This file targets the LOGIC operator mutants that survived the
 * Stryker baseline (ConditionalExpression / EqualityOperator / ArithmeticOperator
 * / LogicalOperator) by constructing inputs at the exact BOUNDARY where each
 * mutated operator diverges from the original, and asserting the precise output.
 *
 * Every test name/comment cites the source line and the mutant it kills, with
 * the expected value hand-computed from the source.
 */

import {
  computeAnnotationDiff,
  computeHighlightDiff,
  computeLineDiff,
  computeCommentDiff,
} from '../annotationDiff'
import { AnnotationResult } from '@/types/labelStudio'

const ar = (
  from_name: string,
  value: any,
  to_name = 'tn',
  type = 'ty',
): AnnotationResult => ({ from_name, to_name, type, value })

// =====================================================================
// computeAnnotationDiff — L56-92
// =====================================================================

describe('computeAnnotationDiff: L56 `if (orig && rev)` LogicalOperator/Conditional', () => {
  // L56 `orig && rev`. Boundary: a key present in BOTH (orig truthy, rev truthy)
  // must take the modified/unchanged branch. With `orig && rev` -> `orig || rev`
  // a key present only in orig would also wrongly enter this branch and emit a
  // bogus `reviewValue` from `rev` (undefined) instead of status 'removed'.
  it('key in BOTH -> modified branch (true side of &&)', () => {
    const res = computeAnnotationDiff([ar('a', 'x')], [ar('a', 'y')])
    expect(res.fields).toHaveLength(1)
    expect(res.fields[0].status).toBe('modified')
    expect(res.fields[0].originalValue).toBe('x')
    expect(res.fields[0].reviewValue).toBe('y')
  })

  // L56 false side reached via L66 (orig only). If `&&`->`||` the branch at L56
  // captures orig-only keys; the real code must instead emit status 'removed'
  // with reviewValue === null (L73). Asserting reviewValue null distinguishes:
  // the L56 branch sets reviewValue to rev.value, never null.
  it('key only in ORIGINAL -> removed, reviewValue null (false side of L56 &&)', () => {
    const res = computeAnnotationDiff([ar('a', 'x')], [])
    expect(res.fields[0].status).toBe('removed')
    expect(res.fields[0].reviewValue).toBeNull()
    expect(res.fields[0].originalValue).toBe('x')
  })

  // L75 `!orig && rev` — added branch. originalValue must be null (L81).
  it('key only in REVIEW -> added, originalValue null (L75 `!orig && rev`)', () => {
    const res = computeAnnotationDiff([], [ar('a', 'y')])
    expect(res.fields[0].status).toBe('added')
    expect(res.fields[0].originalValue).toBeNull()
    expect(res.fields[0].reviewValue).toBe('y')
  })
})

describe('computeAnnotationDiff: L57/L62 deepEqual + `isEqual ? unchanged : modified` ternary', () => {
  // L62 ternary, true side: equal values -> 'unchanged'. If ternary forced to
  // false -> 'modified'. Distinguish unchanged vs modified directly.
  it('equal values -> unchanged (L62 ternary true side)', () => {
    const res = computeAnnotationDiff([ar('a', { t: [1] })], [ar('a', { t: [1] })])
    expect(res.fields[0].status).toBe('unchanged')
    expect(res.summary.unchanged).toBe(1)
    expect(res.summary.modified).toBe(0)
  })

  // L62 ternary, false side: differing values -> 'modified'.
  it('differing values -> modified (L62 ternary false side)', () => {
    const res = computeAnnotationDiff([ar('a', { t: [1] })], [ar('a', { t: [2] })])
    expect(res.fields[0].status).toBe('modified')
    expect(res.summary.modified).toBe(1)
    expect(res.summary.unchanged).toBe(0)
  })

  // L57/L230 deepEqual uses JSON.stringify `===`. Key-order-sensitive: two
  // objects with the same keys in different insertion order stringify
  // differently, so they are 'modified'. A mutated `===`->`!==` in deepEqual
  // would invert: equal-string -> false (modified) and these -> unchanged.
  // Pairs structurally-different-but-shallow-equal-keys to anchor the boundary.
  it('object key order changes JSON string -> modified (deepEqual `===` at L230)', () => {
    const res = computeAnnotationDiff(
      [ar('a', { x: 1, y: 2 })],
      [ar('a', { y: 2, x: 1 })],
    )
    // JSON.stringify({x,y}) !== JSON.stringify({y,x}) -> not equal -> modified.
    expect(res.fields[0].status).toBe('modified')
  })
})

describe('computeAnnotationDiff: L60-61 `||` fallback for to_name/type', () => {
  // L60 `orig.to_name || rev.to_name`: orig.to_name empty (falsy) -> falls back
  // to rev.to_name. With `||`->`&&` the result would be orig.to_name ('') .
  it('empty orig.to_name falls back to rev.to_name (L60 `||` right side)', () => {
    const orig = ar('a', 'v', '' /* empty to_name */, '' /* empty type */)
    const rev = ar('a', 'v', 'REV_TN', 'REV_TY')
    const res = computeAnnotationDiff([orig], [rev])
    expect(res.fields[0].to_name).toBe('REV_TN') // L60: '' || 'REV_TN'
    expect(res.fields[0].type).toBe('REV_TY') // L61: '' || 'REV_TY'
  })

  // L60 `||` left (short-circuit) side: orig.to_name truthy -> keep orig's,
  // even when rev differs. `||`->`&&` would yield rev's value here.
  it('truthy orig.to_name kept over rev (L60 `||` short-circuit left)', () => {
    const orig = ar('a', 'v', 'ORIG_TN', 'ORIG_TY')
    const rev = ar('a', 'v', 'REV_TN', 'REV_TY')
    const res = computeAnnotationDiff([orig], [rev])
    expect(res.fields[0].to_name).toBe('ORIG_TN') // 'ORIG_TN' || 'REV_TN'
    expect(res.fields[0].type).toBe('ORIG_TY')
  })
})

describe('computeAnnotationDiff: L89-92 summary filter `=== status` EqualityOperators', () => {
  // Build a set with exactly one of each status so every count is 1 and the
  // four `f.status === '<literal>'` equalities (L89-92) each must match exactly
  // its own bucket. A swapped/`!==` predicate yields a wrong, non-1 count.
  it('one-of-each set: added/removed/modified/unchanged all === 1, total === 4', () => {
    const original = [
      ar('keep', 'same'), // unchanged
      ar('mod', 'old'), // modified
      ar('gone', 'x'), // removed
    ]
    const review = [
      ar('keep', 'same'), // unchanged
      ar('mod', 'new'), // modified
      ar('new', 'y'), // added
    ]
    const res = computeAnnotationDiff(original, review)
    expect(res.summary.unchanged).toBe(1) // L92 `=== 'unchanged'`
    expect(res.summary.modified).toBe(1) // L91 `=== 'modified'`
    expect(res.summary.removed).toBe(1) // L90 `=== 'removed'`
    expect(res.summary.added).toBe(1) // L89 `=== 'added'`
    expect(res.summary.total).toBe(4) // L88 fields.length
  })

  // Skewed multiplicities so each bucket has a DISTINCT count (1/2/3/0). This
  // kills any cross-wired equality (e.g. removed filter matching 'added'): the
  // numbers only line up when each predicate matches its own literal.
  it('distinct bucket sizes 3 added / 2 removed / 1 modified / 0 unchanged', () => {
    const original = [
      ar('r1', 'a'),
      ar('r2', 'b'), // 2 removed
      ar('m1', 'old'), // 1 modified (also in review w/ diff value)
    ]
    const review = [
      ar('m1', 'new'),
      ar('a1', '1'),
      ar('a2', '2'),
      ar('a3', '3'), // 3 added
    ]
    const res = computeAnnotationDiff(original, review)
    expect(res.summary.added).toBe(3)
    expect(res.summary.removed).toBe(2)
    expect(res.summary.modified).toBe(1)
    expect(res.summary.unchanged).toBe(0)
    expect(res.summary.total).toBe(6)
  })
})

// =====================================================================
// computeHighlightDiff — L113-136
// =====================================================================

describe('computeHighlightDiff: L122/L131 has() Conditionals + L136 sort `-`', () => {
  // L122 `if (revSet.has(key))` true side: a span present in both keyed sets
  // (same start:end:labels) -> 'common'/'both'. Note id is NOT in the key, so a
  // different id with identical start/end/labels still matches.
  it('matching start:end:labels -> common, even with different id (L122 true)', () => {
    const orig = [{ id: 'o', start: 2, end: 7, text: 't', labels: ['A'] }]
    const rev = [{ id: 'DIFFERENT', start: 2, end: 7, text: 't', labels: ['A'] }]
    const res = computeHighlightDiff(orig, rev)
    expect(res.filter((r) => r.status === 'common')).toHaveLength(1)
    expect(res.filter((r) => r.status === 'added')).toHaveLength(0) // L131 false
    expect(res.filter((r) => r.status === 'removed')).toHaveLength(0)
  })

  // L122 false side + L131 `!origSet.has` true side: a label MISMATCH at the
  // same offsets makes the keys differ, so orig -> 'removed' and rev -> 'added'.
  // This pins the equality inside the Set key (label difference must matter).
  it('same offsets, different labels -> 1 removed + 1 added (L122 false, L131 true)', () => {
    const orig = [{ id: 'o', start: 0, end: 5, text: 't', labels: ['A'] }]
    const rev = [{ id: 'r', start: 0, end: 5, text: 't', labels: ['B'] }]
    const res = computeHighlightDiff(orig, rev)
    expect(res.filter((r) => r.status === 'removed')).toHaveLength(1)
    expect(res.filter((r) => r.status === 'added')).toHaveLength(1)
    expect(res.filter((r) => r.status === 'common')).toHaveLength(0)
  })

  // L131 `!origSet.has(key)` false side: review span IS in origSet -> NOT added
  // (it was already emitted as 'common' in the first loop). Result length must
  // be 1, not 2. A dropped `!` (origSet.has) or forced-true conditional would
  // double-emit the review span as 'added'.
  it('review span already in orig is not re-added (L131 `!` false side)', () => {
    const span = { id: 's', start: 1, end: 4, text: 't', labels: ['X'] }
    const res = computeHighlightDiff([span], [{ ...span }])
    expect(res).toHaveLength(1)
    expect(res[0].status).toBe('common')
  })

  // L136 comparator `a.span.start - b.span.start`. Use starts 3 and 9 (diff 6,
  // both nonzero, asymmetric) so a sign flip (`b - a`) reverses the order and a
  // `+` yields a positive constant (12) => no sort. Original ascending: 3 before 9.
  it('sort ascending by start: 9 then 3 -> [3,9] (L136 subtraction sign)', () => {
    const orig = [{ id: 'o', start: 9, end: 12, text: 'b', labels: ['A'] }]
    const rev = [{ id: 'r', start: 3, end: 6, text: 'a', labels: ['B'] }]
    const res = computeHighlightDiff(orig, rev)
    expect(res.map((r) => r.span.start)).toEqual([3, 9])
  })

  // Three spans with distinct starts to make the comparator's transitivity
  // load-bearing: 5,1,8 must come out 1,5,8. `b-a` would give 8,5,1; `+`
  // (constant positive) would leave insertion order 5,1,8.
  it('three spans 5/1/8 sort to 1/5/8 (L136 ordering, anti-`+`/anti-flip)', () => {
    const orig = [
      { id: 'o1', start: 5, end: 6, text: 'a', labels: ['A'] },
      { id: 'o2', start: 1, end: 2, text: 'b', labels: ['B'] },
    ]
    const rev = [{ id: 'r1', start: 8, end: 9, text: 'c', labels: ['C'] }]
    const res = computeHighlightDiff(orig, rev)
    expect(res.map((r) => r.span.start)).toEqual([1, 5, 8])
  })
})

// =====================================================================
// computeCommentDiff — L207-219
// =====================================================================

describe('computeCommentDiff: L211/L219 has() Conditionals + `!`', () => {
  // L211 true: shared id -> 'common'. L219 `!revHas` for that id is false -> not
  // re-added. Exactly 1 result.
  it('shared id -> single common (L211 true, L219 false)', () => {
    const orig = [{ id: 'c1', type: 'n', text: 'a' }]
    const rev = [{ id: 'c1', type: 'n', text: 'b' }] // same id, different text
    const res = computeCommentDiff(orig, rev)
    expect(res).toHaveLength(1)
    expect(res[0].status).toBe('common')
    expect(res[0].source).toBe('both')
  })

  // L211 false (orig id not in revIds) -> 'removed'; L219 true (rev id not in
  // origIds) -> 'added'. Disjoint id sets -> 1 removed + 1 added (length 2).
  it('disjoint ids -> 1 removed + 1 added (L211 false, L219 true)', () => {
    const orig = [{ id: 'only_orig', type: 'n', text: 'a' }]
    const rev = [{ id: 'only_rev', type: 'n', text: 'b' }]
    const res = computeCommentDiff(orig, rev)
    expect(res.filter((r) => r.status === 'removed')).toHaveLength(1)
    expect(res.filter((r) => r.status === 'added')).toHaveLength(1)
    expect(res).toHaveLength(2)
  })
})

// =====================================================================
// computeLineDiff + computeLCS — L162-191, L233-267
// =====================================================================

describe('computeLineDiff: L164-170 while guards (`<`, `&&`, `!==`) + `+1` lineNumbers', () => {
  // A pure removal in the middle. orig = [A,X,B], rev = [A,B]; LCS = [A,B].
  // L164 inner loop fires for X (origLines[1] !== lcs[1]='B') -> removed,
  // lineNumber oi+1 = 2. L165 `oi + 1`: a `-` would give 0, a `*` would give 1.
  // We assert lineNumber === 2 to pin the `+1`.
  it('middle removal: X removed at lineNumber 2 (L164 `&&`/`!==`, L165 `oi+1`)', () => {
    const res = computeLineDiff('A\nX\nB', 'A\nB')
    const removed = res.filter((r) => r.status === 'removed')
    expect(removed).toHaveLength(1)
    expect(removed[0].line).toBe('X')
    expect(removed[0].lineNumber).toBe(2) // oi was 1 -> 1+1 = 2
    // Surrounding context is unchanged A and B in order.
    expect(res.map((r) => `${r.status}:${r.line}`)).toEqual([
      'unchanged:A',
      'removed:X',
      'unchanged:B',
    ])
  })

  // A pure insertion in the middle. orig = [A,B], rev = [A,Y,B]; LCS = [A,B].
  // L169 inner loop fires for Y (revLines[1] !== lcs[1]='B') -> added,
  // lineNumber ri+1 = 2. Pins L170 `ri + 1`.
  it('middle insertion: Y added at lineNumber 2 (L169 `&&`/`!==`, L170 `ri+1`)', () => {
    const res = computeLineDiff('A\nB', 'A\nY\nB')
    const added = res.filter((r) => r.status === 'added')
    expect(added).toHaveLength(1)
    expect(added[0].line).toBe('Y')
    expect(added[0].lineNumber).toBe(2) // ri was 1 -> 1+1 = 2
    expect(res.map((r) => `${r.status}:${r.line}`)).toEqual([
      'unchanged:A',
      'added:Y',
      'unchanged:B',
    ])
  })

  // Trailing-removal path (L181-183). orig = [A,B,C], rev = [A]; LCS = [A].
  // After consuming the common A, oi=1 and the L181 `while (oi < origLines.length)`
  // tail loop must emit B (lineNumber 2) and C (lineNumber 3). Pins both the
  // `<` guard (must keep going while oi<3) and the L182 `oi + 1`.
  it('trailing removals B@2,C@3 from tail loop (L181 `<` guard, L182 `oi+1`)', () => {
    const res = computeLineDiff('A\nB\nC', 'A')
    expect(res.map((r) => `${r.status}:${r.line}:${r.lineNumber ?? ''}`)).toEqual([
      'unchanged:A:',
      'removed:B:2',
      'removed:C:3',
    ])
  })

  // Trailing-insertion path (L185-187). orig = [A], rev = [A,B,C]; LCS = [A].
  // L185 tail loop emits B (ri+1=2) and C (ri+1=3). Pins L185 `<` + L186 `ri+1`.
  it('trailing insertions B@2,C@3 from tail loop (L185 `<` guard, L186 `ri+1`)', () => {
    const res = computeLineDiff('A', 'A\nB\nC')
    expect(res.map((r) => `${r.status}:${r.line}:${r.lineNumber ?? ''}`)).toEqual([
      'unchanged:A:',
      'added:B:2',
      'added:C:3',
    ])
  })

  // L174 unchanged line carries NO lineNumber. A swap that pushed a numbered
  // unchanged would break this; pin lineNumber === undefined.
  it('unchanged lines carry no lineNumber (L174)', () => {
    const res = computeLineDiff('A\nB', 'A\nB')
    expect(res.every((r) => r.status === 'unchanged')).toBe(true)
    expect(res.every((r) => r.lineNumber === undefined)).toBe(true)
  })
})

describe('computeLCS (via computeLineDiff): kills `<=`, `===`, `+`, `-`, `>`, Math.max args', () => {
  // The LCS of [A,B,C,D] vs [A,C,D] is [A,C,D] (length 3). This requires the DP
  // table (L240-247) and backtrack (L254-263) to be correct:
  //  - L242 `a[i-1] === b[j-1]` matches must fire for A,C,D
  //  - L243 `dp[i-1][j-1] + 1` accumulates the diagonal
  //  - L245 Math.max(up, left) carries the best partial through the B gap
  //  - L259 `dp[i-1][j] > dp[i][j-1]` chooses the right backtrack direction
  // Output: A,C,D unchanged with B removed at original line 2.
  it('LCS [A,B,C,D] vs [A,C,D] = [A,C,D], only B removed @2 (DP+backtrack ops)', () => {
    const res = computeLineDiff('A\nB\nC\nD', 'A\nC\nD')
    expect(res.map((r) => `${r.status}:${r.line}`)).toEqual([
      'unchanged:A',
      'removed:B',
      'unchanged:C',
      'unchanged:D',
    ])
    const removed = res.filter((r) => r.status === 'removed')
    expect(removed).toHaveLength(1)
    expect(removed[0].lineNumber).toBe(2)
  })

  // A case where the two backtrack directions have DISTINCT dp values so L259's
  // `>` is load-bearing (not a tie). orig = [X,A,B], rev = [A,B,Y].
  // LCS = [A,B] (length 2). Greedy/equal-handling differences would drop a line.
  // We assert the full 2-line common subsequence survives with the right
  // surrounding add/remove, which only holds when Math.max (L245) and the `>`
  // tiebreak (L259) pick the longer chain.
  it('LCS [X,A,B] vs [A,B,Y] = [A,B] (L245 Math.max, L259 `>` direction)', () => {
    const res = computeLineDiff('X\nA\nB', 'A\nB\nY')
    const unchanged = res.filter((r) => r.status === 'unchanged').map((r) => r.line)
    expect(unchanged).toEqual(['A', 'B']) // common subsequence length 2
    expect(res.filter((r) => r.status === 'removed').map((r) => r.line)).toEqual(['X'])
    expect(res.filter((r) => r.status === 'added').map((r) => r.line)).toEqual(['Y'])
  })

  // Empty original string vs single review line. '' splits to [''], 'only'
  // splits to ['only']; the two single lines differ so L242 `===` is false,
  // dp[1][1] = max(0,0) = 0 -> LCS = []. The L162 `while (li < lcs.length)`
  // loop body never runs (li=0, length=0). Then the two tail loops emit the
  // orig leftover '' as REMOVED @1 (L182 oi+1, oi=0) and the review 'only' as
  // ADDED @1 (L186 ri+1, ri=0). Hand-verified: [removed:'' @1, added:'only' @1].
  // 0+1=1 is non-identity, so a `-` at L182/L186 would yield -1 (impossible
  // lineNumber) and `*` would yield 0; we pin lineNumber === 1 on both.
  it('empty orig vs one line -> removed "" @1 + added "only" @1 (tail `+1`, L242 `===` false)', () => {
    const res = computeLineDiff('', 'only')
    expect(res.filter((r) => r.status === 'unchanged')).toHaveLength(0)
    const removed = res.filter((r) => r.status === 'removed')
    const added = res.filter((r) => r.status === 'added')
    expect(removed).toEqual([{ status: 'removed', line: '', lineNumber: 1 }])
    expect(added).toEqual([{ status: 'added', line: 'only', lineNumber: 1 }])
  })

  // Identical single line: m=n=1, L242 `===` fires (A===A), dp[1][1]=0+1=1,
  // backtrack L255 `===` true -> unshift A. LCS=[A]. All unchanged, length 1.
  // Pins L242/L255 `===` true side and L243 `+1` accumulation.
  it('identical single line -> LCS [A], one unchanged (L242/L255 `===`, L243 `+1`)', () => {
    const res = computeLineDiff('A', 'A')
    expect(res).toHaveLength(1)
    expect(res[0].status).toBe('unchanged')
    expect(res[0].line).toBe('A')
  })

  // Fully disjoint single lines: m=n=1, L242 `===` false (A===B is false) ->
  // dp[1][1] = Math.max(dp[0][1], dp[1][0]) = max(0,0) = 0. LCS=[]. So 1 removed
  // + 1 added, length 2. Pins L242 `===` FALSE side (a `!==` mutation would
  // make A and B "match" -> LCS [A or B] -> wrong unchanged emission).
  it('disjoint single lines -> LCS empty -> removed+added (L242 `===` false side)', () => {
    const res = computeLineDiff('A', 'B')
    expect(res.filter((r) => r.status === 'unchanged')).toHaveLength(0)
    expect(res.filter((r) => r.status === 'removed').map((r) => r.line)).toEqual(['A'])
    expect(res.filter((r) => r.status === 'added').map((r) => r.line)).toEqual(['B'])
  })

  // Repeated lines exercise the L243 `+1` vs L245 max more sharply. orig =
  // [A,A,B], rev = [A,B]. LCS = [A,B] length 2 (one of the two A's matches).
  // If L243 used `-1` or L245 dropped an argument the LCS length would collapse
  // and we'd see two removals instead of one.
  it('repeated A: [A,A,B] vs [A,B] -> LCS [A,B], exactly one A removed', () => {
    const res = computeLineDiff('A\nA\nB', 'A\nB')
    expect(res.filter((r) => r.status === 'removed').map((r) => r.line)).toEqual(['A'])
    expect(res.filter((r) => r.status === 'unchanged').map((r) => r.line)).toEqual(['A', 'B'])
  })
})

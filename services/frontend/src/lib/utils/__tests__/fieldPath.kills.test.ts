/**
 * Mutation kills for fieldPath.ts — surgical assertions for the nightly
 * Stryker survivors (run of 2026-07-13; line numbers refer to fieldPath.ts as
 * of this commit). Each test names the mutant it kills and pins a value the
 * live code and the mutant disagree on.
 *
 * The `!isNaN(Number(segment))` index-vs-key branches (getValueByPath L38,
 * setValueByPath L80) LOOK equivalent — `arr[1]` and `arr['1']` are the same
 * property access — but ZERO-PADDED indices split them: `Number('01') === 1`
 * while `arr['01']` is a plain (missing) string key. The padded-index tests
 * below pin the live Number() semantics.
 */

import {
  formatValue,
  getAllPaths,
  getValueByPath,
  setValueByPath,
} from '../fieldPath'

describe('fieldPath kills · index-vs-key Number() coercion via padded indices (L38, L80)', () => {
  it('getValueByPath reads a[01] as array index 1', () => {
    // Mutant (always string-key): arr['01'] is undefined → defaultValue.
    expect(getValueByPath({ a: [10, 20] }, 'a[01]', 'dflt')).toBe(20)
  })

  it('setValueByPath writes a.01 into array index 1, not a "01" key', () => {
    const out = setValueByPath({ a: [10, 20] }, 'a.01', 'v')
    expect(out.a[1]).toBe('v')
    expect(out.a['01' as any]).toBeUndefined()
  })
})

describe('fieldPath kills · setValueByPath bracket normalization (L58 regex + ".$1")', () => {
  it('a[0] writes into index 0 of an array, not a literal "a[0]" key', () => {
    const out = setValueByPath({}, 'a[0]', 'v')
    // Mutating the replacement string breaks the split into ['a', '0'] and
    // the value lands under a wrong key (e.g. {"a[0]": "v"}).
    expect(Array.isArray(out.a)).toBe(true)
    expect(out.a[0]).toBe('v')
    expect(out['a[0]']).toBeUndefined()
  })

  it('a[12] (multi-digit) also normalizes — kills the \\d+ → \\d regex mutant', () => {
    const out = setValueByPath({}, 'a[12]', 'v')
    expect(Array.isArray(out.a)).toBe(true)
    expect(out.a[12]).toBe('v')
    expect(out['a[12]']).toBeUndefined()
  })
})

describe('fieldPath kills · setValueByPath container instantiation (L73-74)', () => {
  it('overwrites a null intermediate with an ARRAY when the next segment is numeric', () => {
    const out = setValueByPath({ a: null }, 'a.0', 'v')
    // Ternary mutant ([] ↔ {}) yields {a: {0: 'v'}} instead of {a: ['v']}.
    expect(Array.isArray(out.a)).toBe(true)
    expect(out.a[0]).toBe('v')
  })

  it('the fresh array container starts EMPTY (write to index 1 leaves index 0 unset)', () => {
    const out = setValueByPath({ a: null }, 'a.1', 'v')
    // ArrayDeclaration mutant seeds the container non-empty
    // (["Stryker was here"]) — index 0 would carry a phantom element.
    expect(Array.isArray(out.a)).toBe(true)
    expect(out.a.length).toBe(2)
    expect(out.a[0]).toBeUndefined()
    expect(out.a[1]).toBe('v')
  })

  it('overwrites a primitive intermediate with an OBJECT when the next segment is a key', () => {
    const out = setValueByPath({ a: 1 }, 'a.b', 2)
    // Killing the `typeof !== "object"` guard throws ("Cannot create property
    // 'b' on number 1") or leaves the primitive in place.
    expect(out.a).toEqual({ b: 2 })
    expect(Array.isArray(out.a)).toBe(false)
  })

  it('keeps an existing object intermediate (guard must not always fire)', () => {
    const nested = { keep: true }
    const out = setValueByPath({ a: nested }, 'a.b', 2)
    // A guard mutated to always-replace would drop the sibling key.
    expect(out.a.keep).toBe(true)
    expect(out.a.b).toBe(2)
  })
})

describe('fieldPath kills · getAllPaths Date leaf check (L108 instanceof Date)', () => {
  it('treats a Date as a LEAF path, not a container to recurse into', () => {
    const d = new Date('2026-07-13T00:00:00Z')
    // Dropping the `obj instanceof Date` arm recurses into the Date object,
    // which has no enumerable keys — the path vanishes entirely.
    expect(getAllPaths({ d })).toEqual(['d'])
  })

  it('a top-level Date with a prefix yields exactly that prefix', () => {
    expect(getAllPaths(new Date(), 'root')).toEqual(['root'])
  })
})

describe('fieldPath kills · getAllPaths undefined guard (L108 obj === undefined arm)', () => {
  it('undefined input yields NO paths even with a prefix', () => {
    // Dropping the undefined arm falls through to the leaf branch
    // (typeof undefined !== 'object') and fabricates ['root'].
    expect(getAllPaths(undefined, 'root')).toEqual([])
    expect(getAllPaths(null, 'root')).toEqual([])
  })
})

describe('fieldPath kills · formatValue Date branch (L144 instanceof + block)', () => {
  it('formats a Date via toLocaleDateString, not the object/JSON fallback', () => {
    const d = new Date('2026-07-13T00:00:00Z')
    expect(formatValue(d)).toBe(d.toLocaleDateString())
  })
})

describe('fieldPath kills · formatValue array branch (L144 map + ", " join)', () => {
  it('joins with a comma-space and formats elements RECURSIVELY', () => {
    // map(formatValue) mutant (e.g. identity/String) renders booleans as
    // "true"/"false" instead of "Yes"/"No" and null as "null" instead of "".
    expect(formatValue([true, null, 2])).toBe('Yes, , 2')
  })

  it('separator is exactly ", "', () => {
    expect(formatValue([1, 2])).toBe('1, 2')
  })
})

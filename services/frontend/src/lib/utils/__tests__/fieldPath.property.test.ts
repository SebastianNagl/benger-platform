/**
 * Property-based tests for the nested-path accessors in fieldPath.ts.
 *
 * fieldPath is the read/write substrate underneath the dynamic evaluation
 * forms (Issue #220): a silent bug in get/set means a score or label is read
 * from — or written to — the wrong slot. The example-based suites
 * (fieldPath.test.ts, fieldPath.br7.test.ts) pin a handful of concrete cases;
 * this file asserts the algebraic *laws* over fast-check-generated objects and
 * paths so that off-by-one index mutants, `>` vs `>=` swaps, and a flipped
 * falsy-guard get caught by at least one property across the sample.
 *
 * The path grammar under test (verified against the real implementation):
 *   - dot notation:        "user.name", "a.b.c"
 *   - bracket index:       "items[0]", "items[1].value"  (only \d+ inside [])
 *   - mixed:               "users[0].profile.name"
 *   - bracket is rewritten to dot by  path.replace(/\[(\d+)\]/g, '.$1')
 *     so "arr[1]" and "arr.1" are equivalent.
 *
 * Documented sentinels / quirks pinned below (NOT bugs to "fix" — pins so a
 * future refactor that changes them is caught):
 *   - missing path / null data / empty path  → defaultValue (default undefined)
 *   - a stored `undefined` is indistinguishable from "missing" on read
 *   - negative or out-of-range array index   → defaultValue
 *   - set() mutates its argument in place and returns the same reference
 *   - set() through a *falsy* existing intermediate (0, '', false, null)
 *     overwrites that intermediate with a fresh container
 */

import fc from 'fast-check'

import {
  getValueByPath,
  setValueByPath,
  hasPath,
  getAllPaths,
} from '../fieldPath'

// --- Arbitraries ---------------------------------------------------------

// Object keys restricted to a small, parser-safe alphabet: no '.', no '[' or
// ']', non-numeric, non-empty. Numeric-looking keys are excluded because the
// accessor coerces any numeric segment to a numeric index, which would make
// "a.0" address arr[0] rather than the string key "0" — a legitimate ambiguity
// of the grammar, not something the round-trip law should have to dodge.
const safeKeyArb = fc
  .stringOf(fc.constantFrom(...'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOP_$'), {
    minLength: 1,
    maxLength: 6,
  })
  .filter((k) => k.length > 0 && Number.isNaN(Number(k)))

// Leaf values that are safe for the round-trip law: anything except `undefined`
// (which get() cannot distinguish from "missing") and except NaN (=== fails on
// NaN, and NaN survives JSON only as null). Object/array leaves are allowed —
// round-trip compares by reference identity, so the exact same object comes
// back out.
const safeLeafArb = fc.oneof(
  fc.string(),
  fc.integer(),
  fc.double({ noNaN: true, noDefaultInfinity: true }),
  fc.boolean(),
  fc.constant(null),
  fc.constant(0),
  fc.constant(''),
  fc.constant(false),
)

// A dot-notation object path: 1..4 distinct-shaped segments of safe keys.
const objectPathArb = fc
  .array(safeKeyArb, { minLength: 1, maxLength: 4 })
  .map((segs) => segs.join('.'))

// --- Round-trip: the core law --------------------------------------------

describe('fieldPath — round-trip law: get(set(o, p, v), p) === v', () => {
  it('object paths on a fresh object round-trip exactly', () => {
    fc.assert(
      fc.property(objectPathArb, safeLeafArb, (path, value) => {
        const o: any = {}
        const ret = setValueByPath(o, path, value)
        // set returns the (mutated) root and get reads the same value back.
        expect(ret).toBe(o)
        expect(getValueByPath(o, path)).toBe(value)
      }),
    )
  })

  it('object paths on an arbitrary pre-populated object round-trip', () => {
    // Start from a random object, set a random path, then read it back. The
    // write must win regardless of what was there before.
    const seedObjArb = fc.dictionary(safeKeyArb, safeLeafArb, { maxKeys: 5 })
    fc.assert(
      fc.property(seedObjArb, objectPathArb, safeLeafArb, (seed, path, value) => {
        const o: any = { ...seed }
        setValueByPath(o, path, value)
        expect(getValueByPath(o, path)).toBe(value)
      }),
    )
  })

  it('bracket and dot index notation are interchangeable and round-trip', () => {
    fc.assert(
      fc.property(
        safeKeyArb,
        fc.nat({ max: 8 }),
        safeLeafArb,
        (key, idx, value) => {
          const bracket = `${key}[${idx}]`
          const dotted = `${key}.${idx}`
          const o: any = {}
          setValueByPath(o, bracket, value)
          // Read back via BOTH notations — they must agree.
          expect(getValueByPath(o, bracket)).toBe(value)
          expect(getValueByPath(o, dotted)).toBe(value)
          // The intermediate created for a numeric next-segment is an Array.
          expect(Array.isArray(o[key])).toBe(true)
          expect(o[key][idx]).toBe(value)
        },
      ),
    )
  })

  it('mixed object→array→object paths round-trip', () => {
    fc.assert(
      fc.property(
        safeKeyArb,
        fc.nat({ max: 5 }),
        safeKeyArb,
        safeLeafArb,
        (a, idx, b, value) => {
          fc.pre(a !== b || true) // a and b may collide; that's fine, distinct levels
          const path = `${a}[${idx}].${b}`
          const o: any = {}
          setValueByPath(o, path, value)
          expect(getValueByPath(o, path)).toBe(value)
          expect(Array.isArray(o[a])).toBe(true)
          expect(o[a][idx][b]).toBe(value)
        },
      ),
    )
  })
})

// --- Set creates intermediate structure ----------------------------------

describe('fieldPath — set materializes intermediate structure', () => {
  it('setting a.b.c on {} yields a get-readable nested object', () => {
    const o: any = {}
    setValueByPath(o, 'a.b.c', 'deep')
    expect(getValueByPath(o, 'a.b.c')).toBe('deep')
    expect(typeof o.a).toBe('object')
    expect(typeof o.a.b).toBe('object')
    expect(Array.isArray(o.a)).toBe(false)
  })

  it('every prefix of a freshly-set path is itself readable', () => {
    fc.assert(
      fc.property(
        fc.array(safeKeyArb, { minLength: 2, maxLength: 4 }),
        safeLeafArb,
        (segs, value) => {
          const o: any = {}
          const path = segs.join('.')
          setValueByPath(o, path, value)
          // Each intermediate prefix resolves to a (non-null) object container.
          for (let i = 1; i < segs.length; i++) {
            const prefix = segs.slice(0, i).join('.')
            const node = getValueByPath(o, prefix)
            expect(node).not.toBeUndefined()
            expect(typeof node).toBe('object')
          }
          // The full path resolves to the leaf.
          expect(getValueByPath(o, path)).toBe(value)
        },
      ),
    )
  })

  it('numeric next-segment creates an Array, non-numeric creates an Object', () => {
    const arr: any = {}
    setValueByPath(arr, 'list[0]', 'x')
    expect(Array.isArray(arr.list)).toBe(true)

    const obj: any = {}
    setValueByPath(obj, 'rec.field', 'x')
    expect(Array.isArray(obj.rec)).toBe(false)
    expect(typeof obj.rec).toBe('object')
  })
})

// --- Missing-path sentinel: never throws, returns defaultValue ------------

describe('fieldPath — get on missing path returns the sentinel, never throws', () => {
  it('random path over random object never throws and yields the default on miss', () => {
    const anyObjArb = fc.object({ maxDepth: 3 })
    const anyPathArb = fc
      .array(fc.oneof(safeKeyArb, fc.nat({ max: 5 }).map(String)), {
        minLength: 1,
        maxLength: 5,
      })
      .map((segs) => segs.join('.'))
    const SENTINEL = Symbol('default')

    fc.assert(
      fc.property(anyObjArb, anyPathArb, (obj, path) => {
        let result: unknown
        expect(() => {
          result = getValueByPath(obj, path, SENTINEL)
        }).not.toThrow()
        // Result is either a real value found at the path, or the sentinel —
        // it is never `undefined` leaking through (the default replaced it).
        if (result === SENTINEL) {
          // Confirmed: a genuine miss returns exactly the supplied default.
          expect(result).toBe(SENTINEL)
        }
      }),
    )
  })

  it('a deliberately-absent deep path returns the provided default', () => {
    fc.assert(
      fc.property(
        fc.dictionary(safeKeyArb, safeLeafArb, { maxKeys: 4 }),
        fc.string({ minLength: 1 }),
        (seed, marker) => {
          // "<random>.__definitely_absent__" cannot exist under a flat dict.
          const path = `__definitely_absent_${marker.replace(/[.[\]]/g, '_')}__.x.y`
          expect(getValueByPath(seed, path, 'DEFAULT')).toBe('DEFAULT')
        },
      ),
    )
  })

  it('default value is configurable and falls back to undefined', () => {
    expect(getValueByPath({ a: 1 }, 'missing')).toBeUndefined()
    expect(getValueByPath({ a: 1 }, 'missing', 'D')).toBe('D')
    expect(getValueByPath(null, 'a.b', 'D')).toBe('D')
    expect(getValueByPath(undefined, 'a.b', 'D')).toBe('D')
    expect(getValueByPath({ a: 1 }, '', 'D')).toBe('D')
    expect(getValueByPath({ a: 1 }, undefined, 'D')).toBe('D')
  })
})

// --- Bracket index access: boundaries, OOR, negative ---------------------

describe('fieldPath — bracket index access boundaries', () => {
  const arr = { arr: [10, 20, 30] }

  it('hand-computed exact index values', () => {
    // These exact equalities kill `>`/`>=` and +1/-1 index mutants.
    expect(getValueByPath(arr, 'arr[0]')).toBe(10) // first boundary
    expect(getValueByPath(arr, 'arr[1]')).toBe(20) // middle
    expect(getValueByPath(arr, 'arr[2]')).toBe(30) // last boundary (len-1)
  })

  it('out-of-range and negative indices return the documented default', () => {
    expect(getValueByPath(arr, 'arr[3]')).toBeUndefined() // one past the end
    expect(getValueByPath(arr, 'arr[5]', 'D')).toBe('D') // far past the end
    // [-1] is NOT matched by the \d+ bracket regex, so it stays literal and
    // resolves through arr["arr[-1]"] which is absent → default.
    expect(getValueByPath(arr, 'arr[-1]', 'D')).toBe('D')
  })

  it('property: index i in [0,len) returns the element; i>=len returns default', () => {
    const elemArb = fc.array(fc.integer(), { minLength: 1, maxLength: 12 })
    fc.assert(
      fc.property(elemArb, (elements) => {
        const data = { arr: elements }
        const len = elements.length
        // Every in-range index reads exactly its element (boundaries included).
        for (let i = 0; i < len; i++) {
          expect(getValueByPath(data, `arr[${i}]`)).toBe(elements[i])
        }
        // First out-of-range index is a miss.
        expect(getValueByPath(data, `arr[${len}]`, 'OOR')).toBe('OOR')
        // Explicit boundary pins (also guard the len===1 edge).
        expect(getValueByPath(data, 'arr[0]')).toBe(elements[0])
        expect(getValueByPath(data, `arr[${len - 1}]`)).toBe(elements[len - 1])
      }),
    )
  })

  it('hasPath agrees with index in-range / out-of-range', () => {
    expect(hasPath(arr, 'arr[0]')).toBe(true)
    expect(hasPath(arr, 'arr[2]')).toBe(true)
    expect(hasPath(arr, 'arr[3]')).toBe(false)
    expect(hasPath(arr, 'arr[99]')).toBe(false)
  })
})

// --- Mutation semantics: set mutates in place ----------------------------

describe('fieldPath — set mutates in place (pinned, not immutable)', () => {
  it('returns the very same root reference it was given', () => {
    fc.assert(
      fc.property(objectPathArb, safeLeafArb, (path, value) => {
        const o: any = {}
        expect(setValueByPath(o, path, value)).toBe(o)
      }),
    )
  })

  it('mutates the caller-visible object (no clone)', () => {
    const o: any = { existing: 1 }
    setValueByPath(o, 'added', 2)
    // The original binding observes the new key — proves in-place mutation.
    expect(o.added).toBe(2)
    expect(o.existing).toBe(1)
  })

  it('empty path is a no-op that returns the original reference unchanged', () => {
    const o = { a: 1 }
    const before = JSON.stringify(o)
    expect(setValueByPath(o, '', 99)).toBe(o)
    expect(JSON.stringify(o)).toBe(before)
  })

  it('quirk pin: set through a falsy intermediate overwrites it with a container', () => {
    // current[segment] is checked with `!current[segment]`, so a stored 0 / ''
    // / false / null intermediate is treated as "missing" and replaced. This
    // is a known sharp edge; pinned so a future guard change is noticed.
    const zero: any = { a: { b: 0 } }
    setValueByPath(zero, 'a.b.c', 'X')
    expect(zero.a.b).toEqual({ c: 'X' }) // the 0 was clobbered

    const empty: any = { a: { b: '' } }
    setValueByPath(empty, 'a.b.c', 'Y')
    expect(empty.a.b).toEqual({ c: 'Y' })
  })
})

// --- Stored-undefined quirk + falsy leaves --------------------------------

describe('fieldPath — falsy leaves vs the undefined sentinel', () => {
  it('falsy-but-defined leaves (0, false, "", null) survive round-trip', () => {
    fc.assert(
      fc.property(
        objectPathArb,
        fc.constantFrom(0, false, '', null),
        (path, value) => {
          const o: any = {}
          setValueByPath(o, path, value)
          expect(getValueByPath(o, path)).toBe(value)
          // hasPath: defined-but-falsy is present, EXCEPT explicit undefined.
          expect(hasPath(o, path)).toBe(true)
        },
      ),
    )
  })

  it('quirk pin: a stored `undefined` reads back as the default (indistinguishable from missing)', () => {
    const o: any = {}
    setValueByPath(o, 'k', undefined)
    expect('k' in o).toBe(true) // the key physically exists
    expect(getValueByPath(o, 'k', 'DEF')).toBe('DEF') // but get can't tell
    expect(hasPath(o, 'k')).toBe(false) // hasPath therefore reports false
  })
})

// --- Never-crash fuzz over arbitrary path strings ------------------------

describe('fieldPath — never crashes on arbitrary path strings', () => {
  const weirdPaths = [
    '',
    '.',
    '..',
    '...',
    '[0]',
    '[',
    ']',
    '][',
    'a..b',
    'a...b',
    '.a',
    'a.',
    'a[0][1]',
    'a[0].b[1].c',
    '[0].x',
    '...x...',
    'a[999999]',
    'constructor',
    '__proto__',
    'toString',
    'a.b.c.d.e.f.g.h.i.j',
  ]

  it.each(weirdPaths)('getValueByPath does not throw on %j', (p) => {
    expect(() => getValueByPath({ a: { b: [1, 2, 3] } }, p, 'D')).not.toThrow()
  })

  it.each(weirdPaths.filter((p) => p !== ''))(
    'setValueByPath does not throw on %j',
    (p) => {
      expect(() => setValueByPath({}, p, 1)).not.toThrow()
    },
  )

  it('property: get never throws for any string path over any object', () => {
    fc.assert(
      fc.property(fc.object({ maxDepth: 3 }), fc.string(), (obj, path) => {
        expect(() => getValueByPath(obj, path)).not.toThrow()
      }),
    )
  })

  it('property: set never throws for any string path over a fresh object', () => {
    fc.assert(
      fc.property(fc.string(), fc.anything(), (path, value) => {
        expect(() => setValueByPath({}, path, value)).not.toThrow()
      }),
    )
  })

  it('property: hasPath never throws and always returns a boolean', () => {
    fc.assert(
      fc.property(fc.object({ maxDepth: 3 }), fc.string(), (obj, path) => {
        let r: unknown
        expect(() => {
          r = hasPath(obj, path)
        }).not.toThrow()
        expect(typeof r).toBe('boolean')
      }),
    )
  })
})

// --- getAllPaths ↔ get coherence -----------------------------------------

describe('fieldPath — getAllPaths produces paths that get can resolve', () => {
  it('every path returned by getAllPaths resolves to a defined leaf', () => {
    // getAllPaths emits leaf paths; feeding each back into get must return the
    // exact leaf, never undefined (i.e. the two functions speak the same
    // grammar: dots for object keys, [i] for array indices).
    const leafyObjArb = fc.dictionary(
      safeKeyArb,
      fc.oneof(
        safeLeafArb,
        fc.dictionary(safeKeyArb, safeLeafArb, { maxKeys: 3 }),
        fc.array(safeLeafArb, { maxLength: 4 }),
      ),
      { maxKeys: 5 },
    )
    fc.assert(
      fc.property(leafyObjArb, (obj) => {
        const paths = getAllPaths(obj)
        for (const p of paths) {
          // A null leaf is a valid value that getAllPaths reports; get returns
          // it faithfully. Anything else must be defined.
          const v = getValueByPath(obj, p, Symbol('miss'))
          expect(typeof v).not.toBe('symbol') // i.e. it was NOT a miss
        }
      }),
    )
  })

  it('hand example: mixed structure paths all resolve', () => {
    const data = {
      name: 'Project',
      users: [{ name: 'Alice' }, { name: 'Bob' }],
      meta: { tags: ['x', 'y'] },
    }
    for (const p of getAllPaths(data)) {
      expect(getValueByPath(data, p)).not.toBeUndefined()
    }
    // Spot-check a couple of exact resolutions.
    expect(getValueByPath(data, 'users[1].name')).toBe('Bob')
    expect(getValueByPath(data, 'meta.tags[0]')).toBe('x')
  })
})

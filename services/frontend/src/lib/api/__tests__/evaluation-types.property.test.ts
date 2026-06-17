/**
 * Property-based + fixed-point tests for the evaluation metric registry
 * (evaluation-types.ts).
 *
 * This file is the metric-registry crown jewel: a silent bug here renders a
 * wrong leaderboard / scoring DISPLAY — e.g. a 0–18 Notenpunkte grade shown on
 * a 0–1 percent scale, a metric dropped from its group, or a field
 * mis-classified as model vs. human. The existing example tests pin a handful
 * of concrete cases; these assert the registry's *invariants* over
 * fast-check-generated inputs and lock the exact scale-token boundaries with
 * hand-computed fixed points.
 *
 * Functions / contracts pinned here:
 *  - isHumanField / isModelField / getBaseFieldName  (field-source partition)
 *  - getMetricScale / getMetricSummable / isMetricImmediateEligible
 *    (display-scale + aggregation contract feeding the leaderboard formatter)
 *  - getMetricDefinitions / registerMetric           (registry idempotence)
 *  - getGroupedMetrics / registerMetricGroup         (group merge algebra)
 *  - getDimensionDisplayName                          (total label lookup)
 *  - getFieldDisplayName / isSpecialFieldValue        (special-value classify)
 *  - generateEvaluationId                             (prefix + uniqueness)
 *  - static-table integrity (METRIC_ORDER / GROUPED_METRICS / scale tokens)
 *
 * NOTE on the scale contract: the *arithmetic* of rendering a value under a
 * scale (×100 for '0-1', "X / 18 NP" for '0-18', etc.) lives in the
 * leaderboard component, not here. This module owns the resolution step —
 * which scale token a metric maps to — which is the input that drives that
 * formatter. So the scale invariants below pin the *token* a metric resolves
 * to (the thing a wrong-constant mutant would corrupt), not a formatter.
 */

import fc from 'fast-check'

import {
  isHumanField,
  isModelField,
  getBaseFieldName,
  getDimensionDisplayName,
  getFieldDisplayName,
  isSpecialFieldValue,
  generateEvaluationId,
  registerMetric,
  registerMetricGroup,
  getMetricDefinitions,
  getMetricScale,
  getMetricSummable,
  isMetricImmediateEligible,
  getGroupedMetrics,
  FIELD_SPECIFIERS,
  MODEL_FIELD_PREFIX,
  HUMAN_FIELD_PREFIX,
  METRIC_DEFINITIONS,
  GROUPED_METRICS,
  METRIC_ORDER,
  TYPE_SPECIFIC_DIMENSIONS,
  type AvailableMetric,
  type MetricDisplayScale,
} from '../evaluation-types'

// --- Arbitraries ---------------------------------------------------------

// Plain identifier-ish base names (no source prefix, not a specifier).
const baseNameArb = fc.constantFrom(
  'answer',
  'rating',
  'text',
  'span',
  'a_b',
  '__response__',
  'k',
)

// Any field string the UI might hand these classifiers: prefixed, bare,
// the two special specifiers, and a few adversarial strings.
const fieldArb = fc.oneof(
  baseNameArb.map((n) => `${MODEL_FIELD_PREFIX}${n}`),
  baseNameArb.map((n) => `${HUMAN_FIELD_PREFIX}${n}`),
  baseNameArb,
  fc.constant(FIELD_SPECIFIERS.ALL_MODEL),
  fc.constant(FIELD_SPECIFIERS.ALL_HUMAN),
  fc.string(),
)

const VALID_SCALES: MetricDisplayScale[] = ['0-1', '0-100', '0-18', 'raw']
const scaleArb = fc.constantFrom(...VALID_SCALES)

// A well-formed extended metric definition with a unique key per generated run.
function metricDefArb(key: string): fc.Arbitrary<AvailableMetric> {
  return fc.record({
    name: fc.constant(key),
    display_name: fc.string(),
    description: fc.string(),
    category: fc.constantFrom('Extended Category', 'Lexical Metrics'),
    status: fc.constantFrom('stable', 'beta', 'coming-soon') as fc.Arbitrary<
      AvailableMetric['status']
    >,
    supports_parameters: fc.boolean(),
    display_scale: scaleArb,
    summable: fc.boolean(),
    immediate_eligible: fc.boolean(),
  })
}

// --- Field-source partition ---------------------------------------------

describe('field-source classification — properties', () => {
  it('every field is classified into exactly one of {model, human}', () => {
    // The two predicates must partition the input space: no field is both,
    // and no field is neither. A mutated boundary (e.g. dropping the backward-
    // compat unprefixed-is-model branch) breaks the "exactly one" count.
    fc.assert(
      fc.property(fieldArb, (field) => {
        const m = isModelField(field)
        const h = isHumanField(field)
        expect(m && h).toBe(false)
        expect(m || h).toBe(true)
      }),
    )
  })

  it('human: prefix and ALL_HUMAN are human; never model', () => {
    fc.assert(
      fc.property(baseNameArb, (n) => {
        const field = `${HUMAN_FIELD_PREFIX}${n}`
        expect(isHumanField(field)).toBe(true)
        expect(isModelField(field)).toBe(false)
      }),
    )
    expect(isHumanField(FIELD_SPECIFIERS.ALL_HUMAN)).toBe(true)
    expect(isModelField(FIELD_SPECIFIERS.ALL_HUMAN)).toBe(false)
  })

  it('model: prefix, ALL_MODEL and any non-human bare field are model', () => {
    fc.assert(
      fc.property(baseNameArb, (n) => {
        const prefixed = `${MODEL_FIELD_PREFIX}${n}`
        expect(isModelField(prefixed)).toBe(true)
        expect(isHumanField(prefixed)).toBe(false)
        // Backward compat: an unprefixed bare field is treated as model.
        expect(isModelField(n)).toBe(true)
        expect(isHumanField(n)).toBe(false)
      }),
    )
    expect(isModelField(FIELD_SPECIFIERS.ALL_MODEL)).toBe(true)
    expect(isHumanField(FIELD_SPECIFIERS.ALL_MODEL)).toBe(false)
  })

  it('getBaseFieldName inverts prefixing and is idempotent on base names', () => {
    fc.assert(
      fc.property(baseNameArb, (n) => {
        // Round-trip: stripping the prefix recovers the base name.
        expect(getBaseFieldName(`${MODEL_FIELD_PREFIX}${n}`)).toBe(n)
        expect(getBaseFieldName(`${HUMAN_FIELD_PREFIX}${n}`)).toBe(n)
        // Idempotent: a name with no source prefix is returned unchanged, and
        // a second application is a no-op.
        const once = getBaseFieldName(n)
        expect(getBaseFieldName(once)).toBe(once)
      }),
    )
  })

  it('only one prefix is stripped (model:human:x -> human:x)', () => {
    // getBaseFieldName strips at most the leading prefix; a nested-looking
    // string keeps its inner prefix. Pins the "substring once" branch.
    expect(getBaseFieldName(`${MODEL_FIELD_PREFIX}${HUMAN_FIELD_PREFIX}x`)).toBe(
      `${HUMAN_FIELD_PREFIX}x`,
    )
  })
})

// --- Display-scale contract ---------------------------------------------

describe('display-scale resolution — properties', () => {
  it('getMetricScale always returns one of the four documented tokens', () => {
    // Totality: no input (registered, unregistered, garbage) yields a token
    // outside the union. The leaderboard formatter switches on these exact
    // four strings; an out-of-set token would fall through to the raw branch.
    fc.assert(
      fc.property(fc.oneof(fc.string(), fc.constantFrom(...Object.keys(METRIC_DEFINITIONS))), (key) => {
        expect(VALID_SCALES).toContain(getMetricScale(key))
      }),
    )
  })

  it('a registered metric resolves to its declared scale, deterministically', () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        scaleArb,
        fc.boolean(),
        fc.boolean(),
        (id, scale, summable, eligible) => {
          const key = `prop_scale_${id}`
          const def: AvailableMetric = {
            name: key,
            display_name: 'Prop Scale Metric',
            description: '',
            category: 'Extended Category',
            status: 'beta',
            supports_parameters: false,
            display_scale: scale,
            summable,
            immediate_eligible: eligible,
          }
          registerMetric(key, def)
          // Resolution reads through to exactly what was registered, and is
          // stable across repeated calls (no hidden per-call state).
          expect(getMetricScale(key)).toBe(scale)
          expect(getMetricScale(key)).toBe(scale)
          expect(getMetricSummable(key)).toBe(summable)
          expect(isMetricImmediateEligible(key)).toBe(eligible)
        },
      ),
    )
  })

  it('unknown metric keys fall back to the documented defaults', () => {
    fc.assert(
      fc.property(fc.string(), (key) => {
        // Only assert on keys not actually registered (core or extended).
        fc.pre(!(key in getMetricDefinitions()))
        expect(getMetricScale(key)).toBe('0-1') // historical default
        expect(getMetricSummable(key)).toBe(false) // conservative default
        expect(isMetricImmediateEligible(key)).toBe(true) // default eligible
      }),
    )
  })

  it('isMetricImmediateEligible only flips on an explicit === false', () => {
    // Pins the "=== false" comparison: undefined / true / missing all stay
    // eligible; a mutant changing this to truthiness would break the default.
    fc.assert(
      fc.property(fc.uuid(), fc.option(fc.boolean(), { nil: undefined }), (id, flag) => {
        const key = `prop_elig_${id}`
        const def: AvailableMetric = {
          name: key,
          display_name: '',
          description: '',
          category: 'Extended Category',
          status: 'stable',
          supports_parameters: false,
          immediate_eligible: flag as boolean | undefined,
        }
        registerMetric(key, def)
        expect(isMetricImmediateEligible(key)).toBe(flag !== false)
      }),
    )
  })

  // ---- Hand-computed fixed points (kill wrong-constant / boundary mutants) --
  describe('scale token fixed points (every core metric)', () => {
    const EXPECTED_SCALE: Record<string, MetricDisplayScale> = {
      bleu: '0-1',
      rouge: '0-1',
      meteor: '0-1',
      chrf: '0-1',
      exact_match: '0-1',
      bertscore: '0-1',
      moverscore: '0-1',
      semantic_similarity: '0-1',
      factcc: '0-1',
      qags: '0-1',
      coherence: '0-1',
      accuracy: '0-1',
      precision: '0-1',
      recall: '0-1',
      f1: '0-1',
      llm_judge_classic: '0-1',
      llm_judge_custom: '0-1',
    }
    it.each(Object.entries(EXPECTED_SCALE))(
      '%s resolves to scale %s',
      (key, scale) => {
        expect(getMetricScale(key)).toBe(scale)
      },
    )

    const EXPECTED_SUMMABLE: Record<string, boolean> = {
      // Only these two core metrics are additive (sum = count of matches/correct).
      exact_match: true,
      accuracy: true,
      // A representative sample of the non-summable ratio metrics.
      bleu: false,
      rouge: false,
      f1: false,
      bertscore: false,
      llm_judge_classic: false,
    }
    it.each(Object.entries(EXPECTED_SUMMABLE))(
      '%s summable=%s',
      (key, summable) => {
        expect(getMetricSummable(key)).toBe(summable)
      },
    )

    const EXPECTED_IMMEDIATE: Record<string, boolean> = {
      // Heavy / transformer-loading metrics are batch-only.
      bertscore: false,
      moverscore: false,
      semantic_similarity: false,
      factcc: false,
      qags: false,
      coherence: false,
      // Light metrics stay immediate-eligible (no explicit flag => default).
      bleu: true,
      rouge: true,
      exact_match: true,
      accuracy: true,
      llm_judge_classic: true,
    }
    it.each(Object.entries(EXPECTED_IMMEDIATE))(
      '%s immediate_eligible=%s',
      (key, eligible) => {
        expect(isMetricImmediateEligible(key)).toBe(eligible)
      },
    )

    it('exactly the six heavy metrics opt out of immediate eligibility', () => {
      // A drift guard: if a future edit flips immediate_eligible on the wrong
      // metric, this set comparison catches it.
      const heavy = Object.entries(METRIC_DEFINITIONS)
        .filter(([, d]) => d.immediate_eligible === false)
        .map(([k]) => k)
        .sort()
      expect(heavy).toEqual(
        ['bertscore', 'coherence', 'factcc', 'moverscore', 'qags', 'semantic_similarity'].sort(),
      )
    })

    it('exactly two core metrics are summable', () => {
      const summable = Object.entries(METRIC_DEFINITIONS)
        .filter(([, d]) => d.summable === true)
        .map(([k]) => k)
        .sort()
      expect(summable).toEqual(['accuracy', 'exact_match'].sort())
    })
  })
})

// --- Registry idempotence ------------------------------------------------

describe('metric registry — idempotence & union', () => {
  it('registering the same key twice keeps a single entry (last write wins)', () => {
    fc.assert(
      fc.property(fc.uuid(), metricDefArb('placeholder'), (id, _def) => {
        const key = `prop_idem_${id}`
        const first: AvailableMetric = { ..._def, name: key, display_scale: '0-1' }
        const second: AvailableMetric = { ..._def, name: key, display_scale: '0-18' }
        registerMetric(key, first)
        registerMetric(key, second)
        const all = getMetricDefinitions()
        // Exactly one entry under the key, and it's the latest registration.
        const occurrences = Object.keys(all).filter((k) => k === key).length
        expect(occurrences).toBe(1)
        expect(all[key].display_scale).toBe('0-18')
        expect(getMetricScale(key)).toBe('0-18')
      }),
    )
  })

  it('getMetricDefinitions preserves every core metric verbatim', () => {
    // Extended registrations from this (and sibling) test files must never
    // drop or overwrite a core metric — the union always contains all of them.
    const all = getMetricDefinitions()
    for (const [k, v] of Object.entries(METRIC_DEFINITIONS)) {
      expect(all[k]).toBe(v)
    }
  })

  it('get(name) after register returns exactly what was registered', () => {
    fc.assert(
      fc.property(fc.uuid(), (id) => {
        const key = `prop_get_${id}`
        const def: AvailableMetric = {
          name: key,
          display_name: 'X',
          description: 'Y',
          category: 'Extended Category',
          status: 'beta',
          supports_parameters: true,
          display_scale: '0-100',
          summable: true,
          immediate_eligible: false,
        }
        registerMetric(key, def)
        expect(getMetricDefinitions()[key]).toEqual(def)
      }),
    )
  })
})

// --- Group merge algebra -------------------------------------------------

describe('getGroupedMetrics — merge algebra', () => {
  it('returns deep copies: pushing into a result never leaks into the source', () => {
    const groups = getGroupedMetrics()
    const target = groups[0]
    const before = target.metrics.length
    target.metrics.push('__leak_probe__')
    const again = getGroupedMetrics()[0]
    expect(again.metrics).not.toContain('__leak_probe__')
    expect(again.metrics.length).toBe(before)
  })

  it('every metric referenced in a group has at most one occurrence per group', () => {
    // No group lists the same metric key twice — the merge dedups on insert.
    fc.assert(
      fc.property(fc.constant(null), () => {
        for (const g of getGroupedMetrics()) {
          expect(new Set(g.metrics).size).toBe(g.metrics.length)
        }
      }),
      { numRuns: 5 },
    )
  })

  it('merging an extended group into a core group is a union (no dup, core desc wins)', () => {
    fc.assert(
      fc.property(fc.uuid(), fc.array(fc.uuid(), { maxLength: 4 }), (id, extraIds) => {
        const core = GROUPED_METRICS[0] // 'Lexical Metrics'
        const before = getGroupedMetrics().find((g) => g.name === core.name)!
        const beforeMetrics = [...before.metrics]
        const newKeys = extraIds.map((x) => `ext_${id}_${x}`)
        // Include one already-present core metric to exercise the dedup branch.
        const overlap = core.metrics[0]
        registerMetricGroup({
          name: core.name,
          description: 'should-be-ignored-on-merge',
          metrics: [overlap, ...newKeys],
        })
        const after = getGroupedMetrics().find((g) => g.name === core.name)!
        // Core description is preserved, never overwritten by the merge.
        expect(after.description).toBe(core.description)
        // Result is the union: all prior metrics + the new keys, deduped.
        const expectedUnion = new Set([...beforeMetrics, ...newKeys])
        expect(new Set(after.metrics)).toEqual(expectedUnion)
        // No duplicates introduced.
        expect(new Set(after.metrics).size).toBe(after.metrics.length)
        // The overlapping core metric still appears exactly once.
        expect(after.metrics.filter((m) => m === overlap)).toHaveLength(1)
      }),
    )
  })

  it('merge is idempotent: registering the same group twice changes nothing', () => {
    fc.assert(
      fc.property(fc.uuid(), (id) => {
        const name = `Idem Group ${id}`
        const group = { name, description: 'd', metrics: [`m_${id}`] }
        registerMetricGroup(group)
        const afterFirst = getGroupedMetrics().find((g) => g.name === name)!
        registerMetricGroup(group)
        const afterSecond = getGroupedMetrics().find((g) => g.name === name)!
        expect(afterSecond.metrics).toEqual(afterFirst.metrics)
        expect(afterSecond.metrics).toEqual([`m_${id}`])
      }),
    )
  })

  it('a brand-new extended group is appended with its metrics copied', () => {
    fc.assert(
      fc.property(fc.uuid(), (id) => {
        const name = `Fresh Group ${id}`
        const metrics = [`fm_${id}_1`, `fm_${id}_2`]
        registerMetricGroup({ name, description: 'fresh', metrics })
        const found = getGroupedMetrics().find((g) => g.name === name)!
        expect(found).toBeDefined()
        expect(found.metrics).toEqual(metrics)
        // Copied, not aliased — mutating the result must not touch our input.
        found.metrics.push('mutated')
        expect(getGroupedMetrics().find((g) => g.name === name)!.metrics).toEqual(
          metrics,
        )
      }),
    )
  })
})

// --- Dimension display-name lookup --------------------------------------

describe('getDimensionDisplayName — total label lookup', () => {
  it('known type-specific dimensions return their exact documented label', () => {
    for (const [key, label] of Object.entries(TYPE_SPECIFIC_DIMENSIONS)) {
      expect(getDimensionDisplayName(key)).toBe(label)
    }
  })

  it('unknown dimensions fall back to capitalize-first + underscores-to-spaces', () => {
    fc.assert(
      // Lowercase identifier strings that are NOT type-specific keys.
      fc.property(
        fc
          .stringMatching(/^[a-z][a-z_]{0,12}$/)
          .filter((s) => !(s in TYPE_SPECIFIC_DIMENSIONS)),
        (dim) => {
          const expected =
            dim.charAt(0).toUpperCase() + dim.slice(1).replace(/_/g, ' ')
          expect(getDimensionDisplayName(dim)).toBe(expected)
          // The fallback never contains an underscore.
          expect(getDimensionDisplayName(dim)).not.toContain('_')
        },
      ),
    )
  })

  it('fixed points: boundary_accuracy / accuracy collision resolves to the type-specific label', () => {
    // `accuracy` exists as a type-specific key (-> 'Selection Accuracy'); the
    // type-specific branch must win over the capitalize fallback ('Accuracy').
    expect(getDimensionDisplayName('boundary_accuracy')).toBe('Boundary Accuracy')
    expect(getDimensionDisplayName('accuracy')).toBe('Selection Accuracy')
    // Pure fallback example with no underscore.
    expect(getDimensionDisplayName('helpfulness')).toBe('Helpfulness')
  })
})

// --- Special-value classification ---------------------------------------

describe('field specifier classification — total & consistent', () => {
  it('isSpecialFieldValue is true exactly for the two specifiers', () => {
    fc.assert(
      fc.property(fieldArb, (field) => {
        const special =
          field === FIELD_SPECIFIERS.ALL_MODEL ||
          field === FIELD_SPECIFIERS.ALL_HUMAN
        expect(isSpecialFieldValue(field)).toBe(special)
      }),
    )
  })

  it('getFieldDisplayName: specifiers map to their label; bare fields are identity', () => {
    expect(getFieldDisplayName(FIELD_SPECIFIERS.ALL_MODEL)).toBe('All model responses')
    expect(getFieldDisplayName(FIELD_SPECIFIERS.ALL_HUMAN)).toBe('All human annotations')
    // The two unstructured-response aliases.
    expect(getFieldDisplayName('model:__response__')).toBe('Model Response (unstructured)')
    expect(getFieldDisplayName('__response__')).toBe('Model Response (unstructured)')
    // Any other field is returned verbatim.
    fc.assert(
      fc.property(
        fc.string().filter(
          (s) =>
            s !== FIELD_SPECIFIERS.ALL_MODEL &&
            s !== FIELD_SPECIFIERS.ALL_HUMAN &&
            s !== 'model:__response__' &&
            s !== '__response__',
        ),
        (field) => {
          expect(getFieldDisplayName(field)).toBe(field)
        },
      ),
    )
  })
})

// --- ID generation -------------------------------------------------------

describe('generateEvaluationId — prefix & uniqueness', () => {
  it('always starts with the metric name followed by a separator', () => {
    fc.assert(
      // Metric tokens without a dash so the prefix boundary is unambiguous.
      fc.property(fc.stringMatching(/^[a-z_]{1,16}$/), (metric) => {
        const id = generateEvaluationId(metric)
        expect(id.startsWith(`${metric}-`)).toBe(true)
        // timestamp + random suffix => at least three dash-delimited parts.
        expect(id.split('-').length).toBeGreaterThanOrEqual(3)
      }),
    )
  })

  it('successive calls produce distinct ids for the same metric', () => {
    fc.assert(
      fc.property(fc.stringMatching(/^[a-z_]{1,16}$/), (metric) => {
        const ids = new Set(
          Array.from({ length: 8 }, () => generateEvaluationId(metric)),
        )
        // Random + ms timestamp suffix => extremely unlikely to collide; the
        // test pins that the suffix is actually varied (not a constant mutant).
        expect(ids.size).toBeGreaterThan(1)
      }),
    )
  })
})

// --- Static-table structural integrity ----------------------------------

describe('static metric tables — structural invariants', () => {
  it('METRIC_ORDER is exactly the flattened GROUPED_METRICS', () => {
    expect(METRIC_ORDER).toEqual(GROUPED_METRICS.flatMap((g) => g.metrics))
  })

  it('every metric listed in a core group is a defined core metric', () => {
    for (const g of GROUPED_METRICS) {
      for (const m of g.metrics) {
        expect(METRIC_DEFINITIONS[m]).toBeDefined()
        // The definition's self-name matches the registry key.
        expect(METRIC_DEFINITIONS[m].name).toBe(m)
      }
    }
  })

  it('every core metric appears in exactly one group', () => {
    const grouped = GROUPED_METRICS.flatMap((g) => g.metrics)
    // No metric appears in two groups.
    expect(new Set(grouped).size).toBe(grouped.length)
    // Every defined metric is grouped (no orphan that would vanish from the UI).
    for (const key of Object.keys(METRIC_DEFINITIONS)) {
      expect(grouped).toContain(key)
    }
  })

  it("every core metric's declared display_scale is a valid token", () => {
    for (const def of Object.values(METRIC_DEFINITIONS)) {
      if (def.display_scale !== undefined) {
        expect(VALID_SCALES).toContain(def.display_scale)
      }
    }
  })
})

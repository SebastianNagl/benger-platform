/**
 * Additional coverage for evaluation-types.ts pure helpers + the metric
 * registry extension points.
 *
 * The existing evaluation-types tests only cover getDimensionDisplayName /
 * isSpecialFieldValue / getFieldDisplayName / generateEvaluationId. Untested
 * (branch 46%, functions 64%):
 *  - isHumanField / isModelField / getBaseFieldName (field-prefix logic)
 *  - getFieldDisplayName's model:__response__ / __response__ branch
 *  - getDimensionDisplayName's type-specific-dimension branch
 *  - registerMetric / registerMetricGroup / getMetricDefinitions
 *  - getMetricScale / getMetricSummable / isMetricImmediateEligible defaults
 *  - getGroupedMetrics merge-into-existing-group + append-new-group branches
 */

import {
  isHumanField,
  isModelField,
  getBaseFieldName,
  getDimensionDisplayName,
  getFieldDisplayName,
  isSpecialFieldValue,
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
  type AvailableMetric,
} from '../evaluation-types'

describe('field prefix helpers', () => {
  describe('isHumanField', () => {
    it('is true for human:-prefixed fields', () => {
      expect(isHumanField(`${HUMAN_FIELD_PREFIX}answer`)).toBe(true)
    })

    it('is true for the ALL_HUMAN specifier', () => {
      expect(isHumanField(FIELD_SPECIFIERS.ALL_HUMAN)).toBe(true)
    })

    it('is false for model-prefixed and plain fields', () => {
      expect(isHumanField(`${MODEL_FIELD_PREFIX}answer`)).toBe(false)
      expect(isHumanField('plain_field')).toBe(false)
      expect(isHumanField(FIELD_SPECIFIERS.ALL_MODEL)).toBe(false)
    })
  })

  describe('isModelField', () => {
    it('is true for model:-prefixed fields', () => {
      expect(isModelField(`${MODEL_FIELD_PREFIX}answer`)).toBe(true)
    })

    it('is true for the ALL_MODEL specifier', () => {
      expect(isModelField(FIELD_SPECIFIERS.ALL_MODEL)).toBe(true)
    })

    it('treats unprefixed fields as model fields (backward compat)', () => {
      expect(isModelField('legacy_unprefixed')).toBe(true)
    })

    it('is false for human-prefixed fields and the ALL_HUMAN specifier', () => {
      expect(isModelField(`${HUMAN_FIELD_PREFIX}answer`)).toBe(false)
      expect(isModelField(FIELD_SPECIFIERS.ALL_HUMAN)).toBe(false)
    })
  })

  describe('getBaseFieldName', () => {
    it('strips the model: prefix', () => {
      expect(getBaseFieldName(`${MODEL_FIELD_PREFIX}answer`)).toBe('answer')
    })

    it('strips the human: prefix', () => {
      expect(getBaseFieldName(`${HUMAN_FIELD_PREFIX}rating`)).toBe('rating')
    })

    it('returns unprefixed fields unchanged', () => {
      expect(getBaseFieldName('plain')).toBe('plain')
    })
  })
})

describe('getDimensionDisplayName - type-specific branch', () => {
  it('returns the type-specific display name when the dimension is known', () => {
    // boundary_accuracy is a key of TYPE_SPECIFIC_DIMENSIONS.
    expect(getDimensionDisplayName('boundary_accuracy')).toBe(
      'Boundary Accuracy'
    )
  })

  it('falls back to capitalize+underscore-replace for unknown dimensions', () => {
    expect(getDimensionDisplayName('helpfulness')).toBe('Helpfulness')
    expect(getDimensionDisplayName('some_custom_dim')).toBe('Some custom dim')
  })
})

describe('getFieldDisplayName - unstructured response branch', () => {
  it('labels model:__response__ as the unstructured model response', () => {
    expect(getFieldDisplayName('model:__response__')).toBe(
      'Model Response (unstructured)'
    )
  })

  it('labels bare __response__ as the unstructured model response', () => {
    expect(getFieldDisplayName('__response__')).toBe(
      'Model Response (unstructured)'
    )
  })

  it('still resolves the ALL_MODEL / ALL_HUMAN specifiers', () => {
    expect(getFieldDisplayName(FIELD_SPECIFIERS.ALL_MODEL)).toBe(
      'All model responses'
    )
    expect(getFieldDisplayName(FIELD_SPECIFIERS.ALL_HUMAN)).toBe(
      'All human annotations'
    )
  })

  it('returns a regular field name unchanged', () => {
    expect(getFieldDisplayName('my_field')).toBe('my_field')
  })
})

describe('isSpecialFieldValue', () => {
  it('returns false for non-special values', () => {
    expect(isSpecialFieldValue('model:__response__')).toBe(false)
  })
})

describe('metric scale / summable / immediate-eligible accessors', () => {
  it('reads display_scale from a registered metric', () => {
    // bleu is declared with display_scale '0-1'.
    expect(getMetricScale('bleu')).toBe('0-1')
  })

  it('defaults display_scale to 0-1 for an unknown metric', () => {
    expect(getMetricScale('totally_unknown_metric')).toBe('0-1')
  })

  it('reads summable=true for additive metrics', () => {
    // exact_match is declared summable: true.
    expect(getMetricSummable('exact_match')).toBe(true)
  })

  it('reads summable=false for ratio metrics', () => {
    expect(getMetricSummable('bleu')).toBe(false)
  })

  it('defaults summable to false for an unknown metric', () => {
    expect(getMetricSummable('totally_unknown_metric')).toBe(false)
  })

  it('returns false for heavy metrics flagged immediate_eligible:false', () => {
    // bertscore loads a transformer model -> immediate_eligible: false.
    expect(isMetricImmediateEligible('bertscore')).toBe(false)
  })

  it('returns true for metrics without the flag', () => {
    expect(isMetricImmediateEligible('bleu')).toBe(true)
  })

  it('defaults unknown metrics to immediate-eligible', () => {
    expect(isMetricImmediateEligible('totally_unknown_metric')).toBe(true)
  })
})

describe('metric registry extension points', () => {
  const extMetricKey = 'ext_test_metric_unique'

  it('registerMetric makes the metric resolvable via getMetricDefinitions', () => {
    const def: AvailableMetric = {
      name: extMetricKey,
      display_name: 'Extended Test Metric',
      description: 'registered by test',
      category: 'Extended Category',
      status: 'beta',
      supports_parameters: false,
      display_scale: '0-18',
      summable: true,
      immediate_eligible: false,
    }
    registerMetric(extMetricKey, def)

    const all = getMetricDefinitions()
    expect(all[extMetricKey]).toEqual(def)
    // Core metrics still present alongside extended ones.
    expect(all.bleu).toBe(METRIC_DEFINITIONS.bleu)

    // Accessors read through to the registered definition.
    expect(getMetricScale(extMetricKey)).toBe('0-18')
    expect(getMetricSummable(extMetricKey)).toBe(true)
    expect(isMetricImmediateEligible(extMetricKey)).toBe(false)
  })

  it('registerMetricGroup merges metrics into an existing same-named core group', () => {
    registerMetricGroup({
      name: 'Lexical Metrics', // matches a core group
      description: 'ignored on merge',
      metrics: ['exact_match', 'ext_lexical_metric'], // exact_match already present
    })

    const groups = getGroupedMetrics()
    const lexical = groups.find((g) => g.name === 'Lexical Metrics')
    expect(lexical).toBeDefined()
    // The new metric is appended; the duplicate exact_match is NOT added twice.
    expect(lexical!.metrics).toContain('ext_lexical_metric')
    expect(
      lexical!.metrics.filter((m) => m === 'exact_match')
    ).toHaveLength(1)
    // Core description preserved (not overwritten by the merged group).
    expect(lexical!.description).toBe('String and surface-level matching')
  })

  it('registerMetricGroup appends a brand-new group not matching any core group', () => {
    registerMetricGroup({
      name: 'Brand New Extended Group',
      description: 'a wholly new group',
      metrics: ['new_group_metric'],
    })

    const groups = getGroupedMetrics()
    const fresh = groups.find((g) => g.name === 'Brand New Extended Group')
    expect(fresh).toBeDefined()
    expect(fresh!.metrics).toEqual(['new_group_metric'])
  })

  it('getGroupedMetrics returns copies (does not mutate the core GROUPED_METRICS)', () => {
    const groups = getGroupedMetrics()
    const lexical = groups.find((g) => g.name === 'Lexical Metrics')!
    const before = lexical.metrics.length
    lexical.metrics.push('mutation_probe')
    // Re-fetch: the pushed probe must not have leaked into the shared source.
    const again = getGroupedMetrics().find(
      (g) => g.name === 'Lexical Metrics'
    )!
    expect(again.metrics).not.toContain('mutation_probe')
    expect(again.metrics.length).toBe(before)
  })
})

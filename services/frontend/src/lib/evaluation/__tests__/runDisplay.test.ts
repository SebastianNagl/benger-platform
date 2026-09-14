/**
 * Display helpers of the evaluation run page. The translations come from the
 * real German locale so a test reads the sentence a user sees.
 */
import {
  bareMetricName,
  configDisplayLabel,
  describeConfigMatchReason,
  fieldSelectorLabel,
  formatMetricNumber,
  isSidecarMetricKey,
  metricDisplayLabel,
  metricKeyConfigId,
  parseSampleFieldKey,
  readableSampleValue,
  runStatusLabel,
} from '../runDisplay'

const de = require('../../../locales/de/common.json')

function t(key: string, vars?: Record<string, unknown>): string {
  let value: unknown = key
    .split('.')
    .reduce<any>((node, part) => (node == null ? node : node[part]), de)
  if (typeof value !== 'string') return key
  for (const [name, v] of Object.entries(vars ?? {})) {
    value = (value as string).split(`{${name}}`).join(String(v))
  }
  return value as string
}

const registry = {
  llm_judge_rubric: {
    name: 'llm_judge_rubric',
    display_name: 'Bewertungsbogen (LLM Judge)',
    description: '',
    category: 'LLM-as-Judge',
    status: 'stable' as const,
    supports_parameters: true,
    display_scale: '0-1' as const,
  },
  llm_judge_rubric_grade_points: {
    name: 'llm_judge_rubric_grade_points',
    display_name: 'Notenpunkte (Bewertungsbogen)',
    description: '',
    category: 'LLM-as-Judge',
    status: 'stable' as const,
    supports_parameters: false,
    display_scale: '0-18' as const,
  },
}

describe('metric keys', () => {
  it.each([
    [
      'cfg|human:loesung|task.musterloesung|llm_judge_rubric',
      'llm_judge_rubric',
    ],
    ['cfg:answer:gt:bleu', 'bleu'],
    ['exact_match', 'exact_match'],
  ])('%s has the bare name %s', (key, bare) => {
    expect(bareMetricName(key)).toBe(bare)
  })

  it('reads the config id of composite keys only', () => {
    expect(metricKeyConfigId('cfg|a|b|m')).toBe('cfg')
    expect(metricKeyConfigId('cfg:a:b:m')).toBe('cfg')
    expect(metricKeyConfigId('exact_match')).toBeNull()
  })

  it.each([
    'raw_score',
    'cfg|p|r|raw_score',
    'llm_judge_rubric_passed',
    'llm_judge_rubric_details',
    'llm_judge_rubric_raw',
  ])('hides the companion key %s', (key) => {
    expect(isSidecarMetricKey(key)).toBe(true)
  })

  it.each(['llm_judge_rubric', 'llm_judge_rubric_grade_points', 'rouge_1'])(
    'keeps the result key %s',
    (key) => {
      expect(isSidecarMetricKey(key)).toBe(false)
    },
  )

  it('labels a metric from the registry, else in words', () => {
    expect(metricDisplayLabel('cfg|p|r|llm_judge_rubric', registry)).toBe(
      'Bewertungsbogen (LLM Judge)',
    )
    expect(metricDisplayLabel('llm_judge_rubric_grade_points', registry)).toBe(
      'Notenpunkte (Bewertungsbogen)',
    )
    expect(metricDisplayLabel('some_new_metric', registry)).toBe(
      'Some New Metric',
    )
  })

  it('formats Notenpunkte with one decimal and other scores with three', () => {
    expect(
      formatMetricNumber('llm_judge_rubric_grade_points', 11, registry),
    ).toBe('11.0')
    expect(formatMetricNumber('llm_judge_rubric', 0.7, registry)).toBe('0.700')
  })
})

describe('sample field keys', () => {
  it('splits the worker key into config, prediction and reference', () => {
    expect(
      parseSampleFieldKey(
        'structured-rubric-paid|human:loesung|task.musterloesung',
      ),
    ).toEqual({
      configId: 'structured-rubric-paid',
      predictionField: 'human:loesung',
      referenceField: 'task.musterloesung',
    })
  })

  it('keeps a plain field name as the prediction field', () => {
    expect(parseSampleFieldKey('classification')).toEqual({
      configId: null,
      predictionField: 'classification',
      referenceField: null,
    })
  })

  it('names field selectors without their prefixes', () => {
    expect(fieldSelectorLabel('human:loesung', t)).toBe('loesung')
    expect(fieldSelectorLabel('model:answer', t)).toBe('answer')
    expect(fieldSelectorLabel('task.musterloesung', t)).toBe('musterloesung')
    expect(fieldSelectorLabel('__all_model__', t)).toBe(
      t('evaluationBuilder.fields.allModelResponses'),
    )
  })

  it('names a config by its display name, else by its metric', () => {
    const configs = [
      { id: 'a', display_name: 'Bewertungsbogen (gpt-5.4-mini)', metric: 'x' },
      { id: 'b', metric: 'exact_match' },
    ]
    expect(configDisplayLabel('a', configs)).toBe(
      'Bewertungsbogen (gpt-5.4-mini)',
    )
    expect(configDisplayLabel('b', configs)).toBe('Exact Match')
    expect(configDisplayLabel('missing', configs, 'exact_match')).toBe(
      'Exact Match',
    )
    expect(configDisplayLabel(null, configs)).toBeNull()
  })
})

describe('run status', () => {
  it('is localized for known statuses', () => {
    expect(runStatusLabel('completed', t)).toBe('Abgeschlossen')
    expect(runStatusLabel('failed', t)).toBe('Fehlgeschlagen')
    expect(runStatusLabel('running', t)).toBe('Läuft')
  })

  it('shows an unknown status as stored', () => {
    expect(runStatusLabel('mystery', t)).toBe('mystery')
  })
})

describe('config match reasons', () => {
  const rec = (reason: string | null, counts?: object) => ({
    metric: 'llm_judge_rubric',
    reason,
    subject_counts: counts as any,
  })

  it('names the submitted answers a model-side config could grade', () => {
    const sentence = describeConfigMatchReason(
      rec('no_generations', { generations: 0, annotations: 3 }),
      t,
    )
    expect(sentence).toContain('3 eingereichte Antwort(en)')
    expect(sentence).toContain('human:loesung')
  })

  it('says there is nothing on either side when both counts are zero', () => {
    expect(
      describeConfigMatchReason(
        rec('no_generations', { generations: 0, annotations: 0 }),
        t,
      ),
    ).toContain('nichts zu bewerten')
    expect(
      describeConfigMatchReason(
        rec('no_annotations', { generations: 0, annotations: 0 }),
        t,
      ),
    ).toContain('nichts zu bewerten')
  })

  it('names the generations a human-side config could grade', () => {
    expect(
      describeConfigMatchReason(
        rec('no_annotations', { generations: 2, annotations: 0 }),
        t,
      ),
    ).toContain('2 Modellantwort(en)')
  })

  it('keeps the general advice for runs recorded before the counts', () => {
    expect(describeConfigMatchReason(rec('no_generations'), t)).toBe(
      t('evaluations.detail.matchReasons.noGenerations'),
    )
  })

  it.each([
    'generation_filters_excluded_all',
    'all_annotations_cancelled',
    'annotator_filter_excluded_all',
    'no_prediction_fields',
    'classifier_unavailable',
    'other',
  ])('phrases %s in German', (reason) => {
    const sentence = describeConfigMatchReason(rec(reason), t)
    expect(sentence).toBeTruthy()
    expect(sentence).not.toContain('evaluations.detail')
  })

  it('returns null for a matched config and for an unknown code', () => {
    expect(describeConfigMatchReason(rec(null), t)).toBeNull()
    expect(describeConfigMatchReason(rec('brand_new_code'), t)).toBeNull()
  })
})

describe('readable sample values', () => {
  it('shows a string as it is, without quotes', () => {
    expect(readableSampleValue('Die Klage ist\n  zulässig.')).toEqual({
      text: 'Die Klage ist\n  zulässig.',
      isStructured: false,
    })
  })

  it('drops empty Word bookmark anchors', () => {
    expect(
      readableSampleValue('<a id="_Toc123"></a>Gliederung <a id="x" ></a>A')
        .text,
    ).toBe('Gliederung A')
  })

  it('unwraps a single-string wrapper', () => {
    expect(readableSampleValue({ text: 'Musterlösung' })).toEqual({
      text: 'Musterlösung',
      isStructured: false,
    })
  })

  it('pretty-prints structured values', () => {
    const result = readableSampleValue({ value: 'A', label: 'Option A' })
    expect(result.isStructured).toBe(true)
    expect(result.text).toContain('"value": "A"')
  })

  it('handles empty and scalar values', () => {
    expect(readableSampleValue(null).text).toBe('')
    expect(readableSampleValue(undefined).text).toBe('')
    expect(readableSampleValue(3).text).toBe('3')
    expect(readableSampleValue(false).text).toBe('false')
  })
})

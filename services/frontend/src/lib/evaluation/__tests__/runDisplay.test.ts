/**
 * Display helpers of the evaluation run page. The translations come from the
 * real German locale so a test reads the sentence a user sees.
 */
import {
  bareMetricName,
  configDisplayLabel,
  configMetricMean,
  describeBillingBlock,
  describeConfigMatchReason,
  fieldSelectorLabel,
  formatMetricNumber,
  headerForField,
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

describe('field headers from the label config', () => {
  const labelConfig = `<View>
  <Header value="Gliederung"/>
  <Gliederung name="gliederung" toName="sachverhalt"/>
  <Header value="Lösung"/>
  <Loesung name="loesung" toName="sachverhalt"
           linkedTo="gliederung"/>
  <TextArea name="notiz" toName="sachverhalt"/>
</View>`
  const t = (key: string) => key

  it('finds the header directly preceding a field', () => {
    expect(headerForField(labelConfig, 'loesung')).toBe('Lösung')
    expect(headerForField(labelConfig, 'gliederung')).toBe('Gliederung')
  })

  it('returns null for a field without its own header or without a config', () => {
    expect(headerForField(labelConfig, 'notiz')).toBeNull()
    expect(headerForField(labelConfig, 'missing')).toBeNull()
    expect(headerForField(null, 'loesung')).toBeNull()
  })

  it('labels a field selector by its header, else by its bare name', () => {
    expect(fieldSelectorLabel('human:loesung', t, labelConfig)).toBe('Lösung')
    expect(fieldSelectorLabel('human:notiz', t, labelConfig)).toBe('notiz')
    expect(fieldSelectorLabel('human:loesung', t)).toBe('loesung')
  })
})

describe('readableSampleValue on converted .docx text', () => {
  it('drops Markdown escapes and bold markers', () => {
    expect(
      readableSampleValue(
        '__Lösungshinweise__\n\nA\\. Zulässigkeit\n\nPolizei\\- und Sicherheitsrecht \\(PAG\\)',
      ).text,
    ).toBe(
      'Lösungshinweise\n\nA. Zulässigkeit\n\nPolizei- und Sicherheitsrecht (PAG)',
    )
  })

  it('keeps underscores and asterisks that are not markers', () => {
    expect(readableSampleValue('snake_case und 2 * 3').text).toBe(
      'snake_case und 2 * 3',
    )
    expect(readableSampleValue('**fett** und __auch__').text).toBe(
      'fett und auch',
    )
    // A converted bold span that is empty or crosses a line break.
    expect(
      readableSampleValue('__Probeklausur  \n__\n\n__Lösungshinweise__').text,
    ).toBe('Probeklausur  \n\n\nLösungshinweise')
  })
})

describe('configMetricMean', () => {
  const results = {
    paid: {
      'human:loesung_vs_task.musterloesung': {
        llm_judge_rubric: 0.53,
        raw_score: 0.53,
      },
      'human:gliederung_vs_task.musterloesung': { llm_judge_rubric: 0.47 },
    },
    empty: { pair: { other: 1 } },
  }

  it('averages the metric over the config field pairs', () => {
    expect(configMetricMean(results, 'paid', 'llm_judge_rubric')).toBeCloseTo(
      0.5,
    )
  })

  it('is null without values, config or metric', () => {
    expect(configMetricMean(results, 'empty', 'llm_judge_rubric')).toBeNull()
    expect(configMetricMean(results, 'missing', 'llm_judge_rubric')).toBeNull()
    expect(configMetricMean(undefined, 'paid', 'llm_judge_rubric')).toBeNull()
    expect(configMetricMean(results, 'paid', '')).toBeNull()
  })
})

describe('describeBillingBlock', () => {
  it('phrases each billing refusal', () => {
    expect(describeBillingBlock('billing_blocked:org_key_missing', t)).toBe(
      'Die Organisation, über deren Lernplattform diese Klausur läuft, hat keinen API-Schlüssel für die gewählten Bewertungsmodelle hinterlegt. Die KI-Bewertung wurde deshalb nicht gestartet.',
    )
    expect(describeBillingBlock('billing_blocked:org_not_paying', t)).toContain(
      'stellt keine API-Schlüssel bereit',
    )
    expect(
      describeBillingBlock('billing_blocked:connection_removed', t),
    ).toContain('besteht nicht mehr')
    expect(
      describeBillingBlock('billing_blocked:billing_check_failed', t),
    ).toContain('später erneut')
    expect(describeBillingBlock('billing_blocked:toString', t)).toBe(
      'Die Abrechnung hat die KI-Bewertung abgelehnt.',
    )
  })

  it('ignores every other error message', () => {
    expect(describeBillingBlock('worker crashed', t)).toBeNull()
    expect(describeBillingBlock(null, t)).toBeNull()
    expect(describeBillingBlock(undefined, t)).toBeNull()
  })
})

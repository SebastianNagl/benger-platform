import * as fs from 'fs'
import * as path from 'path'

import {
  describeEvaluationConfigWarning,
  describeEvaluationConfigWarnings,
} from '../configWarnings'

const t = (key: string, vars?: Record<string, unknown>) =>
  vars ? `${key} ${JSON.stringify(vars)}` : key

const configs = [
  { id: 'cfg1', display_name: 'Bewertungsbogen', metric: 'llm_judge_rubric' },
]

describe('describeEvaluationConfigWarning', () => {
  it('phrases a model-side config in a project of answers from its fields', () => {
    expect(
      describeEvaluationConfigWarning(
        {
          code: 'no_matching_subjects',
          config_id: 'cfg1',
          metric: 'llm_judge_rubric',
          side: 'model',
          generations: 0,
          annotations: 2,
          selectors: ['__all_model__'],
          message: 'English from the server',
        },
        configs,
        t,
      ),
    ).toBe(
      'evaluationBuilder.warnings.modelSideWithoutGenerations {"name":"Bewertungsbogen","fields":" (__all_model__)","count":2}',
    )
  })

  it('phrases a human-side config in a project of generations', () => {
    expect(
      describeEvaluationConfigWarning(
        {
          code: 'no_matching_subjects',
          config_id: 'cfg1',
          side: 'human',
          generations: 3,
          annotations: 0,
          selectors: ['human:answer', '__all_human__'],
        },
        configs,
        t,
      ),
    ).toBe(
      'evaluationBuilder.warnings.humanSideWithoutAnswers {"name":"Bewertungsbogen","fields":" (human:answer, __all_human__)","count":3}',
    )
  })

  it('names an unknown config by its id and leaves out missing fields', () => {
    expect(
      describeEvaluationConfigWarning(
        { code: 'no_matching_subjects', config_id: 'other', side: 'model' },
        configs,
        t,
      ),
    ).toBe(
      'evaluationBuilder.warnings.modelSideWithoutGenerations {"name":"other","fields":"","count":0}',
    )
    expect(
      describeEvaluationConfigWarning(
        { code: 'no_reference_fields', metric: 'rouge' },
        configs,
        t,
      ),
    ).toBe('evaluationBuilder.warnings.noReferenceFields {"name":"rouge"}')
  })

  it("falls back to the server's message for a code it does not know", () => {
    expect(
      describeEvaluationConfigWarning(
        { code: 'something_new', message: 'Server sentence.' },
        configs,
        t,
      ),
    ).toBe('Server sentence.')
    expect(
      describeEvaluationConfigWarning({ code: 'something_new' }, configs, t),
    ).toBe('')
  })
})

describe('describeEvaluationConfigWarnings', () => {
  it('describes each warning and drops empty or malformed entries', () => {
    expect(describeEvaluationConfigWarnings(undefined, configs, t)).toEqual([])
    expect(
      describeEvaluationConfigWarnings(
        [
          null,
          'text',
          { code: 'unknown' },
          { code: 'no_reference_fields', config_id: 'cfg1' },
        ],
        configs,
        t,
      ),
    ).toEqual([
      'evaluationBuilder.warnings.noReferenceFields {"name":"Bewertungsbogen"}',
    ])
  })
})

describe('warning phrases in the locales', () => {
  const read = (lang: string) =>
    JSON.parse(
      fs.readFileSync(
        path.resolve(__dirname, `../../../locales/${lang}/common.json`),
        'utf8',
      ),
    ).evaluationBuilder.warnings as Record<string, string>
  const placeholders = (text: string) =>
    Array.from(text.matchAll(/\{(\w+)\}/g), (m) => m[1]).sort()

  it('exist in German and English with the same placeholders', () => {
    const de = read('de')
    const en = read('en')
    for (const key of [
      'noReferenceFields',
      'modelSideWithoutGenerations',
      'humanSideWithoutAnswers',
    ]) {
      expect(typeof de[key]).toBe('string')
      expect(typeof en[key]).toBe('string')
      expect(placeholders(de[key])).toEqual(placeholders(en[key]))
    }
    expect(placeholders(de.modelSideWithoutGenerations)).toEqual([
      'count',
      'fields',
      'name',
    ])
  })
})

/**
 * The metric catalogue renders German on German pages.
 *
 * Component tests mock `t`, so a mistyped key or a renderer that prints the
 * English literal directly passes them. This checks the catalogue's keys
 * against both locale files and the renderers' source for literal output.
 */
import * as fs from 'fs'
import * as path from 'path'

import {
  GROUPED_METRICS,
  METRIC_DEFINITIONS,
  metricDescription,
  metricDisplayName,
  metricGroupDescription,
  metricGroupLabel,
} from '@/lib/api/evaluation-types'

const src = (rel: string) =>
  fs.readFileSync(path.resolve(__dirname, '../../..', rel), 'utf8')
const locale = (lang: string) => JSON.parse(src(`locales/${lang}/common.json`))
const lookup = (tree: any, key: string) =>
  key
    .split('.')
    .reduce((node, part) => (node == null ? node : node[part]), tree)
const translator =
  (lang: string) =>
  (key: string, fallback?: string): string => {
    const value = lookup(locale(lang), key)
    return typeof value === 'string' ? value : (fallback ?? key)
  }

const RENDERERS = [
  'components/projects/wizard/StepEvaluationMethods.tsx',
  'components/evaluation/builder/MetricStep.tsx',
  'components/evaluation/MetricSelector.tsx',
]

describe('metric catalogue i18n keys', () => {
  const catalogueKeys = [
    ...GROUPED_METRICS.flatMap((g) => [g.nameKey, g.descriptionKey]),
    ...Object.values(METRIC_DEFINITIONS).flatMap((d) => [
      d.displayNameKey,
      d.descriptionKey,
    ]),
  ]

  it('gives every core group and metric a name and description key', () => {
    expect(catalogueKeys.length).toBe(
      2 * (GROUPED_METRICS.length + Object.keys(METRIC_DEFINITIONS).length),
    )
    expect(catalogueKeys.filter((k) => typeof k !== 'string')).toEqual([])
  })

  it.each(['de', 'en'])('resolves every catalogue key in %s', (lang) => {
    const tree = locale(lang)
    const missing = catalogueKeys.filter(
      (key) => typeof lookup(tree, key as string) !== 'string',
    )
    expect(missing).toEqual([])
  })

  it.each(['de', 'en'])(
    'resolves every key the metric selector renders in %s',
    (lang) => {
      const keys = Array.from(
        src('components/evaluation/MetricSelector.tsx').matchAll(
          /'(evaluation\.(?:methodSelector|metricSelector)\.[\w.]+)'/g,
        ),
        (m) => m[1],
      )
      expect(keys).toEqual(
        expect.arrayContaining([
          'evaluation.methodSelector.category.llmJudge',
          'evaluation.metricSelector.presets.allAvailable',
        ]),
      )
      const tree = locale(lang)
      expect(
        keys.filter((key) => typeof lookup(tree, key) !== 'string'),
      ).toEqual([])
    },
  )

  it('resolves the labeling page position string in both locales', () => {
    expect(src('components/labeling/LabelingInterface.tsx')).toContain(
      "t('annotation.interface.taskPosition'",
    )
    for (const lang of ['de', 'en']) {
      const value = lookup(locale(lang), 'annotation.interface.taskPosition')
      expect(value).toContain('{current}')
      expect(value).toContain('{total}')
    }
  })

  it('renders the catalogue the owner saw in English in German', () => {
    const t = translator('de')
    const lexical = GROUPED_METRICS.find((g) => g.name === 'Lexical Metrics')!
    const llm = GROUPED_METRICS.find((g) => g.name === 'LLM-as-Judge')!
    expect(metricGroupLabel(lexical, t)).toBe('Lexikalische Metriken')
    expect(metricGroupDescription(lexical, t)).toBe(
      'Zeichenketten- und Oberflächenabgleich',
    )
    expect(metricGroupDescription(llm, t)).not.toContain('judge_config')
    expect(metricDisplayName(METRIC_DEFINITIONS.exact_match, t)).toBe(
      'Exakte Übereinstimmung',
    )
    expect(metricDescription(METRIC_DEFINITIONS.exact_match, t)).toBe(
      'Exakter Zeichenkettenabgleich',
    )
  })

  it('falls back to the literal when a key is absent or unresolved', () => {
    const t = translator('de')
    const group = {
      name: 'Extended Judges',
      description: 'Registered by an overlay',
      metrics: [],
    }
    expect(metricGroupLabel(group, t)).toBe('Extended Judges')
    expect(metricGroupLabel({ ...group, nameKey: 'no.such.key' }, t)).toBe(
      'Extended Judges',
    )
    expect(
      metricGroupDescription({ ...group, descriptionKey: 'no.such.key' }, t),
    ).toBe('Registered by an overlay')
    const def = {
      ...METRIC_DEFINITIONS.accuracy,
      displayNameKey: undefined,
      descriptionKey: undefined,
    }
    expect(metricDisplayName(def, t)).toBe('Accuracy')
    expect(metricDescription(def, t)).toBe('Percentage of correct predictions')
  })

  it.each(RENDERERS)('%s prints no catalogue literal directly', (file) => {
    const source = src(file)
    // JSX children only: `key={group.name}` is an identity, not a label.
    expect(source).not.toMatch(
      />\s*\{\s*(?:group|category)\.(?:name|description)\s*\}/,
    )
    expect(source).not.toMatch(
      />\s*\{\s*def\.(?:display_name|description)\s*\}/,
    )
  })
})

/**
 * Every i18n key the evaluation run page renders exists in both locales.
 *
 * The component tests mock `t` to return the key, so a mistyped key passes
 * them and shows the raw key on a real page. This reads the static keys
 * straight from the page and table source and collects the dynamic ones
 * (status labels, match reasons) by calling the helpers that build them.
 */
import {
  describeBillingBlock,
  describeConfigMatchReason,
  fieldSelectorLabel,
  runStatusLabel,
} from '@/lib/evaluation/runDisplay'
import * as fs from 'fs'
import * as path from 'path'

const read = (relative: string) =>
  fs.readFileSync(path.resolve(__dirname, relative), 'utf8')

const sources = [
  read('../page.tsx'),
  read('../../../../components/evaluation/SampleResultsTable.tsx'),
]

const locale = (lang: string) =>
  JSON.parse(read(`../../../../locales/${lang}/common.json`))

const lookup = (tree: any, key: string) =>
  key
    .split('.')
    .reduce((node, part) => (node == null ? node : node[part]), tree)

function dynamicKeys(): string[] {
  const seen = new Set<string>()
  const record = (key: string) => {
    seen.add(key)
    return key
  }
  for (const status of [
    'completed',
    'failed',
    'running',
    'pending',
    'queued',
    'cancelled',
    'paused',
  ]) {
    runStatusLabel(status, record)
  }
  const reasons = [
    'no_generations',
    'generation_filters_excluded_all',
    'no_annotations',
    'all_annotations_cancelled',
    'annotator_filter_excluded_all',
    'no_prediction_fields',
    'classifier_unavailable',
    'other',
  ]
  const countVariants = [
    undefined,
    { generations: 0, annotations: 0 },
    { generations: 2, annotations: 0 },
    { generations: 0, annotations: 2 },
  ]
  for (const reason of reasons) {
    for (const subject_counts of countVariants) {
      describeConfigMatchReason({ metric: 'm', reason, subject_counts }, record)
    }
  }
  for (const reason of [
    'org_not_paying',
    'org_key_missing',
    'connection_removed',
    'billing_check_failed',
    'something_else',
  ]) {
    describeBillingBlock(`billing_blocked:${reason}`, record)
  }
  fieldSelectorLabel('__all_model__', record)
  fieldSelectorLabel('__all_human__', record)
  return Array.from(seen)
}

describe('evaluation run page i18n keys', () => {
  const staticKeys = Array.from(
    new Set(
      sources.flatMap((source) =>
        Array.from(
          source.matchAll(/\bt\(\s*'((?:\w+\.)+\w+)'/g),
          (match) => match[1],
        ),
      ),
    ),
  )
  const keys = [...staticKeys, ...dynamicKeys()]

  it('finds the keys it checks', () => {
    expect(keys).toEqual(
      expect.arrayContaining([
        'evaluations.detail.openProject',
        'evaluations.detail.technicalDetails',
        'evaluation.sampleResultsTable.showMore',
        'evaluations.detail.statusLabels.completed',
        'evaluations.detail.matchReasons.noGenerationsWithAnswers',
        'evaluations.detail.matchReasons.noAnnotationsNothing',
        'evaluations.detail.billingBlocked.orgKeyMissing',
        'evaluations.detail.billingBlocked.other',
      ]),
    )
  })

  it.each(['de', 'en'])('resolves every key in %s', (lang) => {
    const tree = locale(lang)
    const missing = keys.filter((key) => typeof lookup(tree, key) !== 'string')
    expect(missing).toEqual([])
  })
})

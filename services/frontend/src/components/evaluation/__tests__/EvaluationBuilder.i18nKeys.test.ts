/**
 * Every i18n key the evaluation builder renders exists in both locales.
 *
 * The component tests mock `t` to return the key, so a mistyped key passes
 * them and shows the raw key on a real page. This reads the keys straight
 * from the component sources: the builder and its dialog, including keys
 * kept in a lookup table (the step names) rather than passed to t() inline.
 */
import * as fs from 'fs'
import * as path from 'path'

const source = [
  '../EvaluationBuilder.tsx',
  '../builder/EvaluationMethodDialog.tsx',
]
  .map((file) => fs.readFileSync(path.resolve(__dirname, file), 'utf8'))
  .join('\n')
const locale = (lang: string) =>
  JSON.parse(
    fs.readFileSync(
      path.resolve(__dirname, `../../../locales/${lang}/common.json`),
      'utf8',
    ),
  )
const lookup = (tree: any, key: string) =>
  key
    .split('.')
    .reduce((node, part) => (node == null ? node : node[part]), tree)

describe('EvaluationBuilder i18n keys', () => {
  const keys = Array.from(
    new Set(
      Array.from(
        source.matchAll(
          /'((?:evaluationBuilder|evaluation\.metricParams)\.[\w.]+)'/g,
        ),
        (m) => m[1],
      ),
    ),
  )

  it('finds the keys it checks', () => {
    expect(keys).toEqual(
      expect.arrayContaining([
        'evaluationBuilder.list.disabled',
        'evaluationBuilder.placeholders.judgeModel',
        'evaluation.metricParams.rouge.rougeL',
        'evaluationBuilder.parameters.factcc.method',
        'evaluationBuilder.nav.review',
        'evaluationBuilder.discard.keepEditing',
      ]),
    )
  })

  it.each(['de', 'en'])('resolves every key in %s', (lang) => {
    const tree = locale(lang)
    const missing = keys.filter((key) => typeof lookup(tree, key) !== 'string')
    expect(missing).toEqual([])
  })

  it('renders no placeholder as an English literal', () => {
    expect(source).not.toMatch(/placeholder="Select /)
  })
})

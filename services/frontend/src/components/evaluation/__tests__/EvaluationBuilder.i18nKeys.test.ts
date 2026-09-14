/**
 * Every i18n key the evaluation builder renders exists in both locales.
 *
 * The component tests mock `t` to return the key, so a mistyped key passes
 * them and shows the raw key on a real page. This reads the keys straight
 * from the component source.
 */
import * as fs from 'fs'
import * as path from 'path'

const source = fs.readFileSync(
  path.resolve(__dirname, '../EvaluationBuilder.tsx'),
  'utf8',
)
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
          /\bt\(\s*'((?:evaluationBuilder|evaluation\.metricParams)\.[\w.]+)'/g,
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

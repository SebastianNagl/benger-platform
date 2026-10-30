/**
 * The Prompts card shows the judge prompts from the frontend mirrors in
 * evaluation-types.ts; the worker grades with its own Python literals. The
 * card is only worth something if both say the same, so this reads the
 * worker sources straight from the repo (like modelDefaults.drift.test.ts).
 * Python escapes literal braces as {{ }} for str.format(); the mirrors show
 * them as the model sees them.
 */
import * as fs from 'fs'
import * as path from 'path'

import {
  DEFAULT_PROMPT_TEMPLATES,
  JUDGE_FALLBACK_PROMPT_TEMPLATE,
  JUDGE_SYSTEM_PROMPT,
  RUBRIC_JUDGE_CLOSING_RULES,
  RUBRIC_JUDGE_SYSTEM_PROMPT,
} from '../evaluation-types'

const mlEvaluationDir = path.resolve(
  __dirname,
  '../../../../../workers/ml_evaluation',
)

const read = (file: string) =>
  fs.readFileSync(path.join(mlEvaluationDir, file), 'utf8')

function pythonTemplate(source: string, name: string): string {
  const match = source.match(new RegExp(`^${name} = """([\\s\\S]*?)"""`, 'm'))
  if (!match) throw new Error(`${name} not found`)
  return match[1].replace(/\{\{/g, '{').replace(/\}\}/g, '}').trim()
}

describe('judge prompt mirrors', () => {
  const prompts = read('llm_judge_prompts.py')
  const evaluator = read('llm_judge_evaluator.py')

  it.each([
    ['text', 'TEXT_EVALUATION_PROMPT'],
    ['choices', 'CHOICES_EVALUATION_PROMPT'],
    ['span_selection', 'SPAN_EVALUATION_PROMPT'],
    ['numeric', 'NUMERIC_EVALUATION_PROMPT'],
  ])('%s matches %s', (key, pythonName) => {
    expect(DEFAULT_PROMPT_TEMPLATES[key].template.trim()).toBe(
      pythonTemplate(prompts, pythonName),
    )
  })

  it('the fallback matches SINGLE_EVALUATION_PROMPT', () => {
    expect(JUDGE_FALLBACK_PROMPT_TEMPLATE.trim()).toBe(
      pythonTemplate(evaluator, 'SINGLE_EVALUATION_PROMPT'),
    )
  })

  it('the system prompt is the one the generic judge sends', () => {
    expect(evaluator).toContain(`system_prompt = "${JUDGE_SYSTEM_PROMPT}"`)
  })

  // The rubric constants are sent as they are (no str.format), so they are
  // compared without brace unescaping.
  it.each([
    ['RUBRIC_JUDGE_SYSTEM_PROMPT', RUBRIC_JUDGE_SYSTEM_PROMPT],
    ['RUBRIC_JUDGE_CLOSING_RULES', RUBRIC_JUDGE_CLOSING_RULES],
  ])('%s matches the worker', (pythonName, mirror) => {
    const match = evaluator.match(
      new RegExp(`^${pythonName} = """([\\s\\S]*?)"""`, 'm'),
    )
    expect(match?.[1]).toBe(mirror)
  })
})

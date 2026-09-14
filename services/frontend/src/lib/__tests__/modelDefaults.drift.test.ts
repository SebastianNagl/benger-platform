/**
 * The default judge model must be one model on both sides of the stack.
 *
 * The pickers start on DEFAULT_MODEL_ID. A judge config that names no model
 * grades with DEFAULT_JUDGE_MODEL_ID from services/shared/model_defaults.py.
 * The two drifted once: every picker showed gpt-5.4-mini while the worker
 * graded with gpt-4o, and nothing noticed. This reads the Python constant and
 * the model catalog straight from the repo.
 */
import * as fs from 'fs'
import * as path from 'path'

import { DEFAULT_MODEL_ID } from '../modelDefaults'

const servicesDir = path.resolve(__dirname, '../../../..')

describe('DEFAULT_MODEL_ID', () => {
  it('is the model the worker grades a judge config with when it names none', () => {
    const python = fs.readFileSync(
      path.join(servicesDir, 'shared/model_defaults.py'),
      'utf8',
    )
    const match = python.match(/^DEFAULT_JUDGE_MODEL_ID\s*=\s*"([^"]+)"/m)
    expect(match?.[1]).toBe(DEFAULT_MODEL_ID)
  })

  it('is the fallback of every worker path that grades with a judge', () => {
    const read = (file: string) =>
      fs.readFileSync(path.join(servicesDir, 'workers', file), 'utf8')
    const tasks = read('tasks.py')
    const judgeEvaluator = read('evaluation/judge_evaluator.py')
    expect(tasks).toContain(
      'params.get("judge_model") or DEFAULT_JUDGE_MODEL_ID',
    )
    expect(tasks).toContain(
      'judge_entry.get("judge_model_id") or DEFAULT_JUDGE_MODEL_ID',
    )
    expect(judgeEvaluator).toContain(
      'params.get("judge_model") or DEFAULT_JUDGE_MODEL_ID',
    )
    // A literal fallback next to the key is how the two drifted.
    for (const source of [tasks, judgeEvaluator]) {
      expect(source).not.toMatch(/get\("judge_model(_id)?",\s*"/)
    }
  })

  it('is an active row of the model catalog', () => {
    const lines = fs
      .readFileSync(
        path.join(servicesDir, 'shared/seeds/llm_models.yaml'),
        'utf8',
      )
      .split('\n')
    const isEntryStart = (line: string) => /^\s*- id:\s*\S/.test(line)
    const first = lines.findIndex(
      (line) =>
        isEntryStart(line) && line.trim() === `- id: ${DEFAULT_MODEL_ID}`,
    )
    expect(first).toBeGreaterThanOrEqual(0)
    const entry: string[] = []
    for (let i = first + 1; i < lines.length && !isEntryStart(lines[i]); i++) {
      entry.push(lines[i])
    }
    expect(entry.some((line) => /^\s*is_active:\s*true\s*$/.test(line))).toBe(
      true,
    )
  })
})

/**
 * Client of the project questionnaire routes
 * (`routers/projects/questionnaire.py`).
 */

import { QUESTIONNAIRE_TRIGGERS, questionnairesAPI } from '../questionnaires'

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
  },
}))

const client = () => require('@/lib/api').default

beforeEach(() => jest.clearAllMocks())

const result = [
  {
    from_name: 'difficulty',
    to_name: 'text',
    type: 'choices',
    value: { choices: ['hard'] },
  },
] as any

describe('questionnairesAPI', () => {
  it('names the three moments the API knows', () => {
    expect(QUESTIONNAIRE_TRIGGERS).toEqual([
      'before_task',
      'after_submit',
      'korrektur',
    ])
  })

  it('lists the questionnaires of a project past the GET cache', async () => {
    const page = { questionnaires: [], can_edit: true }
    client().get.mockResolvedValue(page)

    expect(await questionnairesAPI.list('p1')).toBe(page)
    expect(client().get).toHaveBeenCalledWith('/projects/p1/questionnaires', {
      cache: 'no-store',
    })
  })

  it('saves one moment with PUT on its trigger', async () => {
    const body = {
      enabled: true,
      config: '<View/>',
      required: false,
      frequency: 'once_per_task' as const,
    }
    client().put.mockResolvedValue({ trigger: 'after_submit', version: 2 })

    expect(await questionnairesAPI.save('p1', 'after_submit', body)).toEqual({
      trigger: 'after_submit',
      version: 2,
    })
    expect(client().put).toHaveBeenCalledWith(
      '/projects/p1/questionnaires/after_submit',
      body,
    )
  })

  it('validates a config without saving it', async () => {
    client().post.mockResolvedValue({ valid: false, errors: ['no View'] })

    expect(await questionnairesAPI.validate('p1', '<Choices/>')).toEqual({
      valid: false,
      errors: ['no View'],
    })
    expect(client().post).toHaveBeenCalledWith(
      '/projects/p1/questionnaires/validate',
      { config: '<Choices/>' },
    )
  })

  it('asks whether a moment is due, sending only the subject fields it has', async () => {
    client().get.mockResolvedValue({ due: true, questionnaire: null })

    expect(
      await questionnairesAPI.status('p1', 'after_submit', {
        task_id: 't1',
        annotation_id: 'a1',
        task_evaluation_id: undefined,
      }),
    ).toEqual({ due: true, questionnaire: null })
    expect(client().get).toHaveBeenCalledWith(
      '/projects/p1/questionnaires/after_submit/status?task_id=t1&annotation_id=a1',
      { cache: 'no-store' },
    )

    await questionnairesAPI.status('p1', 'korrektur', {
      task_evaluation_id: 'te 1&x',
    })
    expect(client().get).toHaveBeenLastCalledWith(
      '/projects/p1/questionnaires/korrektur/status?task_evaluation_id=te+1%26x',
      { cache: 'no-store' },
    )
  })

  it('leaves the query string off when the subject is empty', async () => {
    client().get.mockResolvedValue({ due: false, questionnaire: null })

    await questionnairesAPI.status('p1', 'before_task', {})
    expect(client().get).toHaveBeenCalledWith(
      '/projects/p1/questionnaires/before_task/status',
      { cache: 'no-store' },
    )
  })

  it('posts an answer with the rendered version', async () => {
    const stored = { id: 'r1', trigger: 'before_task', skipped: false }
    client().post.mockResolvedValue(stored)

    expect(
      await questionnairesAPI.answer(
        'p1',
        'before_task',
        { task_id: 't1' },
        result,
        3,
      ),
    ).toBe(stored)
    expect(client().post).toHaveBeenCalledWith(
      '/projects/p1/questionnaires/before_task/responses',
      { task_id: 't1', result, questionnaire_version: 3 },
    )
  })

  it('records a skip as an empty answer flagged skipped', async () => {
    client().post.mockResolvedValue({ id: 'r2', skipped: true })

    await questionnairesAPI.skip(
      'p1',
      'after_submit',
      { task_id: 't1', annotation_id: 'a1' },
      4,
    )
    expect(client().post).toHaveBeenCalledWith(
      '/projects/p1/questionnaires/after_submit/responses',
      {
        task_id: 't1',
        annotation_id: 'a1',
        result: [],
        skipped: true,
        questionnaire_version: 4,
      },
    )
  })

  it('builds the CSV export href for all moments or one', () => {
    expect(questionnairesAPI.csvUrl('p1')).toBe(
      '/api/projects/p1/questionnaire-responses/export.csv?trigger=all',
    )
    expect(questionnairesAPI.csvUrl('p1', 'korrektur')).toBe(
      '/api/projects/p1/questionnaire-responses/export.csv?trigger=korrektur',
    )
  })
})

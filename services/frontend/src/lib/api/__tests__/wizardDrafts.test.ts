/**
 * Client of the creation-wizard draft routes (CORE 2.55).
 */

import { wizardDraftErrorCode, wizardDraftsAPI } from '../wizardDrafts'

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    invalidateCache: jest.fn(),
  },
}))

const client = () => require('@/lib/api').default

beforeEach(() => jest.clearAllMocks())

describe('wizardDraftsAPI', () => {
  it('creates, lists and reads drafts (reads bypass the GET cache)', async () => {
    client().post.mockResolvedValue({ project_id: 'p1' })
    expect(
      await wizardDraftsAPI.create({ title: 'K', client_key: 'k' }),
    ).toEqual({
      project_id: 'p1',
    })
    expect(client().post).toHaveBeenCalledWith('/projects/wizard-drafts', {
      title: 'K',
      client_key: 'k',
    })

    client().get.mockResolvedValueOnce({ items: [{ project_id: 'p1' }] })
    expect(await wizardDraftsAPI.list()).toEqual([{ project_id: 'p1' }])
    expect(client().invalidateCache).toHaveBeenCalledWith(
      '/projects/wizard-drafts',
    )
    client().get.mockResolvedValueOnce(null)
    expect(await wizardDraftsAPI.list()).toEqual([])

    client().get.mockResolvedValueOnce({ project_id: 'p1', state_version: 3 })
    expect((await wizardDraftsAPI.get('p1')).state_version).toBe(3)
    expect(client().get).toHaveBeenLastCalledWith('/projects/p1/wizard-draft')
    expect(client().invalidateCache).toHaveBeenCalledWith(
      '/projects/p1/wizard-draft',
    )
  })

  it('saves, finishes and discards', async () => {
    client().put.mockResolvedValue({ state_version: 2 })
    await wizardDraftsAPI.save('p1', { if_version: 1, state: {} })
    expect(client().put).toHaveBeenCalledWith('/projects/p1/wizard-draft', {
      if_version: 1,
      state: {},
    })

    client().post.mockResolvedValue({ id: 'p1' })
    const body = { client_key: 'k', visibility: 'private' as const }
    expect(await wizardDraftsAPI.finish('p1', body)).toEqual({ id: 'p1' })
    expect(client().post).toHaveBeenCalledWith(
      '/projects/p1/wizard-draft/finish',
      body,
    )
    expect(client().invalidateCache).toHaveBeenCalledWith('/projects')

    client().delete.mockResolvedValue({})
    await wizardDraftsAPI.discard('p1')
    expect(client().delete).toHaveBeenCalledWith('/projects/p1/wizard-draft')
  })

  it('reads the draft tasks and replaces one', async () => {
    client().get.mockResolvedValueOnce({ items: [{ id: 't1' }] })
    expect(await wizardDraftsAPI.tasks('p1')).toEqual([{ id: 't1' }])
    expect(client().get).toHaveBeenLastCalledWith(
      '/projects/p1/wizard-draft/tasks',
    )
    client().get.mockResolvedValueOnce({})
    expect(await wizardDraftsAPI.tasks('p1')).toEqual([])

    client().put.mockResolvedValue({ id: 't1', archived_sheet_ids: ['s1'] })
    await wizardDraftsAPI.replaceTask('p1', 't1', { sv: 'neu' }, 'h')
    expect(client().put).toHaveBeenCalledWith(
      '/projects/p1/wizard-draft/tasks/t1',
      { data: { sv: 'neu' }, meta: {}, row_hash: 'h' },
    )
    await wizardDraftsAPI.replaceTask('p1', 't1', { sv: 'neu' }, 'h', {
      points: 20,
    })
    expect(client().put).toHaveBeenLastCalledWith(
      '/projects/p1/wizard-draft/tasks/t1',
      { data: { sv: 'neu' }, meta: { points: 20 }, row_hash: 'h' },
    )
  })
})

describe('wizardDraftErrorCode', () => {
  it('reads the coded detail of a failed request', () => {
    expect(
      wizardDraftErrorCode({
        response: { data: { detail: { code: 'draft_version_conflict' } } },
      }),
    ).toBe('draft_version_conflict')
    expect(
      wizardDraftErrorCode({ response: { data: { detail: 'text' } } }),
    ).toBeNull()
    expect(
      wizardDraftErrorCode({ response: { data: { detail: { code: 3 } } } }),
    ).toBeNull()
    expect(wizardDraftErrorCode(new Error('x'))).toBeNull()
    expect(wizardDraftErrorCode(null)).toBeNull()
  })
})

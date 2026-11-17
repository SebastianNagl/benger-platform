/**
 * useWizardDraft, driven directly: the organization target, a file as the
 * row source, cloud objects, the evaluation-config writes and the failure
 * paths the wizard suite does not reach.
 *
 * @jest-environment jsdom
 */

import {
  _resetWizardDraftRegistry,
  registerWizardDraftHook,
  registerWizardDraftPolicy,
} from '@/lib/extensions/wizardDraft'
import { act, renderHook } from '@testing-library/react'
import { INITIAL_WIZARD_DATA, type WizardData } from '../types'
import { useWizardDraft } from '../useWizardDraft'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key} ${JSON.stringify(vars)}` : key,
  }),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    update: jest.fn().mockResolvedValue({}),
    runNestedImportJob: jest.fn().mockResolvedValue({}),
    runCloudImportJobs: jest.fn().mockResolvedValue([]),
    bulkDeleteTasks: jest.fn().mockResolvedValue({}),
  },
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    put: jest.fn().mockResolvedValue({}),
    get: jest.fn().mockResolvedValue({ evaluation_configs: [] }),
    invalidateCache: jest.fn(),
  },
}))

jest.mock('@/lib/api/wizardDrafts', () => {
  const actual = jest.requireActual('@/lib/api/wizardDrafts')
  return {
    ...actual,
    wizardDraftsAPI: {
      create: jest.fn(),
      get: jest.fn(),
      save: jest.fn(),
      finish: jest.fn().mockResolvedValue({ id: 'p1' }),
      discard: jest.fn().mockResolvedValue(undefined),
      tasks: jest.fn().mockResolvedValue([]),
      replaceTask: jest.fn(),
      list: jest.fn().mockResolvedValue([]),
    },
  }
})

const draftsAPI = () => require('@/lib/api/wizardDrafts').wizardDraftsAPI
const projectsAPI = () => require('@/lib/api/projects').projectsAPI
const apiClient = () => require('@/lib/api/client').apiClient

const STEPS = ['projectInfo', 'dataImport', 'evaluation', 'rubric', 'settings']

const ORG_DATA: WizardData = {
  ...INITIAL_WIZARD_DATA,
  title: 'Klausur',
  features: {
    ...INITIAL_WIZARD_DATA.features,
    dataImport: true,
    evaluation: true,
    rubric: true,
  },
  visibility: 'organization',
  organizationIds: ['org-1', 'org-2'],
  organizationGroupIds: { 'org-1': 'grp-1' },
}

function coded(code: string, status = 409) {
  return Object.assign(new Error(code), {
    response: { status, data: { detail: { code, message: `${code} text` } } },
  })
}

function setup(data: WizardData = ORG_DATA) {
  const addToast = jest.fn()
  const confirm = jest.fn().mockResolvedValue(true)
  const updateWizardData = jest.fn()
  const hook = renderHook(
    ({ wizardData }) =>
      useWizardDraft({
        wizardData,
        replaceWizardData: jest.fn(),
        updateWizardData,
        stepIds: STEPS,
        currentStepId: 'projectInfo',
        goToStepId: jest.fn(),
        confirm,
        addToast,
        importTimeoutMs: 180000,
      }),
    { initialProps: { wizardData: data } },
  )
  return { ...hook, addToast, confirm, updateWizardData }
}

let version = 1
beforeEach(() => {
  jest.clearAllMocks()
  _resetWizardDraftRegistry()
  registerWizardDraftPolicy({ applies: () => true })
  window.history.replaceState(null, '', '/projects/create')
  version = 1
  draftsAPI().create.mockImplementation(async (body: any) => ({
    project_id: 'p1',
    title: body.title,
    kind: body.kind,
    client_key: body.client_key,
    state: body.state,
    state_version: 1,
    step_id: 'projectInfo',
    target_organization_id: body.target_organization_id,
    target_group_id: body.target_group_id,
  }))
  draftsAPI().save.mockImplementation(async (_id: string, body: any) => {
    version += 1
    return {
      project_id: 'p1',
      state_version: version,
      target_organization_id: body.target_organization_id ?? 'org-1',
      target_group_id: body.target_group_id ?? 'grp-1',
    }
  })
})

async function create(result: ReturnType<typeof setup>['result']) {
  let ok = false
  await act(async () => {
    ok = await result.current.beforeNavigate(0, 1)
  })
  return ok
}

describe('useWizardDraft', () => {
  it('stores the first organization and its group as the target and finishes with every attachment', async () => {
    const { result, rerender } = setup()
    expect(await create(result)).toBe(true)
    expect(draftsAPI().create).toHaveBeenCalledWith(
      expect.objectContaining({
        target_organization_id: 'org-1',
        target_group_id: 'grp-1',
      }),
    )
    // The first save after the create sends no target: it did not change.
    expect(draftsAPI().save.mock.calls[0][1]).not.toHaveProperty(
      'target_organization_id',
    )
    rerender({ wizardData: { ...ORG_DATA, organizationGroupIds: {} } })
    await act(async () => {
      await result.current.save('dataImport')
    })
    expect(draftsAPI().save).toHaveBeenLastCalledWith(
      'p1',
      expect.objectContaining({
        target_organization_id: 'org-1',
        target_group_id: null,
      }),
    )
    let id = ''
    await act(async () => {
      id = await result.current.finish()
    })
    expect(id).toBe('p1')
    expect(draftsAPI().finish).toHaveBeenCalledWith('p1', {
      client_key: expect.any(String),
      visibility: 'organization',
      public_role: null,
      organization_attachments: [
        { organization_id: 'org-1', group_id: null },
        { organization_id: 'org-2', group_id: null },
      ],
    })
    expect(result.current.draft).toBeNull()
  })

  it('keeps saving the state when the server refuses a new target', async () => {
    const { result, rerender, addToast } = setup()
    await create(result)
    rerender({ wizardData: { ...ORG_DATA, organizationIds: ['org-2'] } })
    draftsAPI().save.mockRejectedValueOnce(
      Object.assign(new Error('x'), {
        response: { status: 403, data: { detail: 'not a member of org-2' } },
      }),
    )
    const before = draftsAPI().save.mock.calls.length
    await act(async () => {
      await result.current.save('dataImport')
    })
    const calls = draftsAPI().save.mock.calls.slice(before)
    expect(calls).toHaveLength(2)
    expect(calls[0][1].target_organization_id).toBe('org-2')
    expect(calls[1][1]).not.toHaveProperty('target_organization_id')
    expect(addToast).toHaveBeenCalledWith(
      expect.stringContaining('not a member of org-2'),
      'error',
    )
    // The refused target is not sent again until it changes.
    await act(async () => {
      await result.current.save('dataImport')
    })
    expect(draftsAPI().save.mock.lastCall[1]).not.toHaveProperty(
      'target_organization_id',
    )
    // A failing retry is reported like any failed save.
    rerender({ wizardData: { ...ORG_DATA, organizationIds: ['org-3'] } })
    draftsAPI()
      .save.mockRejectedValueOnce(
        Object.assign(new Error('x'), { response: { status: 404, data: {} } }),
      )
      .mockRejectedValueOnce(new Error('offline'))
    await act(async () => {
      await result.current.save('dataImport')
    })
    expect(addToast).toHaveBeenLastCalledWith(
      expect.stringContaining('projects.creation.wizard.draft.saveFailed'),
      'error',
    )
  })

  it('finishes a public project with its role', async () => {
    const { result } = setup({
      ...ORG_DATA,
      visibility: 'public',
      publicRole: 'CONTRIBUTOR',
    })
    await create(result)
    await act(async () => {
      await result.current.finish()
    })
    expect(draftsAPI().finish).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({
        visibility: 'public',
        public_role: 'CONTRIBUTOR',
        organization_attachments: [],
      }),
    )
    await expect(result.current.finish()).rejects.toThrow('No draft')
  })

  it('generates a client key without crypto.randomUUID', async () => {
    const original = globalThis.crypto
    Object.defineProperty(globalThis, 'crypto', {
      value: {},
      configurable: true,
    })
    try {
      const { result } = setup()
      await create(result)
      expect(draftsAPI().create.mock.calls[0][0].client_key).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
      )
    } finally {
      Object.defineProperty(globalThis, 'crypto', {
        value: original,
        configurable: true,
      })
    }
  })

  it('syncs the rows of a chosen file and the cloud objects once each', async () => {
    const file = new File([JSON.stringify([{ sv: 'Fall' }])], 'klausur.json', {
      type: 'application/json',
    })
    const data: WizardData = {
      ...ORG_DATA,
      selectedFile: file,
      cloudImport: {
        organizationId: 'org-1',
        connectionId: 'c1',
        objectKeys: ['a', 'b'],
      },
    }
    const { result } = setup(data)
    await create(result)
    await act(async () => {
      expect(await result.current.syncTasks()).toBe(true)
    })
    expect(projectsAPI().runNestedImportJob).toHaveBeenCalledTimes(1)
    expect(projectsAPI().runCloudImportJobs).toHaveBeenCalledWith('p1', {
      connection_id: 'c1',
      object_keys: ['a', 'b'],
    })
    expect(result.current.draftImport).toEqual({
      rowCount: 1,
      fileName: 'klausur.json',
    })
    await act(async () => {
      await result.current.syncTasks()
    })
    expect(projectsAPI().runCloudImportJobs).toHaveBeenCalledTimes(1)
  })

  it('replaces a row whose meta changed with the new meta', async () => {
    const rows = [{ data: { sv: 'A' }, meta: { points: 20 } }]
    const { result } = setup({ ...ORG_DATA, pastedData: JSON.stringify(rows) })
    await create(result)
    draftsAPI().tasks.mockResolvedValueOnce([
      {
        id: 't1',
        inner_id: 1,
        row_index: 0,
        row_hash: 'old',
        sheets: [],
        generating: 0,
      },
    ])
    await act(async () => {
      expect(await result.current.syncTasks()).toBe(true)
    })
    expect(draftsAPI().replaceTask).toHaveBeenCalledWith(
      'p1',
      't1',
      { sv: 'A' },
      expect.stringMatching(/^[0-9a-f]{64}$/),
      { points: 20 },
    )
  })

  it('reports a sync that timed out or failed and stays put', async () => {
    const { result, addToast } = setup({
      ...ORG_DATA,
      pastedData: '[{"sv": "A"}]',
    })
    await create(result)
    projectsAPI().runNestedImportJob.mockRejectedValueOnce(
      Object.assign(new Error('slow'), { name: 'ImportJobTimeoutError' }),
    )
    await act(async () => {
      expect(await result.current.syncTasks()).toBe(false)
    })
    expect(addToast).toHaveBeenCalledWith(
      expect.stringContaining('projects.wizard.importDataTimeout'),
      'error',
    )
    draftsAPI().tasks.mockRejectedValueOnce(new Error('down'))
    await act(async () => {
      expect(await result.current.syncTasks()).toBe(false)
    })
    expect(addToast).toHaveBeenCalledWith(
      expect.stringContaining('projects.creation.wizard.draft.syncFailed'),
      'error',
    )
  })

  it('writes changed evaluation configs before the rubric step, and only then', async () => {
    const configs = [{ id: 'c', metric: 'llm_judge' }]
    const configured = { ...ORG_DATA, evaluationConfigs: configs as any }
    const { result, updateWizardData } = setup(configured)
    await create(result)
    apiClient().get.mockResolvedValue({ evaluation_configs: configs })
    await act(async () => {
      expect(await result.current.beforeNavigate(2, 3)).toBe(true)
    })
    expect(apiClient().put).toHaveBeenCalledWith(
      '/evaluations/projects/p1/evaluation-config',
      { evaluation_configs: configs },
    )
    expect(updateWizardData).toHaveBeenCalledWith({
      evaluationConfigs: configs,
    })
    expect(result.current.evalConfigsChanged(configs)).toBe(false)
    expect(result.current.evalConfigsChanged([])).toBe(true)

    apiClient().put.mockClear()
    await act(async () => {
      await result.current.beforeNavigate(2, 3)
    })
    expect(apiClient().put).not.toHaveBeenCalled()
  })

  it('stays when the configuration cannot be written or read back', async () => {
    const { result, addToast } = setup()
    await create(result)
    projectsAPI().update.mockRejectedValueOnce(new Error('nope'))
    await act(async () => {
      expect(await result.current.beforeNavigate(2, 3)).toBe(false)
    })
    expect(addToast).toHaveBeenCalledWith(
      expect.stringContaining(
        'projects.creation.wizard.draft.configSyncFailed',
      ),
      'error',
    )
    apiClient().get.mockRejectedValueOnce(new Error('read failed'))
    await act(async () => {
      expect(await result.current.beforeNavigate(3, 4)).toBe(false)
    })
  })

  it('shows the message of a failing hook', async () => {
    registerWizardDraftHook('created', () => {
      throw new Error('enable failed')
    })
    registerWizardDraftHook('created', () => {
      throw 'not an error'
    })
    const { result, addToast } = setup()
    expect(await create(result)).toBe(true)
    expect(addToast).toHaveBeenCalledWith('enable failed', 'error')
    expect(addToast).toHaveBeenCalledWith(
      'projects.wizard.postCreateHookFailed',
      'error',
    )
  })

  it('reports a draft that cannot be opened and clears the URL when it is gone', async () => {
    window.history.replaceState(null, '', '/projects/create?draft=gone')
    draftsAPI().get.mockRejectedValueOnce(coded('draft_expired', 404))
    const { result, addToast } = setup()
    await act(async () => {
      await Promise.resolve()
    })
    expect(draftsAPI().get).toHaveBeenCalledWith('gone')
    expect(window.location.search).toBe('')
    expect(addToast).toHaveBeenCalledWith(
      expect.stringContaining('draft_expired text'),
      'error',
    )
    draftsAPI().get.mockRejectedValueOnce({
      response: { data: { detail: 'plain' } },
    })
    await act(async () => {
      expect(await result.current.resume('x')).toBe(false)
    })
    expect(addToast).toHaveBeenLastCalledWith(
      expect.stringContaining('plain'),
      'error',
    )
  })

  it('keeps the draft when the discard fails, and treats an expired one as gone', async () => {
    const { result, addToast } = setup()
    await create(result)
    draftsAPI().discard.mockRejectedValueOnce(new Error('offline'))
    await act(async () => {
      expect(await result.current.discardNow()).toBe(false)
    })
    expect(result.current.draft).not.toBeNull()
    expect(addToast).toHaveBeenCalledWith(
      expect.stringContaining('projects.creation.wizard.draft.discardFailed'),
      'error',
    )
    draftsAPI().discard.mockRejectedValueOnce(coded('draft_expired', 404))
    await act(async () => {
      expect(await result.current.discardNow()).toBe(true)
    })
    expect(result.current.draft).toBeNull()
  })

  it('does not discard when the confirmation is declined', async () => {
    const { result, confirm } = setup()
    await create(result)
    confirm.mockResolvedValueOnce(false)
    await act(async () => {
      expect(await result.current.discard()).toBe(false)
    })
    expect(draftsAPI().discard).not.toHaveBeenCalled()
  })

  it('keeps step 1 when the type change is declined', async () => {
    const { result, rerender, confirm } = setup()
    await create(result)
    rerender({ wizardData: { ...ORG_DATA, projectKind: 'exam' } })
    confirm.mockResolvedValueOnce(false)
    await act(async () => {
      expect(await result.current.beforeNavigate(0, 1)).toBe(false)
    })
    expect(draftsAPI().discard).not.toHaveBeenCalled()
  })

  it('is a no-op without a draft', async () => {
    const { result } = setup()
    await act(async () => {
      expect(await result.current.syncTasks()).toBe(true)
      expect(await result.current.discard()).toBe(true)
      expect(await result.current.discardNow()).toBe(true)
      await result.current.save()
    })
    expect(draftsAPI().save).not.toHaveBeenCalled()
  })
})

/**
 * ProjectCreationWizard — draft mode (CORE 2.55).
 *
 * A registered draft policy switches the wizard to a draft project when the
 * user leaves step 1 and the policy applies: the draft is created there, its
 * state is saved with the draft's version, the rows of the data step are
 * synced into it, the configuration is written before the rubric step and
 * read back, and "Create" finishes it through the finish route. Without a
 * policy (all other ProjectCreationWizard suites) none of it runs.
 *
 * @jest-environment jsdom
 */

import {
  _resetWizardDraftRegistry,
  registerWizardDraftHook,
  registerWizardDraftPolicy,
} from '@/lib/extensions/wizardDraft'
import '@testing-library/jest-dom'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectCreationWizard } from '../ProjectCreationWizard'

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn(), back: jest.fn() }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key} ${JSON.stringify(vars)}` : key,
    locale: 'en',
  }),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    importData: jest.fn(),
    update: jest.fn().mockResolvedValue({}),
    updateVisibility: jest.fn(),
    runNestedImportJob: jest.fn().mockResolvedValue({}),
    runCloudImportJobs: jest.fn().mockResolvedValue([]),
    bulkDeleteTasks: jest.fn().mockResolvedValue({ deleted: 1 }),
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
      list: jest.fn().mockResolvedValue([]),
      get: jest.fn(),
      save: jest.fn(),
      finish: jest.fn(),
      discard: jest.fn().mockResolvedValue(undefined),
      tasks: jest.fn().mockResolvedValue([]),
      replaceTask: jest.fn().mockResolvedValue({ archived_sheet_ids: [] }),
    },
  }
})

const mockCreateProject = jest.fn()
const mockFetchProject = jest.fn()
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    createProject: mockCreateProject,
    fetchProject: mockFetchProject,
    loading: false,
  }),
}))

jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({
    models: [],
    loading: false,
    error: null,
    refetch: jest.fn(),
    hasApiKeys: true,
    apiKeyStatus: null,
  }),
  default: () => ({}),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
    showToast: jest.fn(),
    removeToast: jest.fn(),
  }),
  ToastProvider: ({ children }: { children: React.ReactNode }) => children,
}))

jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => {
    if (name === 'ProjectWizardRubricEntry') {
      const RubricEntryStub = ({ checked, onToggle }: any) => (
        <input
          type="checkbox"
          data-testid="wizard-rubric-checkbox"
          checked={!!checked}
          onChange={() => onToggle?.()}
        />
      )
      return RubricEntryStub
    }
    if (name === 'ProjectWizardRubricStep') {
      const RubricStepStub = (props: any) => (
        <div data-testid="rubric-step-stub">
          {props.draftProjectId ?? 'no-draft'}
        </div>
      )
      return RubricStepStub
    }
    return null
  },
  getSlot: () => null,
  hasSlot: () => false,
  registerSlot: jest.fn(),
}))

const draftsAPI = () => require('@/lib/api/wizardDrafts').wizardDraftsAPI
const projectsAPI = () => require('@/lib/api/projects').projectsAPI
const apiClient = () => require('@/lib/api/client').apiClient

const currentStepId = () =>
  screen
    .getByTestId('project-create-step-indicator')
    .getAttribute('data-current-step-id')

function draftResponse(overrides: Record<string, any> = {}) {
  return {
    project_id: 'p1',
    title: 'Klausur',
    kind: null,
    icon: null,
    step_id: 'projectInfo',
    target_organization_id: null,
    target_group_id: null,
    created_at: '2026-11-17T10:00:00Z',
    touched_at: '2026-11-17T10:00:00Z',
    expires_at: '2026-12-17T10:00:00Z',
    client_key: 'key-1',
    state: null,
    state_version: 1,
    ...overrides,
  }
}

function conflictError(code: string) {
  return Object.assign(new Error(code), {
    response: { status: 409, data: { detail: { code, message: code } } },
  })
}

let version = 1
const policy = { applies: (d: any) => d.features?.rubric === true }

async function readFile(file: File): Promise<string> {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.readAsText(file)
  })
}

async function startDraft(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByTestId('project-create-name-input'), 'Klausur')
  await user.click(
    screen
      .getByTestId('wizard-feature-dataImport')
      .querySelector('input[type="checkbox"]') as HTMLElement,
  )
  await user.click(screen.getByTestId('wizard-rubric-checkbox'))
  await user.click(screen.getByTestId('project-create-next-button'))
  await waitFor(() => expect(currentStepId()).toBe('dataImport'))
}

async function pasteRows(
  user: ReturnType<typeof userEvent.setup>,
  rows: unknown[],
) {
  await user.click(screen.getByText('dataImport.tabs.paste'))
  const textarea = await screen.findByTestId(
    'project-create-paste-data-textarea',
  )
  await user.clear(textarea)
  await user.click(textarea)
  await user.paste(JSON.stringify(rows))
}

beforeEach(() => {
  jest.clearAllMocks()
  _resetWizardDraftRegistry()
  window.history.replaceState(null, '', '/projects/create')
  version = 1
  const api = draftsAPI()
  api.create.mockImplementation(async (body: any) =>
    draftResponse({ client_key: body.client_key, title: body.title }),
  )
  api.save.mockImplementation(async (_id: string, body: any) => {
    version += 1
    return draftResponse({
      state_version: version,
      target_organization_id: body.target_organization_id ?? null,
      target_group_id: body.target_group_id ?? null,
    })
  })
  api.finish.mockResolvedValue({ id: 'p1' })
  api.list.mockResolvedValue([])
  api.tasks.mockResolvedValue([])
})

describe('ProjectCreationWizard — draft mode', () => {
  it('leaves the wizard as it is when the policy does not apply', async () => {
    registerWizardDraftPolicy(policy)
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await user.type(screen.getByTestId('project-create-name-input'), 'Plain')
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('settings'))
    expect(draftsAPI().create).not.toHaveBeenCalled()
    expect(draftsAPI().save).not.toHaveBeenCalled()

    mockCreateProject.mockResolvedValue({ id: 'generic-1' })
    await user.click(screen.getByTestId('project-create-submit-button'))
    await waitFor(() =>
      expect(mockPush).toHaveBeenCalledWith('/projects/generic-1'),
    )
    expect(draftsAPI().finish).not.toHaveBeenCalled()
  })

  it('calls no draft route without a registered policy', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await user.type(screen.getByTestId('project-create-name-input'), 'X')
    await user.click(screen.getByTestId('wizard-rubric-checkbox'))
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('rubric'))
    expect(draftsAPI().list).not.toHaveBeenCalled()
    expect(draftsAPI().create).not.toHaveBeenCalled()
    expect(screen.getByTestId('rubric-step-stub')).toHaveTextContent('no-draft')
  })

  it('creates the draft when step 1 is left, runs the created hooks and saves each step', async () => {
    registerWizardDraftPolicy(policy)
    const created = jest.fn()
    registerWizardDraftHook('created', created)
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await startDraft(user)

    const body = draftsAPI().create.mock.calls[0][0]
    expect(body).toMatchObject({
      title: 'Klausur',
      kind: null,
      target_organization_id: null,
      target_group_id: null,
      step_id: 'projectInfo',
    })
    expect(body.client_key).toMatch(/[0-9a-f-]{36}/)
    expect(body.state.features.rubric).toBe(true)
    expect(body.state.selectedFile).toBeUndefined()
    expect(window.location.search).toBe('?draft=p1')
    expect(created).toHaveBeenCalledWith(
      expect.objectContaining({ projectId: 'p1' }),
    )
    expect(draftsAPI().save).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({ step_id: 'dataImport', if_version: 1 }),
    )
    expect(screen.getByTestId('wizard-draft-status')).toBeInTheDocument()

    // Going back saves the step too, with the version the last save returned.
    await user.click(screen.getByTestId('project-create-back-button'))
    await waitFor(() => expect(currentStepId()).toBe('projectInfo'))
    expect(draftsAPI().save).toHaveBeenLastCalledWith(
      'p1',
      expect.objectContaining({ step_id: 'projectInfo', if_version: 2 }),
    )
    // Leaving step 1 again reuses the draft.
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('dataImport'))
    expect(draftsAPI().create).toHaveBeenCalledTimes(1)
  })

  it('saves a few seconds after an edit', async () => {
    registerWizardDraftPolicy(policy)
    jest.useFakeTimers()
    try {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<ProjectCreationWizard />)
      await startDraft(user)
      await user.click(screen.getByText('dataImport.tabs.paste'))
      const textarea = await screen.findByTestId(
        'project-create-paste-data-textarea',
      )
      const saves = draftsAPI().save.mock.calls.length
      await user.type(textarea, 'Zeile')
      await act(async () => {
        jest.advanceTimersByTime(1000)
      })
      expect(draftsAPI().save.mock.calls.length).toBe(saves)
      await act(async () => {
        jest.advanceTimersByTime(3500)
      })
      expect(draftsAPI().save.mock.calls.length).toBe(saves + 1)
      expect(draftsAPI().save).toHaveBeenLastCalledWith(
        'p1',
        expect.objectContaining({
          state: expect.objectContaining({ pastedData: 'Zeile' }),
        }),
      )
    } finally {
      jest.useRealTimers()
    }
  })

  it('syncs the pasted rows into the draft when the data step is left', async () => {
    registerWizardDraftPolicy(policy)
    const synced = jest.fn()
    registerWizardDraftHook('tasksSynced', synced)
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await startDraft(user)
    await pasteRows(user, [
      { sachverhalt: 'Fall 1' },
      { sachverhalt: 'Fall 2' },
    ])

    draftsAPI()
      .tasks.mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: 't1',
          inner_id: 1,
          row_index: 0,
          row_hash: 'a',
          sheets: [],
          generating: 0,
        },
        {
          id: 't2',
          inner_id: 2,
          row_index: 1,
          row_hash: 'b',
          sheets: [],
          generating: 0,
        },
        {
          id: 'manual',
          inner_id: 9,
          row_index: null,
          row_hash: null,
          sheets: [],
          generating: 0,
        },
      ])
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('rubric'))

    const [projectId, file] = projectsAPI().runNestedImportJob.mock.calls[0]
    expect(projectId).toBe('p1')
    const imported = JSON.parse(await readFile(file))
    expect(imported.data).toHaveLength(2)
    expect(imported.data[0]).toMatchObject({
      id: 1,
      data: { sachverhalt: 'Fall 1' },
      meta: { wizard_row_index: 0 },
    })
    expect(imported.data[1].meta.wizard_row_index).toBe(1)
    expect(imported.data[0].meta.wizard_row_hash).toMatch(/^[0-9a-f]{64}$/)
    expect(synced).toHaveBeenCalledWith(
      expect.objectContaining({
        projectId: 'p1',
        tasks: [
          { id: 't1', rowIndex: 0, status: 'created' },
          { id: 't2', rowIndex: 1, status: 'created' },
        ],
      }),
    )
    // The rubric step works on the draft.
    expect(screen.getByTestId('rubric-step-stub')).toHaveTextContent('p1')
  })

  it('asks before setting checked sheets aside, and stays when declined', async () => {
    registerWizardDraftPolicy(policy)
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await startDraft(user)
    await pasteRows(user, [{ sachverhalt: 'Fall 1 (neu)' }])
    const existing = [
      {
        id: 't1',
        inner_id: 1,
        row_index: 0,
        row_hash: 'old',
        sheets: [{ id: 's1', status: 'active', review_state: 'confirmed' }],
        generating: 0,
      },
      {
        id: 't2',
        inner_id: 2,
        row_index: 1,
        row_hash: 'h2',
        sheets: [{ id: 's2', status: 'candidate', review_state: null }],
        generating: 1,
      },
    ]
    draftsAPI().tasks.mockResolvedValue(existing)

    await user.click(screen.getByTestId('project-create-next-button'))
    const dialog = await screen.findByRole('dialog')
    expect(
      within(dialog).getByText(
        'projects.creation.wizard.draft.taskChangeTitle',
      ),
    ).toBeInTheDocument()
    expect(dialog.textContent).toContain('taskChangeUpdated')
    expect(dialog.textContent).toContain('taskChangeRemoved')
    expect(dialog.textContent).toContain('taskChangeGenerating')
    await user.click(
      within(dialog).getByRole('button', { name: 'common.cancel' }),
    )
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(currentStepId()).toBe('dataImport')
    expect(draftsAPI().replaceTask).not.toHaveBeenCalled()

    await user.click(screen.getByTestId('project-create-next-button'))
    const again = await screen.findByRole('dialog')
    await user.click(
      within(again).getByRole('button', {
        name: 'projects.creation.wizard.draft.taskChangeConfirm',
      }),
    )
    await waitFor(() => expect(currentStepId()).toBe('rubric'))
    expect(draftsAPI().replaceTask).toHaveBeenCalledWith(
      'p1',
      't1',
      { sachverhalt: 'Fall 1 (neu)' },
      expect.stringMatching(/^[0-9a-f]{64}$/),
    )
    expect(projectsAPI().bulkDeleteTasks).toHaveBeenCalledWith('p1', ['t2'])
    expect(projectsAPI().runNestedImportJob).not.toHaveBeenCalled()
  })

  it('writes the configuration before the rubric step and reads the evaluation configs back', async () => {
    registerWizardDraftPolicy(policy)
    const configSynced = jest.fn()
    registerWizardDraftHook('configSynced', configSynced)
    const readBack = [{ id: 'cfg', metric: 'llm_judge_rubric', generator: 'x' }]
    apiClient().get.mockResolvedValue({ evaluation_configs: readBack })
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await startDraft(user)
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('rubric'))

    expect(projectsAPI().update).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({
        title: 'Klausur',
        label_config: expect.any(String),
      }),
    )
    expect(configSynced).toHaveBeenCalledWith(
      expect.objectContaining({ projectId: 'p1' }),
    )
    expect(apiClient().get).toHaveBeenCalledWith(
      '/evaluations/projects/p1/evaluation-config',
    )

    // Leaving the rubric step reads them back again; the finish sends them
    // only if they changed since (they did not), then the finish route.
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('settings'))
    expect(apiClient().get).toHaveBeenCalledTimes(2)
    apiClient().put.mockClear()
    await user.click(screen.getByTestId('project-create-submit-button'))
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/projects/p1'))
    expect(mockCreateProject).not.toHaveBeenCalled()
    expect(
      apiClient().put.mock.calls.some((c: any[]) =>
        String(c[0]).includes('evaluation-config'),
      ),
    ).toBe(false)
    expect(draftsAPI().finish).toHaveBeenCalledWith('p1', {
      client_key: expect.any(String),
      visibility: 'private',
      public_role: null,
      organization_attachments: [],
    })
    expect(mockFetchProject).toHaveBeenCalledWith('p1')
    expect(mockAddToast).toHaveBeenCalledWith(
      'store.project.created',
      'success',
    )
  })

  it('discards the draft after a confirmation naming what the policy adds', async () => {
    registerWizardDraftPolicy({
      ...policy,
      describeDiscard: async () => ['2 checked grading sheets'],
    })
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await startDraft(user)
    await user.click(screen.getByTestId('wizard-draft-discard-button'))
    const dialog = await screen.findByRole('dialog')
    expect(dialog.textContent).toContain('2 checked grading sheets')
    await user.click(
      within(dialog).getByRole('button', {
        name: 'projects.creation.wizard.draft.discardConfirm',
      }),
    )
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/projects'))
    expect(draftsAPI().discard).toHaveBeenCalledWith('p1')
    expect(window.location.search).toBe('')
  })

  it('stops saving on a version conflict and loads the latest version', async () => {
    registerWizardDraftPolicy(policy)
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await user.type(screen.getByTestId('project-create-name-input'), 'Klausur')
    await user.click(screen.getByTestId('wizard-rubric-checkbox'))
    draftsAPI().save.mockRejectedValueOnce(
      conflictError('draft_version_conflict'),
    )
    await user.click(screen.getByTestId('project-create-next-button'))
    await screen.findByTestId('wizard-draft-conflict')

    // While the conflict stands, navigation does not write over the draft.
    const saves = draftsAPI().save.mock.calls.length
    await user.click(screen.getByTestId('project-create-next-button'))
    expect(draftsAPI().save.mock.calls.length).toBe(saves)

    draftsAPI().get.mockResolvedValue(
      draftResponse({
        state_version: 7,
        step_id: 'rubric',
        state: { title: 'Anderswo geändert', features: { rubric: true } },
      }),
    )
    await user.click(
      screen.getByRole('button', {
        name: 'projects.creation.wizard.draft.reload',
      }),
    )
    await waitFor(() => expect(currentStepId()).toBe('rubric'))
    expect(
      screen.queryByTestId('wizard-draft-conflict'),
    ).not.toBeInTheDocument()
  })

  it('shows a notice when the draft no longer exists', async () => {
    registerWizardDraftPolicy(policy)
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await user.type(screen.getByTestId('project-create-name-input'), 'Klausur')
    await user.click(screen.getByTestId('wizard-rubric-checkbox'))
    draftsAPI().save.mockRejectedValueOnce(
      Object.assign(new Error('gone'), {
        response: { status: 404, data: { detail: { code: 'draft_expired' } } },
      }),
    )
    await user.click(screen.getByTestId('project-create-next-button'))
    expect(
      await screen.findByTestId('wizard-draft-expired'),
    ).toBeInTheDocument()

    await user.click(
      screen.getByRole('button', {
        name: 'projects.creation.wizard.draft.startOver',
      }),
    )
    await waitFor(() => expect(currentStepId()).toBe('projectInfo'))
    expect(screen.queryByTestId('wizard-draft-expired')).not.toBeInTheDocument()
    expect(screen.getByTestId('project-create-name-input')).toHaveValue('')
    expect(window.location.search).toBe('')
  })

  it('reports a failed save without stopping the wizard', async () => {
    registerWizardDraftPolicy(policy)
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await user.type(screen.getByTestId('project-create-name-input'), 'Klausur')
    await user.click(screen.getByTestId('wizard-rubric-checkbox'))
    draftsAPI().save.mockRejectedValueOnce(new Error('network'))
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('rubric'))
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.stringContaining('projects.creation.wizard.draft.saveFailed'),
      'error',
    )
  })

  it('stays on step 1 when the draft cannot be created', async () => {
    registerWizardDraftPolicy(policy)
    draftsAPI().create.mockRejectedValueOnce(
      Object.assign(new Error('x'), {
        response: { status: 403, data: { detail: 'You are not a member' } },
      }),
    )
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await user.type(screen.getByTestId('project-create-name-input'), 'Klausur')
    await user.click(screen.getByTestId('wizard-rubric-checkbox'))
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith(
        expect.stringContaining('You are not a member'),
        'error',
      ),
    )
    expect(currentStepId()).toBe('projectInfo')
  })

  it('offers a new draft when the type changed after the draft was created', async () => {
    registerWizardDraftPolicy(policy)
    window.history.replaceState(null, '', '/projects/create?draft=p1')
    draftsAPI().get.mockResolvedValue(
      draftResponse({
        kind: 'exam',
        step_id: 'projectInfo',
        state: {
          title: 'Klausur',
          projectKind: 'generic',
          features: { rubric: true },
        },
      }),
    )
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await waitFor(() =>
      expect(screen.getByTestId('project-create-name-input')).toHaveValue(
        'Klausur',
      ),
    )
    await user.click(screen.getByTestId('project-create-next-button'))
    const dialog = await screen.findByRole('dialog')
    await user.click(
      within(dialog).getByRole('button', {
        name: 'projects.creation.wizard.draft.kindChangeConfirm',
      }),
    )
    await waitFor(() => expect(currentStepId()).toBe('rubric'))
    expect(draftsAPI().discard).toHaveBeenCalledWith('p1')
    expect(draftsAPI().create).toHaveBeenCalledWith(
      expect.objectContaining({ kind: null }),
    )
  })

  it('resumes a draft from the URL with its step and the imported-file notice', async () => {
    window.history.replaceState(null, '', '/projects/create?draft=p9')
    version = 4
    draftsAPI().get.mockResolvedValue(
      draftResponse({
        project_id: 'p9',
        step_id: 'settings',
        state_version: 4,
        state: {
          title: 'Fortgesetzt',
          features: { dataImport: true, rubric: true },
          draftImport: { rowCount: 3, fileName: 'klausur.json' },
          draftCloudImported: ['k1'],
        },
      }),
    )
    const user = userEvent.setup()
    // No policy registered: an existing draft still opens.
    render(<ProjectCreationWizard />)
    await waitFor(() => expect(currentStepId()).toBe('settings'))
    expect(draftsAPI().get).toHaveBeenCalledWith('p9')
    expect(
      screen.getByTestId('project-create-step-indicator'),
    ).toBeInTheDocument()

    // Back on the data step the file is gone (a File cannot be saved): the
    // wizard says which tasks the draft holds.
    await user.click(screen.getByTestId('project-create-back-button'))
    await waitFor(() => expect(currentStepId()).toBe('rubric'))
    expect(screen.getByTestId('rubric-step-stub')).toHaveTextContent('p9')
    await user.click(screen.getByTestId('project-create-back-button'))
    await waitFor(() => expect(currentStepId()).toBe('dataImport'))
    expect(
      screen.getByTestId('wizard-draft-import-notice').textContent,
    ).toContain('klausur.json')
    expect(draftsAPI().save).toHaveBeenLastCalledWith(
      'p9',
      expect.objectContaining({
        if_version: 5,
        step_id: 'dataImport',
        state: expect.objectContaining({ draftCloudImported: ['k1'] }),
      }),
    )
  })
})

describe('ProjectCreationWizard — unfinished drafts', () => {
  it('lists the drafts and continues or discards one', async () => {
    registerWizardDraftPolicy(policy)
    const summary = {
      project_id: 'p5',
      title: 'Alte Klausur',
      kind: 'exam',
      icon: '📝',
      step_id: 'dataImport',
      target_organization_id: null,
      target_group_id: null,
      created_at: '2026-11-01T10:00:00Z',
      touched_at: '2026-11-10T10:00:00Z',
      expires_at: '2026-12-10T10:00:00Z',
    }
    draftsAPI().list.mockResolvedValueOnce([
      summary,
      { ...summary, project_id: 'p6' },
    ])
    draftsAPI().list.mockResolvedValueOnce([{ ...summary, project_id: 'p6' }])
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    const items = await screen.findAllByTestId('wizard-draft-item')
    expect(items).toHaveLength(2)
    expect(items[0].textContent).toContain('Alte Klausur')
    expect(items[0].textContent).toContain('expiresOn')

    await user.click(within(items[0]).getByTestId('wizard-draft-discard'))
    const dialog = await screen.findByRole('dialog')
    await user.click(
      within(dialog).getByRole('button', {
        name: 'projects.creation.wizard.draft.discardConfirm',
      }),
    )
    await waitFor(() =>
      expect(screen.getAllByTestId('wizard-draft-item')).toHaveLength(1),
    )
    expect(draftsAPI().discard).toHaveBeenCalledWith('p5')

    draftsAPI().get.mockResolvedValue(
      draftResponse({
        project_id: 'p6',
        step_id: 'dataImport',
        state: {
          title: 'Alte Klausur',
          features: { dataImport: true, rubric: true },
        },
      }),
    )
    await user.click(screen.getByTestId('wizard-draft-continue'))
    await waitFor(() => expect(currentStepId()).toBe('dataImport'))
    expect(window.location.search).toBe('?draft=p6')
    expect(screen.queryByTestId('wizard-draft-list')).not.toBeInTheDocument()
  })
})

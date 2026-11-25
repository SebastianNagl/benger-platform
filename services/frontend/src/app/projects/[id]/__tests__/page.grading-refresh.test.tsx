/**
 * Project detail page: the grading section slot saves policy keys into
 * `evaluation_configs[i].metric_parameters` on its own and then calls
 * `onRefresh`. The evaluation card auto-saves its whole config list, which
 * the server replaces, so the card must re-read the configs on that refresh;
 * otherwise its next save (any method edit) writes the old policy back.
 *
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { apiClient } from '@/lib/api/client'
import { useUIStore } from '@/stores'
import { useProjectStore } from '@/stores/projectStore'
import { setMockFeatureFlags } from '@/test-utils/featureFlagsMock'
import '@testing-library/jest-dom'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import {
  useParams,
  usePathname,
  useRouter,
  useSearchParams,
} from 'next/navigation'

jest.mock('@/lib/featureFlags', () =>
  jest.requireActual('@/test-utils/featureFlagsMock').featureFlagsMockModule(),
)
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useParams: jest.fn(() => ({ id: 'test-project-123' })),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/projects/test-project-123'),
}))

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('@/hooks/useModels')
jest.mock('@/stores')
jest.mock('@/stores/projectStore')

const mockListDesignKeys = jest.fn()
const mockListRuns = jest.fn()
jest.mock('@/lib/api/analysis', () => ({
  analysisAPI: {
    listDesignKeys: (...args: unknown[]) => mockListDesignKeys(...args),
    listRuns: (...args: unknown[]) => mockListRuns(...args),
  },
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    put: jest.fn(),
    post: jest.fn(),
    evaluations: {
      getProjectEvaluationConfig: jest.fn(),
    },
  },
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <div data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </div>
  ),
}))
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
  ),
}))
jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => (
    <div className={className}>{children}</div>
  ),
}))
jest.mock('@/components/shared/Input', () => ({
  Input: (props: any) => <input {...props} />,
}))
jest.mock('@/components/shared/Textarea', () => ({
  Textarea: (props: any) => <textarea {...props} />,
}))
jest.mock('@/components/shared/Label', () => ({
  Label: ({ children, ...props }: any) => <label {...props}>{children}</label>,
}))
jest.mock('@/components/shared/Select', () => ({
  Select: ({ children }: any) => <div data-testid="select">{children}</div>,
  SelectTrigger: ({ children }: any) => <div>{children}</div>,
  SelectValue: () => <div>Select Value</div>,
  SelectContent: ({ children }: any) => <div>{children}</div>,
  SelectItem: ({ children }: any) => <div>{children}</div>,
}))
jest.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({ children }: any) => <div>{children}</div>,
}))
jest.mock('@/components/projects/LabelConfigEditor', () => {
  const React = require('react')
  return {
    // eslint-disable-next-line react/display-name
    LabelConfigEditor: React.forwardRef((_props: any, ref: any) => {
      React.useImperativeHandle(ref, () => ({
        save: jest.fn().mockResolvedValue(undefined),
        isDirty: () => false,
        hasErrors: () => false,
      }))
      return <div data-testid="label-config-editor" />
    }),
  }
})
jest.mock('@/components/projects/PromptStructuresManager', () => ({
  PromptStructuresManager: () => (
    <div data-testid="prompt-structures-manager" />
  ),
}))
jest.mock('@/components/projects/GenerationStructureEditor', () => ({
  GenerationStructureEditor: () => (
    <div data-testid="generation-structure-editor" />
  ),
}))
jest.mock('@/components/evaluation/EvaluationBuilder', () => ({
  // A method edit: rename the first config's metric.
  EvaluationBuilder: ({ evaluations, onEvaluationsChange }: any) => (
    <>
      <button
        data-testid="edit-method"
        onClick={() =>
          onEvaluationsChange(
            evaluations.map((e: any, i: number) =>
              i === 0 ? { ...e, display_name: 'Edited method' } : e,
            ),
          )
        }
      >
        edit method
      </button>
      <pre data-testid="card-configs">{JSON.stringify(evaluations)}</pre>
    </>
  ),
}))
jest.mock('@/components/projects/ParticipantCard', () => ({
  ParticipantCard: ({ projectId, via, onLeft }: any) => (
    <div data-testid="participant-card-stub" data-via={String(via)}>
      <button onClick={onLeft}>leave</button>
      {projectId}
    </div>
  ),
}))
jest.mock('@/components/analysis/ProjectAnalysesSection', () => ({
  ProjectAnalysesSection: ({ projectId, onSummaryChange }: any) => (
    <div data-testid="project-analyses-stub">
      {projectId}
      <button onClick={() => onSummaryChange({ designs: 3, plans: 2 })}>
        report counts
      </button>
    </div>
  ),
}))
jest.mock('@/components/reports/PublicationToggle', () => ({
  PublicationToggle: () => <div data-testid="publication-toggle" />,
}))
jest.mock('date-fns', () => ({
  formatDistanceToNow: () => '2 days ago',
}))

const mockRouter = {
  push: jest.fn(),
  back: jest.fn(),
  replace: jest.fn(),
  forward: jest.fn(),
  refresh: jest.fn(),
  prefetch: jest.fn(),
}

const mockUser = {
  id: 'user-123',
  username: 'testuser',
  email: 'test@example.com',
  role: 'admin',
  is_superadmin: true,
}

const mockProject = {
  id: 'test-project-123',
  title: 'Test Project',
  description: 'desc',
  created_by: 'user-123',
  created_by_name: 'Test User',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
  task_count: 10,
  annotation_count: 5,
  progress_percentage: 50,
  label_config: '<View><Text name="text" value="$text"/></View>',
  instructions: '',
  show_instruction: true,
  show_skip_button: true,
  show_submit_button: true,
  require_comment_on_skip: false,
  require_confirm_before_submit: false,
  maximum_annotations: 1,
  min_annotations_per_task: 1,
  assignment_mode: 'open',
  organizations: [{ id: 'org-1', name: 'TUM' }],
  generation_config: {},
  llm_model_ids: [],
  evaluation_config: {},
  enable_annotation: true,
  enable_generation: true,
  enable_evaluation: true,
  is_public: false,
  is_private: false,
  public_role: null,
  generation_count: 0,
}

let ProjectDetailPage: any
beforeAll(async () => {
  ProjectDetailPage = (await import('../page')).default
})

const initialConfigs = () => [
  {
    id: 'cfg-1',
    metric: 'korrektur',
    display_name: 'Grading',
    metric_parameters: { rubric: 'r1' },
    prediction_fields: ['answer'],
    reference_fields: ['solution'],
    enabled: true,
  },
]

describe('ProjectDetailPage - grading section refresh', () => {
  let server: { evaluation_configs: any[] }

  beforeEach(() => {
    jest.clearAllMocks()
    setMockFeatureFlags({})
    mockListDesignKeys.mockResolvedValue([])
    mockListRuns.mockResolvedValue({ items: [], total: 0 })
    server = { evaluation_configs: initialConfigs() }
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      currentOrganization: null,
    })
    ;(useI18n as jest.Mock).mockReturnValue({ t: (key: string) => key })
    ;(useUIStore as jest.Mock).mockReturnValue({
      isSidebarHidden: false,
      isHydrated: true,
    })
    ;(useModels as jest.Mock).mockReturnValue({
      models: [],
      loading: false,
      error: null,
      refetch: jest.fn(),
      hasApiKeys: true,
      apiKeyStatus: {},
    })
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: { ...mockProject, effective_role: 'ORG_ADMIN' },
      loading: false,
      fetchProject: jest.fn(),
      updateProject: jest.fn().mockResolvedValue({}),
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) =>
      Promise.resolve(
        url.includes('/evaluation-config')
          ? JSON.parse(JSON.stringify(server))
          : { status: 'ok' },
      ),
    )
    // The server replaces the list as a whole, like merge_evaluation_config.
    ;(apiClient.put as jest.Mock).mockImplementation(
      (url: string, body: any) => {
        if (url.includes('/evaluation-config') && body.evaluation_configs) {
          server.evaluation_configs = JSON.parse(
            JSON.stringify(body.evaluation_configs),
          )
        }
        return Promise.resolve({ warnings: [] })
      },
    )
    jest.spyOn(window, 'addEventListener').mockImplementation(jest.fn())
    jest.spyOn(window, 'removeEventListener').mockImplementation(jest.fn())

    const { registerSlot } = jest.requireActual('@/lib/extensions/slots')
    // Stands in for the grading section: it writes the blind and peer
    // policy into the config's metric_parameters on the server, then asks
    // the page to refresh.
    registerSlot('project-evaluation-grading-section', ({ onRefresh }: any) => (
      <button
        data-testid="save-grading-policy"
        onClick={() => {
          const cfg = server.evaluation_configs[0]
          cfg.metric_parameters = {
            ...cfg.metric_parameters,
            blind_policy: 'blind',
            peer_policy: { enabled: true, reviews_per_submission: 2 },
          }
          onRefresh()
        }}
      >
        save grading policy
      </button>
    ))
  })

  afterEach(() => {
    const { registerSlot } = jest.requireActual('@/lib/extensions/slots')
    registerSlot('project-evaluation-grading-section', null as any)
    jest.restoreAllMocks()
  })

  const openEvaluationCard = async () => {
    render(
      <ProjectDetailPage
        params={Promise.resolve({ id: 'test-project-123' })}
      />,
    )
    fireEvent.click(await screen.findByText('project.evaluation.title'))
    fireEvent.click(await screen.findByText('project.evaluationMethods.title'))
  }

  const lastConfigPut = () => {
    const calls = (apiClient.put as jest.Mock).mock.calls.filter(
      ([url, body]: any) =>
        url.includes('/evaluation-config') && body.evaluation_configs,
    )
    return calls[calls.length - 1]?.[1].evaluation_configs
  }

  it('keeps the grading policy when a method edit saves after it', async () => {
    await openEvaluationCard()
    fireEvent.click(await screen.findByTestId('save-grading-policy'))
    // The refresh re-read the configs.
    await waitFor(() =>
      expect(
        (apiClient.get as jest.Mock).mock.calls.filter(([url]: any) =>
          url.includes('/evaluation-config'),
        ).length,
      ).toBeGreaterThanOrEqual(2),
    )

    fireEvent.click(await screen.findByTestId('edit-method'))
    await waitFor(() => expect(lastConfigPut()).toBeDefined(), {
      timeout: 5000,
    })

    const saved = server.evaluation_configs[0]
    expect(saved.display_name).toBe('Edited method')
    expect(saved.metric_parameters).toEqual({
      rubric: 'r1',
      blind_policy: 'blind',
      peer_policy: { enabled: true, reviews_per_submission: 2 },
    })
  })

  it('keeps an unsaved method edit made before the grading save', async () => {
    await openEvaluationCard()
    // Edit first: the card is dirty with its auto-save pending.
    fireEvent.click(await screen.findByTestId('edit-method'))
    fireEvent.click(await screen.findByTestId('save-grading-policy'))

    await waitFor(() => expect(lastConfigPut()).toBeDefined(), {
      timeout: 5000,
    })

    const saved = server.evaluation_configs[0]
    expect(saved.display_name).toBe('Edited method')
    expect(saved.metric_parameters.blind_policy).toBe('blind')
    expect(saved.metric_parameters.peer_policy).toEqual({
      enabled: true,
      reviews_per_submission: 2,
    })
  })
  it('sends the list it started from, so the server keeps writes it missed', async () => {
    await openEvaluationCard()
    fireEvent.click(await screen.findByTestId('edit-method'))
    await waitFor(() => expect(lastConfigPut()).toBeDefined(), {
      timeout: 5000,
    })
    const calls = (apiClient.put as jest.Mock).mock.calls.filter(
      ([url, body]: any) =>
        url.includes('/evaluation-config') && body.evaluation_configs,
    )
    expect(calls[calls.length - 1][1].evaluation_configs_base).toEqual(
      initialConfigs(),
    )
  })

  // Commits a config PUT like the API does: metric_parameters keys the
  // write left as they were in its base keep the server's value.
  const commitRebased = (body: any) => {
    server.evaluation_configs = body.evaluation_configs.map((cfg: any) => {
      const base = body.evaluation_configs_base.find(
        (b: any) => b.id === cfg.id,
      )
      const stored = server.evaluation_configs.find((c: any) => c.id === cfg.id)
      const params = { ...cfg.metric_parameters }
      for (const [key, value] of Object.entries(
        stored?.metric_parameters ?? {},
      )) {
        if (
          JSON.stringify(cfg.metric_parameters?.[key]) ===
          JSON.stringify(base?.metric_parameters?.[key])
        ) {
          params[key] = value
        }
      }
      return JSON.parse(JSON.stringify({ ...cfg, metric_parameters: params }))
    })
  }

  const expectedAfterBoth = {
    display_name: 'Edited method',
    metric_parameters: {
      rubric: 'r1',
      blind_policy: 'blind',
      peer_policy: { enabled: true, reviews_per_submission: 2 },
    },
  }

  it('does not apply a refresh read that a card save overtook', async () => {
    // The server answers a read with the list it holds when the read
    // arrives, and commits a write when it answers it, rebasing the
    // metric_parameters keys the write did not change, like the API does.
    let holdGets = false
    const heldGets: Array<() => void> = []
    const releaseGets = async () => {
      while (heldGets.length > 0) {
        heldGets.splice(0).forEach((release) => release())
        await new Promise((r) => setTimeout(r, 50))
      }
    }
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) => {
      if (!url.includes('/evaluation-config')) {
        return Promise.resolve({ status: 'ok' })
      }
      const snapshot = JSON.parse(JSON.stringify(server))
      if (!holdGets) return Promise.resolve(snapshot)
      return new Promise((resolve) => heldGets.push(() => resolve(snapshot)))
    })
    let releasePut: (() => void) | null = null
    ;(apiClient.put as jest.Mock).mockImplementation(
      (url: string, body: any) =>
        new Promise((resolve) => {
          releasePut = () => {
            if (url.includes('/evaluation-config') && body.evaluation_configs) {
              commitRebased(body)
            }
            resolve({ warnings: [] })
          }
        }),
    )

    await openEvaluationCard()
    fireEvent.click(await screen.findByTestId('edit-method'))
    await waitFor(() => expect(lastConfigPut()).toBeDefined(), {
      timeout: 5000,
    })

    // The grading section saves while the card's PUT is still open; the
    // refresh read is held until after that PUT has been answered.
    holdGets = true
    fireEvent.click(await screen.findByTestId('save-grading-policy'))
    await new Promise((r) => setTimeout(r, 50))
    releasePut!()
    await new Promise((r) => setTimeout(r, 50))
    await releaseGets()

    expect(server.evaluation_configs[0]).toMatchObject(expectedAfterBoth)
    expect(
      JSON.parse(screen.getByTestId('card-configs').textContent!)[0],
    ).toMatchObject(expectedAfterBoth)
  })

  it('keeps the grading policy saved while the card saves its settings', async () => {
    // A batch with a changed setting PATCHes it before its config PUT; the
    // grading section saves while that PATCH is open.
    const heldPatches: Array<() => void> = []
    const updateProject = jest.fn(
      () => new Promise((resolve) => heldPatches.push(() => resolve({}))),
    )
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: {
        ...mockProject,
        effective_role: 'ORG_ADMIN',
        immediate_evaluation_enabled: true,
      },
      loading: false,
      fetchProject: jest.fn(),
      updateProject,
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    ;(apiClient.put as jest.Mock).mockImplementation(
      (url: string, body: any) => {
        if (url.includes('/evaluation-config') && body.evaluation_configs) {
          commitRebased(body)
        }
        return Promise.resolve({ warnings: [] })
      },
    )

    await openEvaluationCard()
    // Switching immediate evaluation off needs no confirmation.
    fireEvent.click(await screen.findByText('project.evaluationSettings.title'))
    fireEvent.click(
      within(await screen.findByTestId('evaluation-timing-group')).getByRole(
        'checkbox',
      ),
    )
    fireEvent.click(await screen.findByTestId('edit-method'))
    await waitFor(() => expect(updateProject).toHaveBeenCalled(), {
      timeout: 5000,
    })

    fireEvent.click(await screen.findByTestId('save-grading-policy'))
    await new Promise((r) => setTimeout(r, 50))
    while (heldPatches.length > 0 || !lastConfigPut()) {
      heldPatches.splice(0).forEach((release) => release())
      await new Promise((r) => setTimeout(r, 50))
    }
    await new Promise((r) => setTimeout(r, 100))

    expect(server.evaluation_configs[0]).toMatchObject(expectedAfterBoth)
    expect(
      JSON.parse(screen.getByTestId('card-configs').textContent!)[0],
    ).toMatchObject(expectedAfterBoth)
  })
})

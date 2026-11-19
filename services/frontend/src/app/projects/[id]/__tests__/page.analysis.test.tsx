/**
 * Project detail page: the one Evaluations quick action. Analysis runs live
 * in the evaluations page's Analyses view, so the action opens that view
 * when the project has analysis runs or variant designs but no metric
 * configs, and the metrics view otherwise. The analysis reads are never
 * made for annotators or participants. The Evaluation card's Analyses part
 * (variant designs, plans, start dialog) shows for the CONTRIBUTOR and
 * ORG_ADMIN roles only.
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
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  EvaluationBuilder: () => <div data-testid="evaluation-builder" />,
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

describe('ProjectDetailPage — Evaluations quick action', () => {
  const contributor = {
    ...mockUser,
    id: 'member-2',
    role: 'CONTRIBUTOR',
    is_superadmin: false,
  }

  const setup = (
    projectOverrides: any,
    user: any = contributor,
    evaluationConfig: any = { status: 'ok' },
  ) => {
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({ user, currentOrganization: null })
    ;(useI18n as jest.Mock).mockReturnValue({ t: (key: string) => key })
    ;(useUIStore as jest.Mock).mockReturnValue({ isSidebarHidden: false })
    ;(useModels as jest.Mock).mockReturnValue({
      models: [],
      loading: false,
      error: null,
      refetch: jest.fn(),
      hasApiKeys: true,
      apiKeyStatus: {},
    })
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: { ...mockProject, ...projectOverrides },
      loading: false,
      fetchProject: jest.fn(),
      updateProject: jest.fn().mockResolvedValue({}),
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) =>
      Promise.resolve(
        url.includes('/evaluation-config')
          ? evaluationConfig
          : { status: 'ok' },
      ),
    )
    jest.spyOn(window, 'addEventListener').mockImplementation(jest.fn())
    jest.spyOn(window, 'removeEventListener').mockImplementation(jest.fn())
  }

  beforeEach(() => {
    jest.clearAllMocks()
    setMockFeatureFlags({ variant_experiments: true })
    mockListDesignKeys.mockResolvedValue([])
    mockListRuns.mockResolvedValue({ items: [], total: 0 })
  })

  const renderPage = () =>
    render(
      <ProjectDetailPage
        params={Promise.resolve({ id: 'test-project-123' })}
      />,
    )

  const clickEvaluations = async () => {
    const action = await screen.findByTestId('project-evaluations')
    expect(action).toHaveTextContent('project.quickActions.evaluations')
    fireEvent.click(action)
  }

  it('has one Evaluations action and no separate Analysis action', async () => {
    mockListDesignKeys.mockResolvedValue(['role_swap'])
    setup({ effective_role: 'CONTRIBUTOR', can_edit: true })
    renderPage()
    await screen.findByTestId('project-evaluations')
    expect(screen.queryByTestId('project-analysis')).not.toBeInTheDocument()
    expect(
      screen.queryByText('project.quickActions.analysis'),
    ).not.toBeInTheDocument()
  })

  it('keeps the classic Evaluations target and asks for nothing while variant_experiments is off', async () => {
    setMockFeatureFlags({})
    mockListRuns.mockResolvedValue({ items: [{ id: 'r1' }], total: 1 })
    setup({ effective_role: 'CONTRIBUTOR', can_edit: true })
    renderPage()
    await clickEvaluations()
    expect(mockRouter.push).not.toHaveBeenCalledWith(
      '/evaluations?projectId=test-project-123&type=analysis',
    )
    expect(mockListRuns).not.toHaveBeenCalled()
    expect(mockListDesignKeys).not.toHaveBeenCalled()
  })

  it('opens the Analyses view for a project with runs and no metric configs', async () => {
    mockListRuns.mockResolvedValue({ items: [{ id: 'r1' }], total: 1 })
    setup({ effective_role: 'CONTRIBUTOR', can_edit: true })
    renderPage()
    await waitFor(() =>
      expect(mockListRuns).toHaveBeenCalledWith('test-project-123', 1),
    )
    await waitFor(async () => {
      mockRouter.push.mockClear()
      await clickEvaluations()
      expect(mockRouter.push).toHaveBeenCalledWith(
        '/evaluations?projectId=test-project-123&type=analysis',
      )
    })
  })

  it('keeps runs reachable after their variant designs are deleted', async () => {
    mockListDesignKeys.mockResolvedValue([])
    mockListRuns.mockResolvedValue({ items: [{ id: 'r1' }], total: 3 })
    setup({ effective_role: 'ORG_ADMIN', can_edit: true })
    renderPage()
    await waitFor(async () => {
      mockRouter.push.mockClear()
      await clickEvaluations()
      expect(mockRouter.push).toHaveBeenCalledWith(
        '/evaluations?projectId=test-project-123&type=analysis',
      )
    })
  })

  it('opens the Analyses view for a project with a design and no runs yet', async () => {
    mockListDesignKeys.mockResolvedValue(['role_swap'])
    setup({ effective_role: 'CONTRIBUTOR', can_edit: true })
    renderPage()
    await waitFor(async () => {
      mockRouter.push.mockClear()
      await clickEvaluations()
      expect(mockRouter.push).toHaveBeenCalledWith(
        '/evaluations?projectId=test-project-123&type=analysis',
      )
    })
  })

  it('opens the Metrics view when the project has metric configs', async () => {
    mockListRuns.mockResolvedValue({ items: [{ id: 'r1' }], total: 1 })
    setup({ effective_role: 'CONTRIBUTOR', can_edit: true }, contributor, {
      evaluation_configs: [{ id: 'cfg-1', metric: 'bleu', enabled: true }],
    })
    renderPage()
    await waitFor(() => expect(mockListRuns).toHaveBeenCalled())
    // Wait for the config read to land before clicking.
    await waitFor(() =>
      expect(apiClient.get).toHaveBeenCalledWith(
        '/evaluations/projects/test-project-123/evaluation-config',
      ),
    )
    await clickEvaluations()
    expect(mockRouter.push).toHaveBeenLastCalledWith(
      '/evaluations?projectId=test-project-123',
    )
  })

  it('opens the Metrics view when nothing about analyses can be read', async () => {
    mockListRuns.mockRejectedValue(new Error('403'))
    mockListDesignKeys.mockRejectedValue(new Error('403'))
    setup({ effective_role: 'CONTRIBUTOR', can_edit: true })
    renderPage()
    await waitFor(() => expect(mockListDesignKeys).toHaveBeenCalled())
    await clickEvaluations()
    expect(mockRouter.push).toHaveBeenLastCalledWith(
      '/evaluations?projectId=test-project-123',
    )
  })

  it('never reads analyses for annotators or participants', async () => {
    setup(
      { effective_role: 'ANNOTATOR', can_edit: false },
      { ...contributor, role: 'ANNOTATOR' },
    )
    const { unmount } = renderPage()
    await screen.findByText('project.quickActions.title')
    expect(screen.queryByTestId('project-evaluations')).not.toBeInTheDocument()
    unmount()

    setup({
      effective_role: 'ANNOTATOR',
      access_tier: 'participant',
      participant_via: 'share',
    })
    renderPage()
    await screen.findByText('project.quickActions.title')
    expect(mockListDesignKeys).not.toHaveBeenCalled()
    expect(mockListRuns).not.toHaveBeenCalled()
  })
})

describe('ProjectDetailPage — Analyses on the Evaluation card', () => {
  const member = (role: string) => ({
    ...mockUser,
    id: `member-${role}`,
    role,
    is_superadmin: false,
  })

  const t = (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key

  const setup = (projectOverrides: any, user: any, evaluationConfig: any) => {
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({ user, currentOrganization: null })
    ;(useI18n as jest.Mock).mockReturnValue({ t })
    ;(useUIStore as jest.Mock).mockReturnValue({ isSidebarHidden: false })
    ;(useModels as jest.Mock).mockReturnValue({
      models: [],
      loading: false,
      error: null,
      refetch: jest.fn(),
      hasApiKeys: true,
      apiKeyStatus: {},
    })
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: { ...mockProject, ...projectOverrides },
      loading: false,
      fetchProject: jest.fn(),
      updateProject: jest.fn().mockResolvedValue({}),
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) =>
      Promise.resolve(
        url.includes('/evaluation-config') ? evaluationConfig : {},
      ),
    )
    jest.spyOn(window, 'addEventListener').mockImplementation(jest.fn())
    jest.spyOn(window, 'removeEventListener').mockImplementation(jest.fn())
  }

  beforeEach(() => {
    jest.clearAllMocks()
    // The Analyses part belongs to variant_experiments.
    setMockFeatureFlags({ variant_experiments: true })
    mockListDesignKeys.mockResolvedValue(['role_swap'])
    mockListRuns.mockResolvedValue({ items: [], total: 0 })
  })

  const openEvaluationCard = async () => {
    fireEvent.click(await screen.findByText('project.evaluation.title'))
  }

  const renderFor = async (
    projectOverrides: any,
    user: any,
    evaluationConfig: any = { analysis_plans: [{ id: 'p1' }] },
  ) => {
    setup(projectOverrides, user, evaluationConfig)
    const view = render(
      <ProjectDetailPage
        params={Promise.resolve({ id: 'test-project-123' })}
      />,
    )
    await openEvaluationCard()
    return view
  }

  it.each([
    ['CONTRIBUTOR', 'CONTRIBUTOR'],
    ['ORG_ADMIN', 'ORG_ADMIN'],
  ])('shows the Analyses part to the %s role', async (_label, role) => {
    await renderFor({ effective_role: role, can_edit: true }, member(role))
    const title = await screen.findByText('analysis.section.title')
    // The badge counts the designs and the saved plans.
    await waitFor(() =>
      expect(
        screen.getByText(
          'analysis.section.designsOne, analysis.section.plansOne',
        ),
      ).toBeInTheDocument(),
    )
    fireEvent.click(title)
    expect(
      await screen.findByTestId('project-analyses-stub'),
    ).toHaveTextContent('test-project-123')
    // The section reports changed counts; the badge follows.
    fireEvent.click(screen.getByText('report counts'))
    expect(
      await screen.findByText(
        'analysis.section.designsMany {"count":3}, analysis.section.plansMany {"count":2}',
      ),
    ).toBeInTheDocument()
  })

  it('says not configured when there are no designs and no plans', async () => {
    mockListDesignKeys.mockResolvedValue([])
    await renderFor(
      { effective_role: 'CONTRIBUTOR', can_edit: true },
      member('CONTRIBUTOR'),
      { evaluation_configs: [] },
    )
    await screen.findByText('analysis.section.title')
    await waitFor(() => expect(mockListDesignKeys).toHaveBeenCalled())
    expect(
      screen.queryByText(/analysis\.section\.(designs|plans)/),
    ).not.toBeInTheDocument()
  })

  it('shows no Analyses part and asks for no designs while variant_experiments is off', async () => {
    setMockFeatureFlags({})
    await renderFor(
      { effective_role: 'CONTRIBUTOR', can_edit: true },
      member('CONTRIBUTOR'),
    )
    await screen.findByText('project.quickActions.title')
    expect(screen.queryByText('analysis.section.title')).not.toBeInTheDocument()
    expect(screen.queryByTestId('project-analyses-stub')).toBeNull()
    expect(mockListDesignKeys).not.toHaveBeenCalled()
  })

  it('hides it from annotators', async () => {
    await renderFor(
      { effective_role: 'ANNOTATOR', can_edit: false },
      member('ANNOTATOR'),
    )
    await screen.findByText('project.quickActions.title')
    expect(screen.queryByText('analysis.section.title')).not.toBeInTheDocument()
    expect(screen.queryByTestId('project-analyses-stub')).toBeNull()
  })

  it('hides it from a signed-in visitor of a public project without edit rights', async () => {
    await renderFor(
      { effective_role: 'CONTRIBUTOR', can_edit: false, is_public: true },
      member('CONTRIBUTOR'),
    )
    await screen.findByText('project.quickActions.title')
    expect(screen.queryByText('analysis.section.title')).not.toBeInTheDocument()
  })

  it('hides it from an editor whose role is not CONTRIBUTOR or ORG_ADMIN', async () => {
    await renderFor(
      { effective_role: 'ANNOTATOR', can_edit: true },
      member('ANNOTATOR'),
    )
    await screen.findByText('project.evaluation.title')
    expect(screen.queryByText('analysis.section.title')).not.toBeInTheDocument()
  })
})

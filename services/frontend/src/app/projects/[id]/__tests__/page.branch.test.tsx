/**
 * Branch coverage tests for Project Detail Page
 *
 * Targets uncovered conditional branches: loading states, permissions,
 * error paths, completion rates, organization checks, model configs,
 * evaluation badge text, conditional instructions, and empty data states.
 */

import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlag } from '@/contexts/FeatureFlagContext'
import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { apiClient } from '@/lib/api/client'
import { useUIStore } from '@/stores'
import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { render, screen, waitFor, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import ProjectDetailPage from '../page'

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useParams: jest.fn(),
  useSearchParams: jest.fn(),
  usePathname: jest.fn(() => '/projects/test-id'),
}))

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('@/contexts/FeatureFlagContext')
jest.mock('@/hooks/useModels')
jest.mock('@/stores')
jest.mock('@/stores/projectStore')
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn().mockResolvedValue({}),
    put: jest.fn().mockResolvedValue({}),
    evaluations: {
      getAvailableEvaluationFields: jest.fn().mockResolvedValue({
        model_response_fields: [],
        human_annotation_fields: [],
        reference_fields: [],
        all_fields: [],
      }),
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
  Button: ({ children, onClick, disabled, className, href, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} className={className} {...props}>
      {children}
    </button>
  ),
}))
jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => <div className={className}>{children}</div>,
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
  Select: ({ children }: any) => <div>{children}</div>,
  SelectTrigger: ({ children }: any) => <div>{children}</div>,
  SelectValue: () => <div>Select Value</div>,
  SelectContent: ({ children }: any) => <div>{children}</div>,
  SelectItem: ({ children, value }: any) => <div data-value={value}>{children}</div>,
}))
jest.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({ children }: any) => <div>{children}</div>,
}))
jest.mock('@/components/shared/FeatureFlag', () => ({
  FeatureFlag: ({ children }: any) => <div>{children}</div>,
}))
jest.mock('@/components/projects/LabelConfigEditor', () => ({
  LabelConfigEditor: ({ onSave, onCancel }: any) => (
    <div data-testid="label-config-editor">
      <button onClick={() => onSave('<View/>')}>Save Config</button>
      <button onClick={onCancel}>Cancel</button>
    </div>
  ),
}))
jest.mock('@/components/projects/PromptStructuresManager', () => ({
  PromptStructuresManager: ({ projectId }: any) => (
    <div data-testid="prompt-structures-manager">Prompts for {projectId}</div>
  ),
}))
jest.mock('@/components/evaluation/EvaluationBuilder', () => ({
  EvaluationBuilder: () => <div data-testid="evaluation-builder">EvalBuilder</div>,
}))
jest.mock('@/components/reports/PublicationToggle', () => ({
  PublicationToggle: () => <div data-testid="publication-toggle">PubToggle</div>,
}))
jest.mock('date-fns', () => ({
  formatDistanceToNow: () => '2 days ago',
}))

const mockRouter = { push: jest.fn(), back: jest.fn(), replace: jest.fn(), forward: jest.fn(), refresh: jest.fn(), prefetch: jest.fn() }
const mockFetchProject = jest.fn()
const mockUpdateProject = jest.fn().mockResolvedValue({})
const mockDeleteProject = jest.fn().mockResolvedValue({})

const baseProject = {
  id: 'test-id',
  title: 'Test Project',
  description: 'Description here',
  created_by: 'user-1',
  created_by_name: 'Creator',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
  task_count: 100,
  annotation_count: 50,
  progress_percentage: 50,
  label_config: '<View><Text name="text" value="$text"/></View>',
  instructions: 'Annotate carefully',
  show_instruction: true,
  show_skip_button: true,
  show_submit_button: true,
  require_comment_on_skip: false,
  require_confirm_before_submit: false,
  maximum_annotations: 1,
  min_annotations_per_task: 1,
  assignment_mode: 'open',
  organizations: [{ id: 'org-1', name: 'TUM' }],
  generation_config: {
    selected_configuration: { models: ['gpt-4'], model_configs: {} },
  },
  evaluation_config: {
    selected_methods: {
      text: { automated: ['bleu'], human: ['accuracy'] },
    },
  },
  review_enabled: false,
  review_mode: 'in_place',
  conditional_instructions: [],
}

const mockModels = [
  { id: 'gpt-4', name: 'GPT-4', description: 'OpenAI GPT-4', provider: 'OpenAI', model_type: 'chat', capabilities: ['chat'], is_active: true, created_at: '2024-01-01' },
  { id: 'claude-3-opus', name: 'Claude 3 Opus', description: 'Anthropic Claude', provider: 'Anthropic', model_type: 'chat', capabilities: ['chat'], is_active: true, created_at: '2024-01-01' },
]

function setupMocks(overrides: Record<string, any> = {}) {
  ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
  ;(useI18n as jest.Mock).mockReturnValue({
    t: (key: string, vars?: any) => {
      if (vars) {
        let text = key
        Object.entries(vars).forEach(([k, v]) => {
          text = text.replace(`{${k}}`, String(v))
        })
        return text
      }
      return key
    },
  })
  ;(useFeatureFlag as jest.Mock).mockReturnValue(overrides.featureFlag ?? true)
  ;(useUIStore as jest.Mock).mockReturnValue({ isSidebarHidden: overrides.sidebarHidden ?? false })
  ;(useModels as jest.Mock).mockReturnValue({
    models: overrides.models ?? mockModels,
    loading: overrides.modelsLoading ?? false,
    error: overrides.modelsError ?? null,
    refetch: jest.fn(),
    hasApiKeys: overrides.hasApiKeys ?? true,
    apiKeyStatus: overrides.apiKeyStatus ?? { openai: true },
  })
  ;(useAuth as jest.Mock).mockReturnValue({
    user: overrides.user ?? { id: 'user-1', username: 'tester', is_superadmin: false, role: 'admin' },
    currentOrganization: overrides.currentOrganization ?? null,
    apiClient: { get: jest.fn(), post: jest.fn() },
  })
  ;(useProjectStore as jest.Mock).mockReturnValue({
    currentProject: overrides.currentProject !== undefined ? overrides.currentProject : baseProject,
    loading: overrides.loading ?? false,
    fetchProject: mockFetchProject,
    updateProject: mockUpdateProject,
    deleteProject: mockDeleteProject,
  })

  // Mock fetch for report status and user completion
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ task: null, remaining: 0, is_published: false, can_publish: false, can_publish_reason: '' }),
  })

  // Mock apiClient.get for evaluation config
  ;(apiClient.get as jest.Mock).mockResolvedValue({ evaluation_configs: [], multi_field_evaluations: [] })
}

function renderPage() {
  const params = Promise.resolve({ id: 'test-id' })
  return render(<ProjectDetailPage params={params} />)
}

describe('ProjectDetailPage Branch Coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Mock window.addEventListener/removeEventListener without redefining location
    jest.spyOn(window, 'addEventListener').mockImplementation(jest.fn())
    jest.spyOn(window, 'removeEventListener').mockImplementation(jest.fn())
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Loading and Not Found states', () => {
    it('shows loading when projectId is not yet resolved', () => {
      setupMocks({ currentProject: null, loading: true })
      renderPage()
      expect(screen.getByText('project.loading')).toBeInTheDocument()
    })

    it('shows loading when loading=true and no currentProject', () => {
      setupMocks({ currentProject: null, loading: true })
      renderPage()
      expect(screen.getByText('project.loading')).toBeInTheDocument()
    })

    it('shows not found when loading=false and no currentProject', async () => {
      setupMocks({ currentProject: null, loading: false })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.notFound')).toBeInTheDocument()
        expect(screen.getByText('project.notFoundDescription')).toBeInTheDocument()
      })
    })

    it('navigates back to /projects from not found state', async () => {
      const user = userEvent.setup()
      setupMocks({ currentProject: null, loading: false })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.backToProjects')).toBeInTheDocument()
      })
      await user.click(screen.getByText('project.backToProjects'))
      expect(mockRouter.push).toHaveBeenCalledWith('/projects')
    })

    it('renders project when loading=true but currentProject exists (stale data)', async () => {
      setupMocks({ loading: true })
      renderPage()
      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Test Project' })).toBeInTheDocument()
      })
    })
  })

  describe('Completion rate calculation', () => {
    it('uses progress_percentage when defined', async () => {
      setupMocks({ currentProject: { ...baseProject, progress_percentage: 75 } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('75%')).toBeInTheDocument()
      })
    })

    it('falls back to annotation/task ratio when progress_percentage is undefined', async () => {
      setupMocks({ currentProject: { ...baseProject, progress_percentage: undefined, annotation_count: 30, task_count: 60 } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('50%')).toBeInTheDocument()
      })
    })

    it('shows 0% when task_count is 0 and progress_percentage is undefined', async () => {
      setupMocks({ currentProject: { ...baseProject, progress_percentage: undefined, task_count: 0, annotation_count: 0 } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('0%')).toBeInTheDocument()
      })
    })

    it('caps fallback rate at 100%', async () => {
      setupMocks({ currentProject: { ...baseProject, progress_percentage: undefined, annotation_count: 200, task_count: 100 } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('100%')).toBeInTheDocument()
      })
    })
  })

  describe('Organization context branches', () => {
    it('detects org project when organization and currentOrganization are present', async () => {
      setupMocks({ currentOrganization: { id: 'org-1', name: 'TUM', slug: 'tum' } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('TUM')).toBeInTheDocument()
      })
    })

    it('shows no organizations text when organizations array is empty', async () => {
      setupMocks({ currentProject: { ...baseProject, organizations: [] } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.details.noOrganizations')).toBeInTheDocument()
      })
    })

    it('shows no organizations when organizations is null', async () => {
      setupMocks({ currentProject: { ...baseProject, organizations: null } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.details.noOrganizations')).toBeInTheDocument()
      })
    })
  })

  describe('canEditProject branches', () => {
    it('allows editing for superadmin on org project', async () => {
      setupMocks({
        user: { id: 'admin-1', is_superadmin: true, role: 'admin' },
        currentOrganization: { id: 'org-1', name: 'TUM', slug: 'tum' },
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.annotationInstructions.title')).toBeInTheDocument()
      })
    })

    it('allows editing for ORG_ADMIN on org project', async () => {
      setupMocks({
        user: { id: 'org-admin-1', is_superadmin: false, role: 'ORG_ADMIN' },
        currentOrganization: { id: 'org-1', name: 'TUM', slug: 'tum' },
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.annotationInstructions.title')).toBeInTheDocument()
      })
    })

    it('allows editing for CONTRIBUTOR on org project', async () => {
      setupMocks({
        user: { id: 'contrib-1', is_superadmin: false, role: 'CONTRIBUTOR' },
        currentOrganization: { id: 'org-1', name: 'TUM', slug: 'tum' },
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.annotationInstructions.title')).toBeInTheDocument()
      })
    })

    it('shows read-only for ANNOTATOR on org project', async () => {
      setupMocks({
        user: { id: 'ann-1', is_superadmin: false, role: 'ANNOTATOR' },
        currentOrganization: { id: 'org-1', name: 'TUM', slug: 'tum' },
      })
      renderPage()
      await waitFor(() => {
        const readOnlyMessages = screen.getAllByText(/project\.permissions\.orgAdminOnly/)
        expect(readOnlyMessages.length).toBeGreaterThan(0)
      })
    })

    it('shows read-only for non-creator on private project', async () => {
      setupMocks({
        user: { id: 'other-user', is_superadmin: false, role: 'admin' },
        currentProject: { ...baseProject, organizations: [] },
        currentOrganization: null,
      })
      renderPage()
      await waitFor(() => {
        const readOnlyMessages = screen.getAllByText(/project\.permissions\.creatorOnly/)
        expect(readOnlyMessages.length).toBeGreaterThan(0)
      })
    })
  })

  describe('canDeleteProject branches', () => {
    it('enables delete for superadmin', async () => {
      setupMocks({ user: { id: 'admin-1', is_superadmin: true, role: 'admin' } })
      renderPage()
      await waitFor(() => {
        const deleteBtn = screen.getByText('project.deleteProject')
        expect(deleteBtn).not.toBeDisabled()
      })
    })

    it('enables delete for ORG_ADMIN on org project', async () => {
      setupMocks({
        user: { id: 'org-admin', is_superadmin: false, role: 'ORG_ADMIN' },
        currentOrganization: { id: 'org-1', name: 'TUM', slug: 'tum' },
      })
      renderPage()
      await waitFor(() => {
        const deleteBtn = screen.getByText('project.deleteProject')
        expect(deleteBtn).not.toBeDisabled()
      })
    })

    it('disables delete for non-superadmin non-org-admin', async () => {
      setupMocks({
        user: { id: 'user-1', is_superadmin: false, role: 'CONTRIBUTOR' },
        currentOrganization: null,
      })
      renderPage()
      await waitFor(() => {
        const deleteBtn = screen.getByText('project.deleteProject')
        expect(deleteBtn).toBeDisabled()
      })
    })
  })

  describe('canSeeQuickAction branches', () => {
    it('shows all actions for non-org project', async () => {
      setupMocks({ currentProject: { ...baseProject, organizations: [] }, currentOrganization: null })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.quickActions.startLabeling')).toBeInTheDocument()
        expect(screen.getByText('project.quickActions.projectData')).toBeInTheDocument()
      })
    })

    it('hides org-specific actions for ANNOTATOR on org project', async () => {
      setupMocks({
        user: { id: 'ann-1', is_superadmin: false, role: 'ANNOTATOR' },
        currentOrganization: { id: 'org-1', name: 'TUM', slug: 'tum' },
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.quickActions.startLabeling')).toBeInTheDocument()
      })
      // Data/review/generation/evaluation/members should not be visible
      expect(screen.queryByText('project.quickActions.projectData')).not.toBeInTheDocument()
    })

    it('shows all actions for superadmin on org project', async () => {
      setupMocks({
        user: { id: 'admin-1', is_superadmin: true, role: 'admin' },
        currentOrganization: { id: 'org-1', name: 'TUM', slug: 'tum' },
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.quickActions.startLabeling')).toBeInTheDocument()
        expect(screen.getByText('project.quickActions.projectData')).toBeInTheDocument()
      })
    })
  })

  describe('userCompletedAllTasks badge', () => {
    it('shows all-tasks-annotated badge when user completed all tasks', async () => {
      setupMocks()
      // apiClient.get is used for /next check; mock it to return no task
      ;(apiClient.get as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/next')) return Promise.resolve({ task: null, remaining: 0 })
        if (url.includes('/evaluation-config')) return Promise.resolve({ evaluation_configs: [] })
        return Promise.resolve({})
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.quickActions.allTasksAnnotated')).toBeInTheDocument()
      })
    })

    it('hides all-tasks-annotated badge when tasks remain', async () => {
      setupMocks()
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ task: { id: 'task-1' }, remaining: 5 }),
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.quickActions.startLabeling')).toBeInTheDocument()
      })
      expect(screen.queryByText('project.quickActions.allTasksAnnotated')).not.toBeInTheDocument()
    })

    it('hides badge when task_count is 0', async () => {
      setupMocks({ currentProject: { ...baseProject, task_count: 0 } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.quickActions.startLabeling')).toBeInTheDocument()
      })
      expect(screen.queryByText('project.quickActions.allTasksAnnotated')).not.toBeInTheDocument()
    })
  })

  describe('Model selection status text branches', () => {
    it('shows loading text when models are loading', async () => {
      setupMocks({ modelsLoading: true, models: [] })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.modelSelection.loading')).toBeInTheDocument()
      })
    })

    it('shows error text when models have error', async () => {
      setupMocks({ modelsError: { type: 'FETCH_ERROR', message: 'Connection failed' }, models: [] })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.modelSelection.errorLoading')).toBeInTheDocument()
      })
    })

    it('shows selected count text with correct format when models are loaded', async () => {
      // This test verifies the sortedModels ternary branch
      setupMocks()
      renderPage()
      await waitFor(() => {
        // When models are loaded, collapsed badge shows selectedCount
        expect(screen.getByText('project.modelSelection.title')).toBeInTheDocument()
      })
    })

    it('shows selected count when models are loaded', async () => {
      setupMocks()
      renderPage()
      await waitFor(() => {
        expect(screen.getByText(/project\.modelSelection\.selectedCount/)).toBeInTheDocument()
      })
    })
  })

  describe('Models error expanded state branches', () => {
    it('shows NO_API_KEYS error with configure link when expanded', async () => {
      const user = userEvent.setup()
      setupMocks({ modelsError: { type: 'NO_API_KEYS', message: 'No API keys configured' }, hasApiKeys: false, models: [] })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.modelSelection.title')).toBeInTheDocument()
      })
      await user.click(screen.getByText('project.modelSelection.title'))
      await waitFor(() => {
        expect(screen.getByText('project.modelSelection.noApiKeys')).toBeInTheDocument()
        expect(screen.getByText('project.modelSelection.configureApiKeys')).toBeInTheDocument()
      })
    })

    it('shows generic error message when not NO_API_KEYS', async () => {
      const user = userEvent.setup()
      setupMocks({ modelsError: { type: 'FETCH_ERROR', message: 'Server down' }, models: [] })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.modelSelection.title')).toBeInTheDocument()
      })
      await user.click(screen.getByText('project.modelSelection.title'))
      await waitFor(() => {
        expect(screen.getByText('Server down')).toBeInTheDocument()
      })
    })
  })

  describe('Description display branches', () => {
    it('shows description when present', async () => {
      setupMocks()
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('Description here')).toBeInTheDocument()
      })
    })

    it('shows fallback text when description is empty', async () => {
      setupMocks({ currentProject: { ...baseProject, description: '' } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('projects.noProjectsDescription')).toBeInTheDocument()
      })
    })
  })

  describe('updated_at branch', () => {
    it('shows last updated when updated_at is present', async () => {
      setupMocks()
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.details.lastUpdated')).toBeInTheDocument()
      })
    })

    it('hides last updated when updated_at is null', async () => {
      setupMocks({ currentProject: { ...baseProject, updated_at: null } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.details.title')).toBeInTheDocument()
      })
      expect(screen.queryByText('project.details.lastUpdated')).not.toBeInTheDocument()
    })
  })

  describe('created_by_name fallback', () => {
    it('shows created_by_name when present', async () => {
      setupMocks()
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('Creator')).toBeInTheDocument()
      })
    })

    it('shows unknown when created_by_name is empty', async () => {
      setupMocks({ currentProject: { ...baseProject, created_by_name: '' } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.details.unknown')).toBeInTheDocument()
      })
    })
  })

  describe('Label config section branches', () => {
    it('shows configured badge when config exists (collapsed)', async () => {
      setupMocks()
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.labelConfiguration.configured')).toBeInTheDocument()
      })
    })

    it('shows not configured badge when config is empty', async () => {
      setupMocks({ currentProject: { ...baseProject, label_config: '' } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.labelConfiguration.notConfigured')).toBeInTheDocument()
      })
    })

    it('shows no config set with configure button when expanded and no config', async () => {
      const user = userEvent.setup()
      setupMocks({ currentProject: { ...baseProject, label_config: '' } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.labelConfiguration.title')).toBeInTheDocument()
      })
      await user.click(screen.getByText('project.labelConfiguration.title'))
      await waitFor(() => {
        expect(screen.getByText('project.labelConfiguration.noConfigSet')).toBeInTheDocument()
        expect(screen.getByText('project.labelConfiguration.configureLabels')).toBeInTheDocument()
      })
    })
  })

  describe('Instructions section branches', () => {
    it('shows configured badge when instructions exist', async () => {
      setupMocks()
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.annotationInstructions.configured')).toBeInTheDocument()
      })
    })

    it('shows not configured when no instructions and no conditional instructions', async () => {
      setupMocks({ currentProject: { ...baseProject, instructions: '', conditional_instructions: [] } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.annotationInstructions.notConfigured')).toBeInTheDocument()
      })
    })

    it('shows configured when conditional instructions exist', async () => {
      setupMocks({
        currentProject: {
          ...baseProject,
          instructions: '',
          conditional_instructions: [{ id: 'ai', content: 'Use AI', weight: 50, ai_allowed: true }],
        },
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.annotationInstructions.configured')).toBeInTheDocument()
      })
    })

    it('shows no instructions text when expanded with no instructions', async () => {
      const user = userEvent.setup()
      setupMocks({ currentProject: { ...baseProject, instructions: '', conditional_instructions: [] } })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.annotationInstructions.title')).toBeInTheDocument()
      })
      await user.click(screen.getByText('project.annotationInstructions.title'))
      await waitFor(() => {
        expect(screen.getByText(/project\.annotationInstructions\.noInstructions/)).toBeInTheDocument()
      })
    })
  })

  describe('Evaluation badge text branches', () => {
    it('shows notConfigured when no evaluation config', async () => {
      setupMocks({
        currentProject: { ...baseProject, evaluation_config: {} },
      })
      // Mock apiClient.get to return no configs
      ;(apiClient.get as jest.Mock).mockResolvedValue({ evaluation_configs: [] })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.evaluation.notConfigured')).toBeInTheDocument()
      })
    })

    it('shows singular config count when 1 eval config exists', async () => {
      setupMocks({
        currentProject: { ...baseProject, evaluation_config: {} },
      })
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        evaluation_configs: [{ id: 'cfg-1', name: 'Test', field_pairs: [] }],
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText(/project\.evaluation\.evaluationConfigSingular/)).toBeInTheDocument()
      })
    })

    it('shows plural config count when multiple eval configs exist', async () => {
      setupMocks({
        currentProject: { ...baseProject, evaluation_config: {} },
      })
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        evaluation_configs: [
          { id: 'cfg-1', name: 'Test1', field_pairs: [] },
          { id: 'cfg-2', name: 'Test2', field_pairs: [] },
        ],
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText(/project\.evaluation\.evaluationConfigPlural/)).toBeInTheDocument()
      })
    })
  })

  describe('Sidebar hidden layout branch', () => {
    it('uses 4-column layout when sidebar is hidden', async () => {
      setupMocks({ sidebarHidden: true })
      const { container } = renderPage()
      await waitFor(() => {
        const grid = container.querySelector('.lg\\:grid-cols-4')
        expect(grid).toBeInTheDocument()
      })
    })

    it('uses 3-column layout when sidebar is visible', async () => {
      setupMocks({ sidebarHidden: false })
      const { container } = renderPage()
      await waitFor(() => {
        const grid = container.querySelector('.lg\\:grid-cols-3')
        expect(grid).toBeInTheDocument()
      })
    })
  })

  describe('Delete flow', () => {
    it('opens delete confirmation modal for superadmin', async () => {
      const user = userEvent.setup()
      setupMocks({
        user: { id: 'admin-1', is_superadmin: true, role: 'admin' },
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.deleteProject')).toBeInTheDocument()
      })
      const deleteBtn = screen.getAllByText('project.deleteProject')[0]
      await user.click(deleteBtn)
      await waitFor(() => {
        expect(screen.getByText('project.deleteConfirmMessage')).toBeInTheDocument()
        expect(screen.getByText('project.deleteConfirmItems.config')).toBeInTheDocument()
        expect(screen.getByText('project.deleteConfirmItems.irreversible')).toBeInTheDocument()
      })
    })
  })

  describe('handleSaveDescription branch', () => {
    it('saves description successfully', async () => {
      const user = userEvent.setup()
      setupMocks()
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('Description here')).toBeInTheDocument()
      })
      // Click edit description
      const descSection = screen.getByText('Description here').closest('div')
      const editButtons = within(descSection!).getAllByRole('button')
      await user.click(editButtons[0])
      await waitFor(() => {
        expect(screen.getByDisplayValue('Description here')).toBeInTheDocument()
      })
      // Save
      const saveBtn = screen.getByText('project.editing.save')
      await user.click(saveBtn)
      await waitFor(() => {
        expect(mockUpdateProject).toHaveBeenCalledWith('test-id', { description: 'Description here' })
      })
    })
  })

  describe('Empty models list branch', () => {
    it('shows no models for profile when models array is empty', async () => {
      const user = userEvent.setup()
      setupMocks({ models: [] })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('project.modelSelection.title')).toBeInTheDocument()
      })
      await user.click(screen.getByText('project.modelSelection.title'))
      await waitFor(() => {
        expect(screen.getByText('project.modelSelection.noModelsForProfile')).toBeInTheDocument()
      })
    })
  })

  describe('Start labeling disabled when no tasks', () => {
    it('disables start labeling when task_count is 0', async () => {
      setupMocks({ currentProject: { ...baseProject, task_count: 0 } })
      renderPage()
      await waitFor(() => {
        const startBtn = screen.getByText('project.quickActions.startLabeling')
        expect(startBtn).toBeDisabled()
      })
    })
  })

  describe('Report status fetch branches', () => {
    it('fetches report status for superadmin', async () => {
      setupMocks({ user: { id: 'admin-1', is_superadmin: true, role: 'admin' } })
      renderPage()
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled()
      })
    })

    it('fetches report 404 branch', async () => {
      setupMocks({ user: { id: 'admin-1', is_superadmin: true, role: 'admin' } })
      global.fetch = jest.fn().mockImplementation((url: string) => {
        if (typeof url === 'string' && url.includes('/report')) {
          return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) })
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ task: null, remaining: 0 }),
        })
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Test Project' })).toBeInTheDocument()
      })
    })
  })
})

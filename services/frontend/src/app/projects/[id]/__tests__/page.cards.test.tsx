/**
 * Project detail page — 4-card structure smoke test.
 *
 * Replaces the deleted page.test.tsx that exercised the old flat DOM.
 * Tests what actually matters in the new architecture: the 4 ConfigCards
 * render with the right titles, and the page wires fetch + auth correctly.
 * Per-card behavior (edit/save lifecycle, label-config-via-ref, settings)
 * is covered by component-level tests for ConfigCard + LabelConfigEditor;
 * deeper UI flows are puppeteer's job.
 *
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlag } from '@/contexts/FeatureFlagContext'
import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { apiClient } from '@/lib/api/client'
import { useUIStore } from '@/stores'
import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import { useRouter, useParams, useSearchParams, usePathname } from 'next/navigation'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useParams: jest.fn(() => ({ id: 'test-project-123' })),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/projects/test-project-123'),
}))

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('@/contexts/FeatureFlagContext')
jest.mock('@/hooks/useModels')
jest.mock('@/stores')
jest.mock('@/stores/projectStore')

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
jest.mock('@/components/shared/FeatureFlag', () => ({
  FeatureFlag: ({ children }: any) => <div>{children}</div>,
}))
jest.mock('@/components/projects/LabelConfigEditor', () => {
  const React = require('react')
  return {
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
  PromptStructuresManager: () => <div data-testid="prompt-structures-manager" />,
}))
jest.mock('@/components/projects/GenerationStructureEditor', () => ({
  GenerationStructureEditor: () => <div data-testid="generation-structure-editor" />,
}))
jest.mock('@/components/evaluation/EvaluationBuilder', () => ({
  EvaluationBuilder: () => <div data-testid="evaluation-builder" />,
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

describe('ProjectDetailPage — 4-card structure', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      currentOrganization: null,
    })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: (key: string) => key, // identity → keys appear verbatim in DOM
    })
    ;(useFeatureFlag as jest.Mock).mockReturnValue(true)
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
      currentProject: mockProject,
      loading: false,
      fetchProject: jest.fn(),
      updateProject: jest.fn().mockResolvedValue({}),
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })
    jest.spyOn(window, 'addEventListener').mockImplementation(jest.fn())
    jest.spyOn(window, 'removeEventListener').mockImplementation(jest.fn())
  })

  it('renders the project title in the header', async () => {
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    await waitFor(() => {
      expect(screen.getAllByText('Test Project').length).toBeGreaterThan(0)
    })
  })

  it('renders all 4 ConfigCards with their titles', async () => {
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    await waitFor(() => {
      // i18n mock returns the key verbatim, so each card title appears as
      // its translation key. The 4 cards from the rework:
      expect(screen.getByText('project.annotationConfiguration.title')).toBeInTheDocument()
      expect(screen.getByText('project.generationConfiguration.title')).toBeInTheDocument()
      expect(screen.getByText('project.evaluation.title')).toBeInTheDocument()
      expect(screen.getByText('project.settings.title')).toBeInTheDocument()
    })
  })

  it('hides Annotation card when enable_annotation is false', async () => {
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: { ...mockProject, enable_annotation: false },
      loading: false,
      fetchProject: jest.fn(),
      updateProject: jest.fn().mockResolvedValue({}),
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    await waitFor(() => {
      expect(screen.getByText('project.generationConfiguration.title')).toBeInTheDocument()
    })
    expect(screen.queryByText('project.annotationConfiguration.title')).not.toBeInTheDocument()
  })

  it('hides Generation card when enable_generation is false', async () => {
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: { ...mockProject, enable_generation: false },
      loading: false,
      fetchProject: jest.fn(),
      updateProject: jest.fn().mockResolvedValue({}),
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    await waitFor(() => {
      expect(screen.getByText('project.annotationConfiguration.title')).toBeInTheDocument()
    })
    expect(screen.queryByText('project.generationConfiguration.title')).not.toBeInTheDocument()
  })

  it('hides Evaluation card when enable_evaluation is false', async () => {
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: { ...mockProject, enable_evaluation: false },
      loading: false,
      fetchProject: jest.fn(),
      updateProject: jest.fn().mockResolvedValue({}),
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    await waitFor(() => {
      expect(screen.getByText('project.annotationConfiguration.title')).toBeInTheDocument()
    })
    expect(screen.queryByText('project.evaluation.title')).not.toBeInTheDocument()
  })

  it('triggers fetchProject on mount', async () => {
    const fetchProject = jest.fn()
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: mockProject,
      loading: false,
      fetchProject,
      updateProject: jest.fn().mockResolvedValue({}),
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    await waitFor(() => {
      expect(fetchProject).toHaveBeenCalledWith('test-project-123')
    })
  })

  it('renders loading state when project is null', async () => {
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: null,
      loading: true,
      fetchProject: jest.fn(),
      updateProject: jest.fn().mockResolvedValue({}),
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    // Loading state — none of the card titles should appear
    expect(screen.queryByText('project.annotationConfiguration.title')).not.toBeInTheDocument()
  })
})

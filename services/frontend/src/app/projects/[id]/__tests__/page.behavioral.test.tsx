/**
 * Behavioral coverage tests for the Project Detail page.
 *
 * These tests drive the PAGE's own logic — render-state branches, the
 * inline title/description editing flow, the delete-confirm modal, the
 * sidebar quick-action navigation, the feature-visibility toggles, the
 * server-vs-fallback completion-rate computation, and the superadmin
 * report card. Heavy children (ConfigCard / SubSection / EvaluationBuilder
 * / modals / permissions panel) are reduced to markers that expose their
 * props so we can exercise the page's handlers without their internals.
 *
 * Distinct from the existing page.cards.test.tsx ("4 cards render") and
 * page.surgical2.test.tsx (line-targeted smoke): every test here asserts
 * real DOM, an invoked callback, a fetch/updateProject arg, or a state
 * transition.
 *
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { apiClient } from '@/lib/api/client'
import { useUIStore } from '@/stores'
import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import {
  render,
  screen,
  waitFor,
  act,
  fireEvent,
  within,
} from '@testing-library/react'
import { useRouter } from 'next/navigation'

// Re-mock next/navigation locally so useRouter().push is a stable captured
// spy (the global jest.setup mock hands back a fresh push each render).
const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useParams: jest.fn(() => ({ id: 'proj-1' })),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/projects/proj-1'),
}))

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('@/hooks/useModels')
jest.mock('@/stores')
jest.mock('@/stores/projectStore')

// Toast — stable captured spy so we can assert on success/error toasts.
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    put: jest.fn(),
    post: jest.fn(),
    evaluations: {
      getAvailableEvaluationFields: jest.fn(),
    },
  },
}))

// Shared shells reduced to pass-through wrappers so inner content always
// renders (the real ones are collapsed-by-default), letting us assert the
// page's own DOM + handlers.
jest.mock('@/components/projects/ConfigCard', () => ({
  ConfigCard: ({ title, children, canEdit, editing, onEdit, onSave, onCancel }: any) => (
    <section data-testid={`config-card-${title}`}>
      <h2>{title}</h2>
      {canEdit !== false && onEdit && (
        <button onClick={onEdit} data-testid={`card-edit-${title}`}>
          edit-{title}
        </button>
      )}
      {editing && onSave && (
        <button onClick={onSave} data-testid={`card-save-${title}`}>
          save-{title}
        </button>
      )}
      {editing && onCancel && (
        <button onClick={onCancel} data-testid={`card-cancel-${title}`}>
          cancel-{title}
        </button>
      )}
      {children}
    </section>
  ),
}))
jest.mock('@/components/projects/SubSection', () => ({
  SubSection: ({ title, children, badge }: any) => (
    <div data-testid={`subsection-${title}`}>
      <h3>{title}</h3>
      {badge && <span data-testid={`subsection-badge-${title}`}>{badge}</span>}
      {children}
    </div>
  ),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </nav>
  ),
}))
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, href, ...props }: any) =>
    href ? (
      <a href={href} {...props}>
        {children}
      </a>
    ) : (
      <button onClick={onClick} disabled={disabled} {...props}>
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
jest.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({ children }: any) => <>{children}</>,
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
jest.mock('@/components/projects/ProjectPermissionsPanel', () => ({
  ProjectPermissionsPanel: (props: any) => (
    <div
      data-testid="permissions-panel"
      data-visibility={props.initialVisibility}
    />
  ),
}))
jest.mock('@/components/evaluation/EvaluationBuilder', () => ({
  EvaluationBuilder: () => <div data-testid="evaluation-builder" />,
}))
jest.mock('@/components/generation/GenerationControlModal', () => ({
  GenerationControlModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="generation-control-modal" /> : null,
}))
jest.mock('@/components/evaluation/EvaluationControlModal', () => ({
  EvaluationControlModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="evaluation-control-modal" /> : null,
}))
jest.mock('@/components/reports/PublicationToggle', () => ({
  PublicationToggle: (props: any) => (
    <button
      data-testid="publication-toggle"
      onClick={() => props.onToggle(!props.isPublished)}
    >
      toggle-publish
    </button>
  ),
}))
jest.mock('date-fns', () => ({ formatDistanceToNow: () => '2 days ago' }))

const baseProject = {
  id: 'proj-1',
  title: 'Legal Benchmark',
  description: 'A legal benchmarking project',
  created_by: 'user-1',
  created_by_name: 'Alice',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
  task_count: 10,
  annotation_count: 4,
  generation_count: 2,
  evaluation_count: 3,
  progress_percentage: 50,
  label_config: '<View/>',
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
}

const superadmin = {
  id: 'user-1',
  username: 'admin',
  email: 'admin@example.com',
  role: 'admin',
  is_superadmin: true,
}

function setStore(overrides: Record<string, any> = {}) {
  const store = {
    currentProject: baseProject,
    loading: false,
    fetchProject: jest.fn(),
    updateProject: jest.fn().mockResolvedValue({}),
    deleteProject: jest.fn().mockResolvedValue({}),
    ...overrides,
  }
  ;(useProjectStore as jest.Mock).mockReturnValue(store)
  return store
}

let ProjectDetailPage: any
beforeAll(async () => {
  ProjectDetailPage = (await import('../page')).default
})

const params = () => Promise.resolve({ id: 'proj-1' })

beforeEach(() => {
  jest.clearAllMocks()
  ;(useRouter as jest.Mock).mockReturnValue({ push: mockPush })
  ;(useAuth as jest.Mock).mockReturnValue({
    user: superadmin,
    currentOrganization: null,
  })
  ;(useI18n as jest.Mock).mockReturnValue({
    t: (key: string, vars?: any) =>
      vars ? `${key}:${JSON.stringify(vars)}` : key,
  })
  ;(useUIStore as jest.Mock).mockReturnValue({ isSidebarHidden: false })
  ;(useModels as jest.Mock).mockReturnValue({
    models: [],
    loading: false,
    error: null,
    refetch: jest.fn(),
    hasApiKeys: true,
    apiKeyStatus: {},
  })
  setStore()
  ;(apiClient.get as jest.Mock).mockResolvedValue({ task: null, remaining: 0 })
  ;(apiClient.evaluations.getAvailableEvaluationFields as jest.Mock).mockResolvedValue(
    { model_response_fields: [], human_annotation_fields: [], reference_fields: [], all_fields: [] },
  )
  global.fetch = jest.fn().mockResolvedValue({
    ok: false,
    status: 404,
    json: jest.fn(),
  }) as any
})

describe('ProjectDetailPage — render-state branches', () => {
  it('shows the loading spinner while loading with no project yet', () => {
    setStore({ currentProject: null, loading: true })
    render(<ProjectDetailPage params={params()} />)
    expect(screen.getByText('project.loading')).toBeInTheDocument()
    expect(screen.queryByText('Legal Benchmark')).not.toBeInTheDocument()
  })

  it('shows the not-found card when loading finished but project is null', async () => {
    setStore({ currentProject: null, loading: false })
    render(<ProjectDetailPage params={params()} />)
    await waitFor(() => {
      expect(screen.getByText('project.notFound')).toBeInTheDocument()
    })
    expect(screen.getByText('project.notFoundDescription')).toBeInTheDocument()
  })

  it('navigates back to /projects from the not-found card button', async () => {
    setStore({ currentProject: null, loading: false })
    render(<ProjectDetailPage params={params()} />)
    const back = await screen.findByText('project.backToProjects')
    fireEvent.click(back)
    expect(mockPush).toHaveBeenCalledWith('/projects')
  })

  it('renders the project header, id and org chips once loaded', async () => {
    render(<ProjectDetailPage params={params()} />)
    await waitFor(() => {
      expect(screen.getAllByText('Legal Benchmark').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('proj-1')).toBeInTheDocument()
    expect(screen.getByText('TUM')).toBeInTheDocument()
  })

  it('fetches the project on mount via the resolved params id', async () => {
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await waitFor(() => {
      expect(store.fetchProject).toHaveBeenCalledWith('proj-1')
    })
  })
})

describe('ProjectDetailPage — inline title editing', () => {
  it('enters edit mode and saves a new title via updateProject', async () => {
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')

    // The pencil button is the only icon button next to the title; entering
    // edit mode swaps the h1 for an <input> seeded with the current title.
    const editButtons = screen.getAllByRole('button')
    // Title edit pencil sits right after the <h1>; click the first pencil.
    const pencil = editButtons.find((b) =>
      b.querySelector('svg'),
    )
    fireEvent.click(pencil!)

    const input = await screen.findByDisplayValue('Legal Benchmark')
    fireEvent.change(input, { target: { value: 'Renamed Project' } })
    fireEvent.click(screen.getByText('project.editing.save'))

    await waitFor(() => {
      expect(store.updateProject).toHaveBeenCalledWith('proj-1', {
        title: 'Renamed Project',
      })
    })
    expect(mockAddToast).toHaveBeenCalledWith('toasts.project.titleUpdated', 'success')
  })

  it('warns and does not call updateProject when the title is blank', async () => {
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')

    const pencil = screen.getAllByRole('button').find((b) => b.querySelector('svg'))
    fireEvent.click(pencil!)
    const input = await screen.findByDisplayValue('Legal Benchmark')
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.click(screen.getByText('project.editing.save'))

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith('toasts.project.titleEmpty', 'warning')
    })
    expect(store.updateProject).not.toHaveBeenCalled()
  })

  it('cancels title editing without persisting and restores the heading', async () => {
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')

    const pencil = screen.getAllByRole('button').find((b) => b.querySelector('svg'))
    fireEvent.click(pencil!)
    const input = await screen.findByDisplayValue('Legal Benchmark')
    fireEvent.change(input, { target: { value: 'Throwaway' } })
    fireEvent.click(screen.getByText('project.editing.cancel'))

    // Heading is back, no update fired.
    await waitFor(() => {
      expect(screen.getAllByText('Legal Benchmark').length).toBeGreaterThan(0)
    })
    expect(store.updateProject).not.toHaveBeenCalled()
  })

  it('shows a failure toast when the title update rejects', async () => {
    const store = setStore({
      updateProject: jest.fn().mockRejectedValue(new Error('boom')),
    })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')

    const pencil = screen.getAllByRole('button').find((b) => b.querySelector('svg'))
    fireEvent.click(pencil!)
    const input = await screen.findByDisplayValue('Legal Benchmark')
    fireEvent.change(input, { target: { value: 'New' } })
    fireEvent.click(screen.getByText('project.editing.save'))

    await waitFor(() => {
      expect(store.updateProject).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'toasts.project.titleUpdateFailed:{"error":"boom"}',
        'error',
      )
    })
  })
})

describe('ProjectDetailPage — delete flow', () => {
  it('opens the confirm modal, deletes, then navigates to /projects', async () => {
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')

    fireEvent.click(screen.getByText('project.deleteProject'))
    // Modal headline includes the project title.
    const headline = screen.getByText('project.deleteConfirmTitle: Legal Benchmark')
    expect(headline).toBeInTheDocument()

    // The modal confirm button is the red one inside the modal subtree;
    // scope to the modal container to avoid the sidebar's open-modal button.
    const modal = headline.closest('div.fixed') as HTMLElement
    const confirm = within(modal).getByText('project.deleteProject')
    fireEvent.click(confirm)

    await waitFor(() => {
      expect(store.deleteProject).toHaveBeenCalledWith('proj-1')
    })
    expect(mockPush).toHaveBeenCalledWith('/projects')
    expect(mockAddToast).toHaveBeenCalledWith('toasts.project.deleted', 'success')
  })

  it('keeps the modal data and toasts an error when delete rejects', async () => {
    const store = setStore({
      deleteProject: jest.fn().mockRejectedValue(new Error('locked')),
    })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')

    fireEvent.click(screen.getByText('project.deleteProject'))
    const headline = screen.getByText('project.deleteConfirmTitle: Legal Benchmark')
    const modal = headline.closest('div.fixed') as HTMLElement
    fireEvent.click(within(modal).getByText('project.deleteProject'))

    await waitFor(() => {
      expect(store.deleteProject).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'toasts.project.deleteFailed:{"error":"locked"}',
        'error',
      )
    })
    expect(mockPush).not.toHaveBeenCalledWith('/projects')
  })
})

describe('ProjectDetailPage — sidebar quick actions', () => {
  it('Start Labeling routes to the label page', async () => {
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    fireEvent.click(screen.getByText('project.quickActions.startLabeling'))
    expect(mockPush).toHaveBeenCalledWith('/projects/proj-1/label')
  })

  it('disables Start Labeling when the project has no tasks', async () => {
    setStore({ currentProject: { ...baseProject, task_count: 0 } })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    const btn = screen.getByText('project.quickActions.startLabeling').closest('button')
    expect(btn).toBeDisabled()
  })

  it('Generation quick action routes to the generations page with the project id', async () => {
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    fireEvent.click(screen.getByText('project.quickActions.generation'))
    expect(mockPush).toHaveBeenCalledWith('/generations?projectId=proj-1')
  })

  it('Evaluations quick action routes to the evaluations page with the project id', async () => {
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    fireEvent.click(screen.getByText('project.quickActions.evaluations'))
    expect(mockPush).toHaveBeenCalledWith('/evaluations?projectId=proj-1')
  })

  it('shows the "all tasks annotated" banner when the user finished every task', async () => {
    // /next returns no task + 0 remaining → userCompletedAllTasks true.
    ;(apiClient.get as jest.Mock).mockResolvedValue({ task: null, remaining: 0 })
    render(<ProjectDetailPage params={params()} />)
    await waitFor(() => {
      expect(
        screen.getByText('project.quickActions.allTasksAnnotated'),
      ).toBeInTheDocument()
    })
  })

  it('hides the "all tasks annotated" banner when tasks remain', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue({ task: { id: 't1' }, remaining: 3 })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith('/projects/proj-1/next')
    })
    expect(
      screen.queryByText('project.quickActions.allTasksAnnotated'),
    ).not.toBeInTheDocument()
  })

  it('renders My Tasks for a non-superadmin and hides it for a superadmin', async () => {
    // Non-superadmin creator sees the My Tasks link.
    ;(useAuth as jest.Mock).mockReturnValue({
      user: { ...superadmin, is_superadmin: false },
      currentOrganization: null,
    })
    const { unmount } = render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    expect(screen.getByText('project.quickActions.myTasks')).toBeInTheDocument()
    unmount()

    // Superadmin: no My Tasks link.
    ;(useAuth as jest.Mock).mockReturnValue({
      user: superadmin,
      currentOrganization: null,
    })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    expect(screen.queryByText('project.quickActions.myTasks')).not.toBeInTheDocument()
  })
})

describe('ProjectDetailPage — statistics + completion rate', () => {
  it('uses server progress_percentage when present (rounded)', async () => {
    setStore({ currentProject: { ...baseProject, progress_percentage: 66.7 } })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    expect(screen.getByText('67%')).toBeInTheDocument()
  })

  it('falls back to the client-side mix when progress_percentage is absent', async () => {
    // annotation stage 5/10 = 50, no generation models, evaluation 3/3 = 3/3.
    // parts: [5,10] and [3,3] → completed 8 / expected 13 → 62%.
    setStore({
      currentProject: {
        ...baseProject,
        progress_percentage: undefined,
        completed_tasks_count: 5,
        task_count: 10,
        generation_models_count: 0,
        evaluations_completed_count: 3,
        evaluation_count: 3,
      },
    })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    expect(screen.getByText('62%')).toBeInTheDocument()
  })

  it('shows 0% in the fallback when no stage has any expected work', async () => {
    setStore({
      currentProject: {
        ...baseProject,
        progress_percentage: undefined,
        completed_tasks_count: 0,
        task_count: 0,
        generation_models_count: 0,
        evaluations_completed_count: 0,
        evaluation_count: 0,
      },
    })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('renders the no-tasks recent-activity empty state with an import CTA', async () => {
    setStore({ currentProject: { ...baseProject, task_count: 0 } })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    fireEvent.click(screen.getByText('project.recentActivity.importData'))
    expect(mockPush).toHaveBeenCalledWith('/projects/proj-1?tab=data')
  })
})

describe('ProjectDetailPage — feature visibility toggles', () => {
  it('persists a feature flip through updateProject when a checkbox is toggled', async () => {
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')

    // Feature-visibility lives in the Project Settings SubSection. Find the
    // checkbox whose label is the Annotation card title.
    const featureSub = screen.getByTestId(
      'subsection-project.settings.featureVisibility.title',
    )
    const checkboxes = within(featureSub).getAllByRole('checkbox')
    // All three start checked (enable_* !== false). Uncheck the first.
    await act(async () => {
      fireEvent.click(checkboxes[0])
    })
    await waitFor(() => {
      expect(store.updateProject).toHaveBeenCalledWith('proj-1', {
        enable_annotation: false,
      })
    })
  })

  it('toasts an error when a feature flip fails', async () => {
    setStore({ updateProject: jest.fn().mockRejectedValue(new Error('nope')) })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    const featureSub = screen.getByTestId(
      'subsection-project.settings.featureVisibility.title',
    )
    const checkboxes = within(featureSub).getAllByRole('checkbox')
    await act(async () => {
      fireEvent.click(checkboxes[1])
    })
    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'toasts.project.settingsSaveFailed:{"error":"nope"}',
        'error',
      )
    })
  })
})

describe('ProjectDetailPage — superadmin report card', () => {
  it('renders the auto-generated hint when no report exists (404)', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: jest.fn(),
    }) as any
    render(<ProjectDetailPage params={params()} />)
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/projects/proj-1/report'),
        expect.objectContaining({ credentials: 'include' }),
      )
    })
    await waitFor(() => {
      expect(screen.getByText('project.report.autoGenerated')).toBeInTheDocument()
    })
  })

  it('renders the publication toggle + edit button when a report exists', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: jest.fn().mockResolvedValue({
        is_published: false,
        can_publish: true,
        can_publish_reason: '',
      }),
    }) as any
    render(<ProjectDetailPage params={params()} />)
    const editBtn = await screen.findByText('project.report.editReport')
    expect(screen.getByTestId('publication-toggle')).toBeInTheDocument()
    fireEvent.click(editBtn)
    expect(mockPush).toHaveBeenCalledWith('/projects/proj-1/report/edit')
  })

  it('reflects a publish toggle into local state with a success toast', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: jest.fn().mockResolvedValue({
        is_published: false,
        can_publish: true,
        can_publish_reason: '',
      }),
    }) as any
    render(<ProjectDetailPage params={params()} />)
    const toggle = await screen.findByTestId('publication-toggle')
    fireEvent.click(toggle)
    expect(mockAddToast).toHaveBeenCalledWith(
      'project.report.publishedSuccessfully',
      'success',
    )
  })

  it('does not fetch the report for a non-superadmin user', async () => {
    ;(useAuth as jest.Mock).mockReturnValue({
      user: { ...superadmin, is_superadmin: false },
      currentOrganization: null,
    })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByText('proj-1')
    // fetchReportStatus early-returns for non-superadmin: no /report fetch.
    const reportCalls = (global.fetch as jest.Mock).mock.calls.filter((c) =>
      String(c[0]).includes('/report'),
    )
    expect(reportCalls).toHaveLength(0)
  })
})

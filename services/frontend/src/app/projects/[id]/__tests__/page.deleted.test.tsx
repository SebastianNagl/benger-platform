/**
 * Project detail page of a soft-deleted project (migration 093). Only
 * superadmins can open one (the API answers 404 to everyone else); they see
 * its contents read-only: no edit controls, no delete, no report publishing,
 * and only the project-data quick action. The banner with the restore lives
 * in the project layout (DeletedProjectBanner.test).
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
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import {
  useParams,
  usePathname,
  useRouter,
  useSearchParams,
} from 'next/navigation'

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

describe('ProjectDetailPage — deleted project (superadmin view)', () => {
  const setup = (projectOverrides: any) => {
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      currentOrganization: null,
    })
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
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      exists: true,
      id: 'r1',
      is_published: false,
      can_publish: true,
    })
    jest.spyOn(window, 'addEventListener').mockImplementation(jest.fn())
    jest.spyOn(window, 'removeEventListener').mockImplementation(jest.fn())
  }

  beforeEach(() => jest.clearAllMocks())

  it('a deleted project opens read-only with only the project-data action', async () => {
    setup({ deleted_at: '2026-09-01T10:00:00Z', effective_role: 'ORG_ADMIN' })
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    await screen.findAllByText('Test Project')

    // Contents stay visible: details, statistics, the way into the tasks.
    expect(screen.getByTestId('project-status')).toHaveTextContent(
      'project.details.deleted',
    )
    expect(
      screen.getByText('project.quickActions.projectData'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('project.quickActions.projectData').closest('button'),
    ).toHaveAttribute('href', '/projects/test-project-123/data')

    // No work in it and no second delete.
    for (const key of [
      'project.quickActions.startLabeling',
      'project.quickActions.generation',
      'project.quickActions.evaluations',
      'project.deleteProject',
    ]) {
      expect(screen.queryByText(key)).not.toBeInTheDocument()
    }
    // The header icon is plain text, not the icon picker.
    expect(screen.getByTestId('project-header-icon').tagName).toBe('SPAN')
    // Neither the visibility danger zone nor report publishing.
    fireEvent.click(screen.getByText('project.settings.title'))
    expect(
      screen.queryByTestId('project-visibility-danger-zone'),
    ).not.toBeInTheDocument()
    expect(screen.queryByTestId('publication-toggle')).not.toBeInTheDocument()
  })

  it('the same project, live, keeps every superadmin control', async () => {
    setup({ deleted_at: null, effective_role: 'ORG_ADMIN' })
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    await screen.findAllByText('Test Project')
    expect(screen.getByTestId('project-status')).toHaveTextContent(
      'project.details.active',
    )
    expect(
      screen.getByText('project.quickActions.startLabeling'),
    ).toBeInTheDocument()
    expect(screen.getByText('project.deleteProject')).toBeInTheDocument()
    expect(screen.getByTestId('project-header-icon').tagName).toBe('BUTTON')
    fireEvent.click(screen.getByText('project.settings.title'))
    expect(
      screen.getByTestId('project-visibility-danger-zone'),
    ).toBeInTheDocument()
    expect(await screen.findByTestId('publication-toggle')).toBeInTheDocument()
  })
})

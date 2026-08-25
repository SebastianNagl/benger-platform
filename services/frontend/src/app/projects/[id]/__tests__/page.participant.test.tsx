/**
 * Project detail page — participant tier (joined via share link / discovery).
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
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  PromptStructuresManager: () => <div data-testid="prompt-structures-manager" />,
}))
jest.mock('@/components/projects/GenerationStructureEditor', () => ({
  GenerationStructureEditor: () => <div data-testid="generation-structure-editor" />,
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

describe('ProjectDetailPage — participant tier', () => {
  const annotatorUser = { ...mockUser, id: 'member-1', role: 'ANNOTATOR', is_superadmin: false }
  const setup = (projectOverrides: any, user: any = annotatorUser) => {
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({ user, currentOrganization: null })
    ;(useI18n as jest.Mock).mockReturnValue({ t: (key: string) => key })
    ;(useFeatureFlag as jest.Mock).mockReturnValue(true)
    ;(useUIStore as jest.Mock).mockReturnValue({ isSidebarHidden: false })
    ;(useModels as jest.Mock).mockReturnValue({
      models: [], loading: false, error: null, refetch: jest.fn(), hasApiKeys: true, apiKeyStatus: {},
    })
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: { ...mockProject, ...projectOverrides },
      loading: false,
      fetchProject: jest.fn(),
      updateProject: jest.fn().mockResolvedValue({}),
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })
    jest.spyOn(window, 'addEventListener').mockImplementation(jest.fn())
    jest.spyOn(window, 'removeEventListener').mockImplementation(jest.fn())
  }

  beforeEach(() => jest.clearAllMocks())

  it('shows the badge + participant card, hides config cards/sharing, skips editor fetches', async () => {
    setup({
      access_tier: 'participant',
      participant_via: 'share',
      effective_role: 'ANNOTATOR',
      can_manage_shares: false,
      evaluation_config: null,
      generation_config: null,
    })
    const { registerSlot } = jest.requireActual('@/lib/extensions/slots')
    registerSlot('project-sharing', () => <div data-testid="sharing-stub" />)
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    expect(await screen.findByTestId('project-participant-badge')).toBeInTheDocument()
    const card = screen.getByTestId('participant-card-stub')
    expect(card).toHaveAttribute('data-via', 'share')
    expect(card).toHaveTextContent('test-project-123')
    // No settings / sharing for participants; quick actions reduced.
    expect(screen.queryByText('project.settings.title')).not.toBeInTheDocument()
    expect(screen.queryByTestId('sharing-stub')).not.toBeInTheDocument()
    expect(screen.queryByText('project.quickActions.projectData')).not.toBeInTheDocument()
    // No evaluation-config / report fetches (they would 403).
    const calledUrls = (apiClient.get as jest.Mock).mock.calls.map((c) => String(c[0]))
    expect(calledUrls.some((u) => u.includes('evaluation-config'))).toBe(false)
    expect(calledUrls.some((u) => u.includes('/report'))).toBe(false)
    fireEvent.click(screen.getByText('leave'))
    expect(mockRouter.push).toHaveBeenCalledWith('/projects')
    registerSlot('project-sharing', null as any)
  })

  it('full-tier annotator (effective_role) gets no participant card and no edit controls', async () => {
    setup({ access_tier: 'full', effective_role: 'ANNOTATOR' })
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    await screen.findAllByText('Test Project')
    expect(screen.queryByTestId('participant-card-stub')).not.toBeInTheDocument()
    expect(screen.queryByTestId('project-participant-badge')).not.toBeInTheDocument()
    // Config cards stay (contents are gated per card), no title edit button.
    expect(screen.getByText('project.settings.title')).toBeInTheDocument()
  })

  it('mounts the deck workspace slot with canEdit for editors', async () => {
    // Org project + CONTRIBUTOR context role (edit rights are membership
    // based; the API's effective_role is display-only on this page).
    setup({ access_tier: 'full', effective_role: 'CONTRIBUTOR' }, {
      ...annotatorUser,
      role: 'CONTRIBUTOR',
    })
    ;(useAuth as jest.Mock).mockReturnValue({
      user: { ...annotatorUser, role: 'CONTRIBUTOR' },
      currentOrganization: { id: 'org-1', name: 'TUM' },
    })
    const { registerSlot } = jest.requireActual('@/lib/extensions/slots')
    const Stub = jest.fn(({ project, canEdit }: any) => (
      <div data-testid="deck-stub" data-can-edit={String(canEdit)}>{project.id}</div>
    ))
    registerSlot('project-deck-workspace', Stub)
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    const stub = await screen.findByTestId('deck-stub')
    expect(stub).toHaveAttribute('data-can-edit', 'true')
    expect(stub).toHaveTextContent('test-project-123')
    registerSlot('project-deck-workspace', null as any)
  })
})

describe('ProjectDetailPage — header icon editing', () => {
  const setup = (projectOverrides: any, user: any) => {
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({ user, currentOrganization: null })
    ;(useI18n as jest.Mock).mockReturnValue({ t: (k: string, d?: any) => (typeof d === 'string' ? d : k) })
    ;(useFeatureFlag as jest.Mock).mockReturnValue(true)
    ;(useUIStore as jest.Mock).mockReturnValue({ isSidebarHidden: false })
    ;(useModels as jest.Mock).mockReturnValue({
      models: [], loading: false, error: null, refetch: jest.fn(), hasApiKeys: true, apiKeyStatus: {},
    })
    const updateProject = jest.fn().mockResolvedValue({})
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: { ...mockProject, ...projectOverrides },
      loading: false,
      fetchProject: jest.fn(),
      updateProject,
      deleteProject: jest.fn().mockResolvedValue({}),
    })
    ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })
    jest.spyOn(window, 'addEventListener').mockImplementation(jest.fn())
    jest.spyOn(window, 'removeEventListener').mockImplementation(jest.fn())
    return { updateProject }
  }
  beforeEach(() => jest.clearAllMocks())

  it('creator: icon is a button that opens the picker and PATCHes the choice', async () => {
    const { updateProject } = setup(
      { icon: '📚', kind: 'exam', created_by: 'user-123' },
      { ...mockUser, is_superadmin: false, role: 'ANNOTATOR' },
    )
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    const icon = await screen.findByTestId('project-header-icon')
    expect(icon.tagName).toBe('BUTTON')
    expect(icon).toHaveTextContent('📚')
    fireEvent.click(icon)
    fireEvent.click(await screen.findByTestId('project-icon-🎓'))
    fireEvent.click(screen.getByTestId('project-icon-save'))
    await waitFor(() =>
      expect(updateProject).toHaveBeenCalledWith('test-project-123', { icon: '🎓' }),
    )
  })

  it('non-creator annotator: icon is plain text', async () => {
    setup({ icon: '📚', created_by: 'someone-else' }, { ...mockUser, id: 'member-1', is_superadmin: false, role: 'ANNOTATOR' })
    const params = Promise.resolve({ id: 'test-project-123' })
    render(<ProjectDetailPage params={params} />)
    const icon = await screen.findByTestId('project-header-icon')
    expect(icon.tagName).toBe('SPAN')
  })
})

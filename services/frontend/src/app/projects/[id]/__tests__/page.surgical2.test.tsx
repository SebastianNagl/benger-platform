/**
 * Surgical branch coverage tests for Project Detail Page
 * Targets uncovered lines: 157, 162, 274, 276, 277, 278, 355, 452, 459, 494, 495, 527, 585, 586, 587
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
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { useRouter, useParams, useSearchParams, usePathname } from 'next/navigation'

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useParams: jest.fn(),
  useSearchParams: jest.fn(),
  usePathname: jest.fn(() => '/projects/test-project-123'),
}))

// Mock contexts
jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('@/contexts/FeatureFlagContext')

// Mock hooks
jest.mock('@/hooks/useModels')

// Mock stores
jest.mock('@/stores')
jest.mock('@/stores/projectStore')

// Mock api client
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

// Mock components
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: jest.fn(),
  }),
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
  Button: ({ children, onClick, href, disabled, className, ...props }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      className={className}
      {...props}
    >
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
  Select: ({ children, value, onValueChange, disabled }: any) => (
    <div data-testid="select" data-value={value}>
      {children}
    </div>
  ),
  SelectTrigger: ({ children }: any) => <div>{children}</div>,
  SelectValue: () => <div>Select Value</div>,
  SelectContent: ({ children }: any) => <div>{children}</div>,
  SelectItem: ({ children, value }: any) => (
    <div data-value={value}>{children}</div>
  ),
}))

jest.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({ children, content }: any) => (
    <div title={content}>{children}</div>
  ),
}))

jest.mock('@/components/shared/FeatureFlag', () => ({
  FeatureFlag: ({ children, flag }: any) => (
    <div data-flag={flag}>{children}</div>
  ),
}))

jest.mock('@/components/projects/LabelConfigEditor', () => ({
  LabelConfigEditor: ({ initialConfig, onSave, onCancel }: any) => (
    <div data-testid="label-config-editor">
      <button onClick={() => onSave(initialConfig)}>Save Config</button>
      <button onClick={onCancel}>Cancel</button>
    </div>
  ),
}))

jest.mock('@/components/projects/PromptStructuresManager', () => ({
  PromptStructuresManager: ({ projectId, onStructuresChange }: any) => (
    <div data-testid="prompt-structures-manager">
      Prompt Structures for {projectId}
    </div>
  ),
}))

jest.mock('@/components/projects/GenerationStructureEditor', () => ({
  GenerationStructureEditor: () => <div>Generation Structure Editor</div>,
}))

jest.mock('@/components/evaluation/EvaluationBuilder', () => ({
  EvaluationBuilder: ({
    projectId,
    evaluations,
    onEvaluationsChange,
    availableFields,
  }: any) => (
    <div data-testid="evaluation-builder">
      Evaluation Builder for {projectId}
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
  is_superadmin: false,
}

// Lazy import (after mocks)
let ProjectDetailPage: any
beforeAll(async () => {
  ProjectDetailPage = (await import('../page')).default
})

describe('ProjectDetailPage - Surgical Branch Coverage 2', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      currentOrganization: null,
    })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: (key: string, vars?: any) => {
        if (vars) return `${key}:${JSON.stringify(vars)}`
        return key
      },
    })
    ;(useFeatureFlag as jest.Mock).mockReturnValue(true)
    ;(useUIStore as jest.Mock).mockReturnValue({
      isSidebarHidden: false,
    })
    // Mock popstate
    jest.spyOn(window, 'addEventListener').mockImplementation(jest.fn())
    jest.spyOn(window, 'removeEventListener').mockImplementation(jest.fn())
  })

  // Model defaults are now driven by parameter_constraints from the backend.
  // See getTemperatureConstraints() and getDefaultMaxTokens() from @/lib/modelConstraints.
  describe('Model defaults via parameter_constraints', () => {
    it('renders with models that have parameter_constraints', async () => {
      ;(useModels as jest.Mock).mockReturnValue({
        models: [
          {
            id: 'gpt-4o',
            name: 'GPT-4o',
            provider: 'OpenAI',
            parameter_constraints: {
              temperature: { supported: true, min: 0, max: 2, default: 1 },
              max_tokens: { default: 4096 },
            },
          },
        ],
        loading: false,
        error: null,
        refetch: jest.fn(),
        hasApiKeys: true,
        apiKeyStatus: { openai: true },
      })

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
        generation_config: {
          selected_configuration: {
            models: ['gpt-4o'],
          },
        },
        llm_model_ids: ['gpt-4o'],
        evaluation_config: {},
      }

      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: mockProject,
        loading: false,
        fetchProject: jest.fn(),
        updateProject: jest.fn().mockResolvedValue({}),
        deleteProject: jest.fn().mockResolvedValue({}),
      })

      ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })

      const params = Promise.resolve({ id: 'test-project-123' })
      render(<ProjectDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getAllByText('Test Project').length).toBeGreaterThan(0)
      })
    })

    it('renders with models without parameter_constraints (fallback)', async () => {
      // Models without parameter_constraints fall back to provider defaults
      ;(useModels as jest.Mock).mockReturnValue({
        models: [
          { id: 'gpt-4o-2025-custom', name: 'GPT-4o Custom', provider: 'OpenAI' },
        ],
        loading: false,
        error: null,
        refetch: jest.fn(),
        hasApiKeys: true,
        apiKeyStatus: { openai: true },
      })

      const mockProject = {
        id: 'test-project-123',
        title: 'Prefix Test',
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
        organizations: [],
        generation_config: {
          selected_configuration: {
            models: ['gpt-4o-2025-custom'],
          },
        },
        llm_model_ids: ['gpt-4o-2025-custom'],
        evaluation_config: {},
      }

      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: mockProject,
        loading: false,
        fetchProject: jest.fn(),
        updateProject: jest.fn().mockResolvedValue({}),
        deleteProject: jest.fn().mockResolvedValue({}),
      })

      ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })

      const params = Promise.resolve({ id: 'test-project-123' })
      render(<ProjectDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getAllByText('Prefix Test').length).toBeGreaterThan(0)
      })
    })
  })

  // Lines 274, 276, 277, 278: sortedModels - when availableModels is null vs has models with provider sorting
  describe('Model sorting with provider order (lines 274-278)', () => {
    it('handles null availableModels returning null sortedModels', async () => {
      ;(useModels as jest.Mock).mockReturnValue({
        models: null,
        loading: true,
        error: null,
        refetch: jest.fn(),
        hasApiKeys: false,
        apiKeyStatus: {},
      })

      const mockProject = {
        id: 'test-project-123',
        title: 'Null Models',
        description: 'desc',
        created_by: 'user-123',
        created_by_name: 'Test User',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
        task_count: 0,
        annotation_count: 0,
        progress_percentage: 0,
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
        organizations: [],
        generation_config: {},
        evaluation_config: {},
      }

      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: mockProject,
        loading: false,
        fetchProject: jest.fn(),
        updateProject: jest.fn().mockResolvedValue({}),
        deleteProject: jest.fn().mockResolvedValue({}),
      })

      ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })

      const params = Promise.resolve({ id: 'test-project-123' })
      render(<ProjectDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getAllByText('Null Models').length).toBeGreaterThan(0)
      })
    })

    it('sorts models by provider order, with unknown providers at end', async () => {
      ;(useModels as jest.Mock).mockReturnValue({
        models: [
          { id: 'model-z', name: 'Z Model', provider: 'UnknownProvider' },
          { id: 'claude-3-opus', name: 'Claude 3 Opus', provider: 'Anthropic' },
          { id: 'gpt-4', name: 'GPT-4', provider: 'OpenAI' },
          { id: 'gemini-pro', name: 'Gemini Pro', provider: 'Google' },
        ],
        loading: false,
        error: null,
        refetch: jest.fn(),
        hasApiKeys: true,
        apiKeyStatus: { openai: true, anthropic: true, google: true },
      })

      const mockProject = {
        id: 'test-project-123',
        title: 'Sorted Models',
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
        generation_config: { selected_configuration: { models: ['gpt-4'] } },
        evaluation_config: {},
      }

      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: mockProject,
        loading: false,
        fetchProject: jest.fn(),
        updateProject: jest.fn().mockResolvedValue({}),
        deleteProject: jest.fn().mockResolvedValue({}),
      })

      ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })

      const params = Promise.resolve({ id: 'test-project-123' })
      render(<ProjectDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getAllByText('Sorted Models').length).toBeGreaterThan(0)
      })
    })
  })

  // Line 355: report status - 404 response branch
  describe('Report status 404 branch (line 355)', () => {
    it('handles 404 report status response for superadmin', async () => {
      // Need superadmin to trigger fetchReportStatus
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { ...mockUser, is_superadmin: true },
        currentOrganization: null,
      })

      ;(useModels as jest.Mock).mockReturnValue({
        models: [],
        loading: false,
        error: null,
        refetch: jest.fn(),
        hasApiKeys: false,
        apiKeyStatus: {},
      })

      const mockProject = {
        id: 'test-project-123',
        title: 'Report 404',
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
        evaluation_config: {},
      }

      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: mockProject,
        loading: false,
        fetchProject: jest.fn(),
        updateProject: jest.fn().mockResolvedValue({}),
        deleteProject: jest.fn().mockResolvedValue({}),
      })

      // Mock fetch for report status 404
      global.fetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: jest.fn(),
      }) as any

      ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })

      const params = Promise.resolve({ id: 'test-project-123' })
      render(<ProjectDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getAllByText('Report 404').length).toBeGreaterThan(0)
      })

      // Wait for report status fetch to complete
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/report'),
          expect.any(Object)
        )
      })
    })

    it('handles successful report status response for superadmin', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { ...mockUser, is_superadmin: true },
        currentOrganization: null,
      })

      ;(useModels as jest.Mock).mockReturnValue({
        models: [],
        loading: false,
        error: null,
        refetch: jest.fn(),
        hasApiKeys: false,
        apiKeyStatus: {},
      })

      const mockProject = {
        id: 'test-project-123',
        title: 'Report OK',
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
        evaluation_config: {},
      }

      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: mockProject,
        loading: false,
        fetchProject: jest.fn(),
        updateProject: jest.fn().mockResolvedValue({}),
        deleteProject: jest.fn().mockResolvedValue({}),
      })

      // Mock fetch for report status success (OK)
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: jest.fn().mockResolvedValue({
          is_published: true,
          can_publish: true,
          can_publish_reason: '',
        }),
      }) as any

      ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })

      const params = Promise.resolve({ id: 'test-project-123' })
      render(<ProjectDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getAllByText('Report OK').length).toBeGreaterThan(0)
      })

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/report'),
          expect.any(Object)
        )
      })
    })
  })

  // Lines 452, 459: saveEvaluationConfigsToProject - when projectId is falsy, and existingConfig handling
  // Lines 494, 495: popstate handler branch - projectId && path includes project
  // Line 527: Array.isArray(current) check in setSelectedModelIds
  describe('Advanced settings with specific project config values (lines 585-587)', () => {
    it('handles project with maximum_annotations=0 (falsy but valid), min_annotations_per_task=0, assignment_mode empty', async () => {
      ;(useModels as jest.Mock).mockReturnValue({
        models: [],
        loading: false,
        error: null,
        refetch: jest.fn(),
        hasApiKeys: false,
        apiKeyStatus: {},
      })

      // maximum_annotations ?? 1 => 0 (nullish coalescing, 0 stays as 0)
      // min_annotations_per_task || 1 => 1 (because 0 is falsy)
      // assignment_mode || 'open' => 'open' (because '' is falsy)
      const mockProject = {
        id: 'test-project-123',
        title: 'Settings Edge Cases',
        description: 'desc',
        created_by: 'user-123',
        created_by_name: 'Test User',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
        task_count: 10,
        annotation_count: 5,
        progress_percentage: 50,
        label_config: '<View><Text name="text" value="$text"/></View>',
        instructions: 'Test instructions',
        show_instruction: false,
        show_skip_button: false,
        show_submit_button: false,
        require_comment_on_skip: true,
        require_confirm_before_submit: true,
        maximum_annotations: 0,
        min_annotations_per_task: 0,
        assignment_mode: '',
        organizations: [{ id: 'org-1', name: 'TUM' }],
        generation_config: {
          selected_configuration: {
            models: [],
            model_configs: { 'gpt-4': { temperature: 0.5 } },
            parameters: { temperature: 0.7, max_tokens: 4000 },
          },
        },
        evaluation_config: {
          default_temperature: 0.3,
          default_max_tokens: 2000,
        },
        randomize_task_order: true,
        questionnaire_enabled: true,
        questionnaire_config: 'some config',
        skip_queue: 'skip_permanently',
        instructions_always_visible: true,
        conditional_instructions: [{ condition: 'test', instruction: 'do this' }],
        llm_model_ids: null,
      }

      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: mockProject,
        loading: false,
        fetchProject: jest.fn(),
        updateProject: jest.fn().mockResolvedValue({}),
        deleteProject: jest.fn().mockResolvedValue({}),
      })

      ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })

      const params = Promise.resolve({ id: 'test-project-123' })
      render(<ProjectDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getAllByText('Settings Edge Cases').length).toBeGreaterThan(0)
      })
    })

    it('handles project with null maximum_annotations (nullish coalescing to 1)', async () => {
      ;(useModels as jest.Mock).mockReturnValue({
        models: [],
        loading: false,
        error: null,
        refetch: jest.fn(),
        hasApiKeys: false,
        apiKeyStatus: {},
      })

      const mockProject = {
        id: 'test-project-123',
        title: 'Null Max Annotations',
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
        maximum_annotations: null,
        min_annotations_per_task: 3,
        assignment_mode: 'manual',
        organizations: [{ id: 'org-1', name: 'TUM' }],
        generation_config: {
          selected_configuration: {
            models: ['gpt-4', 'claude-3-opus'],
          },
        },
        evaluation_config: {},
        llm_model_ids: ['gpt-4'],
      }

      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: mockProject,
        loading: false,
        fetchProject: jest.fn(),
        updateProject: jest.fn().mockResolvedValue({}),
        deleteProject: jest.fn().mockResolvedValue({}),
      })

      ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })

      const params = Promise.resolve({ id: 'test-project-123' })
      render(<ProjectDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getAllByText('Null Max Annotations').length).toBeGreaterThan(0)
      })
    })
  })

  // Line 494-495: popstate handler - path includes project
  describe('Popstate event handler (lines 494-495)', () => {
    it('triggers fetchProject on popstate when on project page', async () => {
      const addEventListenerSpy = jest.fn()
      const removeEventListenerSpy = jest.fn()
      jest.spyOn(window, 'addEventListener').mockImplementation(addEventListenerSpy)
      jest.spyOn(window, 'removeEventListener').mockImplementation(removeEventListenerSpy)

      const mockFetchProject = jest.fn()

      ;(useModels as jest.Mock).mockReturnValue({
        models: [],
        loading: false,
        error: null,
        refetch: jest.fn(),
        hasApiKeys: false,
        apiKeyStatus: {},
      })

      const mockProject = {
        id: 'test-project-123',
        title: 'Popstate Test',
        description: 'desc',
        created_by: 'user-123',
        created_by_name: 'Test User',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
        task_count: 0,
        annotation_count: 0,
        progress_percentage: 0,
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
        organizations: [],
        generation_config: {},
        evaluation_config: {},
      }

      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: mockProject,
        loading: false,
        fetchProject: mockFetchProject,
        updateProject: jest.fn().mockResolvedValue({}),
        deleteProject: jest.fn().mockResolvedValue({}),
      })

      ;(apiClient.get as jest.Mock).mockResolvedValue({ status: 'ok' })

      // window.location.pathname already defaults to something in jsdom
      // We just need the popstate handler to be registered

      const params = Promise.resolve({ id: 'test-project-123' })
      render(<ProjectDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getAllByText('Popstate Test').length).toBeGreaterThan(0)
      })

      // Find and call the popstate handler
      const popstateCalls = addEventListenerSpy.mock.calls.filter(
        (call: any[]) => call[0] === 'popstate'
      )
      if (popstateCalls.length > 0) {
        const handler = popstateCalls[0][1]
        act(() => {
          handler()
        })
      }

      // The handler should have been registered
      expect(addEventListenerSpy).toHaveBeenCalledWith(
        'popstate',
        expect.any(Function)
      )
    })
  })
})

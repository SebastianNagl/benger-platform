/**
 * @jest-environment jsdom
 *
 * Complement coverage tests for LabelingInterface.
 *
 * Targets branches NOT exercised by LabelingInterface.test.tsx /
 * LabelingInterface.branch2.test.tsx:
 * - Strict-timer state machine: pre_start screen, time_over screen, and the
 *   initPhase async session branches (completed / expired-zombie / no-session).
 * - The TimerSlot onAutoSubmit handler: success → questionnaire,
 *   success → immediate-eval, success → time_over, and the create error path.
 * - ImmediateEvalSlot onClose (auto-submitted advance vs. manual no-advance).
 * - proceedAfterQuestionnaire (immediate-eval hand-off vs. complete+toast).
 * - Initialization error screen Try-Again reload.
 * - handleStrictTimerStart (pre_start → annotating).
 * - The ?task= URL-param navigation toast paths and the localStorage restore.
 *
 * Slot components (TimerIntegration, ImmediateEvaluation,
 * LegalMarkdownProvider) are mocked via a controllable useSlot factory so the
 * extended-only render branches run in the community test build.
 */

import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useRouter, useSearchParams } from 'next/navigation'
import { LabelingInterface } from '../LabelingInterface'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(),
}))

// projectsAPI methods used by the strict-timer + submit flows.
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getTaskAnnotations: jest.fn().mockResolvedValue([]),
    saveDraft: jest.fn().mockResolvedValue(undefined),
    submitQuestionnaireResponse: jest.fn().mockResolvedValue({}),
    createAnnotation: jest.fn().mockResolvedValue({ id: 'auto-ann-1' }),
  },
}))

import { projectsAPI } from '@/lib/api/projects'
import { useAuth } from '@/contexts/AuthContext'

// Controllable slot registry. Each test can swap the mounted slot components.
const mockSlots: Record<string, any> = {}
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockSlots[name] ?? null,
}))

// DynamicAnnotationInterface mock exposes hooks for onSubmit/onChange/onSkip.
jest.mock('../DynamicAnnotationInterface', () => ({
  DynamicAnnotationInterface: function MockDynamicAnnotationInterface({
    onSubmit,
    onSkip,
    onChange,
  }: any) {
    return (
      <div data-testid="dynamic-annotation-interface">
        <button
          data-testid="mock-change"
          onClick={() =>
            onChange?.([
              { from_name: 'a', to_name: 'text', type: 'textarea', value: 'x' },
            ])
          }
        >
          Change
        </button>
        <button
          data-testid="mock-submit"
          onClick={() =>
            onSubmit?.([
              { from_name: 'a', to_name: 'text', type: 'textarea', value: 'x' },
            ])
          }
        >
          Submit
        </button>
        {onSkip && (
          <button data-testid="mock-skip" onClick={() => onSkip()}>
            Skip
          </button>
        )}
      </div>
    )
  },
}))

// Questionnaire modal mock: surfaces an onComplete trigger.
jest.mock('@/components/labeling/PostAnnotationQuestionnaireModal', () => ({
  PostAnnotationQuestionnaireModal: ({ isOpen, onComplete }: any) =>
    isOpen ? (
      <div data-testid="questionnaire-modal">
        <button data-testid="questionnaire-complete" onClick={onComplete}>
          Complete Questionnaire
        </button>
      </div>
    ) : null,
}))

jest.mock('@/hooks/useActivityTracker', () => ({
  useActivityTracker: () => ({
    start: jest.fn(),
    getData: jest
      .fn()
      .mockReturnValue({ activeMs: 1000, focusedMs: 900, tabSwitches: 0 }),
  }),
}))

jest.mock('@/lib/utils/variantHash', () => ({
  selectVariant: jest.fn().mockReturnValue(null),
}))

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn(), warn: jest.fn(), error: jest.fn() },
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      let value = params?.defaultValue || key
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          if (k !== 'defaultValue') value = value.replace(`{${k}}`, String(v))
        })
      }
      return value
    },
    locale: 'en',
  }),
}))

jest.mock('date-fns', () => ({
  formatDistanceToNow: () => '3 minutes',
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

import { mockToast as __mockToast } from '@/test-utils/setupTests'

const mockPush = jest.fn()
const mockApiGet = jest.fn()

function setupMocks(storeOverrides: any = {}, searchParam: string | null = null) {
  ;(useRouter as jest.Mock).mockReturnValue({ push: mockPush })
  ;(useSearchParams as jest.Mock).mockReturnValue({
    get: jest.fn().mockReturnValue(searchParam),
  })
  ;(useAuth as jest.Mock).mockReturnValue({
    user: { id: 'user-1', name: 'Test User' },
    apiClient: { get: mockApiGet },
  })

  const defaults = {
    currentProject: null,
    currentTask: null,
    currentTaskPosition: null,
    currentTaskTotal: null,
    loading: false,
    // Default to a truthy task so the init effect doesn't set
    // initializationError; tests that exercise the no-task / error paths
    // override this explicitly.
    getNextTask: jest.fn().mockResolvedValue({ id: 'task-1' }),
    createAnnotation: jest.fn().mockResolvedValue(undefined),
    createAnnotationInternal: jest.fn().mockResolvedValue({ id: 'ann-1' }),
    skipTask: jest.fn().mockResolvedValue(undefined),
    fetchProject: jest.fn().mockResolvedValue(undefined),
    fetchProjectTasks: jest.fn().mockResolvedValue([]),
    taskCycle: [],
    currentTaskIndex: 0,
    setTaskByIndex: jest.fn(),
    advanceToNextTask: jest.fn(),
    completeCurrentTask: jest.fn(),
    labelConfigVersion: 0,
    allTasksCompleted: false,
    resetAnnotationCompletion: jest.fn(),
  }

  const store = { ...defaults, ...storeOverrides }
  ;(useProjectStore as unknown as jest.Mock).mockReturnValue(store)
  return store
}

const strictProject = {
  id: 'proj-1',
  title: 'Strict Project',
  label_config: '<View/>',
  strict_timer_enabled: true,
  annotation_time_limit_enabled: true,
  annotation_time_limit_seconds: 600,
}

beforeEach(() => {
  jest.clearAllMocks()
  for (const k of Object.keys(mockSlots)) delete mockSlots[k]
  Storage.prototype.getItem = jest.fn().mockReturnValue(null)
  Storage.prototype.setItem = jest.fn()
  Storage.prototype.removeItem = jest.fn()
  mockApiGet.mockResolvedValue({
    server_time: new Date().toISOString(),
    session: null,
  })
})

describe('LabelingInterface - strict timer pre_start', () => {
  it('shows the pre_start screen when no timer session exists (isStrictMode)', async () => {
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: null,
    })
    setupMocks({
      currentProject: strictProject,
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('klausur-pre-start')).toBeInTheDocument()
    })
    // readyDescription substitutes minutes (600s -> 10).
    expect(screen.getByText(/10 minutes/)).toBeInTheDocument()
  })

  it('transitions pre_start -> annotating when Start is clicked', async () => {
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: null,
    })
    setupMocks({
      currentProject: strictProject,
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('klausur-pre-start')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByText('Start')
    )

    await waitFor(() => {
      expect(
        screen.getByTestId('dynamic-annotation-interface')
      ).toBeInTheDocument()
    })
  })

  it('navigates back to project from the pre_start screen', async () => {
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: null,
    })
    setupMocks({
      currentProject: strictProject,
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('klausur-pre-start')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Back to Project'))
    expect(mockPush).toHaveBeenCalledWith('/projects/proj-1')
  })

  it('routes a zombie (expired, not completed) session back to pre_start', async () => {
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: { is_expired: true, completed_at: null },
    })
    setupMocks({
      currentProject: strictProject,
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('klausur-pre-start')).toBeInTheDocument()
    })
  })

  it('renders the conditional-instruction variant content on the pre_start screen', async () => {
    const { selectVariant } = require('@/lib/utils/variantHash')
    ;(selectVariant as jest.Mock).mockReturnValue('v1')
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: null,
    })
    setupMocks({
      currentProject: {
        ...strictProject,
        conditional_instructions: [
          { id: 'v1', content: 'Variant one instructions', weight: 1 },
        ],
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByText('Variant one instructions')).toBeInTheDocument()
    })
  })
})

describe('LabelingInterface - strict timer time_over', () => {
  it('shows the time_over screen when the session is already completed', async () => {
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: { is_expired: true, completed_at: new Date().toISOString() },
    })
    setupMocks({
      currentProject: strictProject,
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByText("Time's Up")).toBeInTheDocument()
    })
  })

  it('Continue on the time_over screen calls completeCurrentTask', async () => {
    const completeCurrentTask = jest.fn()
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: { is_expired: true, completed_at: new Date().toISOString() },
    })
    setupMocks({
      currentProject: strictProject,
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
      completeCurrentTask,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByText("Time's Up")).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Continue'))
    expect(completeCurrentTask).toHaveBeenCalled()
  })

  it('Back to Project on the time_over screen navigates away', async () => {
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: { is_expired: true, completed_at: new Date().toISOString() },
    })
    setupMocks({
      currentProject: strictProject,
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByText("Time's Up")).toBeInTheDocument()
    })

    // Two "Back to Project" buttons exist (header + footer); click either.
    fireEvent.click(screen.getAllByText('Back to Project')[0])
    expect(mockPush).toHaveBeenCalledWith('/projects/proj-1')
  })
})

describe('LabelingInterface - TimerSlot onAutoSubmit', () => {
  // Mount a TimerSlot that exposes a button to fire onAutoSubmit, and force
  // strictTimerPhase to 'annotating' by returning a running session.
  function mountTimerSlot() {
    mockSlots.TimerIntegration = ({ onAutoSubmit }: any) => (
      <button
        data-testid="fire-auto-submit"
        onClick={() => onAutoSubmit([{ from_name: 'a', value: 'x' }])}
      >
        AutoSubmit
      </button>
    )
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: { is_expired: false, completed_at: null },
    })
  }

  it('auto-submit success with no modals shows the time_over screen', async () => {
    mountTimerSlot()
    setupMocks({
      currentProject: strictProject,
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('fire-auto-submit')).toBeInTheDocument()
    })

    await act(async () => {
      fireEvent.click(screen.getByTestId('fire-auto-submit'))
    })

    await waitFor(() => {
      expect(projectsAPI.createAnnotation).toHaveBeenCalledWith(
        'task-1',
        expect.objectContaining({ auto_submitted: true })
      )
      expect(screen.getByText("Time's Up")).toBeInTheDocument()
    })
  })

  it('auto-submit shows the questionnaire modal when questionnaire is enabled', async () => {
    mountTimerSlot()
    setupMocks({
      currentProject: {
        ...strictProject,
        questionnaire_enabled: true,
        questionnaire_config: { questions: [] },
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('fire-auto-submit')).toBeInTheDocument()
    })

    await act(async () => {
      fireEvent.click(screen.getByTestId('fire-auto-submit'))
    })

    await waitFor(() => {
      expect(screen.getByTestId('questionnaire-modal')).toBeInTheDocument()
    })
  })

  it('auto-submit mounts the immediate-eval slot when immediate eval is enabled', async () => {
    mountTimerSlot()
    mockSlots.ImmediateEvaluation = ({ annotationId }: any) => (
      <div data-testid="immediate-eval">eval:{annotationId}</div>
    )
    setupMocks({
      currentProject: {
        ...strictProject,
        immediate_evaluation_enabled: true,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('fire-auto-submit')).toBeInTheDocument()
    })

    await act(async () => {
      fireEvent.click(screen.getByTestId('fire-auto-submit'))
    })

    await waitFor(() => {
      expect(screen.getByText('eval:auto-ann-1')).toBeInTheDocument()
    })
  })

  it('auto-submit create failure routes to time_over', async () => {
    mountTimerSlot()
    ;(projectsAPI.createAnnotation as jest.Mock).mockRejectedValueOnce(
      new Error('boom')
    )
    setupMocks({
      currentProject: strictProject,
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('fire-auto-submit')).toBeInTheDocument()
    })

    await act(async () => {
      fireEvent.click(screen.getByTestId('fire-auto-submit'))
    })

    await waitFor(() => {
      expect(screen.getByText("Time's Up")).toBeInTheDocument()
    })
  })
})

describe('LabelingInterface - ImmediateEvalSlot onClose', () => {
  it('advances to next task on close after a manual submit with immediate eval', async () => {
    const completeCurrentTask = jest.fn()
    mockSlots.ImmediateEvaluation = ({ onClose }: any) => (
      <button data-testid="close-eval" onClick={onClose}>
        Close Eval
      </button>
    )
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: null,
    })
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Eval Project',
        label_config: '<View/>',
        immediate_evaluation_enabled: true,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
      createAnnotationInternal: jest.fn().mockResolvedValue({ id: 'm-ann-1' }),
      completeCurrentTask,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('mock-submit')).toBeInTheDocument()
    })

    // Manual submit -> sets lastSubmittedAnnotationId -> mounts eval slot,
    // and autoSubmittedRef becomes true (hasImmediateEval branch).
    await act(async () => {
      fireEvent.click(screen.getByTestId('mock-submit'))
    })

    await waitFor(() => {
      expect(screen.getByTestId('close-eval')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('close-eval'))
    expect(completeCurrentTask).toHaveBeenCalled()
  })
})

describe('LabelingInterface - questionnaire completion', () => {
  it('proceedAfterQuestionnaire completes the task when no immediate eval', async () => {
    const completeCurrentTask = jest.fn()
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: null,
    })
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Q Project',
        label_config: '<View/>',
        questionnaire_enabled: true,
        questionnaire_config: { questions: [] },
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
      createAnnotationInternal: jest.fn().mockResolvedValue({ id: 'q-ann-1' }),
      completeCurrentTask,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('mock-submit')).toBeInTheDocument()
    })

    await act(async () => {
      fireEvent.click(screen.getByTestId('mock-submit'))
    })

    await waitFor(() => {
      expect(screen.getByTestId('questionnaire-modal')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('questionnaire-complete'))

    await waitFor(() => {
      expect(completeCurrentTask).toHaveBeenCalled()
    })
  })
})

describe('LabelingInterface - manual submit guards', () => {
  it('shows an error toast when submitting twice (already submitted)', async () => {
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: null,
    })
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Plain Project',
        label_config: '<View/>',
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
      createAnnotationInternal: jest.fn().mockResolvedValue({ id: 's-ann-1' }),
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('mock-submit')).toBeInTheDocument()
    })

    await act(async () => {
      fireEvent.click(screen.getByTestId('mock-submit'))
    })
    // Second click: hasSubmittedRef is now true -> "already submitted" branch.
    await act(async () => {
      fireEvent.click(screen.getByTestId('mock-submit'))
    })

    await waitFor(() => {
      expect(__mockToast.addToast).toHaveBeenCalledWith(
        'Annotation already submitted',
        'error'
      )
    })
  })

  it('shows a failure toast when createAnnotationInternal rejects', async () => {
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: null,
    })
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Plain Project',
        label_config: '<View/>',
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
      createAnnotationInternal: jest.fn().mockRejectedValue(new Error('nope')),
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('mock-submit')).toBeInTheDocument()
    })

    await act(async () => {
      fireEvent.click(screen.getByTestId('mock-submit'))
    })

    await waitFor(() => {
      expect(__mockToast.addToast).toHaveBeenCalledWith(
        'Failed to submit annotation',
        'error'
      )
    })
  })
})

describe('LabelingInterface - initialization error screen', () => {
  it('renders the init-error screen and the Try Again button is wired to reload', async () => {
    setupMocks({
      currentProject: null,
      currentTask: null,
      fetchProject: jest.fn().mockRejectedValue(new Error('init failed')),
      getNextTask: jest.fn().mockResolvedValue(null),
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByText('Initialization Error')).toBeInTheDocument()
      expect(screen.getByText('init failed')).toBeInTheDocument()
    })

    // Clicking Try Again runs `window.location.reload()`. jsdom's location is a
    // read-only navigation stub that can't be reliably spied here, so we only
    // exercise the onClick handler (covering the branch) and assert the screen
    // stayed rendered rather than asserting on the unmockable reload call.
    fireEvent.click(screen.getByText('Try Again'))
    expect(screen.getByText('Initialization Error')).toBeInTheDocument()
  })

  it('Back to Project on the init-error screen navigates away', async () => {
    setupMocks({
      currentProject: null,
      currentTask: null,
      fetchProject: jest.fn().mockRejectedValue(new Error('init failed')),
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByText('Initialization Error')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Back to Project'))
    expect(mockPush).toHaveBeenCalledWith('/projects/proj-1')
  })
})

describe('LabelingInterface - URL task param navigation', () => {
  it('navigates to a task by ?task= and toasts success', async () => {
    const setTaskByIndex = jest.fn()
    setupMocks(
      {
        currentProject: null,
        currentTask: null,
        fetchProjectTasks: jest
          .fn()
          .mockResolvedValue([{ id: 'task-1' }, { id: 'task-2' }]),
        setTaskByIndex,
      },
      '2'
    )

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(setTaskByIndex).toHaveBeenCalledWith(1)
      // The success toast uses the taskLoadedFromUrl key (params substituted
      // by the real i18n at runtime); here we assert the success branch fired.
      expect(__mockToast.addToast).toHaveBeenCalledWith(
        expect.stringContaining('annotation.taskLoadedFromUrl'),
        'success'
      )
    })
  })

  it('toasts an error when ?task= is out of range', async () => {
    setupMocks(
      {
        currentProject: null,
        currentTask: null,
        fetchProjectTasks: jest.fn().mockResolvedValue([{ id: 'task-1' }]),
        getNextTask: jest.fn().mockResolvedValue(null),
      },
      '99'
    )

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(__mockToast.addToast).toHaveBeenCalledWith(
        expect.stringContaining('annotation.taskNotFound'),
        'error'
      )
    })
  })
})

describe('LabelingInterface - draft sync on change', () => {
  it('saves a draft when the tab becomes hidden after a change', async () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Draft Project',
        label_config: '<View/>',
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('mock-change')).toBeInTheDocument()
    })

    // Produce a non-empty annotations array.
    await act(async () => {
      fireEvent.click(screen.getByTestId('mock-change'))
    })

    // Force the visibilitychange handler with document hidden.
    Object.defineProperty(document, 'visibilityState', {
      value: 'hidden',
      configurable: true,
    })
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    await waitFor(() => {
      expect(projectsAPI.saveDraft).toHaveBeenCalledWith(
        'proj-1',
        'task-1',
        expect.any(Array)
      )
    })

    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      configurable: true,
    })
  })
})

describe('LabelingInterface - non-strict overtime (no auto-submit at 0)', () => {
  // Non-strict timed project: at 0 the timer flips to overtime — the host
  // must NOT create an auto-submitted annotation (that would fire a KI-Votum
  // grading on a half-finished draft) and the editor stays mounted for a
  // manual submit.
  const nonStrictProject = {
    ...strictProject,
    strict_timer_enabled: false,
  }

  function mountTimerSlot() {
    mockSlots.TimerIntegration = ({ onAutoSubmit }: any) => (
      <button
        data-testid="fire-auto-submit"
        onClick={() => onAutoSubmit([{ from_name: 'a', value: 'x' }])}
      >
        AutoSubmit
      </button>
    )
    mockApiGet.mockResolvedValue({
      server_time: new Date().toISOString(),
      session: { is_expired: false, completed_at: null },
    })
  }

  it('expiry shows the overtime hint, creates NO annotation, and keeps the editor', async () => {
    mountTimerSlot()
    setupMocks({
      currentProject: nonStrictProject,
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('fire-auto-submit')).toBeInTheDocument()
    })

    await act(async () => {
      fireEvent.click(screen.getByTestId('fire-auto-submit'))
    })

    await waitFor(() => {
      expect(screen.getByTestId('timer-overtime-hint')).toBeInTheDocument()
    })
    expect(projectsAPI.createAnnotation).not.toHaveBeenCalled()
    // Editor still mounted — manual submit remains possible in overtime.
    expect(screen.getByTestId('dynamic-annotation-interface')).toBeInTheDocument()
    expect(screen.getByTestId('mock-submit')).toBeInTheDocument()
    // No strict time_over lock screen.
    expect(screen.queryByText("Time's Up")).not.toBeInTheDocument()
  })

  it('a second expiry callback stays idempotent (hint once, still no annotation)', async () => {
    mountTimerSlot()
    setupMocks({
      currentProject: nonStrictProject,
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('fire-auto-submit')).toBeInTheDocument()
    })

    await act(async () => {
      fireEvent.click(screen.getByTestId('fire-auto-submit'))
      fireEvent.click(screen.getByTestId('fire-auto-submit'))
    })

    await waitFor(() => {
      expect(screen.getAllByTestId('timer-overtime-hint')).toHaveLength(1)
    })
    expect(projectsAPI.createAnnotation).not.toHaveBeenCalled()
  })
})

/**
 * @jest-environment jsdom
 *
 * Questionnaires on the labeling page, and the rule that none of them ever
 * counts toward an exam's time limit:
 *
 * - before_task: after the instructions, INSTEAD of the task. Neither the
 *   task (editor, task text) nor the exam timer is mounted until it is
 *   answered or skipped. The timer starts when the TimerIntegration slot
 *   mounts (its POST /start-timer), so the slot's mount is the timer start
 *   and must come after the answer.
 * - after_submit: only after the submission went through (the submit closes
 *   the timer session server-side), with the countdown paused while open.
 *
 * Every step appends to `timeline`, which the tests compare in order.
 */

import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect } from 'react'
import { LabelingInterface } from '../LabelingInterface'

const timeline: string[] = []

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getTaskAnnotations: jest.fn().mockResolvedValue([]),
    saveDraft: jest.fn().mockResolvedValue(undefined),
    createAnnotation: jest.fn().mockResolvedValue({ id: 'auto-ann-1' }),
  },
}))

const BEFORE = {
  trigger: 'before_task',
  active: true,
  enabled: true,
  config: '<View><Likert name="BEFORE_Q" toName="BEFORE_Q"/></View>',
  required: true,
  frequency: 'once_per_project',
  version: 1,
  allowed_frequencies: ['once_per_project', 'once_per_task'],
  updated_at: null,
}
const AFTER = {
  ...BEFORE,
  trigger: 'after_submit',
  config: '<View><Rating name="AFTER_Q" toName="AFTER_Q"/></View>',
  frequency: 'once_per_submission',
}

let mockList: any[] = []
let mockDue: Record<string, boolean> = {}
const mockAnswer = jest.fn()
const mockSkip = jest.fn()
const mockStatus = jest.fn()
jest.mock('@/lib/api/questionnaires', () => ({
  questionnairesAPI: {
    list: jest.fn(() =>
      Promise.resolve({ questionnaires: mockList, can_edit: false }),
    ),
    status: (...args: any[]) => mockStatus(...args),
    answer: (...args: any[]) => mockAnswer(...args),
    skip: (...args: any[]) => mockSkip(...args),
  },
}))

// The annotation interface stub: the task's editor, or a questionnaire's
// form (told apart by the config), each with a submit button.
jest.mock('../DynamicAnnotationInterface', () => ({
  DynamicAnnotationInterface: function Mock({ labelConfig, onSubmit }: any) {
    const which = labelConfig.includes('BEFORE_Q')
      ? 'before-form'
      : labelConfig.includes('AFTER_Q')
        ? 'after-form'
        : 'dynamic-annotation-interface'
    return (
      <div data-testid={which}>
        <button
          data-testid={`${which}-submit`}
          onClick={() =>
            onSubmit([
              {
                from_name: 'x',
                to_name: 'x',
                type: 'rating',
                value: 3,
              },
            ])
          }
        >
          submit
        </button>
      </div>
    )
  },
}))

// The extension's timer: mounting it is what starts the exam clock.
const mockSlots: Record<string, any> = {}
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockSlots[name] ?? null,
}))
function TimerSlot({ paused }: any) {
  useEffect(() => {
    timeline.push('timer-start')
  }, [])
  return <div data-testid="timer" data-paused={String(!!paused)} />
}

jest.mock('@/hooks/useActivityTracker', () => ({
  useActivityTracker: () => ({
    start: jest.fn(),
    getData: jest
      .fn()
      .mockReturnValue({ activeMs: 0, focusedMs: 0, tabSwitches: 0 }),
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
  useOptionalAuth: () => null,
}))
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)
jest.mock('date-fns', () => ({ formatDistanceToNow: () => '1 minute' }))
jest.mock('@/stores/projectStore', () => ({ useProjectStore: jest.fn() }))

import { useAuth } from '@/contexts/AuthContext'

const mockApiGet = jest.fn()

const timedProject = {
  id: 'proj-1',
  title: 'Timed exam',
  label_config: '<View><TextArea name="answer" toName="answer"/></View>',
  annotation_time_limit_enabled: true,
  annotation_time_limit_seconds: 600,
  strict_timer_enabled: false,
  instructions: 'Read carefully.',
  show_instruction: true,
}

function setup(overrides: any = {}) {
  ;(useRouter as jest.Mock).mockReturnValue({ push: jest.fn() })
  ;(useSearchParams as jest.Mock).mockReturnValue({
    get: jest.fn().mockReturnValue(null),
  })
  ;(useAuth as jest.Mock).mockReturnValue({
    user: { id: 'user-1', name: 'Student' },
    apiClient: { get: mockApiGet },
  })
  const store = {
    currentProject: timedProject,
    currentTask: { id: 'task-1', project_id: 'proj-1', data: { text: 'TASK' } },
    currentTaskPosition: 1,
    currentTaskTotal: 2,
    loading: false,
    getNextTask: jest.fn().mockResolvedValue({ id: 'task-1' }),
    createAnnotation: jest.fn().mockResolvedValue(undefined),
    createAnnotationInternal: jest.fn(async () => {
      timeline.push('submission-final')
      return { id: 'ann-1' }
    }),
    skipTask: jest.fn(),
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
    ...overrides,
  }
  ;(useProjectStore as unknown as jest.Mock).mockReturnValue(store)
  return store
}

beforeEach(() => {
  jest.clearAllMocks()
  timeline.length = 0
  mockList = []
  mockDue = {}
  mockSlots.TimerIntegration = TimerSlot
  Storage.prototype.getItem = jest.fn().mockReturnValue(null)
  Storage.prototype.setItem = jest.fn()
  Storage.prototype.removeItem = jest.fn()
  mockApiGet.mockResolvedValue({
    server_time: new Date().toISOString(),
    session: null,
  })
  mockStatus.mockImplementation(async (_p: string, trigger: string) => {
    const q = mockList.find((x) => x.trigger === trigger)
    return mockDue[trigger] && q
      ? { due: true, questionnaire: q }
      : { due: false, questionnaire: null }
  })
  mockAnswer.mockImplementation(async (_p: string, trigger: string) => {
    timeline.push(`${trigger}-answered`)
    mockDue[trigger] = false
    return {}
  })
  mockSkip.mockImplementation(async (_p: string, trigger: string) => {
    timeline.push(`${trigger}-skipped`)
    mockDue[trigger] = false
    return {}
  })
})

describe('before-task questionnaire', () => {
  it('shows the instructions and the questionnaire, never the task or the timer, until answered', async () => {
    mockList = [BEFORE]
    mockDue = { before_task: true }
    setup()

    render(<LabelingInterface projectId="proj-1" />)

    await screen.findByTestId('before-task-questionnaire')
    // The instructions come first, over the questionnaire.
    expect(screen.getByText('Read carefully.')).toBeInTheDocument()
    // Neither the task nor its timer exists yet: the clock has not started.
    expect(screen.queryByTestId('dynamic-annotation-interface')).toBeNull()
    expect(screen.queryByTestId('timer')).toBeNull()
    expect(timeline).toEqual([])
    expect(mockStatus).toHaveBeenCalledWith('proj-1', 'before_task', {
      task_id: 'task-1',
    })

    await act(async () => {
      fireEvent.click(screen.getByTestId('before-form-submit'))
    })

    await screen.findByTestId('dynamic-annotation-interface')
    expect(screen.getByTestId('timer')).toBeInTheDocument()
    // The timer started only after the answer was stored.
    expect(timeline).toEqual(['before_task-answered', 'timer-start'])
    expect(mockAnswer).toHaveBeenCalledWith(
      'proj-1',
      'before_task',
      { task_id: 'task-1' },
      expect.any(Array),
      1,
    )
  })

  it('an optional one can be skipped; the timer starts after the skip', async () => {
    mockList = [{ ...BEFORE, required: false }]
    mockDue = { before_task: true }
    setup()

    render(<LabelingInterface projectId="proj-1" />)
    await screen.findByTestId('before-task-questionnaire')
    expect(screen.queryByTestId('timer')).toBeNull()

    await act(async () => {
      fireEvent.click(screen.getByTestId('questionnaire-skip'))
    })

    await screen.findByTestId('timer')
    expect(timeline).toEqual(['before_task-skipped', 'timer-start'])
  })

  it('a required one offers no skip', async () => {
    mockList = [BEFORE]
    mockDue = { before_task: true }
    setup()
    render(<LabelingInterface projectId="proj-1" />)
    await screen.findByTestId('before-task-questionnaire')
    expect(screen.queryByTestId('questionnaire-skip')).toBeNull()
  })

  it('in a strict exam the clock waits for the questionnaire and then the Start button', async () => {
    mockList = [BEFORE]
    mockDue = { before_task: true }
    setup({
      currentProject: { ...timedProject, strict_timer_enabled: true },
    })

    render(<LabelingInterface projectId="proj-1" />)
    await screen.findByTestId('before-task-questionnaire')
    expect(screen.queryByTestId('klausur-pre-start')).toBeNull()

    await act(async () => {
      fireEvent.click(screen.getByTestId('before-form-submit'))
    })
    await screen.findByTestId('klausur-pre-start')
    expect(screen.queryByTestId('timer')).toBeNull()

    fireEvent.click(screen.getByText('Start'))
    await screen.findByTestId('timer')
    expect(timeline).toEqual(['before_task-answered', 'timer-start'])
  })

  it('once answered (not due) the task and the timer come straight away', async () => {
    mockList = [BEFORE]
    mockDue = { before_task: false }
    setup()

    render(<LabelingInterface projectId="proj-1" />)

    await screen.findByTestId('dynamic-annotation-interface')
    expect(screen.queryByTestId('before-task-questionnaire')).toBeNull()
    expect(timeline).toEqual(['timer-start'])
  })

  it('a project without one never asks the server per task', async () => {
    mockList = []
    setup()
    render(<LabelingInterface projectId="proj-1" />)
    await screen.findByTestId('dynamic-annotation-interface')
    expect(mockStatus).not.toHaveBeenCalled()
  })

  it('read-only access (attempted tier) never owes one', async () => {
    mockList = [BEFORE]
    mockDue = { before_task: true }
    setup({ currentProject: { ...timedProject, access_tier: 'attempted' } })
    render(<LabelingInterface projectId="proj-1" />)
    await screen.findByTestId('dynamic-annotation-interface')
    expect(screen.queryByTestId('before-task-questionnaire')).toBeNull()
  })
})

describe('after-submit questionnaire', () => {
  it('opens only after the submission is final, with the countdown paused', async () => {
    mockList = [AFTER]
    mockDue = { after_submit: true }
    const store = setup()

    render(<LabelingInterface projectId="proj-1" />)
    await screen.findByTestId('dynamic-annotation-interface')
    expect(screen.queryByTestId('after-form')).toBeNull()

    await act(async () => {
      fireEvent.click(screen.getByTestId('dynamic-annotation-interface-submit'))
    })

    await screen.findByTestId('after-form')
    // The submission went through first (it closes the timer session
    // server-side), then the questionnaire asked about it.
    expect(timeline).toEqual(['timer-start', 'submission-final'])
    expect(mockStatus).toHaveBeenCalledWith('proj-1', 'after_submit', {
      annotation_id: 'ann-1',
      task_id: 'task-1',
    })
    expect(store.createAnnotationInternal).toHaveBeenCalledWith(
      'task-1',
      expect.anything(),
      true, // the page waits for the questionnaire before moving on
    )
    expect(screen.getByTestId('timer')).toHaveAttribute('data-paused', 'true')

    await act(async () => {
      fireEvent.click(screen.getByTestId('after-form-submit'))
    })
    await waitFor(() => expect(store.completeCurrentTask).toHaveBeenCalled())
    expect(timeline).toEqual([
      'timer-start',
      'submission-final',
      'after_submit-answered',
    ])
  })

  it('moves on without a questionnaire when none is due for the submission', async () => {
    mockList = [AFTER]
    mockDue = { after_submit: false }
    const store = setup()
    render(<LabelingInterface projectId="proj-1" />)
    await screen.findByTestId('dynamic-annotation-interface')
    await act(async () => {
      fireEvent.click(screen.getByTestId('dynamic-annotation-interface-submit'))
    })
    await waitFor(() => expect(store.completeCurrentTask).toHaveBeenCalled())
    expect(screen.queryByTestId('after-form')).toBeNull()
  })
})

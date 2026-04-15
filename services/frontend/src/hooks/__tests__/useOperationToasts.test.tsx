/**
 * @jest-environment jsdom
 */

import { act, render, renderHook } from '@testing-library/react'
import { useOperationToasts } from '../useOperationToasts'

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      if (vars) {
        return key.replace(/\{(\w+)\}/g, (_, name) =>
          vars[name] !== undefined ? String(vars[name]) : `{${name}}`
        )
      }
      return key
    },
    currentLanguage: 'en',
  }),
}))

// Mock the OperationToast component
const mockOperationToast = jest.fn(() => null)

jest.mock('@/components/shared/OperationToast', () => ({
  OperationToast: (props: any) => {
    mockOperationToast(props)
    return null
  },
}))

describe('useOperationToasts', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.runOnlyPendingTimers()
    jest.useRealTimers()
  })

  describe('Basic Hook Behavior', () => {
    it('should return expected interface', () => {
      const { result } = renderHook(() => useOperationToasts())

      expect(result.current).toHaveProperty('toasts')
      expect(result.current).toHaveProperty('addOperationToast')
      expect(result.current).toHaveProperty('updateOperationToast')
      expect(result.current).toHaveProperty('dismissToast')
      expect(result.current).toHaveProperty('dismissOperationToasts')
      expect(result.current).toHaveProperty('clearAllToasts')
      expect(result.current).toHaveProperty('renderToasts')
      expect(result.current).toHaveProperty('startGeneration')
      expect(result.current).toHaveProperty('updateGeneration')
      expect(result.current).toHaveProperty('startEvaluation')
      expect(result.current).toHaveProperty('updateEvaluation')

      expect(typeof result.current.addOperationToast).toBe('function')
      expect(typeof result.current.updateOperationToast).toBe('function')
      expect(typeof result.current.dismissToast).toBe('function')
      expect(typeof result.current.dismissOperationToasts).toBe('function')
      expect(typeof result.current.clearAllToasts).toBe('function')
      expect(typeof result.current.renderToasts).toBe('function')
      expect(typeof result.current.startGeneration).toBe('function')
      expect(typeof result.current.updateGeneration).toBe('function')
      expect(typeof result.current.startEvaluation).toBe('function')
      expect(typeof result.current.updateEvaluation).toBe('function')
    })

    it('should initialize with empty toasts array', () => {
      const { result } = renderHook(() => useOperationToasts())

      expect(result.current.toasts).toEqual([])
    })

    it('should maintain stable function references', () => {
      const { result, rerender } = renderHook(() => useOperationToasts())

      const firstAddOperationToast = result.current.addOperationToast
      const firstUpdateOperationToast = result.current.updateOperationToast
      const firstDismissToast = result.current.dismissToast
      const firstDismissOperationToasts = result.current.dismissOperationToasts
      const firstClearAllToasts = result.current.clearAllToasts
      const firstRenderToasts = result.current.renderToasts

      rerender()

      expect(result.current.addOperationToast).toBe(firstAddOperationToast)
      expect(result.current.updateOperationToast).toBe(
        firstUpdateOperationToast
      )
      expect(result.current.dismissToast).toBe(firstDismissToast)
      expect(result.current.dismissOperationToasts).toBe(
        firstDismissOperationToasts
      )
      expect(result.current.clearAllToasts).toBe(firstClearAllToasts)
      expect(result.current.renderToasts).toBe(firstRenderToasts)
    })
  })

  describe('Data Fetching/State Management', () => {
    it('should add a new operation toast', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-123',
          'Test message',
          'Test details'
        )
      })

      expect(result.current.toasts).toHaveLength(1)
      expect(result.current.toasts[0]).toMatchObject({
        type: 'generation',
        status: 'started',
        taskId: 'task-123',
        message: 'Test message',
        details: 'Test details',
        persistent: false,
      })
      expect(result.current.toasts[0].id).toMatch(/^generation-task-123-\d+$/)
      expect(result.current.toasts[0].createdAt).toBeInstanceOf(Date)
    })

    it('should add persistent toast', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'evaluation',
          'running',
          'task-456',
          'Persistent message',
          undefined,
          true
        )
      })

      expect(result.current.toasts[0].persistent).toBe(true)
    })

    it('should return toast id when adding', () => {
      const { result } = renderHook(() => useOperationToasts())

      let toastId: string = ''
      act(() => {
        toastId = result.current.addOperationToast(
          'generation',
          'started',
          'task-789',
          'Test'
        )
      })

      expect(toastId).toBeTruthy()
      expect(toastId).toMatch(/^generation-task-789-\d+$/)
      expect(result.current.toasts[0].id).toBe(toastId)
    })

    it('should add multiple toasts', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Message 1'
        )
        result.current.addOperationToast(
          'evaluation',
          'running',
          'task-2',
          'Message 2'
        )
        result.current.addOperationToast(
          'generation',
          'completed',
          'task-3',
          'Message 3'
        )
      })

      expect(result.current.toasts).toHaveLength(3)
      expect(result.current.toasts[0].taskId).toBe('task-1')
      expect(result.current.toasts[1].taskId).toBe('task-2')
      expect(result.current.toasts[2].taskId).toBe('task-3')
    })

    it('should replace existing toast for same operation type and task', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-123',
          'First message'
        )
      })

      expect(result.current.toasts).toHaveLength(1)
      const firstMessage = result.current.toasts[0].message

      act(() => {
        result.current.addOperationToast(
          'generation',
          'running',
          'task-123',
          'Second message'
        )
      })

      expect(result.current.toasts).toHaveLength(1)
      expect(result.current.toasts[0].message).not.toBe(firstMessage)
      expect(result.current.toasts[0].message).toBe('Second message')
      expect(result.current.toasts[0].status).toBe('running')
    })

    it('should not replace toast if type is different', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-123',
          'Generation'
        )
        result.current.addOperationToast(
          'evaluation',
          'started',
          'task-123',
          'Evaluation'
        )
      })

      expect(result.current.toasts).toHaveLength(2)
    })

    it('should not replace toast if taskId is different', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-123',
          'Task 123'
        )
        result.current.addOperationToast(
          'generation',
          'started',
          'task-456',
          'Task 456'
        )
      })

      expect(result.current.toasts).toHaveLength(2)
    })
  })

  describe('Loading States', () => {
    it('should set toast status to started', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Starting...'
        )
      })

      expect(result.current.toasts[0].status).toBe('started')
    })

    it('should set toast status to running', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'running',
          'task-1',
          'Processing...'
        )
      })

      expect(result.current.toasts[0].status).toBe('running')
    })

    it('should transition from started to running via update', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Starting...'
        )
      })

      expect(result.current.toasts[0].status).toBe('started')

      act(() => {
        result.current.updateOperationToast(
          'generation',
          'task-1',
          'running',
          'Processing...'
        )
      })

      expect(result.current.toasts[0].status).toBe('running')
      expect(result.current.toasts[0].message).toBe('Processing...')
    })
  })

  describe('Error Handling', () => {
    it('should handle failed status', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'failed',
          'task-1',
          'Operation failed',
          'Error details'
        )
      })

      expect(result.current.toasts[0].status).toBe('failed')
      expect(result.current.toasts[0].details).toBe('Error details')
    })

    it('should auto-dismiss failed toast after 8 seconds', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'failed',
          'task-1',
          'Failed'
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        jest.advanceTimersByTime(7999)
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        jest.advanceTimersByTime(1)
      })

      expect(result.current.toasts).toHaveLength(0)
    })

    it('should not auto-dismiss persistent failed toast', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'failed',
          'task-1',
          'Failed',
          'Error',
          true
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        jest.advanceTimersByTime(10000)
      })

      expect(result.current.toasts).toHaveLength(1)
    })
  })

  describe('Data Transformation/Callbacks', () => {
    it('should update existing toast message and details', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Initial message',
          'Initial details'
        )
      })

      act(() => {
        result.current.updateOperationToast(
          'generation',
          'task-1',
          'running',
          'Updated message',
          'Updated details'
        )
      })

      expect(result.current.toasts[0].message).toBe('Updated message')
      expect(result.current.toasts[0].details).toBe('Updated details')
      expect(result.current.toasts[0].status).toBe('running')
    })

    it('should preserve toast id when updating', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Message'
        )
      })

      const originalId = result.current.toasts[0].id

      act(() => {
        result.current.updateOperationToast(
          'generation',
          'task-1',
          'running',
          'Updated'
        )
      })

      expect(result.current.toasts[0].id).toBe(originalId)
    })

    it('should dismiss toast by id', () => {
      const { result } = renderHook(() => useOperationToasts())

      let toastId: string
      act(() => {
        toastId = result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Message'
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        result.current.dismissToast(toastId)
      })

      expect(result.current.toasts).toHaveLength(0)
    })

    it('should dismiss operation toasts by type and taskId', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Gen 1'
        )
        result.current.addOperationToast(
          'evaluation',
          'started',
          'task-1',
          'Eval 1'
        )
        result.current.addOperationToast(
          'generation',
          'started',
          'task-2',
          'Gen 2'
        )
      })

      expect(result.current.toasts).toHaveLength(3)

      act(() => {
        result.current.dismissOperationToasts('generation', 'task-1')
      })

      expect(result.current.toasts).toHaveLength(2)
      expect(result.current.toasts[0].type).toBe('evaluation')
      expect(result.current.toasts[1].taskId).toBe('task-2')
    })

    it('should clear all toasts', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'M1'
        )
        result.current.addOperationToast(
          'evaluation',
          'started',
          'task-2',
          'M2'
        )
        result.current.addOperationToast(
          'generation',
          'started',
          'task-3',
          'M3'
        )
      })

      expect(result.current.toasts).toHaveLength(3)

      act(() => {
        result.current.clearAllToasts()
      })

      expect(result.current.toasts).toHaveLength(0)
    })
  })

  describe('Refetch/Invalidation', () => {
    it('should auto-dismiss completed toast after 5 seconds', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'completed',
          'task-1',
          'Completed'
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        jest.advanceTimersByTime(4999)
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        jest.advanceTimersByTime(1)
      })

      expect(result.current.toasts).toHaveLength(0)
    })

    it('should auto-dismiss updated completed toast after 5 seconds', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'running',
          'task-1',
          'Running'
        )
      })

      act(() => {
        result.current.updateOperationToast(
          'generation',
          'task-1',
          'completed',
          'Done'
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        jest.advanceTimersByTime(5000)
      })

      expect(result.current.toasts).toHaveLength(0)
    })

    it('should not auto-dismiss started status', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Started'
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        jest.advanceTimersByTime(10000)
      })

      expect(result.current.toasts).toHaveLength(1)
    })

    it('should not auto-dismiss running status', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'running',
          'task-1',
          'Running'
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        jest.advanceTimersByTime(10000)
      })

      expect(result.current.toasts).toHaveLength(1)
    })

    it('should not auto-dismiss persistent completed toast', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'completed',
          'task-1',
          'Done',
          undefined,
          true
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        jest.advanceTimersByTime(10000)
      })

      expect(result.current.toasts).toHaveLength(1)
    })
  })

  describe('Edge Cases', () => {
    it('should handle dismissing non-existent toast', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'M1'
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        result.current.dismissToast('non-existent-id')
      })

      expect(result.current.toasts).toHaveLength(1)
    })

    it('should handle dismissing operation toasts with no matches', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'M1'
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        result.current.dismissOperationToasts('evaluation', 'task-99')
      })

      expect(result.current.toasts).toHaveLength(1)
    })

    it('should handle updating non-existent toast', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'M1'
        )
      })

      act(() => {
        result.current.updateOperationToast(
          'evaluation',
          'task-99',
          'completed',
          'Done'
        )
      })

      expect(result.current.toasts).toHaveLength(1)
      expect(result.current.toasts[0].message).toBe('M1')
    })

    it('should handle clearing empty toasts array', () => {
      const { result } = renderHook(() => useOperationToasts())

      expect(result.current.toasts).toHaveLength(0)

      act(() => {
        result.current.clearAllToasts()
      })

      expect(result.current.toasts).toHaveLength(0)
    })

    it('should handle adding toast without details', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Message only'
        )
      })

      expect(result.current.toasts[0].details).toBeUndefined()
    })

    it('should handle updating toast without details', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Initial',
          'Initial details'
        )
      })

      act(() => {
        result.current.updateOperationToast(
          'generation',
          'task-1',
          'completed',
          'Done'
        )
      })

      expect(result.current.toasts[0].details).toBeUndefined()
    })

    it('should generate unique ids for same type and taskId added at different times', () => {
      const { result } = renderHook(() => useOperationToasts())

      let id1: string
      let id2: string

      act(() => {
        id1 = result.current.addOperationToast(
          'generation',
          'completed',
          'task-1',
          'M1'
        )
      })

      act(() => {
        jest.advanceTimersByTime(5000)
      })

      act(() => {
        id2 = result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'M2'
        )
      })

      expect(id1).not.toBe(id2)
    })

    it('should handle rapid sequential adds and updates', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'M1'
        )
        result.current.updateOperationToast(
          'generation',
          'task-1',
          'running',
          'M2'
        )
        result.current.updateOperationToast(
          'generation',
          'task-1',
          'completed',
          'M3'
        )
      })

      expect(result.current.toasts).toHaveLength(1)
      expect(result.current.toasts[0].message).toBe('M3')
      expect(result.current.toasts[0].status).toBe('completed')
    })

    it('should handle multiple toasts with same status', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'running',
          'task-1',
          'M1'
        )
        result.current.addOperationToast(
          'generation',
          'running',
          'task-2',
          'M2'
        )
        result.current.addOperationToast(
          'evaluation',
          'running',
          'task-3',
          'M3'
        )
      })

      expect(result.current.toasts).toHaveLength(3)
      expect(result.current.toasts.every((t) => t.status === 'running')).toBe(
        true
      )
    })
  })

  describe('API Integration/Cleanup', () => {
    it('should render null when no toasts exist', () => {
      const { result } = renderHook(() => useOperationToasts())

      const rendered = result.current.renderToasts()

      expect(rendered).toBeNull()
    })

    it('should render toast components when toasts exist', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Test message'
        )
      })

      const toastsJSX = result.current.renderToasts()

      expect(toastsJSX).not.toBeNull()

      render(toastsJSX)

      expect(mockOperationToast).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'generation',
          status: 'started',
          taskId: 'task-1',
          message: 'Test message',
        })
      )
    })

    it('should render toasts sorted by creation time (oldest first)', () => {
      const { result } = renderHook(() => useOperationToasts())

      const mockNow = Date.now()
      jest
        .spyOn(Date, 'now')
        .mockReturnValueOnce(mockNow)
        .mockReturnValueOnce(mockNow + 1000)
        .mockReturnValueOnce(mockNow + 2000)

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'M1'
        )
      })

      act(() => {
        result.current.addOperationToast(
          'evaluation',
          'started',
          'task-2',
          'M2'
        )
      })

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-3',
          'M3'
        )
      })

      const toastsJSX = result.current.renderToasts()
      render(toastsJSX)

      const calls = mockOperationToast.mock.calls
      expect(calls[0][0].taskId).toBe('task-1')
      expect(calls[1][0].taskId).toBe('task-2')
      expect(calls[2][0].taskId).toBe('task-3')
    })

    it('should provide onDismiss callback in rendered toast', () => {
      const { result } = renderHook(() => useOperationToasts())

      let toastId: string
      act(() => {
        toastId = result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'Test'
        )
      })

      const toastsJSX = result.current.renderToasts()
      render(toastsJSX)

      const dismissCallback = mockOperationToast.mock.calls[0][0].onDismiss

      expect(typeof dismissCallback).toBe('function')

      act(() => {
        dismissCallback()
      })

      expect(result.current.toasts).toHaveLength(0)
    })

    it('should startGeneration with singular model count', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.startGeneration('gen-task-1', 1)
      })

      expect(result.current.toasts).toHaveLength(1)
      expect(result.current.toasts[0].type).toBe('generation')
      expect(result.current.toasts[0].status).toBe('started')
      expect(result.current.toasts[0].taskId).toBe('gen-task-1')
      expect(result.current.toasts[0].message).toBe(
        'operations.generation.starting'
      )
      expect(result.current.toasts[0].details).toBe(
        'operations.generation.initializing'
      )
      expect(result.current.toasts[0].persistent).toBe(false)
    })

    it('should startGeneration with plural model count', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.startGeneration('gen-task-2', 3)
      })

      expect(result.current.toasts[0].message).toBe(
        'operations.generation.starting'
      )
    })

    it('should updateGeneration', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.startGeneration('gen-task-1', 2)
      })

      act(() => {
        result.current.updateGeneration(
          'gen-task-1',
          'running',
          'Processing...',
          'Model 1 of 2'
        )
      })

      expect(result.current.toasts[0].status).toBe('running')
      expect(result.current.toasts[0].message).toBe('Processing...')
      expect(result.current.toasts[0].details).toBe('Model 1 of 2')
    })

    it('should startEvaluation with singular count', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.startEvaluation('eval-task-1', 1)
      })

      expect(result.current.toasts).toHaveLength(1)
      expect(result.current.toasts[0].type).toBe('evaluation')
      expect(result.current.toasts[0].status).toBe('started')
      expect(result.current.toasts[0].taskId).toBe('eval-task-1')
      expect(result.current.toasts[0].message).toBe(
        'operations.evaluation.starting'
      )
      expect(result.current.toasts[0].details).toBe(
        'operations.evaluation.initializing'
      )
    })

    it('should startEvaluation with plural count', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.startEvaluation('eval-task-2', 5)
      })

      expect(result.current.toasts[0].message).toBe(
        'operations.evaluation.starting'
      )
    })

    it('should updateEvaluation', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.startEvaluation('eval-task-1', 3)
      })

      act(() => {
        result.current.updateEvaluation(
          'eval-task-1',
          'completed',
          'Evaluation complete',
          'All responses evaluated'
        )
      })

      expect(result.current.toasts[0].status).toBe('completed')
      expect(result.current.toasts[0].message).toBe('Evaluation complete')
      expect(result.current.toasts[0].details).toBe('All responses evaluated')
    })

    it('should clean up timers when toast is manually dismissed before auto-dismiss', () => {
      const { result } = renderHook(() => useOperationToasts())

      let toastId: string
      act(() => {
        toastId = result.current.addOperationToast(
          'generation',
          'completed',
          'task-1',
          'Done'
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      act(() => {
        result.current.dismissToast(toastId)
      })

      expect(result.current.toasts).toHaveLength(0)

      act(() => {
        jest.advanceTimersByTime(5000)
      })

      expect(result.current.toasts).toHaveLength(0)
    })

    it('should handle component unmount with pending timers', () => {
      const { result, unmount } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'completed',
          'task-1',
          'Done'
        )
        result.current.addOperationToast(
          'evaluation',
          'failed',
          'task-2',
          'Error'
        )
      })

      expect(result.current.toasts).toHaveLength(2)

      unmount()

      expect(() => {
        act(() => {
          jest.advanceTimersByTime(10000)
        })
      }).not.toThrow()
    })

    it('should return toast id from helper functions', () => {
      const { result } = renderHook(() => useOperationToasts())

      let genId: string
      let evalId: string

      act(() => {
        genId = result.current.startGeneration('gen-1', 2)
        evalId = result.current.startEvaluation('eval-1', 3)
      })

      expect(genId).toBeTruthy()
      expect(evalId).toBeTruthy()
      expect(genId).toMatch(/^generation-gen-1-\d+$/)
      expect(evalId).toMatch(/^evaluation-eval-1-\d+$/)
    })

    it('should maintain stable helper function references', () => {
      const { result, rerender } = renderHook(() => useOperationToasts())

      const firstStartGen = result.current.startGeneration
      const firstUpdateGen = result.current.updateGeneration
      const firstStartEval = result.current.startEvaluation
      const firstUpdateEval = result.current.updateEvaluation

      rerender()

      expect(result.current.startGeneration).toBe(firstStartGen)
      expect(result.current.updateGeneration).toBe(firstUpdateGen)
      expect(result.current.startEvaluation).toBe(firstStartEval)
      expect(result.current.updateEvaluation).toBe(firstUpdateEval)
    })

    it('should handle multiple renders without duplicating toasts', () => {
      const { result, rerender } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'generation',
          'started',
          'task-1',
          'M1'
        )
      })

      expect(result.current.toasts).toHaveLength(1)

      rerender()
      rerender()
      rerender()

      expect(result.current.toasts).toHaveLength(1)
    })

    it('should provide all toast properties to OperationToast component', () => {
      const { result } = renderHook(() => useOperationToasts())

      act(() => {
        result.current.addOperationToast(
          'evaluation',
          'running',
          'task-123',
          'Test message',
          'Test details'
        )
      })

      const toastsJSX = result.current.renderToasts()
      render(toastsJSX)

      expect(mockOperationToast).toHaveBeenCalledWith(
        expect.objectContaining({
          id: expect.stringMatching(/^evaluation-task-123-\d+$/),
          type: 'evaluation',
          status: 'running',
          taskId: 'task-123',
          message: 'Test message',
          details: 'Test details',
          onDismiss: expect.any(Function),
        })
      )
    })
  })
})

/**
 * Coverage for the EvaluationsClient methods left untested by
 * evaluations.test.ts (file at ~74.86% lines / 50.78% branches).
 *
 * Targets zero-coverage methods + uncovered branches:
 *  getResults, getSamples (default + explicit paging), getConfusionMatrix
 *  (encoding), getGenerationResult (includeHistory branch), getTaskEvaluation
 *  (includeHistory=false + generationId), runImmediateEvaluation (both body
 *  branches), pollImmediateEvaluation (complete / onUpdate / timeout),
 *  cancelEvaluationRun, cancelAllProjectEvaluations, getResultsByTaskModel
 *  (both branches), getProjectResultsByTaskModel (empty + all-set),
 *  getMetricDistribution (both), getEvaluationSamples (no-params /
 *  passed:false / all-set), getProjectEvaluationResults + getEvaluatedModels
 *  (URL assertions for both branches).
 *
 * Mirrors evaluations.test.ts: jest.mock('../base', ...) with a
 * MockBaseApiClient. Each test then uses
 * `jest.spyOn(client as any, 'request').mockResolvedValue(...)` and asserts the
 * URL via `mock.calls[0][0]` and options via `mock.calls[0][1]`.
 */

import { EvaluationsClient } from '../evaluations'

jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    protected async request<T>(_url: string, _options?: RequestInit): Promise<T> {
      return {} as T
    }
    clearCache() {}
    clearUserCache(_userId: string) {}
  },
}))

describe('EvaluationsClient - uncovered methods', () => {
  let client: EvaluationsClient
  let requestSpy: jest.SpyInstance

  beforeEach(() => {
    client = new EvaluationsClient()
    requestSpy = jest
      .spyOn(client as any, 'request')
      .mockResolvedValue({ ok: true })
  })

  afterEach(() => {
    jest.restoreAllMocks()
    jest.useRealTimers()
  })

  const url = () => requestSpy.mock.calls[0][0] as string
  const opts = () => requestSpy.mock.calls[0][1] as RequestInit | undefined

  describe('getResults', () => {
    it('GETs /evaluations/run/results/{id}', async () => {
      await client.getResults('eval-1')
      expect(url()).toBe('/evaluations/run/results/eval-1')
      // No explicit options -> defaults to GET in the base layer.
      expect(opts()).toBeUndefined()
    })
  })

  describe('getSamples', () => {
    it('uses default paging when params are omitted', async () => {
      await client.getSamples('eval-1')
      expect(url()).toBe('/evaluations/eval-1/samples?page=1&page_size=100')
    })

    it('uses explicit page + page_size', async () => {
      await client.getSamples('eval-1', { page: 3, page_size: 25 })
      expect(url()).toBe('/evaluations/eval-1/samples?page=3&page_size=25')
    })
  })

  describe('getConfusionMatrix', () => {
    it('URL-encodes the field name', async () => {
      await client.getConfusionMatrix('eval-1', 'field name/with')
      expect(url()).toBe(
        '/evaluations/eval-1/confusion-matrix?field_name=field%20name%2Fwith'
      )
    })
  })

  describe('getGenerationResult includeHistory branch', () => {
    it('appends include_history=true when requested', async () => {
      await client.getGenerationResult('t1', 'm1', undefined, true)
      const u = url()
      expect(u).toContain('/generation/generation-result?')
      expect(u).toContain('task_id=t1')
      expect(u).toContain('model_id=m1')
      expect(u).toContain('include_history=true')
      expect(opts()).toMatchObject({ method: 'GET' })
    })

    it('appends structure_key but not include_history when only structureKey given', async () => {
      await client.getGenerationResult('t1', 'm1', 'struct-A')
      const u = url()
      expect(u).toContain('structure_key=struct-A')
      expect(u).not.toContain('include_history')
    })
  })

  describe('getTaskEvaluation branches', () => {
    it('appends include_history=false and generation_id', async () => {
      await client.getTaskEvaluation('t1', 'm1', false, 'gen-9')
      const u = url()
      expect(u).toContain('/evaluations/sample-result?')
      expect(u).toContain('task_id=t1')
      expect(u).toContain('model_id=m1')
      expect(u).toContain('include_history=false')
      expect(u).toContain('generation_id=gen-9')
    })

    it('omits include_history when defaulting to true and no generationId', async () => {
      await client.getTaskEvaluation('t1', 'm1')
      const u = url()
      expect(u).not.toContain('include_history')
      expect(u).not.toContain('generation_id')
    })
  })

  describe('runImmediateEvaluation body branches', () => {
    it('POSTs an annotation_id body when annotationId is supplied', async () => {
      await client.runImmediateEvaluation('p1', 't1', 'ann-1')
      expect(url()).toBe('/evaluations/projects/p1/tasks/t1/immediate')
      expect(opts()).toMatchObject({
        method: 'POST',
        body: JSON.stringify({ annotation_id: 'ann-1' }),
      })
    })

    it('POSTs an empty object body when no annotationId', async () => {
      await client.runImmediateEvaluation('p1', 't1')
      expect(opts()).toMatchObject({ method: 'POST', body: '{}' })
    })
  })

  describe('pollImmediateEvaluation', () => {
    it('returns immediately when the first status is completed', async () => {
      const completed = {
        success: true,
        task_id: 't1',
        status: 'completed',
        results: [],
        message: 'done',
      }
      requestSpy.mockResolvedValueOnce(completed)

      const result = await client.pollImmediateEvaluation('p1', 't1', 'eval-1')

      expect(result).toBe(completed)
      expect(url()).toBe(
        '/evaluations/projects/p1/tasks/t1/immediate/eval-1/status'
      )
      // Polled exactly once — no setTimeout wait reached.
      expect(requestSpy).toHaveBeenCalledTimes(1)
    })

    it('returns immediately when the first status is failed', async () => {
      const failed = {
        success: false,
        task_id: 't1',
        status: 'failed',
        results: [],
        message: 'error',
      }
      requestSpy.mockResolvedValueOnce(failed)

      const result = await client.pollImmediateEvaluation('p1', 't1', 'eval-1')
      expect(result).toBe(failed)
    })

    it('invokes onUpdate for pending statuses before completion', async () => {
      jest.useFakeTimers()
      const pending = {
        success: false,
        task_id: 't1',
        status: 'pending',
        results: [],
        message: 'working',
        methods: [{ metric_name: 'bleu', display_name: 'BLEU', status: 'pending' }],
      }
      const completed = {
        success: true,
        task_id: 't1',
        status: 'completed',
        results: [],
        message: 'done',
      }
      requestSpy
        .mockResolvedValueOnce(pending)
        .mockResolvedValueOnce(completed)
      const onUpdate = jest.fn()

      const promise = client.pollImmediateEvaluation('p1', 't1', 'eval-1', {
        intervalMs: 1,
        onUpdate,
      })

      // Drain the pending-iteration's setTimeout(interval) wait.
      await jest.advanceTimersByTimeAsync(2)
      const result = await promise

      expect(onUpdate).toHaveBeenCalledTimes(1)
      expect(onUpdate).toHaveBeenCalledWith(pending)
      expect(result).toBe(completed)
      expect(requestSpy).toHaveBeenCalledTimes(2)
    })

    it('returns a soft-failure payload when it times out without polling', async () => {
      // timeoutMs: 0 makes the while-guard false on entry: request is never
      // called and the synthetic timeout payload is returned (last === null).
      const result = await client.pollImmediateEvaluation('p1', 't1', 'eval-1', {
        timeoutMs: 0,
      })

      expect(requestSpy).not.toHaveBeenCalled()
      expect(result).toMatchObject({
        success: false,
        task_id: 't1',
        status: 'failed',
        message: 'Evaluation is taking longer than expected',
        results: [],
        methods: null,
        expected_metrics: null,
        completed_metrics: null,
      })
      expect(result.error).toContain('did not finish within the expected time')
    })
  })

  describe('cancel endpoints', () => {
    it('cancelEvaluationRun POSTs the run cancel endpoint', async () => {
      await client.cancelEvaluationRun('eval-1')
      expect(url()).toBe('/evaluations/run/eval-1/cancel')
      expect(opts()).toMatchObject({ method: 'POST' })
    })

    it('cancelAllProjectEvaluations POSTs the project cancel-all endpoint', async () => {
      await client.cancelAllProjectEvaluations('p1')
      expect(url()).toBe('/evaluations/projects/p1/runs/cancel-all')
      expect(opts()).toMatchObject({ method: 'POST' })
    })
  })

  describe('lifecycle endpoints (issue #198)', () => {
    it('pauseEvaluationRun POSTs the run pause endpoint', async () => {
      await client.pauseEvaluationRun('eval-1')
      expect(url()).toBe('/evaluations/run/eval-1/pause')
      expect(opts()).toMatchObject({ method: 'POST' })
    })

    it('resumeEvaluationRun POSTs the run resume endpoint', async () => {
      await client.resumeEvaluationRun('eval-1')
      expect(url()).toBe('/evaluations/run/eval-1/resume')
      expect(opts()).toMatchObject({ method: 'POST' })
    })

    it('retryEvaluationRun POSTs the run retry endpoint', async () => {
      await client.retryEvaluationRun('eval-1')
      expect(url()).toBe('/evaluations/run/eval-1/retry')
      expect(opts()).toMatchObject({ method: 'POST' })
    })
  })

  describe('getResultsByTaskModel', () => {
    it('omits the query string by default', async () => {
      await client.getResultsByTaskModel('eval-1')
      expect(url()).toBe('/evaluations/eval-1/results/by-task-model')
    })

    it('adds include_history=true when requested', async () => {
      await client.getResultsByTaskModel('eval-1', true)
      expect(url()).toBe(
        '/evaluations/eval-1/results/by-task-model?include_history=true'
      )
    })
  })

  describe('getProjectResultsByTaskModel', () => {
    it('emits no query string when all optional params are omitted', async () => {
      await client.getProjectResultsByTaskModel('p1')
      expect(url()).toBe('/evaluations/projects/p1/results/by-task-model')
    })

    it('omits evaluation_ids for an empty array', async () => {
      await client.getProjectResultsByTaskModel('p1', [])
      expect(url()).toBe('/evaluations/projects/p1/results/by-task-model')
    })

    it('comma-joins evaluation_ids and appends include_history + metric', async () => {
      await client.getProjectResultsByTaskModel('p1', ['a', 'b'], true, 'bleu')
      const u = url()
      expect(u).toContain('/evaluations/projects/p1/results/by-task-model?')
      // join(',') then URLSearchParams encodes the comma as %2C
      expect(u).toContain('evaluation_ids=a%2Cb')
      expect(u).toContain('include_history=true')
      expect(u).toContain('metric=bleu')
    })

    it('omits metric when it is null', async () => {
      await client.getProjectResultsByTaskModel('p1', ['a'], false, null)
      const u = url()
      expect(u).toContain('evaluation_ids=a')
      expect(u).not.toContain('metric=')
      expect(u).not.toContain('include_history')
    })

    it('appends evaluation_config_id and omits evaluation_ids for the config-scoped fetch', async () => {
      // The results grid scopes by config id and lets the backend scan all runs
      // (no run-id pinning) — so evaluation_ids must be absent.
      await client.getProjectResultsByTaskModel('p1', undefined, false, 'bleu', 'cfg-xyz')
      const u = url()
      expect(u).toContain('metric=bleu')
      expect(u).toContain('evaluation_config_id=cfg-xyz')
      expect(u).not.toContain('evaluation_ids=')
    })

    it('omits evaluation_config_id when it is null', async () => {
      await client.getProjectResultsByTaskModel('p1', undefined, false, 'bleu', null)
      expect(url()).not.toContain('evaluation_config_id')
    })
  })

  describe('getMetricDistribution', () => {
    it('omits the field_name query when fieldName is absent', async () => {
      await client.getMetricDistribution('eval-1', 'bleu')
      expect(url()).toBe(
        '/evaluations/eval-1/metrics/bleu/distribution'
      )
    })

    it('appends field_name when provided', async () => {
      await client.getMetricDistribution('eval-1', 'bleu', 'answer')
      expect(url()).toBe(
        '/evaluations/eval-1/metrics/bleu/distribution?field_name=answer'
      )
    })
  })

  describe('getEvaluationSamples', () => {
    it('emits no query string when params are omitted', async () => {
      await client.getEvaluationSamples('eval-1')
      expect(url()).toBe('/evaluations/eval-1/samples')
    })

    it('appends passed=false (uses !== undefined, not truthiness)', async () => {
      await client.getEvaluationSamples('eval-1', { passed: false })
      expect(url()).toBe('/evaluations/eval-1/samples?passed=false')
    })

    it('appends all params when supplied', async () => {
      await client.getEvaluationSamples('eval-1', {
        fieldName: 'answer',
        passed: true,
        page: 2,
        pageSize: 50,
      })
      const u = url()
      expect(u).toContain('field_name=answer')
      expect(u).toContain('passed=true')
      expect(u).toContain('page=2')
      expect(u).toContain('page_size=50')
    })

    it('omits page when page is 0 (falsy)', async () => {
      await client.getEvaluationSamples('eval-1', { page: 0 })
      expect(url()).toBe('/evaluations/eval-1/samples')
    })
  })

  describe('getProjectEvaluationResults latestOnly branch', () => {
    it('omits the query string when latestOnly defaults to true', async () => {
      await client.getProjectEvaluationResults('p1')
      expect(url()).toBe('/evaluations/run/results/project/p1')
    })

    it('adds latest_only=false when latestOnly is false', async () => {
      await client.getProjectEvaluationResults('p1', false)
      expect(url()).toBe(
        '/evaluations/run/results/project/p1?latest_only=false'
      )
    })
  })

  describe('getEvaluatedModels includeConfigured branch', () => {
    it('omits the query string by default', async () => {
      await client.getEvaluatedModels('p1')
      expect(url()).toBe('/evaluations/projects/p1/evaluated-models')
    })

    it('adds include_configured=true when requested', async () => {
      await client.getEvaluatedModels('p1', true)
      expect(url()).toBe(
        '/evaluations/projects/p1/evaluated-models?include_configured=true'
      )
    })
  })
})

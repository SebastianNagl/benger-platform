/**
 * Tests for the projectsAPI cloud-import methods (org storage connections):
 * createCloudImportJobs, listCloudImports and the runCloudImportJobs driver
 * (create one job per key, poll all to terminal, aggregate failures).
 */

import apiClient from '@/lib/api'
import { projectsAPI } from '../projects'

// Mock the apiClient
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
    put: jest.fn(),
  },
}))

describe('projectsAPI — cloud imports', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('createCloudImportJobs POSTs the connection id + object keys', async () => {
    const response = {
      jobs: [
        { job_id: 'job-1', object_key: 'imports/a.json', status: 'pending' },
        { job_id: 'job-2', object_key: 'imports/b.csv', status: 'pending' },
      ],
    }
    ;(apiClient.post as jest.Mock).mockResolvedValue(response)

    const res = await projectsAPI.createCloudImportJobs('proj-1', {
      connection_id: 'conn-1',
      object_keys: ['imports/a.json', 'imports/b.csv'],
    })

    expect(apiClient.post).toHaveBeenCalledWith(
      '/projects/proj-1/cloud-imports',
      {
        connection_id: 'conn-1',
        object_keys: ['imports/a.json', 'imports/b.csv'],
      }
    )
    expect(res).toEqual(response)
  })

  it('listCloudImports GETs the history endpoint', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue([])

    await projectsAPI.listCloudImports('proj-1')

    expect(apiClient.get).toHaveBeenCalledWith('/projects/proj-1/cloud-imports')
  })

  it('runCloudImportJobs creates jobs then polls each to completion', async () => {
    ;(apiClient.post as jest.Mock).mockResolvedValue({
      jobs: [
        { job_id: 'job-1', object_key: 'imports/a.json', status: 'pending' },
        { job_id: 'job-2', object_key: 'imports/b.csv', status: 'pending' },
      ],
    })
    // job-1 completes after one running poll; job-2 completes immediately.
    const statusByJob: Record<string, any[]> = {
      'job-1': [
        { job_id: 'job-1', status: 'running', result: null },
        {
          job_id: 'job-1',
          status: 'completed',
          result: { created_tasks: 2 },
        },
      ],
      'job-2': [
        {
          job_id: 'job-2',
          status: 'completed',
          result: { created_tasks: 5 },
        },
      ],
    }
    const polls: Record<string, number> = { 'job-1': 0, 'job-2': 0 }
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) => {
      const jobId = url.split('/').pop() as string
      const seq = statusByJob[jobId]
      const status = seq[Math.min(polls[jobId]++, seq.length - 1)]
      return Promise.resolve(status)
    })

    const onStatus = jest.fn()
    const finals = await projectsAPI.runCloudImportJobs(
      'proj-1',
      { connection_id: 'conn-1', object_keys: ['imports/a.json', 'imports/b.csv'] },
      { onStatus },
      { pollIntervalMs: 1 }
    )

    expect(apiClient.get).toHaveBeenCalledWith('/projects/proj-1/imports/job-1')
    expect(apiClient.get).toHaveBeenCalledWith('/projects/proj-1/imports/job-2')
    expect(finals).toHaveLength(2)
    expect(finals.every((s) => s.status === 'completed')).toBe(true)
    // onStatus reports per object key.
    expect(onStatus).toHaveBeenCalledWith(
      'imports/a.json',
      expect.objectContaining({ job_id: 'job-1' })
    )
    expect(onStatus).toHaveBeenCalledWith(
      'imports/b.csv',
      expect.objectContaining({ job_id: 'job-2' })
    )
  })

  it('runCloudImportJobs throws an aggregate error listing every failed key', async () => {
    ;(apiClient.post as jest.Mock).mockResolvedValue({
      jobs: [
        { job_id: 'job-1', object_key: 'imports/a.json', status: 'pending' },
        { job_id: 'job-2', object_key: 'imports/b.csv', status: 'pending' },
      ],
    })
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) => {
      if (url.endsWith('job-1')) {
        return Promise.resolve({
          job_id: 'job-1',
          status: 'completed',
          result: null,
        })
      }
      return Promise.resolve({
        job_id: 'job-2',
        status: 'failed',
        error_message: 'bad payload',
        result: null,
      })
    })

    await expect(
      projectsAPI.runCloudImportJobs(
        'proj-1',
        { connection_id: 'conn-1', object_keys: ['imports/a.json', 'imports/b.csv'] },
        undefined,
        { pollIntervalMs: 1 }
      )
    ).rejects.toThrow('imports/b.csv: bad payload')
  })

  it('runCloudImportJobs falls back to a generic message when the worker left none', async () => {
    ;(apiClient.post as jest.Mock).mockResolvedValue({
      jobs: [
        { job_id: 'job-1', object_key: 'imports/a.json', status: 'pending' },
      ],
    })
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      job_id: 'job-1',
      status: 'failed',
      error_message: null,
      result: null,
    })

    await expect(
      projectsAPI.runCloudImportJobs(
        'proj-1',
        { connection_id: 'conn-1', object_keys: ['imports/a.json'] },
        undefined,
        { pollIntervalMs: 1 }
      )
    ).rejects.toThrow('imports/a.json: Import job failed')
  })

  it('runCloudImportJobs aborts polling via the signal', async () => {
    ;(apiClient.post as jest.Mock).mockResolvedValue({
      jobs: [
        { job_id: 'job-1', object_key: 'imports/a.json', status: 'pending' },
      ],
    })
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      job_id: 'job-1',
      status: 'running',
      result: null,
    })
    const controller = new AbortController()
    const promise = projectsAPI.runCloudImportJobs(
      'proj-1',
      { connection_id: 'conn-1', object_keys: ['imports/a.json'] },
      undefined,
      { pollIntervalMs: 1, signal: controller.signal }
    )
    controller.abort()

    await expect(promise).rejects.toThrow('Import polling aborted')
  })
})

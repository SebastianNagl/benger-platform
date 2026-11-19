import type { ImportJobStatus } from '@/lib/api/projects'
import { repeatedImport } from '@/lib/import/repeatedImport'

const base: ImportJobStatus = {
  job_id: 'job-2',
  project_id: 'p1',
  format: 'nested',
  status: 'completed',
  progress: 100,
  byte_size: 10,
  error_message: null,
  result: { created_tasks: 2 },
  created_at: null,
  updated_at: null,
  expires_at: null,
}

describe('repeatedImport', () => {
  it('is null for an import that wrote its payload', () => {
    expect(repeatedImport(base)).toBeNull()
    expect(repeatedImport({ ...base, duplicate_of_job_id: null })).toBeNull()
    expect(repeatedImport(null)).toBeNull()
    expect(repeatedImport(undefined)).toBeNull()
  })

  it('names the earlier job and when it completed', () => {
    expect(
      repeatedImport({
        ...base,
        duplicate_of_job_id: 'job-1',
        result: {
          no_op: true,
          duplicate_of: {
            job_id: 'job-1',
            completed_at: '2026-11-19T08:00:00+00:00',
            payload_sha256: 'a'.repeat(64),
          },
        },
      }),
    ).toEqual({ jobId: 'job-1', completedAt: '2026-11-19T08:00:00+00:00' })
  })

  it('has no date when the result carries none', () => {
    expect(
      repeatedImport({ ...base, duplicate_of_job_id: 'job-1', result: null }),
    ).toEqual({ jobId: 'job-1', completedAt: null })
  })
})

import type { ImportJobStatus } from '@/lib/api/projects'

/**
 * The earlier import a completed job repeated, or null. An import of a file
 * the same target already imported with the same options completes without
 * writing anything (the job's `duplicate_of_job_id` names the earlier job),
 * so a caller says so instead of reporting a successful import.
 */
export function repeatedImport(
  status: ImportJobStatus | null | undefined,
): { jobId: string; completedAt: string | null } | null {
  if (!status?.duplicate_of_job_id) return null
  return {
    jobId: status.duplicate_of_job_id,
    completedAt: status.result?.duplicate_of?.completed_at ?? null,
  }
}

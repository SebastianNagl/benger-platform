/**
 * Writes of a project's evaluation config list.
 */

import { apiClient } from './client'

/**
 * Replace the project's evaluation configs with `configs`.
 *
 * The API replaces the list as a whole, so a writer whose list is older
 * than the stored one would put back an old value of every
 * `metric_parameters` key another writer saved since (for example a grading
 * section that saves its policy keys on its own). `base` is the list as this
 * writer last read or saved it: per config, a key the writer did not change
 * against `base` keeps the stored value. `null` only when the writer has read
 * nothing yet (a fresh project), then the list is stored as sent.
 */
export async function putEvaluationConfigs<T = unknown>(
  projectId: string,
  configs: readonly unknown[],
  base: readonly unknown[] | null,
): Promise<T> {
  const body: Record<string, unknown> = { evaluation_configs: configs }
  if (base) body.evaluation_configs_base = base
  return apiClient.put(
    `/evaluations/projects/${projectId}/evaluation-config`,
    body,
  )
}

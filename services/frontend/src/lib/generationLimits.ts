import { useFeatureFlag } from '@/lib/featureFlags'
import { VARIANT_EXPERIMENTS } from '@/lib/featureFlags/platformFlags'

/**
 * Upper bound of runs per task for generation, mirroring
 * MAX_GENERATION_RUNS_PER_TASK in services/shared/generation_fidelity.py
 * (the API rejects more). Repeated runs of one task stay one task with many
 * runs, which variant designs need by the dozen.
 */
export const MAX_GENERATION_RUNS_PER_TASK = 100

/**
 * The cap before generation fidelity raised it; it stays the cap while the
 * variant_experiments flag is off (CLASSIC_MAX_GENERATION_RUNS_PER_TASK in
 * generation_fidelity.py).
 */
export const CLASSIC_MAX_GENERATION_RUNS_PER_TASK = 25

/** The runs-per-task cap for the current viewer. */
export function useMaxGenerationRunsPerTask(): number {
  return useFeatureFlag(VARIANT_EXPERIMENTS)
    ? MAX_GENERATION_RUNS_PER_TASK
    : CLASSIC_MAX_GENERATION_RUNS_PER_TASK
}

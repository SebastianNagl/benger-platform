/**
 * Upper bound of runs per task for generation, mirroring
 * MAX_GENERATION_RUNS_PER_TASK in services/shared/generation_fidelity.py
 * (the API rejects more). Repeated runs of one task stay one task with many
 * runs, which variant designs need by the dozen.
 */
export const MAX_GENERATION_RUNS_PER_TASK = 100

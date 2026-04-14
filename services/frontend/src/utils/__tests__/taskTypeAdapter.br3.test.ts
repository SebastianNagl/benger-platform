/**
 * @jest-environment jsdom
 *
 * Branch coverage: taskTypeAdapter.ts
 * Target: br3[1] L48 - labelStudioTaskToApi with falsy total_annotations
 */

import { labelStudioTaskToApi } from '../taskTypeAdapter'

describe('taskTypeAdapter branch coverage', () => {
  it('uses 0 for annotation_count when total_annotations is falsy', () => {
    const lsTask = {
      id: '1',
      data: { text: 'test' },
      is_labeled: false,
      total_annotations: 0,
      cancelled_annotations: 0,
      total_generations: 0,
      meta: {},
    } as any

    const result = labelStudioTaskToApi(lsTask)
    expect(result.annotation_count).toBe(0)
  })
})

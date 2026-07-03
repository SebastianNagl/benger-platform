/**
 * Targeted edge-case coverage for util branches not exercised elsewhere.
 */
import { findNextUnannotatedItem } from '../annotationStatus'
import { clearAllStores } from '../clearAllStores'
import { flattenJson } from '../jsonUtils'
import { localInputToIso } from '../projectWindow'
import { labelStudioTaskToApi } from '../taskTypeAdapter'

describe('util edge-case coverage', () => {
  describe('projectWindow.localInputToIso', () => {
    it('returns null for an empty input', () => {
      expect(localInputToIso('')).toBeNull()
    })

    it('returns null for an invalid date string', () => {
      expect(localInputToIso('not-a-date')).toBeNull()
    })

    it('returns an ISO string for a valid local input', () => {
      expect(localInputToIso('2024-01-01T12:00')).toContain('2024-01-01')
    })
  })

  describe('taskTypeAdapter.labelStudioTaskToApi', () => {
    it('defaults template_data to {} and annotation_count to 0 with no data', () => {
      const api = labelStudioTaskToApi({ id: 1 } as any)
      expect(api.template_data).toEqual({})
      expect(api.annotation_count).toBe(0)
    })
  })

  describe('jsonUtils.flattenJson', () => {
    it('flattens an array of objects and keeps null values', () => {
      const out = flattenJson({ arr: [{ a: 1 }], n: null })
      expect(out['arr[0].a']).toBe(1)
      expect(out['n']).toBeNull()
    })
  })

  describe('annotationStatus.findNextUnannotatedItem', () => {
    it('returns null when there are no items', () => {
      expect(findNextUnannotatedItem([], [])).toBeNull()
    })
  })

  describe('clearAllStores', () => {
    it('runs with preserveInitialized=true without throwing', () => {
      expect(() => clearAllStores(true)).not.toThrow()
    })
  })
})

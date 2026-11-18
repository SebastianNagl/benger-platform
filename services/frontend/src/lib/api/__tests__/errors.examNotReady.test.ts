/**
 * isExamNotReadyError: true only for the 403 `{code: "exam_not_ready"}` a
 * participant's task read gets while an exam is held closed.
 */

import { EXAM_NOT_READY, apiError } from '@/test-utils/examNotReady'
import { EXAM_NOT_READY_CODE, isExamNotReadyError } from '../errors'

describe('isExamNotReadyError', () => {
  it('recognises the 403 exam_not_ready answer', () => {
    expect(EXAM_NOT_READY_CODE).toBe('exam_not_ready')
    expect(isExamNotReadyError(EXAM_NOT_READY)).toBe(true)
    expect(isExamNotReadyError(apiError(403, { code: 'exam_not_ready' }))).toBe(
      true,
    )
  })

  it.each([
    ['another 403 code', apiError(403, { code: 'project_window_upcoming' })],
    ['a string 403 detail', apiError(403, 'Not enough permissions')],
    ['the code on a 404', apiError(404, { code: 'exam_not_ready' })],
    [
      'a 403 without a body',
      Object.assign(new Error('x'), { response: { status: 403, data: null } }),
    ],
    ['an error without response', new Error('network')],
    ['null', null],
    ['undefined', undefined],
    ['a string', 'exam_not_ready'],
  ])('is false for %s', (_label, error) => {
    expect(isExamNotReadyError(error)).toBe(false)
  })
})

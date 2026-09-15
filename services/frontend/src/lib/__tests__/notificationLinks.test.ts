/**
 * Deep links for the "new grading on your submission" notifications.
 */
import {
  EVALUATION_RECEIVED_TYPES,
  getEvaluationReceivedHref,
  isEvaluationReceivedType,
} from '@/lib/notificationLinks'

describe('isEvaluationReceivedType', () => {
  it.each(EVALUATION_RECEIVED_TYPES)('accepts %s', (type) => {
    expect(isEvaluationReceivedType(type)).toBe(true)
  })

  it.each(['evaluation_completed', 'korrektur_assigned', '', null, undefined])(
    'rejects %p',
    (type) => {
      expect(isEvaluationReceivedType(type)).toBe(false)
    },
  )
})

describe('getEvaluationReceivedHref', () => {
  it('opens an exam in the student shell for a student', () => {
    expect(
      getEvaluationReceivedHref(
        { project_id: 'p1', project_kind: 'exam' },
        'student',
      ),
    ).toBe('/student/exams/p1')
  })

  it('opens the task list for an expert, even on an exam', () => {
    expect(
      getEvaluationReceivedHref(
        { project_id: 'p1', project_kind: 'exam' },
        'expert',
      ),
    ).toBe('/projects/p1/my-tasks')
  })

  it.each([null, undefined, 'flashcard_collection'])(
    'opens the task list for a student when the project kind is %p',
    (kind) => {
      expect(
        getEvaluationReceivedHref(
          { project_id: 'p1', project_kind: kind },
          'student',
        ),
      ).toBe('/projects/p1/my-tasks')
    },
  )

  it.each([null, undefined, {}, { project_kind: 'exam' }])(
    'returns null without a project (%p)',
    (data) => {
      expect(getEvaluationReceivedHref(data, 'student')).toBeNull()
      expect(getEvaluationReceivedHref(data, 'expert')).toBeNull()
    },
  )
})

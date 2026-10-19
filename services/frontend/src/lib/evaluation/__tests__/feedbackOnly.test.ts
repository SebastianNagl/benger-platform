import { isFeedbackOnlyResult } from '../feedbackOnly'

describe('isFeedbackOnlyResult', () => {
  it('recognises a score-less judge row', () => {
    expect(
      isFeedbackOnlyResult({
        llm_judge_feedback: { value: null, details: { feedback_only: true } },
      }),
    ).toBe(true)
  })

  it('leaves scored and malformed rows alone', () => {
    expect(isFeedbackOnlyResult({ bleu: 0.4 })).toBe(false)
    expect(
      isFeedbackOnlyResult({ llm_judge_custom: { value: 0.8, details: {} } }),
    ).toBe(false)
    expect(isFeedbackOnlyResult({ x: { details: null } })).toBe(false)
    expect(isFeedbackOnlyResult(null)).toBe(false)
  })
})
